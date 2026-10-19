"""Standing rules as records (design 4.10).

The workspace's rules file is the starting set: `seed_rules` makes a record for each of its rules that has none yet,
once, and the file is never written back. From then on the records are the truth, and every reader of the rules
(stage entry checks, load-time validation) goes through `active_rules` and `rule_names` here.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from engine.config.schema import RuleScope, StandingRule
from engine.references import join_scope
from engine.storage import StoreError, WriteContext

_ENGINE = WriteContext(actor="engine", trust="trusted", op="rules.seed")


def _view(source: Any) -> Any:
    """A store, a snapshot or a transaction as something that lists records."""
    return source if hasattr(source, "list") else source.read()


def rule_names(source: Any) -> set[str]:
    """The name of every rule record, whatever its status."""
    return {r.data["name"] for r in _view(source).list("rule")}


def active_rules(source: Any) -> list[StandingRule]:
    """The rules in force now: the active rule records, as the config's rule shape, each named by its record's name."""
    found = []
    for stored in _view(source).list("rule"):
        data = stored.data
        if data["status"] != "active":
            continue
        found.append(
            StandingRule(
                id=data["name"],
                text=data["text"],
                applies_to=RuleScope.model_validate(
                    {key: data["applies_to"].get(key) for key in RuleScope.model_fields if key in data["applies_to"]}
                ),
                source=data.get("source"),
                status="active",
                check=data.get("check"),
                constrains=list(data.get("constrains") or []),
            )
        )
    return found


def seed_rules(store: Any) -> list[str]:
    """Make a rule record for each rule in the starting set that has none, active with the origin `seed`. A rule
    that already has a record (live, retired or deleted) is left as it is, so running this again adds nothing and a
    rule the person retired is not brought back. Returns the names created."""
    starting = list(store.plugins.cfg.rules.rules)
    if not starting:
        return []
    have = {r.data["name"] for r in store.read().list("rule", include_deleted=True)}
    missing = [rule for rule in starting if rule.id not in have]
    if not missing:
        return []
    now = store.clock()
    declared = store.plugins.references()
    with store.transaction() as tx:
        for rule in missing:
            learned = datetime.combine(rule.added, time.min, tzinfo=UTC).isoformat() if rule.added else now
            # The reach holds ids: a name in the starting file is resolved, and one nothing matches is kept as written.
            reach = join_scope(tx, rule.applies_to.model_dump(), declared, soft=True)
            tx.create(
                "rule",
                {
                    "name": rule.id,
                    "text": rule.text,
                    "applies_to": reach,
                    "check": rule.check,
                    "constrains": list(rule.constrains),
                    "origin": "seed",
                    # A rule the file already gave up on is kept as history, not put back in force.
                    "status": "active" if rule.status == "active" else "retired",
                    "source": rule.source,
                    "learned_at": learned,
                },
                _ENGINE,
            )
    return [rule.id for rule in missing]


def add_rule(tx: Any, store: Any, op: Any, w: WriteContext, st: Any, *, evidence: Any) -> list[dict[str, Any]]:
    """Apply `rule.add`: check the name and the code check it names, then create the rule. From the person's own
    words it is active at once; from anyone else it is a proposal, which merges into an active or proposed rule that
    says the same, and is kept as discarded when it is close to a rule the person discarded recently. Returns the
    records touched."""
    stage_checks = store.plugins.stage_checks
    if op.check is not None and op.check not in stage_checks:
        raise StoreError(f"there is no check called {op.check}")
    kept = st.person  # the person's own words apply at once, even before the workspace knows who they are
    data: dict[str, Any] = {
        "text": " ".join(op.text.split()),
        "applies_to": join_scope(tx, op.applies_to.model_dump(mode="json", by_alias=True), store.plugins.references()),
        "check": op.check,
        "constrains": list(dict.fromkeys(op.constrains)),
        "origin": st.origin,
        "trust": st.trust,
        "status": "active" if kept else "proposed",
        "evidence": evidence,
        "learned_at": st.now,
        "kept_by": st.pm if kept else None,
        "kept_at": st.now if kept else None,
    }
    if not kept:
        from engine.knowledge import close_to_discard, merge_into
        from engine.proposals import duplicate_of

        existing = duplicate_of(tx, "rule", data)
        if existing is not None:
            merge_into(tx, "rule", existing, _as_knowledge_evidence(tx, evidence, st), w)
            return [{"kind": "rule", "id": existing.id}]
        if (close := close_to_discard(tx, "rule", data, st)) is not None:
            data.update(status="discarded", discard_reason=close)
    taken = {r.data["name"] for r in tx.list("rule", include_deleted=True)}
    name = op.name
    if name is not None:
        if name in taken:
            raise StoreError(f"there is already a rule named {name}")
        if name in stage_checks:
            raise StoreError(f"{name} is the name of a built-in check; give the rule another name")
    record_id = tx.new_id("rule")
    data["name"] = name or _free_name(f"rule-{record_id.split('-', 1)[1]}", taken | set(stage_checks))
    return [{"kind": "rule", "id": tx.create("rule", data, w, record_id=record_id).id}]


def _as_knowledge_evidence(tx: Any, evidence: Any, st: Any) -> dict[str, Any] | None:
    """A rule's evidence (the source and the words) in the shape evidence is merged in: the source only when it is a
    saved input, and the request that made the proposal."""
    if not evidence:
        return None
    source = evidence.get("source")
    found = {
        "quote": evidence.get("quote"),
        "source": source if source and tx.get("source", source) is not None else None,
        "request": st.request if st.request and tx.get("request", st.request) is not None else None,
        "signal": None,
        "changeset": None,
    }
    return found if found["quote"] or found["source"] else None


def _free_name(wanted: str, taken: set[str]) -> str:
    name, n = wanted, 2
    while name in taken:
        name, n = f"{wanted}-{n}", n + 1
    return name


def retire_rule(tx: Any, op: Any, w: WriteContext) -> str:
    """Apply `rule.retire`: an active rule becomes retired. Returns the rule's id."""
    current = tx.get("rule", op.id)
    if current is None:
        raise StoreError(f"there is no rule {op.id}")
    if current.data["status"] != "active":
        raise StoreError(f"{op.id} isn't an active rule")
    tx.update("rule", op.id, {"status": "retired"}, w, read_version=current.version)
    return op.id
