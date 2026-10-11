"""Person actions (plugin API 0.3): deterministic work a person starts on a record, a file or the workspace.

Running an action gives one proposal for one review: the ops it would apply, the files it made, previews and named
choices. Flipping a choice runs the action again. The person approves exactly what they reviewed: the proposal is kept
under a token and applied as theirs (actor `pm`), so person-only values apply and system ops need no second go. If
the target changed since the review, nothing applies and the person runs the action again.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from engine.config import Config
from engine.ops import CHANGESET, NEEDS_EVIDENCE, OP_MODELS
from engine.storage import Store, StoreError, WriteContext

#: What a preview may be: pictures and plain text, never markup or anything that runs.
PREVIEW_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "text/plain"}
#: Core ops an action may propose. Ops that must cite evidence need an input to quote, which an action doesn't have;
#: file.add is the host's own, made from the proposal's files.
ACTION_CORE_OPS = frozenset(OP_MODELS) - NEEDS_EVIDENCE - {"file.add"}
_PLACEHOLDER = "$file:"


class ActionFailed(StoreError):
    """The action couldn't produce a proposal; the reason is in plain words."""


@dataclass
class Pending:
    token: str
    plugin: str
    action: str
    target: dict[str, Any] | None  # {kind, id, version}
    choices: dict[str, Any]
    summary: str
    ops: list[dict[str, Any]]
    files: list[dict[str, Any]]  # name, media_type, size, sha256, file_kind, project, meta, replaces
    previews: list[dict[str, Any]]
    choice_list: list[dict[str, Any]]
    notes: list[str]
    created: float = field(default_factory=time.monotonic)
    expires_at: str = ""


class Proposals:
    """Proposals waiting for the person, kept in memory for a while; restarting forgets them."""

    def __init__(self) -> None:
        self._items: dict[str, Pending] = {}

    def put(self, pending: Pending, keep_minutes: float, limit: int = 50) -> None:
        self._prune(keep_minutes)
        while len(self._items) >= limit:
            self._items.pop(next(iter(self._items)))
        self._items[pending.token] = pending

    def take(self, token: str, keep_minutes: float) -> Pending:
        self._prune(keep_minutes)
        pending = self._items.pop(token, None)
        if pending is None:
            raise StoreError("that review has expired; run the action again")
        return pending

    def _prune(self, keep_minutes: float) -> None:
        cutoff = time.monotonic() - keep_minutes * 60
        for token in [t for t, p in self._items.items() if p.created < cutoff]:
            del self._items[token]


def available(store: Store, kind: str | None = None, record_id: str | None = None) -> list[Any]:
    """The actions a person can start on a record of `kind` (or on the workspace when kind is None)."""
    target = store.read().get(kind, record_id) if kind and record_id else None
    found = []
    for name, registrar in store.plugins.registrars.items():
        if not store.plugins.active(name):
            continue
        for action in registrar.actions.values():
            if action.on != kind:
                continue
            if action.file_kinds and (target is None or target.data.get("file_kind") not in action.file_kinds):
                continue
            found.append(action)
    return sorted(found, key=lambda a: a.label)


def _registration(store: Store, name: str) -> tuple[str, Any]:
    plugin = name.split("/")[0]
    registrar = store.plugins.registrars.get(plugin)
    if registrar is None or name not in registrar.actions or not store.plugins.active(plugin):
        raise StoreError(f"there is no action {name} running now")
    return plugin, registrar.actions[name]


def preview(
    store: Store,
    cfg: Config,
    name: str,
    target: dict[str, str] | None = None,
    choices: dict[str, Any] | None = None,
) -> Pending:
    """Run an action and keep its proposal for the person's review."""
    from engine.plugin_api import ActionContext, Proposal
    from engine.tools import ToolError

    plugin, action = _registration(store, name)
    choices = dict(choices or {})
    view = store.read()
    record = None
    if action.on is None:
        if target is not None:
            raise StoreError(f"{action.label} works on the whole workspace, not on one record")
    else:
        if target is None or target.get("kind") != action.on:
            raise StoreError(f"{action.label} works on a {action.on}")
        record = view.get(action.on, target["id"])
        if record is None:
            raise StoreError(f"there is no {action.on} {target['id']}")
        if action.file_kinds and record.data.get("file_kind") not in action.file_kinds:
            raise StoreError(f"{action.label} doesn't work on this kind of file")
    registrar = store.plugins.registrars[plugin]
    context = store.plugins._with_files(ActionContext(view, plugin, registrar.config, store.plugins.tool_box(plugin)))
    try:
        result = action.run(record, context, dict(choices))
    except (ToolError, StoreError) as err:
        raise ActionFailed(str(err)) from None
    except Exception as err:
        store.plugins.disable(plugin, f"action {name} failed: {err}")
        raise ActionFailed(f"{action.label} failed, and the add-on it belongs to was turned off") from None
    if not isinstance(result, Proposal):
        store.plugins.disable(plugin, f"action {name} returned something other than a Proposal")
        raise ActionFailed(f"{action.label} failed, and the add-on it belongs to was turned off")
    try:
        pending = _checked(store, cfg, plugin, name, record, choices, result)
    except StoreError as err:
        raise ActionFailed(f"{action.label} proposed something that can't apply: {err}") from None
    store.plugins.proposals.put(pending, cfg.workspace.plugins.actions.keep_minutes)
    return pending


