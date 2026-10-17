"""Test launcher behavior with local locks and injected clocks, servers, and UI."""

import subprocess
import sys
import threading
from types import SimpleNamespace
from urllib.error import URLError

import pytest

import engine.launcher as launcher
from engine.launcher import InstanceLock, LocalServer, readiness_probe, restart_enabled, wait_ready

MENU = {"title": "App", "labels": {"open": "Open", "restart": "Restart", "quit": "Quit"}, "open_path": "/"}


class Clock:
    def __init__(self):
        self.value = 0
        self.pauses = []

    def now(self):
        return self.value

    def pause(self, duration):
        self.pauses.append(duration)
        self.value += duration


def test_readiness_immediate_and_retry():
    clock = Clock()
    replies = iter([False, False, True])
    calls = []

    def probe(url, timeout):
        calls.append((url, timeout))
        return next(replies)

    assert wait_ready("http://127.0.0.1:8123/healthz", probe=probe, clock=clock.now, pause=clock.pause)
    assert len(calls) == 3
    assert clock.pauses == [0.1, 0.1]


def test_readiness_timeout_has_bounded_probe_and_pause():
    clock = Clock()
    timeouts = []

    def probe(url, timeout):
        timeouts.append(timeout)
        return False

    assert not wait_ready(
        "http://127.0.0.1:8123/", timeout=0.25, interval=0.2, probe=probe, clock=clock.now, pause=clock.pause
    )
    assert clock.value == 0.25
    assert timeouts == [0.25, pytest.approx(0.05)]


@pytest.mark.parametrize("option", ["timeout", "interval", "request_timeout"])
def test_invalid_readiness_timing(option):
    with pytest.raises(ValueError):
        wait_ready("http://127.0.0.1:8123/", **{option: 0})


@pytest.mark.parametrize("option", ["cancelled", "alive"])
def test_cancelled_or_dead_server_does_not_probe(option):
    def unexpected(*args):
        raise AssertionError("Probe must not run")

    options = {option: lambda: option == "cancelled"}
    assert not wait_ready("http://127.0.0.1:8123/", probe=unexpected, **options)


def test_cancelled_after_successful_probe():
    values = iter([False, True])
    assert not wait_ready("http://127.0.0.1:8123/", probe=lambda *args: True, cancelled=lambda: next(values))


@pytest.mark.parametrize("url", ["https://127.0.0.1/", "http://192.0.2.1/", "http://localhost/", "http://x@127.0.0.1/"])
def test_probe_rejects_nonloopback_urls(url):
    with pytest.raises(ValueError):
        readiness_probe(url, 1)


@pytest.mark.parametrize("status,redirected,expected", [(200, False, True), (204, False, False), (200, True, False)])
def test_probe_response(monkeypatch, status, redirected, expected):
    url = "http://127.0.0.1:8123/healthz"

    class Response:
        def __enter__(self):
            self.status = status
            self.url = "http://192.0.2.1/" if redirected else url
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        launcher, "build_opener", lambda *args: SimpleNamespace(open=lambda *args, **kwargs: Response())
    )
    assert readiness_probe(url, 1) is expected


def test_probe_connection_error(monkeypatch):
    def fail(*args, **kwargs):
        raise URLError("Not ready")

    monkeypatch.setattr(launcher, "build_opener", lambda *args: SimpleNamespace(open=fail))
    assert not readiness_probe("http://127.0.0.1:8123/", 1)


def test_os_lock_exclusion_release_and_persistent_file(tmp_path):
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    try:
        assert first.acquire()
        assert not second.acquire()
        with pytest.raises(RuntimeError):
            first.acquire()
        first.release()
        first.release()
        assert first.path.exists()
        assert second.acquire()
    finally:
        first.release()
        second.release()


def test_lock_is_exclusive_between_processes(tmp_path):
    lock = InstanceLock(tmp_path)
    script = (
        "from engine.launcher import InstanceLock; import sys; "
        "lock=InstanceLock(sys.argv[1]); won=lock.acquire(); lock.release(); "
        "print('acquired' if won else 'busy')"
    )
    try:
        assert lock.acquire()
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)], check=True, capture_output=True, text=True
        )
        assert result.stdout.strip() == "busy"
    finally:
        lock.release()
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "acquired"


