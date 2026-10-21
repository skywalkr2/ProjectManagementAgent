"""The last failures, kept in detail so a person can send them with their feedback (design 7, Help).

A failure is a failed call to an AI account, a failed account check, a failed read of a source, or an unexpected error
in the app or its worker. The first three are already recorded where they happen (the runs, the source reads and the
last account check); the last is appended here to `problems.jsonl` in the workspace's private folder, a short line each
(time, where, exception type, masked message, never a traceback), kept to the newest few.

What a report holds is what a maintainer needs: when, what was being done, the account's kind, adapter and program
version, the request's settings, the status, the error kind and the service's own error text. Never the packet, the
request, any mail, note or record text, a file's name, or a person's or project's name. Text that came from outside is
masked before it is kept or shown (`mask`): keys, tokens and passwords become "<secret>", email addresses "<address>",
paths "<path>", names of the workspace's own people, projects, files and organizations "<name>", and a URL keeps only
its scheme and host. The app sends nothing: the person reads the lines and sends them, or not.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit

from engine.ai.task import NO_WORK_KINDS
from engine.secrets import SecretError, resolve_secret
from engine.state_file import changing, write_whole

log = logging.getLogger(__name__)

FILE = "problems.jsonl"
#: How many lines are kept for each problem the person may be offered.
KEEP_FACTOR = 5
#: The most characters of an error's text a line keeps (after masking).
TEXT_LIMIT = 400
#: A value shorter than this is never taken for a secret by its value alone.
MIN_SECRET = 6
SECRET = "<secret>"
ADDRESS = "<address>"
PATH = "<path>"
NAME = "<name>"

Doing = Literal["task", "account_check", "source_read", "app"]


@dataclass(frozen=True)
class Problem:
    """One failure as the person will see it, already masked. `what` is the task kind, the part of an account check, the
    connector of a source or where in the app, by `doing`."""

    at: datetime
    doing: Doing
    what: str | None = None
    service: str | None = None
    adapter: str | None = None
    program_version: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    status: int | None = None
    error_kind: str | None = None
    text: str = ""


# --- masking -------------------------------------------------------------------------------------------------------

_URL = re.compile(r"""[A-Za-z][A-Za-z0-9+.-]*://[^\s"'<>)\]}]+""")
_ADDRESS = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_PATH = re.compile(
    r"""(?<![\w/\\:.])(?:
        [A-Za-z]:[\\/][^\s"'<>,;)]*
        | \\\\[^\s"'<>,;)]+
        | ~[/\\][^\s"'<>,;)]*
        | /(?:home|Users|tmp|var|mnt|opt|root|media|Volumes|private|srv|etc|usr|run|Library)/[^\s"'<>,;)]*
    )""",
    re.VERBOSE,
)
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)(\s+)[A-Za-z0-9._~+/=-]{8,}")
_SECRET_KEY = re.compile(
    r"""(?ix)
    \b([\w-]*(?:key|token|secret|password|passwd|pwd|credential|authorization|auth)[\w-]*)
    (["']?\s*[:=]\s*)
    (["']?)([^\s"',;&})]+)"""
)
_SECRET_SAID = re.compile(
    r"""(?ix)\b((?:key|token|secret|password|credential)s?\s+(?:provided|supplied|given|used|sent|received|presented)
    \s*[:=]?\s*)(["']?)([^\s"',;&})]+)"""
)
_LONG_RUN = re.compile(r"[A-Za-z0-9_\-+/=.~]{20,}")
_PREFIXED = re.compile(r"\b[A-Za-z]{2,10}[-_][A-Za-z0-9_-]{20,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)
_STATUS = re.compile(r"\bHTTP[ /]?([1-5]\d\d)\b")


def _host_only(url: str) -> str:
    """A URL as its scheme and host alone: no user, port, path, query or fragment."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return "<url>"
    if parts.scheme.lower() == "file" or not host:
        return PATH if parts.scheme.lower() == "file" else "<url>"
    shown = f"[{host}]" if ":" in host else host
    return f"{parts.scheme.lower()}://{shown}"


def _looks_secret_value(value: str, quoted: bool) -> bool:
    """A value after a key-like name is masked unless it is a short plain word, so a sentence like "key: missing" keeps
    its meaning while "key=abc123" and a quoted value do not."""
    if quoted or len(value) >= 12:
        return True
    if value.isdigit() and len(value) < 8:  # a count or a limit, such as a token limit
        return False
    return not value.isalpha() and len(value) >= 3


def _mixed(token: str) -> bool:
    return (any(c.isdigit() for c in token) and any(c.isalpha() for c in token)) or (
        any(c.isupper() for c in token) and any(c.islower() for c in token)
    )


def mask(
    text: str,
    secrets: Iterable[str] = (),
    names: Iterable[str] = (),
    keep: Iterable[str] = (),
) -> str:
    """The text with what must not leave this computer replaced: the exact values in `secrets` and anything shaped like
    a key, token or password ("<secret>"), email addresses ("<address>"), a URL's all but its scheme and host, file
    paths ("<path>"), and each of `names` as a whole word ("<name>"). `keep` is text that looks like a token but is
    not (a model's id, which an error names)."""
    if not text:
        return ""
    held = {k for k in keep if k}
    for value in sorted({s for s in secrets if len(s) >= MIN_SECRET}, key=len, reverse=True):
        text = text.replace(value, SECRET)
    text = _PRIVATE_KEY.sub(SECRET, text)
    text = _URL.sub(lambda m: _host_only(m.group(0)), text)
    text = _ADDRESS.sub(ADDRESS, text)
    text = _PATH.sub(PATH, text)
    text = _AUTH_SCHEME.sub(lambda m: f"{m.group(1)}{m.group(2)}{SECRET}", text)

    def key_value(m: re.Match[str]) -> str:
        value = m.group(4).rstrip(".")
        if not value or value in (SECRET, ADDRESS, PATH, NAME) or not _looks_secret_value(value, bool(m.group(3))):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{m.group(3)}{SECRET}{m.group(4)[len(value) :]}"

    def said_value(m: re.Match[str]) -> str:
        value = m.group(3).rstrip(".")
        if not value or value in (SECRET, ADDRESS, PATH, NAME) or not _looks_secret_value(value, bool(m.group(2))):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{SECRET}{m.group(3)[len(value) :]}"

    text = _SECRET_KEY.sub(key_value, text)
    text = _SECRET_SAID.sub(said_value, text)

    def token(m: re.Match[str]) -> str:
        found = m.group(0)
        if found in held or any(h in found for h in held if len(h) >= 8) or not _mixed(found):
            return found
        return SECRET

    text = _LONG_RUN.sub(token, text)
    text = _PREFIXED.sub(lambda m: m.group(0) if m.group(0) in held or not _mixed(m.group(0)) else SECRET, text)
    for name in sorted({n.strip() for n in names if len(n.strip()) >= 3}, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", NAME, text, flags=re.IGNORECASE)
    return text


def _config_values(node: Any) -> Iterable[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, Mapping):
        for value in node.values():
            yield from _config_values(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _config_values(value)


def resolved_secrets(ws: Any, cfg: Any, env: Mapping[str, str] | None = None) -> set[str]:
    """The values of the workspace's own secrets: every `env:` or `file:` reference in the settings (accounts, sources,
    add-ons) that resolves, and each key the app keeps in its private folder. Only the values, never where from."""
    env = os.environ if env is None else env
    found: set[str] = set()
    for model in getattr(cfg, "files", {}).values():
        try:
            data = model.model_dump(mode="json")
        except Exception:  # a file's model that can't be shown holds no secret this can name
            continue
        for value in _config_values(data):
            scheme = value.partition(":")[0]
            if scheme in ("env", "file") and ":" in value:
                try:
                    secret = resolve_secret(value, env)
                except (SecretError, OSError):
                    continue
                if secret:
                    found.add(secret)
    try:
        for path in (ws.private_dir / "keys").iterdir():
            if path.is_file():
                found.add(path.read_text(encoding="utf-8").strip())
    except OSError:
        pass
    return {s for s in found if len(s) >= MIN_SECRET}


def own_names(store: Any) -> set[str]:
    """The names the workspace's records give people, projects, organizations, teams and files: what an error's text
    must not repeat."""
    view = store.read()
    names: set[str] = set()
    for stored in view.list("person"):
        data = stored.data
        full = str(data.get("full_name") or "")
        names.add(full)
        names.update(part for part in re.split(r"[\s,]+", full) if len(part) >= 3)
        names.update(str(a) for a in data.get("aliases") or [])
        if data.get("first_name"):
            names.add(str(data["first_name"]))
    for kind in ("project", "organization", "team", "file"):
        for stored in view.list(kind):
            if stored.data.get("name"):
                names.add(str(stored.data["name"]))
    return {n for n in names if len(n.strip()) >= 3}


@dataclass(frozen=True)
class Masker:
    """What to hide, found once: callable on a text."""

    secrets: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    keep: frozenset[str] = frozenset()

    def __call__(self, text: str | None) -> str:
        return mask(text or "", self.secrets, self.names, self.keep)


def masker_for(ws: Any, store: Any, cfg: Any, env: Mapping[str, str] | None = None) -> Masker:
    models = {
        model
        for provider in getattr(getattr(cfg, "ai", None), "providers", {}).values()
        for model in provider.models.values()
    }
    return Masker(frozenset(resolved_secrets(ws, cfg, env)), frozenset(own_names(store)), frozenset(models))


def _cut(text: str, limit: int = TEXT_LIMIT) -> str:
    one = " ".join(text.split())
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


def status_of(text: str | None) -> int | None:
    """The HTTP status the adapters write at the start of a failed call's text, if there is one."""
    found = _STATUS.search(text or "")
    return int(found.group(1)) if found else None


# --- the app's own errors ------------------------------------------------------------------------------------------


def note(
    ws: Any,
    store: Any,
    cfg: Any,
    where: str,
    error: BaseException,
    *,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Keep a line for an unexpected error: when, where (a short fixed label), the exception's type and its message with
    the secrets, addresses, paths and names masked. No traceback. Never raises: the place that failed goes on."""
    try:
        masked = _cut(masker_for(ws, store, cfg, env)(str(error)))
        line = {
            "at": (now or datetime.now(UTC)).isoformat(),
            "where": where,
            "type": type(error).__name__,
            "message": masked,
        }
        path = ws.private_dir / FILE
        keep = max(1, cfg.ui.feedback_problem_max * KEEP_FACTOR)
        with changing(path):
            try:
                lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            except OSError:
                lines = []
            lines.append(json.dumps(line, sort_keys=True))
            write_whole(path, "\n".join(lines[-keep:]) + "\n", mode=0o600)
    except Exception:  # a failure to report a failure must never be a second one
        log.warning("Couldn't keep a line about an error")


def _app_lines(ws: Any) -> list[dict[str, Any]]:
    try:
        raw = (ws.private_dir / FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    lines = []
    for text in raw:
        try:
            row = json.loads(text)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("at"), str):
            lines.append(row)
    return lines


# --- gathering ------------------------------------------------------------------------------------------------------


def _at(text: Any) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _shown(value: Any) -> str:
    return "yes" if value is True else "no" if value is False else str(value)


def _request_settings(cfg: Any, name: str | None) -> dict[str, str]:
    """The account's request settings that decide what a call sends."""
    provider = cfg.ai.providers.get(name or "")
    if provider is None or provider.agent is not None:
        return {}
    out = {
        "send_temperature": _shown(provider.send_temperature),
        "json_mode": _shown(provider.json_mode),
        "max_tokens_param": provider.max_tokens_param,
    }
    if provider.effort_param:
        out["effort_param"] = provider.effort_param
    return out


def _account(cfg: Any, name: str | None, version: Callable[[str], str | None]) -> dict[str, Any]:
    provider = cfg.ai.providers.get(name or "")
    if provider is None:
        return {}
    return {
        "service": provider.kind or provider.adapter,
        "adapter": provider.adapter,
        "program_version": version(name or "") if provider.adapter == "cli-agent" else None,
    }


def default_program_version(cfg: Any) -> Callable[[str], str | None]:
    """Reads an agent account's program version from the program itself (reused for a few minutes)."""

    def read(name: str) -> str | None:
        from engine.ai import matrix
        from engine.ai.adapters import make_adapter

        try:
            return matrix.current_program_version(cfg, name, make_adapter)
        except Exception:  # a program that can't say its version leaves it blank
            return None

    return read


def recent(
    ws: Any,
    store: Any,
    cfg: Any,
    now: datetime,
    *,
    masker: Masker | None = None,
    program_version: Callable[[str], str | None] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[Problem]:
    """The failures of the last `ui.feedback_problem_days` days, newest first, at most `ui.feedback_problem_max`, each
    masked and its error text cut. Empty when there were none."""
    hide = masker or masker_for(ws, store, cfg, env)
    version = program_version or default_program_version(cfg)
    since = now - timedelta(days=cfg.ui.feedback_problem_days)
    found = [*_failed_runs(store, cfg, since, hide, version), *_failed_reads(store, cfg, since, hide)]
    found += _failed_checks(ws, cfg, since, hide, version)
    found += _app_problems(ws, since, hide)
    found.sort(key=lambda p: p.at, reverse=True)
    return found[: cfg.ui.feedback_problem_max]


def _failed_runs(
    store: Any, cfg: Any, since: datetime, hide: Masker, version: Callable[[str], str | None]
) -> list[Problem]:
    out = []
    for stored in store.read().since("run", "started_at", since.date().isoformat()):
        run = stored.data
        when = _at(run.get("started_at"))
        if when is None or when < since or run.get("outcome") == "ok" or run.get("error_kind") in NO_WORK_KINDS:
            continue
        task = cfg.ai.tasks.get(run["task"])
        tier = cfg.ai.tiers.get(run["tier"])
        params = {"tier": run["tier"], "model": run["model"]}
        if task is not None:
            params["temperature"] = str(task.temperature)
            params["max_output"] = str(task.max_output)
        if tier is not None and tier.effort:
            params["effort"] = tier.effort
        params.update(_request_settings(cfg, run["provider"]))
        detail = run.get("error_detail") or ""
        out.append(
            Problem(
                at=when,
                doing="task",
                what=run["task"],
                params=params,
                status=status_of(detail),
                error_kind=run.get("error_kind") or run.get("outcome"),
                text=_cut(hide(detail)),
                **_account(cfg, run["provider"], version),
            )
        )
    return out


def _failed_reads(store: Any, cfg: Any, since: datetime, hide: Masker) -> list[Problem]:
    connectors = {s.id: s.connector for s in cfg.watch.sources}
    out = []
    for stored in store.read().since("watch_run", "started_at", since.date().isoformat()):
        run = stored.data
        when = _at(run.get("started_at"))
        if when is None or when < since or run.get("outcome") != "failed":
            continue
        text = run.get("error") or ""
        out.append(
            Problem(
                at=when,
                doing="source_read",
                what=connectors.get(run["source"]),
                status=status_of(text),
                error_kind=run.get("error_kind"),
                text=_cut(hide(text)),
            )
        )
    return out


def _failed_checks(
    ws: Any, cfg: Any, since: datetime, hide: Masker, version: Callable[[str], str | None]
) -> list[Problem]:
    from engine.ai.smoke import last_test

    test = last_test(ws)
    when = _at(test.get("at")) if test else None
    if test is None or when is None or when < since:
        return []
    out: list[Problem] = []
    seen: set[tuple[Any, ...]] = set()
    for result in test.get("results") or []:
        if not isinstance(result, dict) or result.get("ok") or result.get("offline") or not result.get("provider"):
            continue
        name = result["provider"]
        provider = cfg.ai.providers.get(name)
        ref = str(result.get("ref") or "")
        model_key = ref.partition("/")[2]
        params = {"tier": str(result.get("tier") or "")}
        if provider is not None and model_key:
            params["model"] = provider.models.get(model_key, model_key)
        found = result.get("params") or []
        for label, value in zip(("task", "temperature", "max_output", "effort"), found, strict=False):
            if label != "task":
                params[label] = str(value)
        params.update(_request_settings(cfg, name))
        raw = str(result.get("error_detail") or result.get("detail") or "")
        problem = Problem(
            at=when,
            doing="account_check",
            what=str(result.get("part") or "call"),
            params=params,
            status=status_of(raw),
            error_kind=result.get("error_kind") or None,
            text=_cut(hide(raw)),
            **_account(cfg, name, version),
        )
        key = (name, problem.what, problem.error_kind, problem.text, tuple(sorted(params.items())))
        if key not in seen:
            seen.add(key)
            out.append(problem)
    return out


def _app_problems(ws: Any, since: datetime, hide: Masker) -> list[Problem]:
    out = []
    for row in _app_lines(ws):
        when = _at(row.get("at"))
        if when is None or when < since:
            continue
        out.append(
            Problem(
                at=when,
                doing="app",
                what=str(row.get("where") or "") or None,
                error_kind=str(row.get("type") or "") or None,
                text=_cut(hide(str(row.get("message") or ""))),
            )
        )
    return out