def _checked(
    store: Store, cfg: Config, plugin: str, name: str, record: Any, choices: dict[str, Any], result: Any
) -> Pending:
    from engine.files import check_file, store_blob

    limits = cfg.workspace.plugins.actions
    summary = " ".join(str(result.summary).split())
    if not summary or len(summary) > 500:
        raise StoreError("the summary must be one line of up to 500 characters")
    choice_list = []
    for c in result.choices:
        options = [{"value": str(v), "label": str(label)} for v, label in c.options]
        choice_list.append({"id": c.id, "label": c.label, "value": c.value, "options": options, "help": c.help})
    offered = {c["id"]: c for c in choice_list}
    for key, value in choices.items():
        choice = offered.get(key)
        if choice is None:
            raise StoreError(f"there is no choice called {key}")
        valid = {o["value"] for o in choice["options"]} if choice["options"] else {True, False}
        if (str(value) if choice["options"] else value) not in valid:
            raise StoreError(f"{value!r} isn't one of the options for {choice['label']}")
    for c in choice_list:
        allowed = {o["value"] for o in c["options"]}
        if allowed and str(c["value"]) not in allowed:
            raise StoreError(f"choice {c['id']} is set to a value it doesn't offer")
        if not allowed and not isinstance(c["value"], bool):
            raise StoreError(f"choice {c['id']} without options must be on or off")
    if len(result.previews) > limits.max_previews:
        raise StoreError(f"more than {limits.max_previews} previews")
    previews = []
    for p in result.previews:
        if p.media_type not in PREVIEW_TYPES:
            raise StoreError(f"previews can't be {p.media_type}")
        if not isinstance(p.data, bytes) or len(p.data) > limits.preview_mb * 1024 * 1024:
            raise StoreError(f"preview {p.name} is larger than {limits.preview_mb:g} MB")
        previews.append({"name": p.name, "media_type": p.media_type, "data": p.data, "caption": p.caption})
    view = store.read()
    files = []
    own_kinds = {"attachment", *store.plugins.registrars[plugin].file_kinds}
    for f in result.files:
        if f.file_kind not in own_kinds:
            raise StoreError(f"file kind {f.file_kind} isn't core or the add-on's own")
        if not isinstance(f.data, bytes):
            raise StoreError(f"{f.name} must be bytes")
        clean, details = check_file(
            store,
            cfg,
            view,
            name=f.name,
            media_type=f.media_type,
            size=len(f.data),
            file_kind=f.file_kind,
            meta=f.meta,
            project=f.project,
            replaces=f.replaces,
        )
        files.append(
            {
                "name": clean,
                "media_type": f.media_type,
                "size": len(f.data),
                "sha256": store_blob(store, f.data),
                "file_kind": f.file_kind,
                "project": f.project,
                "meta": details,
                "replaces": f.replaces,
            }
        )
    own_ops = set(store.plugins.registrars[plugin].ops)
    ops = []
    for op in result.ops:
        if not isinstance(op, dict) or op.get("op") not in ACTION_CORE_OPS | own_ops:
            shown = op.get("op") if isinstance(op, dict) else op
            raise StoreError(f"{shown} isn't an op an action may propose")
        ops.append(_placeholders_checked(op, len(files)))
    stand_ins = [f"FILE-{i + 1}" for i in range(len(files))]
    _validated([*_file_ops(files, stand_ins), *(_substituted(op, stand_ins) for op in ops)], store, summary)
    target = {"kind": record.kind, "id": record.id, "version": record.version} if record is not None else None
    keep = cfg.workspace.plugins.actions.keep_minutes
    return Pending(
        token=secrets.token_urlsafe(18),
        plugin=plugin,
        action=name,
        target=target,
        choices={c["id"]: c["value"] for c in choice_list},
        summary=summary,
        ops=ops,
        files=files,
        previews=previews,
        choice_list=choice_list,
        notes=[" ".join(str(n).split()) for n in result.notes],
        expires_at=datetime.fromtimestamp(time.time() + keep * 60, UTC).isoformat(),
    )


