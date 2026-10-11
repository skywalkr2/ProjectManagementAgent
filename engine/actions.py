"""Person actions (plugin API 0.3): deterministic work a person starts on a record, a file or the workspace.

Running an action gives one proposal for one review: the ops it would apply, the files it made, previews and named
choices, and items the person keeps or drops without a rerun. Flipping a choice runs the action again, and the person's
ticks carry over to items that came back unchanged. The person approves exactly what they reviewed: the proposal is kept
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
from engine.texts import text_presence

#: What a preview may be: pictures and plain text, never markup or anything that runs.
PREVIEW_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "text/plain"}
#: Core ops an action may propose. Ops that must cite evidence need an input to quote, which an action doesn't have;
#: file.add is the host's own, made from the proposal's files.
ACTION_CORE_OPS = frozenset(OP_MODELS) - NEEDS_EVIDENCE - {"file.add", "text.accept", "text.discard", "text.draft"}
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
    items: list[dict[str, Any]] = field(default_factory=list)  # id, label, group, kept, ops
    groups: list[dict[str, Any]] = field(default_factory=list)  # id, heading, explanation
    all_or_nothing: bool = False
    requests: list[dict[str, Any]] = field(default_factory=list)  # task, about {kind, id} or None, note
    problems: list[str] = field(default_factory=list)  # why ops outside the items would be refused, if applied now
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

    def peek(self, token: str, keep_minutes: float) -> Pending | None:
        self._prune(keep_minutes)
        return self._items.get(token)

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
    view = store.read()
    target = view.get(kind, record_id) if kind and record_id else None
    found = []
    for name, registrar in store.plugins.registrars.items():
        if not store.plugins.active(name):
            continue
        for action in registrar.actions.values():
            if action.on != kind:
                continue
            if action.file_kinds and (target is None or target.data.get("file_kind") not in action.file_kinds):
                continue
            if action.where and (target is None or not action.offered_on(target, text_presence(store, view, target))):
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
    *,
    previous: str | None = None,
    kept: dict[str, bool] | None = None,
) -> Pending:
    """Run an action and keep its proposal for the person's review. `previous` is the review this one replaces (after a
    choice changed): its ticks carry over to items with the same id and the same ops. `kept` then sets ticks by item
    id."""
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
        from engine.records import kind_label

        what = kind_label(store.plugins.records.get(action.on), action.on)
        if target is None or target.get("kind") != action.on:
            raise StoreError(f"{action.label} works on a {what}")
        record = view.get(action.on, target["id"])
        if record is None:
            raise StoreError(f"there is no {what} {target['id']}")
        if action.file_kinds and record.data.get("file_kind") not in action.file_kinds:
            raise StoreError(f"{action.label} doesn't work on this kind of file")
        if not action.offered_on(record, text_presence(store, view, record)):
            raise StoreError(f"{action.label} isn't for this {what}")
    registrar = store.plugins.registrars[plugin]
    actions, files = cfg.workspace.plugins.actions, cfg.storage.files
    limits = {
        "max_items": actions.max_items,
        "max_requests": actions.max_requests,
        "max_previews": actions.max_previews,
        "preview_mb": actions.preview_mb,
        "keep_minutes": actions.keep_minutes,
        "max_file_mb": files.max_file_mb,
        "max_total_mb": files.max_total_mb,
        "room_mb": max(0.0, files.max_total_mb - sum(f.data["size"] for f in view.list("file")) / (1024 * 1024)),
        "accepted_types": list(files.accepted_types),
    }
    context = store.plugins._with_files(
        ActionContext(view, plugin, registrar.config, store.plugins.tool_box(plugin), limits, now=_workspace_now(cfg))
    )
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
    _trial(store, cfg, pending)
    keep = cfg.workspace.plugins.actions.keep_minutes
    before = store.plugins.proposals.peek(previous, keep) if previous else None
    if before is not None and before.action == name and before.target == pending.target:
        ticks = {i["id"]: i for i in before.items}
        for item in pending.items:
            old = ticks.get(item["id"])
            if old is not None and old["ops"] == item["ops"]:
                item["kept"] = old["kept"]
    _tick(pending, kept or {})
    store.plugins.proposals.put(pending, keep)
    return pending


def _trial(store: Store, cfg: Config, pending: Pending) -> None:
    """Try the whole proposal without keeping anything, and mark what would be refused: an item gets its reason and
    starts dropped; anything else is listed in `problems`. The person can then change a choice instead."""
    from engine.applier import refusals

    first = store.read().sequences().get("file", 1)
    ids = [f"FILE-{first + i}" for i in range(len(pending.files))]
    in_items = [op for item in pending.items for op in item["ops"]]
    ops = [*_file_ops(pending.files, ids), *(_substituted(op, ids) for op in [*pending.ops, *in_items])]
    found = refusals(_validated(ops, store, pending.summary), _person_context(store, cfg, pending.plugin, ""))
    start = len(pending.files) + len(pending.ops)
    pending.problems = list(dict.fromkeys(found[i] for i in range(start) if i in found))
    at = start
    for item in pending.items:
        reasons = [found[i] for i in range(at, at + len(item["ops"])) if i in found]
        at += len(item["ops"])
        item["refused"] = "; ".join(dict.fromkeys(reasons)) or None
        if reasons:
            item["kept"] = False


def _person_context(store: Store, cfg: Config, plugin: str, request_id: str) -> Any:
    """The applier's context for a proposal the person applies as their own."""
    from engine.applier import Context, Inputs
    from engine.names import People

    allowed = tuple(sorted(ACTION_CORE_OPS | {"file.add"} | set(store.plugins.registrars[plugin].ops)))
    return Context(
        store,
        cfg,
        People(store, cfg),
        allowed,
        Inputs(request_id, None, "", "", "trusted"),
        confirmed_by_pm=True,
        actor="pm",
    )


