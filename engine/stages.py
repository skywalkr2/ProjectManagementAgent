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
        raise StoreError("stage.move: record does not exist")
    if record.version != op.read_version:
        raise StoreError("stage.move: record changed since it was read")
    settings = store.plugins.stages.types.get(record.kind)
    target = next((s for s in settings.stages if s.id == op.to), None) if settings else None
    if target is None:
        raise StoreError(f"stage.move: unknown stage {op.to}")
    if record.data.get("stage") == op.to:
        raise StoreError("stage.move: record is already in that stage")
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
    tx.update(record.kind, record.id, {"stage": target.id}, context, read_version=op.read_version)
    return [{"kind": record.kind, "id": record.id}]
