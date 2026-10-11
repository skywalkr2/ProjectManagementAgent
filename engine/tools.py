"""Outside programs a plugin declares in `requires.tools` (design 3.2, 3.5), run without a shell in a fresh folder.

Where a program is found is set per computer in `.cockpit/tools.yaml`, which is never synced:

    epubcheck: {command: [java, -jar, /opt/epubcheck/epubcheck.jar], env: {JAVA_HOME: /opt/java}}
    typst: /usr/local/bin/typst

A tool missing from that file is looked up on the PATH by its name. Each declared tool is probed once per process: its
probe command runs, and the first version number in its output is compared with the declared minimum.

A run writes the given files into a temporary folder, runs the program there with a timeout and a minimal environment,
and returns its exit code, output and the files it wrote that match the call's `collect` patterns, within size caps. The
folder is deleted afterwards. Everything a program returns is untrusted material.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from packaging.version import InvalidVersion, Version

#: Environment variables passed through to programs; everything else is left out.
_PASSED_ENV = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")


class ToolError(Exception):
    """A run that can't start: an undeclared or missing tool, or a bad file name or pattern."""


@dataclass(frozen=True)
class ToolStatus:
    name: str
    found: bool
    version: str | None = None
    reason: str = ""


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    output_cut: bool = False  # stdout or stderr was longer than the cap and was cut there
    files: dict[str, bytes] = field(default_factory=dict)  # collected files, by path inside the folder
    omitted: list[dict[str, Any]] = field(default_factory=list)  # matched but not returned: {name, size, reason}
    seconds: float = 0.0


@dataclass(frozen=True)
class ToolLimits:
    timeout_seconds: float = 120
    max_timeout_seconds: float = 1800
    probe_timeout_seconds: float = 10
    output_kb: int = 512
    collect_file_mb: float = 25
    collect_total_mb: float = 100


def read_locations(path: Path) -> dict[str, dict[str, Any]]:
    """The per-computer tool locations: name -> {command: [...], env: {...}}. A missing file means none."""
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ToolError(f"{path.name} must map tool names to a path or a command")
    found = {}
    for name, value in raw.items():
        if isinstance(value, str):
            value = {"command": [value]}
        elif isinstance(value, list):
            value = {"command": value}
        if not isinstance(value, dict) or not value.get("command"):
            raise ToolError(f"{path.name}: {name} needs a path or a command")
        command = value["command"]
        command = [command] if isinstance(command, str) else command
        env = value.get("env") or {}
        if not all(isinstance(c, str) for c in command) or not isinstance(env, dict):
            raise ToolError(f"{path.name}: {name} has a command or env that isn't text")
        found[str(name)] = {"command": list(command), "env": {str(k): str(v) for k, v in env.items()}}
    return found


def _version_in(text: str) -> str | None:
    match = re.search(r"\d+(?:\.\d+)+|\d+", text)
    return match.group(0) if match else None