def _placeholders_checked(value: Any, count: int) -> Any:
    if isinstance(value, str) and value.startswith(_PLACEHOLDER):
        index = value[len(_PLACEHOLDER) :]
        if not index.isdigit() or int(index) >= count:
            raise StoreError(f"{value} doesn't name one of the proposal's files")
    elif isinstance(value, dict):
        return {k: _placeholders_checked(v, count) for k, v in value.items()}
    elif isinstance(value, list):
        return [_placeholders_checked(v, count) for v in value]
    return value


def _substituted(value: Any, ids: list[str]) -> Any:
    if isinstance(value, str) and value.startswith(_PLACEHOLDER):
        return ids[int(value[len(_PLACEHOLDER) :])]
    if isinstance(value, dict):
        return {k: _substituted(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [_substituted(v, ids) for v in value]
    return value


def _file_ops(files: list[dict[str, Any]], ids: list[str]) -> list[dict[str, Any]]:
    return [{"op": "file.add", "id": file_id, **f} for f, file_id in zip(files, ids, strict=True)]


def _validated(ops: list[dict[str, Any]], store: Store, summary: str) -> Any:
    try:
        return CHANGESET.validate_python({"summary": summary, "ops": ops}, context={"op_models": store.plugins.ops})
    except ValidationError as err:
        first = err.errors()[0]
        raise StoreError(f"{'.'.join(map(str, first['loc']))}: {first['msg']}") from None


def labels(store: Store, pending: Pending) -> list[dict[str, Any]]:
    """Each op the proposal would apply, with its one-line label, for the review."""
    from engine.applier import _label

    ids = [f"FILE-{i + 1}" for i in range(len(pending.files))]
    ops = [*_file_ops(pending.files, ids), *(_substituted(op, ids) for op in pending.ops)]
    parsed = _validated(ops, store, pending.summary).ops
    return [{"op": op.op, "label": _label(op) or _fallback_label(raw)} for op, raw in zip(parsed, ops, strict=True)]


def _fallback_label(op: dict[str, Any]) -> str:
    for key in ("text", "title", "answer", "full_name", "name"):
        if isinstance(op.get(key), str) and op[key].strip():
            return " ".join(op[key].split())[:200]
    return ""


def apply(store: Store, cfg: Config, token: str) -> str:
    """Apply exactly the proposal the person reviewed, as theirs. Returns the changeset id."""
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People

    pending = store.plugins.proposals.take(token, cfg.workspace.plugins.actions.keep_minutes)
    if not store.plugins.active(pending.plugin):
        raise StoreError("the add-on this action belongs to is turned off")
    if pending.target is not None:
        current = store.read().get(pending.target["kind"], pending.target["id"])
        if current is None or current.version != pending.target["version"]:
            raise StoreError("it changed since you reviewed it; run the action again")
    with store.transaction() as tx:
        ids = [tx.new_id("file") for _ in pending.files]
        request = tx.create(
            "request",
            {
                "task": pending.action,
                "origin": "pm",
                "state": "done",
                "note": pending.summary,
                "created_at": store.clock(),
            },
            WriteContext("pm", "trusted", "action.request"),
        )
    ops = [*_file_ops(pending.files, ids), *(_substituted(op, ids) for op in pending.ops)]
    changeset = _validated(ops, store, pending.summary)
    allowed = tuple(sorted(ACTION_CORE_OPS | {"file.add"} | set(store.plugins.registrars[pending.plugin].ops)))
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        allowed,
        Inputs(request.id, None, "", "", "trusted"),
        confirmed_by_pm=True,
        actor="pm",
    )
    action = {"name": pending.action, "target": pending.target, "choices": pending.choices}
    cs_id = apply_changeset(changeset, [], ctx, run=None, extra={"action": action, "reviewed": True})
    with store.transaction() as tx:
        current = tx.get("request", request.id)
        tx.update(
            "request",
            request.id,
            {"changeset": cs_id},
            WriteContext("engine", "trusted", "action.request"),
            read_version=current.version,
        )
    return cs_id
