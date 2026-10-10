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
