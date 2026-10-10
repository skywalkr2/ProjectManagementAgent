"""Deterministic stage entry checks; neither code checks nor rules dispatch AI."""

from engine.config.schema import STAGE_WORDING
from engine.plugin_api import StageCheckResult


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


def record_status(store, record, view=None):
    """The next configured stage and every deterministic entry-check result."""
    settings = store.plugins.stages.types.get(record.kind)
    stages = settings.stages if settings else []
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
    return {
        "record": {"kind": record.kind, "id": record.id},
        "version": record.version,
        "current": current,
        "current_label": next((s.label for s in stages if s.id == current), None),
        "next": None if target is None else {"id": target.id, "label": target.label},
        "checks": checks,
        "ready": target is not None and all(c["passed"] for c in checks),
    }


def validate_move(store, op, view):
    from engine.storage import StoreError

    record = view.get(op.record.kind, op.record.id)
    if record is None:
        raise StoreError(wording(store.plugins.cfg, "record_missing"))
    if record.version != op.read_version:
        raise StoreError(wording(store.plugins.cfg, "record_changed"))
    settings = store.plugins.stages.types.get(record.kind)
    target = next((s for s in settings.stages if s.id == op.to), None) if settings else None
    if target is None:
        raise StoreError(wording(store.plugins.cfg, "stage_unknown").format(stage=op.to))
    if record.data.get("stage") == op.to:
        raise StoreError(wording(store.plugins.cfg, "stage_same"))
    checks = [(check, entry_check(store, check, record, view)) for check in target.entry]
    failed = [f"{check}: {result.reason}" for check, result in checks if not result.passed]
    if failed:
        raise StoreError("; ".join(failed))
    return record, target


def apply_move(store, tx, op, context):
    """Called only by the applier, inside its ledger transaction."""
    from engine.storage import StoreError

    if context.actor not in ("pm", "rule"):
        raise StoreError(wording(store.plugins.cfg, "confirm"))
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
    for task in dict.fromkeys(target.starts):
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
        for record in store.read().list(kind):
            status = record_status(store, record)
            if not status["ready"]:
                continue
            op = StageMoveOp(record=status["record"], to=status["next"]["id"], read_version=record.version)
            try:
                moved.append(move_stage(store, op, actor="rule"))
            except StoreError:
                # Another writer or changed entry check leaves the record for a later pass.
                continue
    return moved


def approve_stage_request(store, request_id, read_version):
    """The person's go. Cost control must insert estimates and budget authorization here before granting approval.

    Keep the stage provenance on the request so future cost limits can charge both
    its task kind and its originating record. No AI work runs before this gate.
    """
    from engine.storage import StoreError, WriteContext

    with store.transaction() as tx:
        request = tx.get("request", request_id)
        if request is None or not request.data.get("stage_start") or request.data.get("approval") != "required":
            raise StoreError(wording(store.plugins.cfg, "not_waiting"))
        if request.version != read_version or request.data["state"] != "needs_you":
            raise StoreError(wording(store.plugins.cfg, "request_changed"))
        origin = request.data["stage_start"]
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