def _workspace_now(cfg: Config) -> datetime:
    """Now, in the workspace's time zone (UTC when it names none this computer knows)."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        zone = ZoneInfo(cfg.workspace.user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = UTC
    return datetime.now(zone)


def _tick(pending: Pending, kept: dict[str, bool]) -> None:
    items = {i["id"]: i for i in pending.items}
    for item_id, value in kept.items():
        if item_id not in items:
            raise StoreError(f"there is no item {item_id} in this review")
        if not isinstance(value, bool):
            raise StoreError("an item is kept or dropped: true or false")
        items[item_id]["kept"] = value


def _tick_requests(pending: Pending, kept: dict[str, bool]) -> None:
    requests = {r["id"]: r for r in pending.requests}
    for request_id, value in kept.items():
        if request_id not in requests:
            raise StoreError(f"there is no request {request_id} in this review")
        if not isinstance(value, bool):
            raise StoreError("a request is kept or dropped: true or false")
        requests[request_id]["kept"] = value


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
        choice_list.append(
            {
                "id": c.id,
                "label": c.label,
                "value": c.value,
                "options": options,
                "help": c.help,
                "group": c.group,
                "text": bool(c.text),
                "max_length": int(c.max_length),
            }
        )
    groups = []
    for g in result.groups:
        if not str(g.id) or not " ".join(str(g.heading).split()):
            raise StoreError("every group needs an id and a heading")
        groups.append({"id": str(g.id), "heading": " ".join(str(g.heading).split()), "explanation": g.explanation})
    group_ids = [g["id"] for g in groups]
    if len(group_ids) != len(set(group_ids)):
        raise StoreError("group ids must be unique")
    if len({c["id"] for c in choice_list}) != len(choice_list):
        raise StoreError("choice ids must be unique")
    for c in choice_list:
        if c["group"] is not None and c["group"] not in group_ids:
            raise StoreError(f"choice {c['id']} is in a group the proposal doesn't list")
    # The proposal's own choices are what stands: a choice the run no longer offers is dropped, and one whose earlier
    # value it no longer offers shows the value the action fell back to.
    for c in choice_list:
        if c["text"]:
            if c["options"] or not isinstance(c["value"], str):
                raise StoreError(f"text choice {c['id']} has a text value and no options")
            if not 1 <= c["max_length"] <= 2000 or len(c["value"]) > c["max_length"]:
                raise StoreError(f"choice {c['id']} is longer than {c['max_length']} characters")
            continue
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
        previews.append(
            {
                "name": p.name,
                "media_type": p.media_type,
                "data": p.data,
                "caption": p.caption,
                "alt": p.alt or p.caption,
            }
        )
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
    total = cfg.storage.files.max_total_mb
    if sum(f["size"] for f in files) + sum(f.data["size"] for f in view.list("file")) > total * 1024 * 1024:
        raise StoreError(f"these files together would go over the {total:g} MB limit for all files")
    own_ops = set(store.plugins.registrars[plugin].ops)

    def proposed(op: Any) -> dict[str, Any]:
        if not isinstance(op, dict) or op.get("op") not in ACTION_CORE_OPS | own_ops:
            shown = op.get("op") if isinstance(op, dict) else op
            raise StoreError(f"{shown} isn't an op an action may propose")
        return _placeholders_checked(op, len(files))

    ops = [proposed(op) for op in result.ops]
    if len(result.items) > limits.max_items:
        raise StoreError(f"more than {limits.max_items} items")
    items = []
    for item in result.items:
        label = " ".join(str(item.label).split())
        if not str(item.id) or not label or not item.ops:
            raise StoreError("every item needs an id, a label and at least one op")
        if item.group is not None and item.group not in group_ids:
            raise StoreError(f"item {item.id} is in a group the proposal doesn't list")
        # An item's ops apply and undo together.
        item_ops = [{"group": f"item:{item.id}", **proposed(op)} for op in item.ops]
        items.append(
            {"id": str(item.id), "label": label[:200], "group": item.group, "kept": bool(item.kept), "ops": item_ops}
        )
    if len({i["id"] for i in items}) != len(items):
        raise StoreError("item ids must be unique")
    stand_ins = [f"FILE-{i + 1}" for i in range(len(files))]
    every = [*ops, *(op for i in items for op in i["ops"])]
    _validated([*_file_ops(files, stand_ins), *(_substituted(op, stand_ins) for op in every)], store, summary)
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
        items=items,
        groups=groups,
        all_or_nothing=bool(result.all_or_nothing),
        requests=_requests_checked(store, plugin, result.requests, ops, {i["id"] for i in items}, set(group_ids)),
        expires_at=datetime.fromtimestamp(time.time() + keep * 60, UTC).isoformat(),
    )


def _resolved(store: Store, pending: Pending, cs_id: str) -> list[dict[str, Any]]:
    """The proposal's requests with any about a record it created pointing at that record; one whose op wasn't
    applied, or whose item was dropped, is left out."""
    outcomes = store.read().get("changeset", cs_id).data["ops"]
    first_item_op, at = {}, len(pending.files) + len(pending.ops)
    for item in pending.items:
        if item["kept"]:
            first_item_op[item["id"]] = (at, at + len(item["ops"]))
            at += len(item["ops"])
    found = []
    for request in pending.requests:
        if not request.get("kept", True):
            continue
        about = request["about"]
        if not about or ("op" not in about and "item" not in about):
            found.append(request)
            continue
        if "op" in about:
            span = (len(pending.files) + about["op"], len(pending.files) + about["op"] + 1)
        elif about["item"] in first_item_op:
            span = first_item_op[about["item"]]
        else:
            continue
        on = store.plugins.task_kind(request["task"]).on
        made = [
            record
            for outcome in outcomes[span[0] : span[1]]
            if outcome["status"] == "applied"
            for record in outcome.get("records", [])
            if record["kind"] == on
        ]
        if made:
            found.append({**request, "about": {"kind": made[0]["kind"], "id": made[0]["id"]}})
    return found


def _queue(store: Store, cfg: Config, requests: list[dict[str, Any]]) -> None:
    """Queue an applied proposal's requests, each waiting for the person's go."""
    from engine.stages import wording

    with store.transaction() as tx:
        for r in requests:
            tx.create(
                "request",
                {
                    "task": r["task"],
                    "about": r["about"],
                    "note": r["note"] or None,
                    "part": r.get("part"),
                    "origin": "pm",
                    "state": "needs_you",
                    "approval": "required",
                    "waiting": wording(cfg, "waiting"),
                    "created_at": store.clock(),
                },
                WriteContext("pm", "trusted", "action.request"),
            )


def _requests_checked(
    store: Store,
    plugin: str,
    requests: list[Any],
    ops: list[Any] = (),
    items: set[str] = frozenset(),
    groups: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    """A proposal's requests, each naming one of the plugin's own task kinds and a record it may work on, with an id
    for the review, kept unless the person drops it, and the `group` it belongs to, if any."""
    from engine.plugin_host import check_about
    from engine.texts import check_part

    limit = store.plugins.cfg.workspace.plugins.actions.max_requests
    if len(requests) > limit:
        raise StoreError(f"more than {limit} requests: an action may queue at most that many at once")
    checked = []
    view = store.read()
    for r in requests:
        if not isinstance(r, dict) or not isinstance(r.get("task"), str):
            raise StoreError("a request to queue names a task kind")
        task = r["task"]
        if task not in store.plugins.registrars[plugin].tasks:
            raise StoreError(f"{task} isn't one of this plugin's task kinds")
        about = r.get("about")
        if isinstance(about, (list, tuple)):
            about = {"kind": about[0], "id": about[1]}
        kind = store.plugins.task_kind(task)
        if isinstance(about, dict) and ("op" in about or "item" in about):
            # A record this proposal creates: resolved when it applies, and dropped with its item.
            if kind.on is None:
                raise StoreError(f"{task} doesn't work on a record")
            if "op" in about and not (isinstance(about["op"], int) and 0 <= about["op"] < len(ops)):
                raise StoreError(f"a request names op {about.get('op')}, which the proposal doesn't have")
            if "item" in about and about["item"] not in items:
                raise StoreError(f"a request names item {about.get('item')}, which the proposal doesn't have")
            about = {k: about[k] for k in ("op", "item") if k in about}
        else:
            check_about(view, kind, about, store)
        try:
            part = check_part(store.plugins.task_kind(task), r.get("part"))
        except ValueError as err:
            raise StoreError(str(err)) from None
        note = " ".join(str(r.get("note", "")).split())[:2000]
        group = r.get("group")
        if group is not None and group not in groups:
            raise StoreError(f"a request names group {group}, which the proposal doesn't have")
        checked.append(
            {
                "id": f"r{len(checked) + 1}",
                "task": task,
                "about": about,
                "note": note,
                "part": part,
                "kept": True,
                "group": group,
            }
        )
    return checked


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


def to_apply(pending: Pending, ids: list[str]) -> list[dict[str, Any]]:
    """Every op that applies with the ticks as they are: the files, the proposal's own ops, then kept items' ops."""
    kept = [op for item in pending.items if item["kept"] for op in item["ops"]]
    return [*_file_ops(pending.files, ids), *(_substituted(op, ids) for op in [*pending.ops, *kept])]


def labels(store: Store, pending: Pending, ops: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Each op with its one-line label, for the review: by default everything that applies with the current ticks."""
    from engine.applier import _label

    ids = [f"FILE-{i + 1}" for i in range(len(pending.files))]
    ops = to_apply(pending, ids) if ops is None else [_substituted(op, ids) for op in ops]
    parsed = _validated(ops, store, pending.summary).ops
    view = store.read()
    return [
        {"op": op.op, "label": _label(op, view, store) or _fallback_label(raw)}
        for op, raw in zip(parsed, ops, strict=True)
    ]