@pytest.mark.parametrize(
    "pending,busy,expected", [(False, False, False), (True, False, True), (False, True, False), (True, True, False)]
)
def test_menu_restart_state(pending, busy, expected):
    assert restart_enabled(lambda: pending, busy) is expected


def test_busy_does_not_call_waiting_callback():
    def unexpected():
        raise AssertionError("Busy state should short-circuit")

    assert not restart_enabled(unexpected, True)


class Server:
    instances = None

    def __init__(self, factory, port):
        self.calls = []
        self.error = None
        self.thread = None
        self.instances.append(self)

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")

    def alive(self):
        return True


class Item:
    def __init__(self, text, action, **kwargs):
        self.text, self.action, self.options = text, action, kwargs


class Icon:
    def __init__(self, name, image, title, menu):
        self.menu = menu
        self.stopped = False

    def run(self, setup=None):
        assert threading.current_thread() is threading.main_thread()
        self.menu[-1].action(self, self.menu[-1])

    def stop(self):
        self.stopped = True

    def update_menu(self):
        pass


@pytest.fixture
def environment(monkeypatch):
    servers, opened = [], []
    monkeypatch.setattr(Server, "instances", servers)
    monkeypatch.setattr(launcher, "LocalServer", Server)
    monkeypatch.setattr(launcher, "wait_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace(Icon=Icon, Menu=lambda *items: items, MenuItem=Item))
    return servers, opened


def test_launch_and_quit_cleanup(environment, tmp_path):
    servers, opened = environment
    launcher.launch(lambda: object(), 8123, tmp_path, icon_image=object(), **MENU)
    assert servers[0].calls == ["start", "stop"]
    assert opened == ["http://127.0.0.1:8123/"]
    lock = InstanceLock(tmp_path)
    try:
        assert lock.acquire()
    finally:
        lock.release()


def test_second_launch_only_opens_browser(environment, tmp_path):
    servers, opened = environment
    lock = InstanceLock(tmp_path)
    try:
        assert lock.acquire()
        lock.publish(8123, "/healthz")
        launcher.launch(lambda: object(), 9000, tmp_path, **MENU)
        assert not servers
        assert opened == ["http://127.0.0.1:8123/"]
    finally:
        lock.release()


def test_second_launch_not_ready(environment, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "wait_ready", lambda *args, **kwargs: False)
    lock = InstanceLock(tmp_path)
    try:
        assert lock.acquire()
        with pytest.raises(RuntimeError, match="existing instance"):
            launcher.launch(lambda: object(), 8123, tmp_path, **MENU)
    finally:
        lock.release()


def test_restart_rechecks_predicate_and_starts_only_after_stop(environment, tmp_path, monkeypatch):
    acknowledgments = []

    class RestartIcon(Icon):
        def run(self, setup=None):
            restart = self.menu[1]
            assert restart.options["enabled"](restart)
            restart.action(self, restart)
            self.menu[0].action(self, self.menu[0])
            self.menu[-1].action(self, self.menu[-1])

    monkeypatch.setitem(
        sys.modules, "pystray", SimpleNamespace(Icon=RestartIcon, Menu=lambda *items: items, MenuItem=Item)
    )
    launcher.launch(
        lambda: object(),
        8123,
        tmp_path,
        restart_waiting=lambda: True,
        restarted=lambda: acknowledgments.append(True),
        icon_image=object(),
        **MENU,
    )
    assert environment[0][0].calls == ["start", "stop", "start", "stop"]
    assert acknowledgments == [True]
    assert len(environment[1]) == 2


def test_restart_disabled_callback_cannot_force_restart(environment, tmp_path, monkeypatch):
    class DisabledIcon(Icon):
        def run(self, setup=None):
            assert not self.menu[1].options["enabled"](self.menu[1])
            self.menu[1].action(self, self.menu[1])

    monkeypatch.setitem(
        sys.modules, "pystray", SimpleNamespace(Icon=DisabledIcon, Menu=lambda *items: items, MenuItem=Item)
    )
    launcher.launch(lambda: object(), 8123, tmp_path, icon_image=object(), **MENU)
    assert environment[0][0].calls == ["start", "stop"]


def test_startup_failure_releases_lock(environment, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "wait_ready", lambda *args, **kwargs: False)
    with pytest.raises(RuntimeError, match="failed readiness"):
        launcher.launch(lambda: object(), 8123, tmp_path, icon_image=object(), **MENU)
    assert environment[0][0].calls == ["start", "stop"]
    lock = InstanceLock(tmp_path)
    try:
        assert lock.acquire()
    finally:
        lock.release()


def test_launch_requires_main_thread(environment, tmp_path):
    errors = []

    def work():
        try:
            launcher.launch(lambda: object(), 8123, tmp_path, **MENU)
        except RuntimeError as error:
            errors.append(str(error))

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert errors == ["The tray launcher must run on the main thread"]


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_invalid_port(port):
    with pytest.raises(ValueError):
        LocalServer(lambda: None, port)


def test_local_server_stop_sets_graceful_exit():
    joined = []
    server = LocalServer(lambda: None, 8123)
    server.server = SimpleNamespace(should_exit=False)
    inner = server.server
    server.thread = SimpleNamespace(join=joined.append, is_alive=lambda: False)
    server.stop()
    assert inner.should_exit
    assert joined == [12]
    assert server.thread is None


def test_local_server_refuses_restart_if_stop_hangs():
    server = LocalServer(lambda: None, 8123)
    server.server = SimpleNamespace(should_exit=False)
    server.thread = SimpleNamespace(join=lambda timeout: None, is_alive=lambda: True)
    with pytest.raises(RuntimeError, match="did not stop"):
        server.stop()


def test_lock_metadata_validation(tmp_path):
    lock = InstanceLock(tmp_path)
    assert lock.connection() is None
    with pytest.raises(RuntimeError):
        lock.publish(8123, "/healthz")
    try:
        assert lock.acquire()
        assert lock.connection() is None
        lock.publish(8123, "/healthz")
        assert lock.connection() == (8123, "/healthz")
    finally:
        lock.release()


def test_local_server_start_uses_one_factory_worker(monkeypatch):
    captured = {}

    class Socket:
        def setsockopt(self, *args):
            pass

        def bind(self, address):
            captured["address"] = address

        def listen(self, backlog):
            pass

        def close(self):
            captured["closed"] = True

    class Thread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

        def is_alive(self):
            return False

        def join(self, *args):
            pass

    def config(app_factory, **kwargs):
        captured.update(kwargs)
        captured["factory_callable"] = app_factory
        return object()

    def server(config):
        return SimpleNamespace(run=lambda **kwargs: captured.update(kwargs), should_exit=False)

    monkeypatch.setattr(launcher.socket, "socket", lambda *args: Socket())
    monkeypatch.setattr(launcher.threading, "Thread", Thread)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(Config=config, Server=server))

    def factory():
        return object()

    controller = LocalServer(factory, 8123)
    controller.start()
    assert captured["address"] == ("127.0.0.1", 8123)
    assert captured["workers"] == 1 and captured["reload"] is False and captured["factory"] is True
    assert captured["factory_callable"] is factory
    assert len(captured["sockets"]) == 1
    controller.stop()


def test_open_path_carries_base_path_and_token(environment, tmp_path):
    servers, opened = environment
    options = dict(MENU, open_path="/cockpit/?token=abc")
    launcher.launch(lambda: object(), 8123, tmp_path, icon_image=object(), **options)
    assert opened == ["http://127.0.0.1:8123/cockpit/?token=abc"]


def test_second_launch_opens_the_same_path_on_the_owners_port(environment, tmp_path):
    servers, opened = environment
    lock = InstanceLock(tmp_path)
    try:
        assert lock.acquire()
        lock.publish(8123, "/healthz")
        launcher.launch(lambda: object(), 9000, tmp_path, **dict(MENU, open_path="/cockpit/?token=abc"))
        assert opened == ["http://127.0.0.1:8123/cockpit/?token=abc"]
    finally:
        lock.release()


@pytest.mark.parametrize("change", [{"open_path": "cockpit/"}, {"labels": {"open": "Open"}}])
def test_launch_refuses_bad_menu_options(tmp_path, change):
    with pytest.raises(ValueError):
        launcher.launch(lambda: object(), 8123, tmp_path, **dict(MENU, **change))
