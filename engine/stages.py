"""Deterministic stage entry checks; neither code checks nor rules dispatch AI."""

import logging

from engine.config.schema import STAGE_WORDING
from engine.plugin_api import StageCheckResult

log = logging.getLogger(__name__)


def wording(cfg, key):
    return cfg.stages.wording.get(key, STAGE_WORDING[key])


def entry_check(store, check_id, record, view=None):
    cfg = store.plugins.cfg
    rules = {rule.id: rule for rule in cfg.rules.rules}
    rule = rules.get(check_id)
    if rule is None:
        return store.plugins.stage_check(check_id, record, view)
    if rule.status != "active":
        return StageCheckResult(False, wording(cfg, "rule_inactive"))
    scope = rule.applies_to
    if (
        scope.records
        and not any(record.kind == target or target.startswith(record.kind + ".") for target in scope.records)
    ) or any(record.data.get(key) != value for key, value in scope.filter.items()):
        return StageCheckResult(False, wording(cfg, "rule_scope"))
    if rule.check is None:
        return StageCheckResult(False, wording(cfg, "rule_prose"))
    result = store.plugins.stage_check(rule.check, record, view)
    return StageCheckResult(result.passed, f"{rule.text}: {result.reason}" if rule.text else result.reason)


def record_title(record):
    """The item's display name: its name, else its title, else its text, else its id."""
    for key in ("name", "title", "text"):
        value = record.data.get(key)
        if isinstance(value, str) and value.strip():
            # A sentence used as a title drops its final period, so it reads inside "<title> is ready for ...".
            title = value.strip()
            return title[:-1].rstrip() if title.endswith(".") and not title.endswith("..") else title
    return record.id


def record_status(store, record, view=None):
    """The next configured stage and every deterministic entry-check result."""
    settings = store.plugins.stages.types.get(record.kind)
    stages = (settings.stages or []) if settings else []
    current = record.data.get("stage")
    ids = [stage.id for stage in stages]
    # Removed stages remain data and history. Never guess a successor for them.
    index = -1 if current is None else (ids.index(current) if current in ids else len(stages))
    target = stages[index + 1] if index + 1 < len(stages) else None
    checks = (
        []
        if target is None
        else [{"id": check, **vars(entry_check(store, check, record, view))} for check in target.entry]
    )
    if "/" in record.kind and not store.plugins.active(record.kind.split("/")[0]):
        checks.append(
            {"id": "plugin-active", "passed": False, "reason": wording(store.plugins.cfg, "type_unavailable")}
        )
    return {
        "record": {"kind": record.kind, "id": record.id},
        "title": record_title(record),
        "version": record.version,
        "current": current,
        "current_label": next((s.label for s in stages if s.id == current), None),
        "next": None if target is None else {"id": target.id, "label": target.label},
        "stages": [{"id": stage.id, "label": stage.label} for stage in stages],
        "checks": checks,
        "ready": target is not None and all(c["passed"] for c in checks),
    }


def validate_move(store, op, view):
    from engine.storage import StoreError

    record = view.get(op.record.kind, op.record.id)
    if record is None:
        raise StoreError(wording(store.plugins.cfg, "record_missing"))
    if "/" in record.kind and not store.plugins.active(record.kind.split("/")[0]):
        raise StoreError(wording(store.plugins.cfg, "type_unavailable"))
    if record.version != op.read_version:
        raise StoreError(wording(store.plugins.cfg, "record_changed"))
    settings = store.plugins.stages.types.get(record.kind)
    stages = (settings.stages or []) if settings else []
    ids = [stage.id for stage in stages]
    if op.to not in ids:
        raise StoreError(wording(store.plugins.cfg, "stage_unknown").format(stage=op.to))
    target = stages[ids.index(op.to)]
    current = record.data.get("stage")
    if current == op.to:
        raise StoreError(wording(store.plugins.cfg, "stage_same"))
    # An item not yet in a stage (or in one config removed) may start at any stage whose entry checks pass,
    # so work already under way can be brought in where it is.
    here = ids.index(current) if current in ids else None
    if here is not None and ids.index(op.to) < here:
        # Moving back needs no entry checks: the record already passed them on the way forward.
        return record, target
    if here is not None and ids.index(op.to) != here + 1:
        raise StoreError(wording(store.plugins.cfg, "stage_skip"))
    failed = [
        result.reason for result in (entry_check(store, c, record, view) for c in target.entry) if not result.passed
    ]
    if failed:
        raise StoreError("; ".join(failed))
    return record, target