def _fallback_label(op: dict[str, Any]) -> str:
    for key in ("text", "title", "answer", "full_name", "name"):
        if isinstance(op.get(key), str) and op[key].strip():
            return " ".join(op[key].split())[:200]
    return ""


def apply(
    store: Store,
    cfg: Config,
    token: str,
    kept: dict[str, bool] | None = None,
    kept_requests: dict[str, bool] | None = None,
) -> str:
    """Apply exactly the proposal the person reviewed, as theirs, with their final ticks (`kept`, by item id, and
    `kept_requests`, by request id). Returns the changeset id."""
    from engine.applier import apply_changeset

    keep = cfg.workspace.plugins.actions.keep_minutes
    pending = store.plugins.proposals.take(token, keep)
    try:
        _tick(pending, kept or {})
        _tick_requests(pending, kept_requests or {})
    except StoreError:
        store.plugins.proposals.put(pending, keep)
        raise
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
    changeset = _validated(to_apply(pending, ids), store, pending.summary)
    ctx = _person_context(store, cfg, pending.plugin, request.id)
    action = {
        "name": pending.action,
        "target": pending.target,
        "choices": pending.choices,
        "kept": [i["id"] for i in pending.items if i["kept"]],
        "dropped": [i["id"] for i in pending.items if not i["kept"]],
    }
    cs_id = apply_changeset(
        changeset,
        [],
        ctx,
        run=None,
        extra={"action": action, "reviewed": True},
        all_or_nothing=pending.all_or_nothing,
    )
    if pending.requests and store.read().get("changeset", cs_id).data["status"] != "rejected":
        _queue(store, cfg, _resolved(store, pending, cs_id))
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
