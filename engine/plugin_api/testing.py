"""Testing a plugin: part of the plugin API, for plugins' own tests. A connector without a network
(`connector_context`, `read`), and everything else in a throwaway workspace (`plugin_workspace`).

    from engine.plugin_api.testing import Reply, connector_context, read

    def service(asked):
        if asked.path == "/v1/changes":
            return Reply(json={"items": [...], "next": "m2"})
        return Reply(status=404)

    context = connector_context(service, network=["api.example.com"], secrets={"client-id": "x"},
                                tokens={"myplugin/account": "token"})
    poll = read(my_poll, MySettings(), {}, context)

`service(asked)` answers every request the connector makes through `context.web`: `asked` has the method, url,
path (decoded; `raw_path` as sent), query (a dict of lists, blank values kept; `param(name)` gives the first value),
headers and body (text, and `form` / `json()` parsed). A `Reply()` with neither `json` nor `text` has an empty body;
answer `Reply(json={})` for a service that answers an empty JSON object. Only hosts in `network` are reached, over
HTTPS, as in the app. `secrets` answers `context.secret(name)` and records `context.keep_secret`; `tokens` answers
`context.access_token(name)`, and a sign-in missing from it raises `ConnectorError("auth")` as an expired sign-in
does; `granted` answers `context.granted(name)` with each sign-in's allowed scopes (left out, `context.granted` is
None, as for a connector of a plugin with no sign-ins). `read` runs `poll` and checks its answer the way the
watcher does.
"""

from __future__ import annotations

import json as jsonlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from engine.connectors import ConnectorContext, ConnectorError, Poll, checked_poll

__all__ = [
    "Asked",
    "Reply",
    "connector_context",
    "read",
    "plugin_workspace",
    "PluginWorkspace",
    "Outcome",
    "AskResult",
    "ActionResult",
    "PluginDidNotStart",
    "PluginState",
    "SavedWorkspace",
]


@dataclass(frozen=True)
class Asked:
    """One request a connector made."""

    method: str
    url: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: str
    raw_path: str = ""

    def param(self, name: str, default: str | None = None) -> str | None:
        """The first value of a query parameter, or `default` when it isn't there."""
        values = self.query.get(name)
        return values[0] if values else default

    @property
    def form(self) -> dict[str, list[str]]:
        """A form body, parsed, blank values kept."""
        return parse_qs(self.body, keep_blank_values=True)

    def json(self) -> Any:
        return jsonlib.loads(self.body) if self.body else None


@dataclass(frozen=True)
class Reply:
    """An answer: a status, and a JSON value or text, with headers (a Retry-After, say)."""

    status: int = 200
    json: Any = None
    text: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


def connector_context(
    service: Callable[[Asked], Reply],
    *,
    network: list[str],
    secrets: dict[str, str] | None = None,
    tokens: dict[str, str] | None = None,
    granted: dict[str, set[str]] | None = None,
    workspace_root: Path | str = ".",
) -> ConnectorContext:
    """A connector's context whose web client is answered by `service`. `kept` secrets land in `secrets`."""
    from engine.net import WebClient

    kept = secrets if secrets is not None else {}
    signed_in = dict(tokens or {})
    allowed = {name: set(scopes) for name, scopes in (granted or {}).items()}

    def answer(request: httpx.Request) -> httpx.Response:
        parts = urlsplit(str(request.url))
        asked = Asked(
            request.method,
            str(request.url),
            unquote(parts.path),
            parse_qs(parts.query, keep_blank_values=True),
            dict(request.headers),
            request.content.decode("utf-8", errors="replace"),
            parts.path,
        )
        reply = service(asked)
        if not isinstance(reply, Reply):
            raise TypeError("the service function answers with a Reply")
        if reply.json is not None:
            return httpx.Response(reply.status, json=reply.json, headers=reply.headers)
        return httpx.Response(reply.status, text=reply.text or "", headers=reply.headers)

    def access_token(name: str) -> str:
        if name not in signed_in:
            raise ConnectorError("auth", f"Sign in to {name} first.")
        return signed_in[name]

    return ConnectorContext(
        workspace_root=Path(workspace_root),
        web=WebClient(list(network), transport=httpx.MockTransport(answer)),
        secret=kept.get,
        keep_secret=kept.__setitem__,
        access_token=access_token,
        granted=(lambda name: set(allowed.get(name, set()))) if granted is not None else None,
    )


