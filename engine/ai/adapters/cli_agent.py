"""Adapter for a command-line agent run as a program, signed in as the person (design 6.16, agent mode).

The agent runs locked down in a scratch folder of its own, outside the workspace: it gets the packet on its input or
as a file there, and answers on its output or in the folder's `outbox/`. It sees only PATH, HOME, the language
settings, the user name (where a system keychain keeps its sign-in), the temporary folder and the variables the account
lists. The command, its locked-down flags, how the packet goes in and where the answer comes out are all the account's
settings; `lockdown_test()` checks that the flags hold.

Errors are read only from the program's exit code and error stream, never from its answer, using the patterns and
exit codes the account's settings give. An agent that prints its errors on its output instead says so in its settings;
then, and only for a run that failed, that output is read as its error report.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.ai.task import AgentIdentity, AiError, AiResult, AiTask, IdentityUnknown, ModelInfo
from engine.prompts import render

#: Variables every agent sees: where programs are, its home and user name (where its own sign-in is kept, in a file
#: or the system's keychain), this user's temporary folder and the language settings.
BASE_ENV = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "USER",
    "LOGNAME",
    "USERNAME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
)
ERROR_TAIL = 4000
VERSION_CHARS = 200
IDENTITY_CHARS = 200

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class LockdownCheck:
    """One lockdown probe: what was tried and whether the agent behaved as a locked-down agent must."""

    name: str  # outbox, outside, shell
    ok: bool
    detail: str


#: Error wording common to command-line agents, read after an account's own patterns.
COMMON_ERRORS: dict[str, tuple[str, ...]] = {
    "quota": (
        r"exceeded (?:your|the) (?:\w+ )?quota",
        r"quota (?:exceeded|reached)",
        r"usage limit (?:reached|exceeded)",
        r"hit your (?:usage )?limit",
        r"out of (?:credits?|quota)",
    ),
    "rate_limited": (r"rate.?limit", r"too many requests", r"\b429\b", r"overloaded"),
}


class CliAgentAdapter:
    name = "cli-agent"

    def __init__(self, settings: Any, secret: str | None = None, *, runner: Runner = subprocess.run):
        agent = getattr(settings, "agent", None)
        if agent is None or not agent.command:
            raise AiError("other", "this account has no agent command set up")
        self.settings = settings
        self.agent = agent
        self.secret = secret
        self._runner = runner

    # ---- running ----------------------------------------------------------------------------------------------------

    def run(self, task: AiTask, model: str) -> AiResult:
        answer_name = "answer.json" if task.output == "json" else "answer.md"
        with _scratch() as scratch:
            outbox = scratch / "outbox"
            outbox.mkdir()
            prompt = "\n\n".join(p for p in (task.instructions, task.stable, task.request) if p)
            if self.agent.output_via == "outbox":
                prompt += "\n\n" + render("agent-answer", {"answer": str(outbox / answer_name)})
            done, seconds = self._start(prompt, model, scratch, outbox, task.effort)
            if done.returncode != 0:
                raise self.classify_error(done.returncode, self._error_report(done), None)
            if self.agent.output_via == "outbox":
                path = outbox / answer_name
                if not path.is_file():
                    raise AiError("no_output", f"the agent finished without writing {answer_name}")
                return self._result(done.stdout, path.read_text(encoding="utf-8", errors="replace"), model, seconds)
            return self._result(done.stdout, None, model, seconds)

    def _start(
        self, prompt: str, model: str, scratch: Path, outbox: Path, effort: str | None = None
    ) -> tuple[subprocess.CompletedProcess, float]:
        packet = scratch / "packet.md"
        packet.write_text(prompt, encoding="utf-8")
        home = self._fresh_home(scratch) if self.agent.home == "fresh" else None
        if self.agent.packet_via == "argument" and len(prompt) > MAX_ARGUMENT_CHARS:
            raise AiError("other", "the packet is too long to pass on the command line; this agent can't take it")
        values = {"model": model, "packet": str(packet), "outbox": str(outbox), "scratch": str(scratch)}
        values["prompt"] = prompt
        args = [_fill(part, values) for part in self.agent.command]
        if effort and self.agent.effort_option:
            args += [part.replace("{effort}", effort) for part in self.agent.effort_option]
        if shutil.which(args[0], path=self._env(home).get("PATH")) is None and not Path(args[0]).is_file():
            raise AiError("provider_down", f"the agent program {args[0]} isn't installed on this computer")
        started = time.monotonic()
        try:
            done = self._runner(  # noqa: S603 - the account's own program, arguments as a list, no shell
                args,
                input=prompt if self.agent.packet_via == "stdin" else "",
                cwd=scratch,
                env=self._env(home),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            raise AiError("timeout", f"the agent didn't finish in {self.settings.timeout_seconds} seconds") from None
        except OSError as err:
            raise AiError("provider_down", f"the agent program couldn't start: {err}") from None
        return done, time.monotonic() - started

    def _error_report(self, done: subprocess.CompletedProcess) -> str:
        """What a failed run says about its failure: its error stream, preceded, for an agent whose settings say it
        reports on its output, by that output (the text field when the output is JSON)."""
        stream = (done.stderr or "").strip()
        if not self.agent.errors.report_on_output:
            return stream
        out = (done.stdout or "").strip()
        if self.agent.output_json and self.agent.output_fields.text:
            try:
                said = _at(json.loads(out), self.agent.output_fields.text)
            except ValueError:
                said = None
            out = said.strip() if isinstance(said, str) else out
        return "\n".join(part for part in (out, stream) if part)

    def _env(self, home: Path | None = None) -> dict[str, str]:
        env = {name: os.environ[name] for name in (*BASE_ENV, *self.agent.pass_env) if name in os.environ}
        if self.agent.key_env and self.secret:
            env[self.agent.key_env] = self.secret
        if home is not None:
            env["HOME"] = env["USERPROFILE"] = str(home)
        return env

    def _fresh_home(self, scratch: Path) -> Path:
        """An empty home folder for one run, with only the sign-in files the account lists copied in."""
        home = scratch / "home"
        home.mkdir(exist_ok=True)
        real = Path(os.environ.get("HOME") or Path.home())
        for relative in self.agent.home_files:
            source = (real / relative).resolve()
            if not source.is_relative_to(real.resolve()) or not source.exists():
                continue
            target = home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
        return home

    def _result(self, stdout: str, answer: str | None, model: str, seconds: float) -> AiResult:
        """The run's result. A program that finished without error but left no answer (nothing on its output, or an
        empty answer file) is its own outcome, never an empty answer."""
        result = self._read_result(stdout, answer, model, seconds)
        if not result.text.strip():
            raise AiError("no_output", "the agent finished without an answer")
        return result

    def _read_result(self, stdout: str, answer: str | None, model: str, seconds: float) -> AiResult:
        fields = self.agent.output_fields
        if not self.agent.output_json:
            return AiResult(
                text=(answer if answer is not None else stdout).strip(), model_served=model, seconds=seconds
            )
        if answer is None and not stdout.strip():
            raise AiError("no_output", "the agent finished without an answer")
        try:
            data = json.loads(stdout)
        except ValueError:
            raise AiError("invalid_output", "the agent's output wasn't the JSON its settings describe") from None
        if answer is None:
            text = _at(data, fields.text) if fields.text else stdout
            if not isinstance(text, str):
                raise AiError("invalid_output", f"the agent's output has no text at {fields.text}")
        else:
            text = answer
        served = _at(data, fields.model) if fields.model else None
        return AiResult(
            text=text.strip(),
            model_served=served if isinstance(served, str) and served else model,
            seconds=seconds,
            input_tokens=_number(_at(data, fields.input_tokens), int) if fields.input_tokens else None,
            output_tokens=_number(_at(data, fields.output_tokens), int) if fields.output_tokens else None,
            cached_input_tokens=(
                _number(_at(data, fields.cached_input_tokens), int) if fields.cached_input_tokens else None
            ),
            cost_usd=_number(_at(data, fields.cost_usd), float) if fields.cost_usd else None,
        )

    # ---- errors -----------------------------------------------------------------------------------------------------

    def classify_error(self, exit_code: int | None, error_stream: str, transport_error: str | None) -> AiError:
        """What a failed run means, from the program's exit code and error stream only. A failure with nothing on the
        error stream, one the account's patterns call a banner, or one ended by a signal is `no_work`: the program
        ran but did nothing."""
        tail = (error_stream or "")[-ERROR_TAIL:]
        if transport_error:
            return AiError("provider_down", transport_error)
        errors = self.agent.errors
        kind = errors.exit_codes.get(exit_code) if exit_code is not None else None
        if kind is None:
            for name in ("auth", "quota", "rate_limited"):
                if any(re.search(p, tail, re.I) for p in getattr(errors, name)):
                    kind = name
                    break
        if kind is None:
            # After the account's own patterns, the wording most agents use for a spent plan or a request to slow
            # down, so an account set up without patterns still stops the work instead of retrying it as unknown.
            kind = next(
                (name for name, pats in COMMON_ERRORS.items() if any(re.search(p, tail, re.I) for p in pats)), None
            )
        if kind is None and (
            any(re.search(p, tail, re.I) for p in errors.no_work)
            or not tail.strip()
            or (exit_code is not None and exit_code < 0)
        ):
            # The program ran and failed with nothing to say on its error stream (or only the account's own banner
            # wording, or was ended by a signal): it did no work. That is no answer of the model's and no try.
            kind = "no_work"
        detail = tail.strip() or f"the agent stopped with exit code {exit_code} and said nothing"
        if kind == "auth":
            return AiError("auth", detail, hint=self.sign_in_hint() or None)
        wait = _reset_seconds(tail, errors.reset) if kind in ("quota", "rate_limited") else None
        return AiError(kind or "other", detail, retry_after=wait)

    def sign_in_hint(self) -> str:
        return self.agent.sign_in_hint

    def program_version(self) -> str | None:
        """The agent program's own version line, or None when it can't be read (not installed, no answer, an error or
        too slow). It runs with the same allowlisted environment as a run, and never reads the version from a run."""
        args = self.agent.version_command or [self.agent.command[0], "--version"]
        with _scratch() as scratch:
            try:
                done = self._runner(  # noqa: S603 - the account's own program, arguments as a list, no shell
                    args,
                    input="",
                    cwd=scratch,
                    env=self._env(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.agent.version_timeout_seconds,
                )
            except (subprocess.TimeoutExpired, OSError):
                return None
        if done.returncode != 0:
            return None
        for stream in (done.stdout, done.stderr):
            for line in (stream or "").splitlines():
                if line.strip():
                    return line.strip()[:VERSION_CHARS]
        return None

    def identity(self) -> AgentIdentity | IdentityUnknown:
        """The account the agent is signed in as, read from the program itself by the command the account names, and
        from the part of its output the account's settings point to (a JSON field, or a line, optionally a pattern
        within it). Unknown, with the reason in plain words, when no command is set, it fails, is too slow, says
        nothing or doesn't have what the settings point to: never a guess from anything else. It runs with the same
        allowlisted environment as a run."""
        agent = self.agent
        if not agent.identity_command:
            return IdentityUnknown("the account's settings don't say how to ask this program which sign-in it uses")
        shown = " ".join(agent.identity_command)
        with _scratch() as scratch:
            try:
                done = self._runner(  # noqa: S603 - the account's own program, arguments as a list, no shell
                    agent.identity_command,
                    input="",
                    cwd=scratch,
                    env=self._env(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=agent.identity_timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                return IdentityUnknown(
                    f"asking the program didn't finish in {agent.identity_timeout_seconds:g} seconds"
                )
            except OSError as err:
                return IdentityUnknown(f"the program couldn't be started to ask: {err}")
        if done.returncode != 0:
            said = (done.stderr or "").strip().splitlines()
            tail = f": {said[-1][:IDENTITY_CHARS]}" if said else ""
            return IdentityUnknown(f"asking the program stopped with exit code {done.returncode}{tail}")
        out = (done.stdout or "").strip()
        if not out:
            return IdentityUnknown("the program answered with nothing")
        if agent.identity_field:
            try:
                data = json.loads(out)
            except ValueError:
                return IdentityUnknown("the program's answer isn't the JSON the settings describe")
            found = _at(data, agent.identity_field)
            if not isinstance(found, str) or not found.strip():
                return IdentityUnknown(f"the program's answer has no account at {agent.identity_field}")
            account, where = found, f"field {agent.identity_field}"
        else:
            lines = [line for line in out.splitlines() if line.strip()]
            if agent.identity_line > len(lines):
                return IdentityUnknown(f"the program's answer has no line {agent.identity_line}")
            account, where = lines[agent.identity_line - 1], f"line {agent.identity_line}"
        if agent.identity_pattern:
            try:
                match = re.search(agent.identity_pattern, account)
            except re.error:
                return IdentityUnknown("the pattern in the account's settings isn't a valid pattern")
            if match is None or not match.groups() or not (match.group(1) or "").strip():
                return IdentityUnknown("the program's answer doesn't match the pattern in the account's settings")
            account, where = match.group(1), f"{where}, by pattern"
        account = account.strip()[:IDENTITY_CHARS]
        return AgentIdentity(account, f"asked the program with {shown} ({where})")

    def catalog(self) -> dict[str, ModelInfo]:
        """An agent publishes no catalog; its models and prices come from the account's settings."""
        return {}

    # ---- lockdown ---------------------------------------------------------------------------------------------------

    def lockdown_test(self, model: str) -> list[LockdownCheck]:
        """Ask the agent to write in its outbox, write outside its folder and start a shell. Locked down means only
        the first happens (or none, for an agent that answers on its output)."""
        with _scratch() as scratch, _scratch() as elsewhere:
            outbox = scratch / "outbox"
            outbox.mkdir()
            inside, outside, shell = outbox / "lockdown.txt", elsewhere / "outside.txt", elsewhere / "shell.txt"
            prompt = render("agent-lockdown", {"inside": str(inside), "outside": str(outside), "shell": str(shell)})
            try:
                self._start(prompt, model, scratch, outbox)
            except AiError as err:
                return [LockdownCheck("outbox", False, f"the agent couldn't run: {err}")]
            checks = []
            if self.agent.output_via == "outbox":
                wrote = inside.is_file()
                checks.append(
                    LockdownCheck("outbox", wrote, "wrote to its outbox" if wrote else "couldn't write to its outbox")
                )
            escaped = outside.exists()
            checks.append(
                LockdownCheck(
                    "outside", not escaped, "wrote outside its folder" if escaped else "writing elsewhere was refused"
                )
            )
            ran = shell.exists()
            checks.append(LockdownCheck("shell", not ran, "started a shell" if ran else "starting a shell was refused"))
            if self.agent.home == "fresh":
                checks.append(self._memory_check(model))
            return checks

    def _memory_check(self, model: str) -> LockdownCheck:
        """With a fresh home: a file the agent writes in its home must not be in this user's home afterwards."""
        real = Path(os.environ.get("HOME") or Path.home())
        probe = ".cockpit-memory-probe"
        existed = (real / probe).exists()
        with _scratch() as scratch:
            outbox = scratch / "outbox"
            outbox.mkdir()
            try:
                self._start(render("agent-memory", {"name": probe}), model, scratch, outbox)
            except AiError as err:
                return LockdownCheck("memory", False, f"the agent couldn't run: {err}")
        leaked = not existed and (real / probe).exists()
        if leaked:
            (real / probe).unlink(missing_ok=True)
        detail = "it wrote to this user's home folder" if leaked else "nothing it keeps reaches the next run"
        return LockdownCheck("memory", not leaked, detail)


class _scratch:
    """A fresh folder in the system's temporary space, removed afterwards."""

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix="cockpit-agent-"))
        return self.path

    def __exit__(self, *exc: object) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


#: The longest packet passed as one command-line argument, well inside every system's limit.
MAX_ARGUMENT_CHARS = 100_000


def _fill(part: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(model|packet|outbox|scratch|prompt)\}", lambda m: values[m.group(1)], part)


def _reset_seconds(text: str, patterns: list[str]) -> float | None:
    """Seconds until a limit resets, from the first pattern that matches the error stream: its first group is a number
    of seconds or an ISO 8601 date and time. None when nothing matches or the group can't be read."""
    for pattern in patterns:
        found = re.search(pattern, text, re.I)
        if not found or not found.groups():
            continue
        said = (found.group(1) or "").strip()
        try:
            return max(0.0, float(said))
        except ValueError:
            pass
        try:
            when = datetime.fromisoformat(said.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, (when - datetime.now(UTC)).total_seconds())
    return None


def _at(data: Any, path: str) -> Any:
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and key.lstrip("-").isdigit():
            index = int(key)
            data = data[index] if -len(data) <= index < len(data) else None
        else:
            return None
    return data


def _number(value: Any, kind: type) -> Any:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return kind(value)
