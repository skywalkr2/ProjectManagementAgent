"""Adapter for a command-line agent run as a program, signed in as the person (design 6.16, agent mode).

The agent runs locked down in a scratch folder of its own, outside the workspace: it gets the packet on its input or
as a file there, and answers on its output or in the folder's `outbox/`. It sees only PATH, HOME, the language
settings and the variables the account lists. The command, its locked-down flags, how the packet goes in and where
the answer comes out are all the account's settings; `lockdown_test()` checks that the flags hold.

Errors are read only from the program's exit code and error stream, never from its answer, using the patterns and
exit codes the account's settings give.
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
from pathlib import Path
from typing import Any

from engine.ai.task import AiError, AiResult, AiTask, ModelInfo
from engine.prompts import render

#: Variables every agent sees: where programs are, its home (where its own sign-in lives) and the language settings.
BASE_ENV = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "LANG", "LC_ALL", "LC_CTYPE")
ERROR_TAIL = 4000

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class LockdownCheck:
    """One lockdown probe: what was tried and whether the agent behaved as a locked-down agent must."""

    name: str  # outbox, outside, shell
    ok: bool
    detail: str


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
            done, seconds = self._start(prompt, model, scratch, outbox)
            if done.returncode != 0:
                raise self.classify_error(done.returncode, done.stderr, None)
            if self.agent.output_via == "outbox":
                path = outbox / answer_name
                if not path.is_file():
                    raise AiError("invalid_output", f"the agent finished without writing {answer_name}")
                return self._result(done.stdout, path.read_text(encoding="utf-8", errors="replace"), model, seconds)
            return self._result(done.stdout, None, model, seconds)

    def _start(self, prompt: str, model: str, scratch: Path, outbox: Path) -> tuple[subprocess.CompletedProcess, float]:
        packet = scratch / "packet.md"
        packet.write_text(prompt, encoding="utf-8")
        values = {"model": model, "packet": str(packet), "outbox": str(outbox), "scratch": str(scratch)}
        args = [_fill(part, values) for part in self.agent.command]
        if shutil.which(args[0], path=self._env().get("PATH")) is None and not Path(args[0]).is_file():
            raise AiError("provider_down", f"the agent program {args[0]} isn't installed on this computer")
        started = time.monotonic()
        try:
            done = self._runner(  # noqa: S603 - the account's own program, arguments as a list, no shell
                args,
                input=prompt if self.agent.packet_via == "stdin" else "",
                cwd=scratch,
                env=self._env(),
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

    def _env(self) -> dict[str, str]:
        env = {name: os.environ[name] for name in (*BASE_ENV, *self.agent.pass_env) if name in os.environ}
        if self.agent.key_env and self.secret:
            env[self.agent.key_env] = self.secret
        return env

    def _result(self, stdout: str, answer: str | None, model: str, seconds: float) -> AiResult:
        fields = self.agent.output_fields
        if not self.agent.output_json:
            return AiResult(
                text=(answer if answer is not None else stdout).strip(), model_served=model, seconds=seconds
            )
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
        """What a failed run means, from the program's exit code and error stream only."""
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
        detail = tail.strip() or f"the agent stopped with exit code {exit_code}"
        if kind == "auth":
            return AiError("auth", detail, hint=self.sign_in_hint() or None)
        return AiError(kind or "other", detail)

    def sign_in_hint(self) -> str:
        return self.agent.sign_in_hint

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
            return checks


class _scratch:
    """A fresh folder in the system's temporary space, removed afterwards."""

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix="cockpit-agent-"))
        return self.path

    def __exit__(self, *exc: object) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def _fill(part: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(model|packet|outbox|scratch)\}", lambda m: values[m.group(1)], part)


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