def read(poll: Callable[..., Poll], settings: Any, state: dict[str, Any] | None, context: ConnectorContext) -> Poll:
    """Run a connector's `poll` and check its answer as the watcher does. A ConnectorError passes through."""
    return checked_poll(poll(settings, dict(state or {}), context))


# ---- a throwaway workspace with the plugin loaded --------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """What became of a changeset: its id, its `status` (applied, held, rejected) and one entry per op (`op`,
    `status` applied/held/refused, `reason`). `refused` lists the reasons of the refused ops; `problems` are those of
    the changeset as a whole."""

    changeset: str
    status: str
    ops: list[dict[str, Any]]
    problems: list[dict[str, Any]]

    @property
    def applied(self) -> list[dict[str, Any]]:
        return [o["op"] for o in self.ops if o.get("status") == "applied"]

    @property
    def held(self) -> list[dict[str, Any]]:
        return [o["op"] for o in self.ops if o.get("status") == "held"]

    @property
    def refused(self) -> list[str]:
        return [str(o.get("reason") or "") for o in self.ops if o.get("status") == "refused"]


@dataclass(frozen=True)
class AskResult:
    """A run of a task kind: the request's `state` (review: the answer waits for the person; needs_you: it was held,
    with `waiting` saying why) and the `outcome` of its changeset, when there is one."""

    request: str
    state: str
    waiting: str | None
    outcome: Outcome | None


@dataclass
class ActionResult:
    """A person action's proposal as the review shows it: `summary`, `ops`, `notes`, `items`, `requests` and
    `problems` (why ops would be refused if applied now). `apply(kept=...)` applies it as the person would."""

    summary: str
    ops: list[dict[str, Any]]
    notes: list[str]
    items: list[dict[str, Any]]
    requests: list[dict[str, Any]]
    problems: list[str]
    _apply: Callable[..., Outcome]

    def apply(self, kept: dict[str, bool] | None = None) -> Outcome:
        return self._apply(kept)


class PluginDidNotStart(RuntimeError):
    """A plugin given to `plugin_workspace` didn't start: `plugin` names it and `reason` says why, as its status on
    the Add-ons screen would."""

    def __init__(self, plugin: str, reason: str):
        super().__init__(f"the plugin {plugin} didn't start: {reason}")
        self.plugin, self.reason = plugin, reason


@dataclass(frozen=True)
class PluginState:
    """A plugin's status as the host keeps it: `state` (enabled, disabled, off), the `reason` it is off, `notes`
    (problems it was told about) and its declared programs' `tools` status."""

    state: str
    reason: str | None
    notes: list[str]
    tools: dict[str, str]


@dataclass(frozen=True)
class SavedWorkspace:
    """A workspace saved with `ws.save()`, to start tests from fresh copies of: `plugin_workspace(...,
    from_saved=saved)`."""

    path: Path