class Tools:
    """Runs declared programs for the host. Plugins get a `ToolBox` limited to the tools their manifest declares."""

    def __init__(
        self,
        locations: Mapping[str, Mapping[str, Any]],
        limits: ToolLimits,
        *,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.locations = {name: dict(value) for name, value in locations.items()}
        self.limits = limits
        self._which = which
        self._probed: dict[tuple[str, str, str], ToolStatus] = {}

    def command(self, name: str) -> list[str] | None:
        """The command that starts a tool on this computer, or None when it isn't found."""
        entry = self.locations.get(name)
        command = list(entry["command"]) if entry else [name]
        first = command[0]
        resolved = first if os.path.isabs(first) and os.path.exists(first) else self._which(first)
        return [resolved, *command[1:]] if resolved else None

    def probe(self, name: str, probe: str, min_version: str) -> ToolStatus:
        """Whether a tool is here and new enough. The probe's first word is the tool's name; the rest are its
        arguments. Probed once per process."""
        key = (name, probe, min_version)
        if key in self._probed:
            return self._probed[key]
        status = self._probe(name, probe, min_version)
        self._probed[key] = status
        return status

    def _probe(self, name: str, probe: str, min_version: str) -> ToolStatus:
        command = self.command(name)
        if command is None:
            return ToolStatus(name, False, reason=f"{name} isn't installed on this computer")
        words = shlex.split(probe)
        try:
            done = subprocess.run(  # noqa: S603 - a declared program, arguments as a list, no shell
                [*command, *words[1:]],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.limits.probe_timeout_seconds,
                env=self._env(name),
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as err:
            return ToolStatus(name, False, reason=f"{name} didn't answer its version check ({type(err).__name__})")
        version = _version_in(done.stdout + "\n" + done.stderr)
        if min_version:
            try:
                if version is None or Version(version) < Version(min_version):
                    shown = version or "unknown"
                    return ToolStatus(name, False, version, f"{name} {shown} is older than {min_version}")
            except InvalidVersion:
                return ToolStatus(name, False, version, f"{name} reported a version that can't be compared")
        return ToolStatus(name, True, version)

    def _env(self, name: str, work: str | None = None) -> dict[str, str]:
        env = {k: os.environ[k] for k in _PASSED_ENV if k in os.environ}
        if work is not None:
            env.update(HOME=work, TMPDIR=work, TEMP=work, TMP=work)
        env.update(self.locations.get(name, {}).get("env", {}))
        return env

    def run(
        self,
        name: str,
        args: Sequence[str],
        files: Mapping[str, bytes] | None = None,
        *,
        timeout: float | None = None,
        collect: Sequence[str] = (),
        max_file_mb: float | None = None,
        max_total_mb: float | None = None,
    ) -> ToolResult:
        command = self.command(name)
        if command is None:
            raise ToolError(f"{name} isn't installed on this computer")
        if not all(isinstance(a, str) for a in args):
            raise ToolError("arguments are text")
        limit = min(timeout or self.limits.timeout_seconds, self.limits.max_timeout_seconds)
        per_file = min(max_file_mb or self.limits.collect_file_mb, self.limits.collect_file_mb)
        total = min(max_total_mb or self.limits.collect_total_mb, self.limits.collect_total_mb)
        patterns = [_safe_relative(p, "pattern") for p in collect]
        with tempfile.TemporaryDirectory(prefix="cockpit-tool-") as work:
            root = Path(work).resolve()
            for rel, data in (files or {}).items():
                target = root / _safe_relative(rel, "file name")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            started = time.monotonic()
            result = self._spawn([*command, *args], root, self._env(name, str(root)), limit)
            result.seconds = round(time.monotonic() - started, 3)
            result.files, result.omitted = _collect(root, patterns, per_file, total)
        return result

    def _spawn(self, argv: list[str], cwd: Path, env: dict[str, str], timeout: float) -> ToolResult:
        posix = os.name == "posix"
        process = subprocess.Popen(  # noqa: S603 - a declared program, arguments as a list, no shell
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=posix,
        )
        timed_out = False
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if posix:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            out, err = process.communicate()
        cap = self.limits.output_kb * 1024
        cut = len(out) > cap or len(err) > cap
        return ToolResult(
            returncode=process.returncode if not timed_out else -1,
            stdout=out[:cap].decode("utf-8", errors="replace"),
            stderr=err[:cap].decode("utf-8", errors="replace"),
            timed_out=timed_out,
            output_cut=cut,
        )


def _safe_relative(value: str, what: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", value):
        raise ToolError(f"{what} {value!r} must stay inside the working folder")
    return str(path)


def _collect(
    root: Path, patterns: list[str], per_file_mb: float, total_mb: float
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    files: dict[str, bytes] = {}
    omitted: list[dict[str, Any]] = []
    used = 0
    seen: set[str] = set()
    for pattern in patterns:
        for match in sorted(root.glob(pattern)):
            rel = match.relative_to(root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            if match.is_symlink() or not match.is_file() or not match.resolve().is_relative_to(root):
                omitted.append({"name": rel, "size": None, "reason": "not a regular file in the working folder"})
                continue
            size = match.stat().st_size
            if size > per_file_mb * 1024 * 1024:
                omitted.append({"name": rel, "size": size, "reason": f"larger than {per_file_mb:g} MB"})
                continue
            if used + size > total_mb * 1024 * 1024:
                omitted.append({"name": rel, "size": size, "reason": f"over the {total_mb:g} MB total"})
                continue
            used += size
            files[rel] = match.read_bytes()
    return files, omitted


class ToolBox:
    """What a plugin sees: only the tools its manifest declares, each probed before it runs. Every run is recorded."""

    def __init__(self, tools: Tools, plugin: str, declared: Mapping[str, Any], record: Callable[..., None]):
        self.__tools, self.__plugin, self.__declared, self.__record = tools, plugin, dict(declared), record

    def available(self, name: str) -> bool:
        tool = self.__declared.get(name)
        return tool is not None and self.__tools.probe(name, tool.probe, tool.min_version).found

    def run(
        self,
        name: str,
        args: Sequence[str],
        files: Mapping[str, bytes] | None = None,
        *,
        timeout: float | None = None,
        collect: Sequence[str] = (),
        max_file_mb: float | None = None,
        max_total_mb: float | None = None,
    ) -> ToolResult:
        """Run a declared tool. `files` are written to a fresh working folder first, by relative path; `collect`
        patterns return files the program wrote there. Caps and the timeout may be lowered, never raised."""
        tool = self.__declared.get(name)
        if tool is None:
            raise ToolError(f"{name} isn't declared in requires.tools")
        status = self.__tools.probe(name, tool.probe, tool.min_version)
        if not status.found:
            raise ToolError(status.reason)
        result = self.__tools.run(
            name,
            list(args),
            files,
            timeout=timeout,
            collect=collect,
            max_file_mb=max_file_mb,
            max_total_mb=max_total_mb,
        )
        self.__record(self.__plugin, name, list(args), sorted(files or {}), result)
        return result
