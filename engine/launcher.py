"""Run a local ASGI app behind a native tray icon with a per-folder process lock."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class InstanceLock:
    """Hold an OS lock on a persistent file; process exit releases ownership.

    The file is deliberately never unlinked, avoiding lock-inode races. Instances
    sharing a data folder reuse the owner's published port and readiness path.
    """

    def __init__(self, data_folder: str | Path):
        self.path = Path(data_folder) / "launcher.lock"
        self.file = None

    def acquire(self) -> bool:
        if self.file is not None:
            raise RuntimeError("Lock acquisition already attempted successfully")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        except OSError as error:
            handle.close()
            if sys.platform == "win32" and error.errno in {13, 11, 36}:
                return False
            raise
        handle.seek(1)
        handle.truncate()
        handle.flush()
        self.file = handle
        return True

    def publish(self, port: int, readiness_path: str) -> None:
        if self.file is None:
            raise RuntimeError("Only the lock owner can publish connection details")
        self.file.seek(1)
        self.file.truncate()
        self.file.write(json.dumps({"port": port, "readiness_path": readiness_path}).encode("utf-8"))
        self.file.flush()

    def connection(self) -> tuple[int, str] | None:
        try:
            with self.path.open("rb") as handle:
                handle.seek(1)
                data = json.load(handle)
            port, path = data["port"], data["readiness_path"]
            if (
                type(port) is int
                and 1 <= port <= 65535
                and isinstance(path, str)
                and path.startswith("/")
                and not any(char in path for char in "?#\r\n")
            ):
                return port, path
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def release(self) -> None:
        handle, self.file = self.file, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def readiness_probe(url: str, timeout: float) -> bool:
    """Check an HTTP readiness endpoint without using system proxy settings."""
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise ValueError("Readiness must be an HTTP loopback URL")

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(url, timeout=timeout) as response:
            return response.status == 200 and response.url == url
    except (OSError, URLError):
        return False


def wait_ready(
    url: str,
    *,
    timeout: float = 15,
    interval: float = 0.1,
    request_timeout: float = 0.5,
    probe: Callable[[str, float], bool] = readiness_probe,
    clock: Callable[[], float] = time.monotonic,
    pause: Callable[[float], None] = time.sleep,
    cancelled: Callable[[], bool] = lambda: False,
    alive: Callable[[], bool] = lambda: True,
) -> bool:
    """Wait within a deadline; injectable I/O and clock make tests deterministic."""
    if timeout <= 0 or interval <= 0 or request_timeout <= 0:
        raise ValueError("Readiness timing values must be positive")
    deadline = clock() + timeout
    while not cancelled() and alive():
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        if probe(url, min(request_timeout, remaining)):
            return not cancelled() and alive()
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        pause(min(interval, remaining))
    return False


def restart_enabled(restart_waiting: Callable[[], bool], busy: bool = False) -> bool:
    """Enable Restart only for a pending restart while no operation is running."""
    return not busy and bool(restart_waiting())


class LocalServer:
    """Own one server thread and a prebound socket, detecting bind failures first."""

    def __init__(self, app_factory: Callable[[], Any], port: int, *, shutdown_timeout: float = 10):
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self.app_factory = app_factory
        self.port = port
        self.shutdown_timeout = shutdown_timeout
        self.thread = None
        self.server = None
        self.socket = None
        self.error = None

    def start(self) -> None:
        import uvicorn

        if self.thread is not None and self.thread.is_alive():
            raise RuntimeError("Server is already running")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            elif sys.platform != "win32":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", self.port))
            listener.listen(128)
            config = uvicorn.Config(
                self.app_factory,
                factory=True,
                host="127.0.0.1",
                port=self.port,
                reload=False,
                workers=1,
                lifespan="on",
                timeout_graceful_shutdown=self.shutdown_timeout,
            )
            self.server = uvicorn.Server(config)
            self.socket = listener
            self.error = None

            def serve() -> None:
                try:
                    self.server.run(sockets=[listener])
                except BaseException as error:
                    self.error = error
                finally:
                    listener.close()

            self.thread = threading.Thread(target=serve, name="local-web-server", daemon=False)
            self.thread.start()
        except BaseException:
            listener.close()
            raise

    def alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def stop(self) -> None:
        if self.server is None or self.thread is None:
            return
        self.server.should_exit = True
        self.thread.join(self.shutdown_timeout + 2)
        if self.thread.is_alive():
            raise RuntimeError("Server did not stop; refusing to start a duplicate")
        if self.socket is not None:
            self.socket.close()
        self.thread = self.server = self.socket = None


def launch(
    app_factory: Callable[[], Any],
    port: int,
    data_folder: str | Path,
    *,
    title: str,
    labels: Mapping[str, str],
    open_path: str,
    readiness_path: str = "/healthz",
    restart_waiting: Callable[[], bool] = lambda: False,
    restarted: Callable[[], None] = lambda: None,
    icon_image: Any = None,
    startup_timeout: float = 15,
) -> None:
    """Run the tray loop on the main thread; a second launch only opens the app.

    title names the icon; labels holds the menu wording for "open", "restart" and "quit", supplied from the wording
    sheet. open_path is the path (with the base path and any query) the browser opens, on this instance's port or on
    the running instance's port for a second launch.

    Restart recreates the ASGI app in this process; it does not replace Python
    modules, install updates, or restart the interpreter. The waiting callback
    must be thread-safe. restarted acknowledges a successful server restart.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("The tray launcher must run on the main thread")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not readiness_path.startswith("/") or any(char in readiness_path for char in "?#\r\n"):
        raise ValueError("readiness_path must be a local absolute path without query or fragment")
    if not open_path.startswith("/") or any(char in open_path for char in "\r\n"):
        raise ValueError("open_path must be a local absolute path")
    missing = {"open", "restart", "quit"} - set(labels)
    if missing:
        raise ValueError(f"labels is missing {sorted(missing)}")
    url = f"http://127.0.0.1:{port}{open_path}"
    health = f"http://127.0.0.1:{port}{readiness_path}"
    lock = InstanceLock(data_folder)
    if not lock.acquire():

        def existing_ready(candidate_url: str, timeout: float) -> bool:
            connection = lock.connection()
            if connection is None:
                return False
            owner_port, owner_path = connection
            return readiness_probe(f"http://127.0.0.1:{owner_port}{owner_path}", timeout)

        if not wait_ready(health, timeout=startup_timeout, probe=existing_ready):
            raise RuntimeError("The existing instance is not ready; check its status before trying again")
        connection = lock.connection()
        if connection is None:
            raise RuntimeError("The existing instance closed before opening its browser")
        webbrowser.open(f"http://127.0.0.1:{connection[0]}{open_path}")
        return
    controller = LocalServer(app_factory, port)
    try:
        import pystray

        if icon_image is None:
            from PIL import Image, ImageDraw

            icon_image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(icon_image)
            draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill="#742b32")
            draw.rectangle((20, 20, 44, 26), fill="#fff1d6")
            draw.rectangle((29, 26, 35, 46), fill="#fff1d6")
        controller.start()
        lock.publish(port, readiness_path)
        if not wait_ready(health, timeout=startup_timeout, alive=controller.alive):
            raise RuntimeError("The local server failed readiness") from controller.error
        busy = threading.Lock()
        failures = []
        closed = threading.Event()

        def open_app(icon, item) -> None:
            webbrowser.open(url)

        def restart(icon, item) -> None:
            if not busy.acquire(blocking=False):
                return
            try:
                if not restart_waiting():
                    return
                controller.stop()
                controller.start()
                if not wait_ready(health, timeout=startup_timeout, alive=controller.alive):
                    raise RuntimeError("Restarted server failed readiness") from controller.error
                restarted()
            except Exception as error:
                failures.append(error)
                closed.set()
                icon.stop()
            finally:
                busy.release()
                icon.update_menu()

        def quit_app(icon, item) -> None:
            closed.set()
            icon.stop()

        icon = pystray.Icon(
            title,
            icon_image,
            title,
            menu=pystray.Menu(
                pystray.MenuItem(labels["open"], open_app, default=True),
                pystray.MenuItem(
                    labels["restart"], restart, enabled=lambda item: restart_enabled(restart_waiting, busy.locked())
                ),
                pystray.MenuItem(labels["quit"], quit_app),
            ),
        )
        webbrowser.open(url)

        def refresh_menu(icon) -> None:
            icon.visible = True
            while not closed.wait(0.5):
                icon.update_menu()

        try:
            icon.run(setup=refresh_menu)
        finally:
            closed.set()
        if failures:
            raise RuntimeError("The server could not restart") from failures[0]
    finally:
        # Keep ownership until shutdown finishes; a hung server must not overlap a new one.
        try:
            controller.stop()
        except Exception:

            def release_after_exit() -> None:
                if controller.thread is not None:
                    controller.thread.join()
                lock.release()

            threading.Thread(target=release_after_exit, name="server-lock-cleanup", daemon=True).start()
            raise
        else:
            lock.release()
