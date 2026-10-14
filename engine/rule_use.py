"""Whether a standing rule applied to a run, or was only present (design 6.22).

A run's knowledge log lists the rules it was given. Each is **applied** when the run's changeset has an op of a kind the
rule constrains or sets a field it constrains, when the check the rule names ran on the output, or when a later
correction names the rule; otherwise it is **present**. All of this is decided from records and never by asking the
model, and the model's own claim that it followed a rule is never counted.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import Any

from engine.records import Rule
from engine.storage import WriteContext

_ENGINE = WriteContext(actor="engine", trust="trusted", op="run.knowledge")


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


def record_applied(store: Any, run_id: str, changeset_id: str, checks_ran: Collection[str] = ()) -> list[str]:
    """After a run's changeset is applied: mark each rule the run was given that its ops, or a check that ran on its
    output, show applied. `checks_ran` is the names of the checks that ran on the output; no check runs on a run's
    output today, so callers leave it empty. Returns the rule ids marked."""
    with store.transaction() as tx:
        run = tx.get("run", run_id)
        changeset = tx.get("changeset", changeset_id)
        if run is None or changeset is None or not run.data.get("knowledge"):
            return []
        ops = [o.get("op") or {} for o in changeset.data.get("ops", [])]
        shown = []
        for rule_id in run.data["knowledge"].get("given", []):
            if not rule_id.startswith(f"{Rule.prefix}-"):
                continue
            rule = tx.get("rule", rule_id)
            if rule is not None and applied_by(rule, ops, checks_ran):
                shown.append(rule_id)
        return _mark(tx, run_id, shown)


def record_named(tx: Any, run_id: str | None, refs: Iterable[str]) -> list[str]:
    """When a correction of a run's work names rules in `refs`, count each the run was given as applied on that run."""
    if run_id is None:
        return []
    return _mark(tx, run_id, [r for r in refs if r.startswith(f"{Rule.prefix}-")])
