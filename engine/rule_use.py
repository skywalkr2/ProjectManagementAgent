"""Whether a standing rule applied to a run, or was only present (design 6.22).

A run's knowledge log lists the rules it was given. Each is **applied** when the run's changeset has an op of a kind the
rule constrains or sets a field it constrains, when the check the rule names ran on the output (it runs on every
output the rule's scope covers, holding or not), or when a later
correction names the rule; otherwise it is **present**. All of this is decided from records and never by asking the
model, and the model's own claim that it followed a rule is never counted.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import Any

from engine.config.schema import RuleScope
from engine.records import Rule
from engine.stages import covers, output_check_ran
from engine.storage import WriteContext

_ENGINE = WriteContext(actor="engine", trust="trusted", op="run.knowledge")

#: The name a change's problem carries when an active rule's check fails on what the change would write.
RULE_CHECK = "rule-check"


def _scope(data: dict[str, Any]) -> RuleScope:
    return RuleScope.model_validate(
        {k: v for k, v in (data.get("applies_to") or {}).items() if k in RuleScope.model_fields}
    )


def failing_rules(store: Any, view: Any, task: str | None, records: Iterable[Any]) -> list[tuple[Any, str]]:
    """Each active rule with a code check whose scope covers one of `records` (as they are in `view`) and the task
    kind, and whose check fails on it: (the rule record, the check's reason). One entry per rule, for the first record
    it fails on. A check that is missing or turned off fails, as a stage entry check does."""
    written = list(records)
    found: list[tuple[Any, str]] = []
    if not written:
        return found
    for rule in view.list("rule"):
        data = rule.data
        if data.get("status") != "active" or not data.get("check"):
            continue
        scope = _scope(data)
        if scope.task_kinds and task not in scope.task_kinds:
            continue
        for record in written:
            if not covers(scope, record):
                continue
            result = store.plugins.stage_check(data["check"], record, view)
            if not result.passed:
                found.append((rule, result.reason))
                break
    return found


def _set(value: Any) -> bool:
    return value not in (None, "", [], {})


def constrained_by_ops(constrains: Iterable[str], ops: Iterable[dict[str, Any]]) -> bool:
    """Whether some op is of a kind in `constrains` (`question.add`) or sets a field in it (`action.add.owners`)."""
    wanted = list(constrains)
    for op in ops:
        kind = op.get("op", "")
        for item in wanted:
            if item == kind:
                return True
            if kind and item.startswith(kind + ".") and _set(op.get(item[len(kind) + 1 :])):
                return True
    return False


def applied_by(rule: Any, ops: Iterable[dict[str, Any]], checks_ran: Collection[str] = ()) -> bool:
    """Whether a rule record applied to an output: its constrained ops or fields are there, or its check ran on it."""
    data = rule.data
    if data.get("check") and data["check"] in checks_ran:
        return True
    return constrained_by_ops(data.get("constrains") or [], ops)


def _mark(tx: Any, run_id: str, rule_ids: Iterable[str]) -> list[str]:
    """Move rules the run was given from present to applied on its knowledge log. Returns the ones moved."""
    run = tx.get("run", run_id)
    if run is None or not run.data.get("knowledge"):
        return []
    log = dict(run.data["knowledge"])
    given, applied = log.get("given", []), log.get("rules_applied", [])
    fresh = [r for r in dict.fromkeys(rule_ids) if r in given and r not in applied]
    if not fresh:
        return []
    log["rules_applied"] = [*applied, *fresh]
    log["rules_present"] = [r for r in log.get("rules_present", []) if r not in fresh]
    tx.update("run", run_id, {"knowledge": log}, _ENGINE, read_version=run.version)
    return fresh


def _written(view: Any, changeset: Any) -> list[Any]:
    """The records a changeset's applied ops wrote, as they are now. A record that is gone is left out."""
    seen: dict[tuple[str, str], Any] = {}
    for outcome in changeset.data.get("ops", []):
        if outcome.get("status") != "applied":
            continue
        for ref in outcome.get("records") or []:
            key = (ref.get("kind", ""), ref.get("id", ""))
            if key not in seen and key[0] and key[1]:
                found = view.get(*key)
                seen[key] = found if found is not None and not found.deleted else None
    return [r for r in seen.values() if r is not None]


def record_applied(store: Any, run_id: str, changeset_id: str, checks_ran: Collection[str] = ()) -> list[str]:
    """After a run's changeset is applied: mark each rule the run was given that its ops, or a check that ran on its
    output, show applied. A rule's code check runs on the records the changeset wrote when the rule's scope covers
    them (engine/stages.py), and the rule counts as applied whether the check held or not. `checks_ran` adds names
    of checks a caller knows ran on the output. A rule whose check held or refused one of the changeset's ops before it
    applied counts as applied too. Returns the rule ids marked."""
    view = store.read()
    run, changeset = view.get("run", run_id), view.get("changeset", changeset_id)
    if run is None or changeset is None or not run.data.get("knowledge"):
        return []
    ops = [o.get("op") or {} for o in changeset.data.get("ops", [])]
    stopped = {
        p.get("rule")
        for o in changeset.data.get("ops", [])
        for p in o.get("problems") or []
        if p.get("check") == RULE_CHECK
    }
    request = view.get("request", changeset.data.get("request") or "")
    task = request.data.get("task") if request is not None else None
    written = None
    shown = []
    for rule_id in run.data["knowledge"].get("given", []):
        if not rule_id.startswith(f"{Rule.prefix}-"):
            continue
        rule = view.get("rule", rule_id)
        if rule is None or rule.data.get("status") != "active":
            continue
        ran = set(checks_ran)
        if rule_id in stopped:
            ran.add(rule.data.get("check") or RULE_CHECK)
        elif rule.data.get("check") and rule.data["check"] not in ran:
            written = _written(view, changeset) if written is None else written
            if output_check_ran(store, rule.data["check"], _scope(rule.data), task, written, view):
                ran.add(rule.data["check"])
        if applied_by(rule, ops, ran):
            shown.append(rule_id)
    with store.transaction() as tx:
        return _mark(tx, run_id, shown)


def record_named(tx: Any, run_id: str | None, refs: Iterable[str]) -> list[str]:
    """When a correction of a run's work names rules in `refs`, count each the run was given as applied on that run."""
    if run_id is None:
        return []
    return _mark(tx, run_id, [r for r in refs if r.startswith(f"{Rule.prefix}-")])