def apply_move(store, tx, op, context):
    """Called only by the applier, inside its ledger transaction."""
    from engine.storage import StoreError

    if context.actor not in ("pm", "rule"):
        raise StoreError(wording(store.plugins.cfg, "confirm"))
    origin = {"actor": context.actor, "trust": context.trust, "via": "screen" if context.actor == "pm" else "rule"}
    refusals = store.plugins.validators(op, view=tx, origin=origin)
    if refusals:
        raise StoreError("; ".join(refusals))
    record, target = validate_move(store, op, tx)
    if context.actor == "rule":
        settings = store.plugins.stages.types[record.kind]
        status = record_status(store, record, tx)
        if (
            (settings.moves or store.plugins.stages.moves) != "rule"
            or not status["ready"]
            or status["next"]["id"] != target.id
        ):
            raise StoreError(wording(store.plugins.cfg, "person_required"))
    tx.update(record.kind, record.id, {"stage": target.id}, context, read_version=op.read_version)
    touched = [{"kind": record.kind, "id": record.id}]
    pending = {}
    for request in tx.list("request"):
        origin = request.data.get("stage_start")
        if not origin or origin["record"] != record.id or origin["kind"] != record.kind:
            continue
        if request.data["state"] != "needs_you" or request.data.get("approval") != "required":
            continue
        if origin["stage"] == target.id:
            pending[request.data["task"]] = request
        else:
            # Left before the go: close it in this changeset, so Undo of the move reopens it.
            tx.update(
                "request",
                request.id,
                {"state": "done", "waiting": wording(store.plugins.cfg, "stage_left_before_go")},
                context,
                read_version=request.version,
            )
            touched.append({"kind": "request", "id": request.id})
    for task in dict.fromkeys(target.starts):
        if task in pending:
            continue
        store.plugins.task_kind(task)
        request = tx.create(
            "request",
            {
                "task": task,
                "origin": "schedule",
                "state": "needs_you",
                "approval": "required",
                "stage_start": {
                    "kind": record.kind,
                    "record": record.id,
                    "stage": target.id,
                    "changeset": context.changeset,
                },
                "waiting": wording(store.plugins.cfg, "waiting"),
                "created_at": store.clock(),
            },
            context,
        )
        touched.append({"kind": "request", "id": request.id})
    return touched


def move_ready_records(store):
    """One next-stage move per record per worker pass, without dispatching AI."""
    from engine.applier import move_stage
    from engine.ops import StageMoveOp
    from engine.storage import StoreError

    moved = []
    for kind, settings in store.plugins.stages.types.items():
        if (settings.moves or store.plugins.stages.moves) != "rule":
            continue
        if kind not in store.plugins.records or ("/" in kind and not store.plugins.active(kind.split("/")[0])):
            continue
        for record in store.read().list(kind):
            try:
                if held_back(store, record, settings.stages or []):
                    continue
                status = record_status(store, record)
                if not status["ready"]:
                    continue
                op = StageMoveOp(record=status["record"], to=status["next"]["id"], read_version=record.version)
                moved.append(move_stage(store, op, actor="rule"))
            except StoreError:
                # Another writer or changed entry check leaves the record for a later pass.
                continue
            except Exception:
                # One bad record must not stop the worker; it stays where it is and the next pass tries again.
                log.exception("Automatic stage move failed for %s %s", kind, record.id)
                continue
    return moved


def held_back(store, record, stages):
    """True when the person moved the record back (or undid a move): rules leave it until the person moves it on."""
    ids = [stage.id for stage in stages]
    for row in reversed(store.read().ledger(kind=record.kind, record_id=record.id)):
        if row["field"] != "stage" or row["before"] == row["after"]:
            continue
        if row["actor"] == "rule":
            return False

        def position(stage):
            return -1 if stage is None else ids.index(stage) if stage in ids else len(ids)

        return position(row["after"]) < position(row["before"])
    return False


def approve_stage_request(store, request_id, read_version):
    """The person's go. Cost control must insert estimates and budget authorization here before granting approval.

    Keep the stage provenance on the request so future cost limits can charge both
    its task kind and its originating record. No AI work runs before this gate.
    """
    from engine.storage import StoreError, WriteContext

    with store.transaction() as tx:
        request = tx.get("request", request_id)
        if request is None or request.data.get("approval") != "required":
            raise StoreError(wording(store.plugins.cfg, "not_waiting"))
        if request.version != read_version or request.data["state"] != "needs_you":
            raise StoreError(wording(store.plugins.cfg, "request_changed"))
        origin = request.data.get("stage_start")
        if origin:
            record = tx.get(origin["kind"], origin["record"])
            if record is None or record.data.get("stage") != origin["stage"]:
                raise StoreError(wording(store.plugins.cfg, "stage_left"))
        store.plugins.task_kind(request.data["task"])
        tx.update(
            "request",
            request_id,
            {"approval": "granted", "state": "queued", "waiting": None},
            WriteContext("pm", "trusted", "stage.task.approve"),
            read_version=read_version,
        )


def stage_history(store, kind, record_id):
    """History is a ledger query, including undo; no second history store can drift."""
    return [
        {
            "sequence": row["seq"],
            "at": row["at"],
            "from_stage": row["before"],
            "to_stage": row["after"],
            "version": row["version"],
            "actor": row["actor"],
            "op": row["op"],
            "changeset": row["changeset"],
            "request": row["request"],
            "source": row["evidence"],
        }
        for row in store.read().ledger(kind=kind, record_id=record_id)
        if row["field"] == "stage" and row["before"] != row["after"]
    ]