class PluginWorkspace:
    """A throwaway workspace (the fictional demo's data) with the plugins loaded, for a plugin's own tests. Use it
    through `plugin_workspace(...)`. Everything here goes through the same paths as the app: the applier, the
    dispatcher with a scripted answer, person actions, events, stage moves and the synced folder's layout.

    Its attributes: `root` (the workspace folder), `plugins` (the names of the plugins given, in order) and `cfg`
    (the workspace's settings as loaded). `store` and `ws` are the host's own objects: reach them only where no
    method here covers a test, since they change with the host."""

    def __init__(
        self,
        root: Path,
        folders: tuple[str | Path, ...],
        settings: dict[str, dict[str, Any]] | None,
        *,
        from_saved: SavedWorkspace | None = None,
        require_started: bool = True,
    ):
        import shutil

        import yaml

        from engine.cli import add_plugin
        from engine.config import load_config
        from engine.shipped import demo
        from engine.storage import Store
        from engine.workspace import Workspace, init_workspace
        from engine.yaml_load import load_yaml

        if from_saved is not None:
            shutil.copytree(from_saved.path, root, symlinks=True)
            self.ws = Workspace(root)
            self.plugins = list(load_yaml((root / ".plugin-workspace.yaml").read_text(encoding="utf-8")))
            self.cfg = load_config(self.ws.config_dir, env={})
            self.store = Store(self.ws.db_path, cfg=self.cfg)
            self._check_started(require_started)
            return
        self.ws = init_workspace(root, template=demo("demo-b"), git=False)
        storage_path = self.ws.config_dir / "storage.yaml"
        storage = load_yaml(storage_path.read_text(encoding="utf-8")) or {}
        storage.setdefault("backups", {})["automatic"] = False
        storage_path.write_text(yaml.safe_dump(storage), encoding="utf-8")
        self.plugins = [add_plugin(self.ws, str(folder)) for folder in folders]
        for name, values in (settings or {}).items():
            (self.ws.config_dir / "plugins").mkdir(exist_ok=True)
            (self.ws.config_dir / "plugins" / f"{name}.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")
        (self.ws.root / ".plugin-workspace.yaml").write_text(yaml.safe_dump(self.plugins), encoding="utf-8")
        self.cfg = load_config(self.ws.config_dir, env={})
        self.store = Store(self.ws.db_path, cfg=self.cfg)
        self._check_started(require_started)

    def _check_started(self, required: bool) -> None:
        if not required:
            return
        for name in self.plugins:
            if not self.store.plugins.active(name):
                status = self.store.plugins.status.get(name)
                reason = (status.reason if status is not None else None) or "it isn't installed"
                self.store.close()
                raise PluginDidNotStart(name, reason)

    def status(self, plugin: str | None = None) -> PluginState:
        """A plugin's status (the first plugin given, unless named), whether it started or not."""
        found = self.store.plugins.status.get(plugin or self.plugins[0])
        if found is None:
            return PluginState("off", "it isn't installed or turned on", [], {})
        return PluginState(found.state, found.reason, list(found.notes), dict(found.tools))

    def registered(self, plugin: str | None = None) -> dict[str, dict[str, Any]]:
        """What a plugin registered, by kind, read-only: {"sign_ins": {name: its declaration}, "connectors": ...,
        "triage_matchers", "setup_steps", "actions", "tasks", "ops", "records", "panels", "today", "jobs",
        "stage_checks", "file_kinds", "lints"}. Empty kinds are left out. A started plugin only."""
        from types import MappingProxyType

        registrar = self.store.plugins.registrars.get(plugin or self.plugins[0])
        if registrar is None:
            return {}
        kinds = (
            ("sign_ins", "sign_ins"),
            ("connectors", "connectors"),
            ("triage_matchers", "triage_matchers"),
            ("setup_steps", "setup_steps"),
            ("actions", "actions"),
            ("tasks", "tasks"),
            ("ops", "ops"),
            ("records", "records"),
            ("panels", "panels"),
            ("today", "today_lines"),
            ("jobs", "jobs"),
            ("stage_checks", "stage_checks"),
            ("file_kinds", "file_kinds"),
            ("lints", "lints"),
        )
        found = {}
        for label, attribute in kinds:
            value = getattr(registrar, attribute, None)
            if value:
                found[label] = MappingProxyType(dict(value))
        return found

    def save(self, path: str | Path) -> SavedWorkspace:
        """Save this workspace as it is now (records, settings, the plugins linked in), so other tests start from
        fresh copies of it with `plugin_workspace(..., from_saved=saved)` instead of building it again."""
        import shutil

        target = Path(path)
        self.store.close()
        try:
            shutil.copytree(self.ws.root, target, symlinks=True)
        finally:
            from engine.storage import Store

            self.store = Store(self.ws.db_path, cfg=self.cfg)
        return SavedWorkspace(target)

    @property
    def root(self) -> Path:
        return self.ws.root

    def view(self, plugin: str | None = None) -> Any:
        """A ReadView as the plugin sees it (the first plugin given, unless named)."""
        from engine.plugin_api import ReadView

        return self.store.plugins._with_files(ReadView(self.store.read(), plugin or self.plugins[0]))

    def _outcome(self, cs_id: str) -> Outcome:
        record = self.store.read().get("changeset", cs_id)
        return Outcome(cs_id, record.data["status"], list(record.data["ops"]), list(record.data.get("problems") or []))

    def apply(
        self, ops: list[dict[str, Any]], *, summary: str = "Test", as_person: bool = True, trusted: bool = True
    ) -> Outcome:
        """Apply ops as the person (their own change, applied at once) or as the assistant (checked by validators and
        lints first, `trusted=False` for work from outside content), and say what became of each."""
        from engine.applier import Context, Inputs, apply_changeset, check
        from engine.names import People
        from engine.ops import CHANGESET
        from engine.storage import WriteContext

        changeset = CHANGESET.validate_python(
            {"summary": summary, "ops": ops}, context={"op_models": self.store.plugins.ops}
        )
        with self.store.transaction() as tx:
            request = tx.create(
                "request",
                {"task": "notes", "origin": "pm", "state": "done", "note": summary, "created_at": self.store.clock()},
                WriteContext("pm", "trusted", "test"),
            )
        ctx = Context(
            self.store,
            self.cfg,
            People(self.store, self.cfg),
            tuple(self.store.plugins.ops),
            Inputs(request.id, None, "", summary, "trusted" if trusted else "untrusted"),
            confirmed_by_pm=as_person,
            actor="pm" if as_person else "assistant",
        )
        problems = [] if as_person else check(changeset, ctx)
        return self._outcome(apply_changeset(changeset, problems, ctx, run=None))

    def ask(
        self,
        task: str,
        *,
        answer: Any,
        about: tuple[str, str] | None = None,
        part: dict[str, Any] | None = None,
        note: str = "",
    ) -> AskResult:
        """Run a task kind with a scripted answer, through the dispatcher: the packet, the checks, the fix round and
        the review. `answer` is the answer's text, a dict (sent as JSON) or a function of the run's task, whose
        `request` carries the fix round's feedback, so it can answer differently each round."""
        from datetime import UTC, datetime

        from engine.ai.adapters.stub import set_responder
        from engine.ai.router import Router
        from engine.dispatcher import process
        from engine.storage import WriteContext

        def respond(asked: Any) -> str:
            value = answer(asked) if callable(answer) else answer
            return value if isinstance(value, str) else jsonlib.dumps(value)

        data: dict[str, Any] = {
            "task": task,
            "origin": "pm",
            "state": "queued",
            "note": note,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if about is not None:
            data["about"] = {"kind": about[0], "id": about[1]}
        if part is not None:
            data["part"] = part
        with self.store.transaction() as tx:
            request = tx.create("request", data, WriteContext("pm", "trusted", "test"))
        set_responder(respond)
        try:
            process(self.ws, self.store, self.cfg, Router(self.cfg, self.store, env={}), request.id)
        finally:
            set_responder(None)
        done = self.store.read().get("request", request.id)
        cs_id = done.data.get("changeset")
        return AskResult(
            request.id, done.data["state"], done.data.get("waiting"), self._outcome(cs_id) if cs_id else None
        )

    def action(self, name: str, target: Any = None, choices: dict[str, Any] | None = None) -> ActionResult:
        """Run a person action on a record (a Stored, or (kind, id)) or the workspace, and get its proposal."""
        from engine import actions

        ref = None
        if target is not None:
            kind, record_id = (target.kind, target.id) if hasattr(target, "kind") else target
            ref = {"kind": kind, "id": record_id}
        pending = actions.preview(self.store, self.cfg, name, ref, choices)

        def apply(kept: dict[str, bool] | None) -> Outcome:
            return self._outcome(actions.apply(self.store, self.cfg, pending.token, kept))

        return ActionResult(
            pending.summary,
            list(pending.ops),
            list(pending.notes),
            list(pending.items),
            list(pending.requests),
            list(pending.problems),
            apply,
        )

    def emit(self, event: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Raise an event as the core would and return the work the handlers queued: one dict per new request
        (`task`, `about`, `note`, `state`)."""
        before = {r.id for r in self.store.read().list("request")}
        self.store.plugins.publish(event, payload)
        return [
            {k: r.data.get(k) for k in ("task", "about", "note", "state")}
            for r in self.store.read().list("request")
            if r.id not in before
        ]

    def move_stage(self, record: Any, to: str) -> Outcome:
        """Move a record to a stage as the person would; a refusal (an entry check failing) raises StoreError."""
        from engine.applier import move_stage
        from engine.ops import StageMoveOp

        fresh = self.store.read().get(record.kind, record.id)
        cs_id = move_stage(
            self.store,
            StageMoveOp(record={"kind": record.kind, "id": record.id}, to=to, read_version=fresh.version),
        )
        return self._outcome(cs_id)

    def stage_status(self, record: Any) -> Any:
        return self.view(record.kind.split("/")[0] if "/" in record.kind else None).stage_status(record)

    def folder(self) -> dict[str, bytes]:
        """The files the synced folder would hold now, by path, as the core writes them (the plugin's layout,
        its generated files and the core's own)."""
        from engine.sync import Blob, readable_files

        files, _ = readable_files(self.store, self.store.read())
        return {path: data.path.read_bytes() if isinstance(data, Blob) else data for path, data in files.items()}

    def close(self) -> None:
        self.store.close()


def plugin_workspace(
    *folders: str | Path,
    settings: dict[str, dict[str, Any]] | None = None,
    root: str | Path | None = None,
    from_saved: SavedWorkspace | None = None,
    require_started: bool = True,
) -> Any:
    """A throwaway workspace with these plugins loaded (a plugin folder holding plugin.yaml, or an installed plugin's
    name), with `settings` per plugin as its settings file. A context manager: the workspace is made in `root` (a
    pytest `tmp_path`, say) or a temporary folder, and closed after. A plugin folder is linked into the workspace
    (copied where links aren't allowed), so a temporary copy of a folder works as well as the real one.

    `from_saved` starts from a fresh copy of a workspace saved with `ws.save(path)` (then `folders` and `settings`
    are those it was saved with). A plugin that doesn't start raises `PluginDidNotStart` (with `plugin` and
    `reason`); `require_started=False` opens the workspace anyway, to look at `ws.status()`.

        with plugin_workspace(PLUGIN_FOLDER, root=tmp_path) as ws:
            done = ws.apply([{"op": "myplugin/add", "title": "One"}])
            assert done.status == "applied"
    """
    import contextlib
    import tempfile

    @contextlib.contextmanager
    def opened() -> Any:
        with contextlib.ExitStack() as stack:
            base = Path(root) if root is not None else Path(stack.enter_context(tempfile.TemporaryDirectory()))
            workspace = PluginWorkspace(
                base / "workspace", folders, settings, from_saved=from_saved, require_started=require_started
            )
            try:
                yield workspace
            finally:
                workspace.close()

    return opened()
