"""Who made the item a Today line is about (design 7.7), for the inspector to say.

Read from the change that made the item and from the item itself; nothing is stored. The maker is the assistant (a
run), a rule (a change the engine made by its own rule) or the person (their own entry). The state says whether the
item is only *suggested* and waits for the person's yes (a question, a decision, an owner to pick, a held item, an
escalation) or was *added* already, with Undo (a promise found, a date moved). The attribution is for the person's own
screens: it is built only here, for the line, and is never written into a record or any text others read.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from engine.origin import LINK, SOURCE, source_origin

#: Ledger actors that name the maker of a record. Any other actor (the engine, a watcher, an import, an add-on) names
#: no one the person would be told about, unless the record was made as part of a change, which names its own maker.
_ASSISTANT, _PERSON = "assistant", "pm"


def _day(stamp: Any, zone: Any) -> str | None:
    try:
        moment = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is not None and zone is not None:
        moment = moment.astimezone(zone)
    return moment.date().isoformat()


def _rule(view: Any, rule_id: str) -> dict[str, Any]:
    """The rule a change names, with the rule record's own name when one exists."""
    found = view.get("rule", rule_id)
    if found is None:
        found = next((r for r in view.list("rule") if r.data.get("name") == rule_id), None)
    return {"id": rule_id, "label": found.data["name"] if found is not None else None}


def _source(view: Any, source_id: str | None) -> dict[str, Any] | None:
    """The input an item came from, with the link to it: its page, else its saved text. None when there is none."""
    source = view.get("source", source_id) if source_id else None
    origin = source_origin(source)
    if source is None or origin is None or origin["kind"] not in (LINK, SOURCE):
        return None
    return {"title": source.data.get("title") or "", "origin": origin}


def _maker_of_changeset(cs: Any) -> str | None:
    """`rule`, `person` or `assistant` for a change: a rule's by its name, a person action's as the person's own."""
    if cs.data.get("by_rule"):
        return "rule"
    if cs.data.get("action"):
        return "person"
    return "assistant"


def _answered(view: Any, question: Any, zone: Any) -> dict[str, Any] | None:
    """How and when a question was answered or dropped, with the answer given; None while it is open."""
    status = question.data.get("status")
    if status not in ("answered", "dropped"):
        return None
    rows = [r for r in view.ledger(kind="question", record_id=question.id) if r.get("field") == "status"]
    when = rows[-1]["at"] if rows else None
    return {
        "how": status,
        "on": _day(when, zone) if when else None,
        "answer": question.data.get("answer") if status == "answered" else None,
    }


def _build(
    view: Any,
    *,
    kind: str,
    state: str,
    rule: str | None,
    source: str | None,
    inferred: bool = False,
    answered: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "rule": _rule(view, rule) if kind == "rule" and rule else None,
        "source": _source(view, source),
        "state": state,
        "answered": answered,
        "inferred": inferred,
    }


def _request_source(view: Any, request_id: str | None) -> str | None:
    request = view.get("request", request_id, include_deleted=True) if request_id else None
    return (request.data.get("source") or None) if request is not None else None


def of_record(
    view: Any, kind: str, record_id: str, *, state: str, zone: Any = None, maker: str | None = None
) -> dict[str, Any] | None:
    """The maker of one record, from the ledger entry that created it. None when nothing names a maker (the engine,
    an import, an add-on). `maker` forces the maker when the line's own suggestion is the assistant's, whoever made
    the record it is about."""
    record = view.get(kind, record_id, include_deleted=True)
    rows = view.ledger(kind=kind, record_id=record_id)
    if record is None or not rows:
        return None
    first = rows[0]
    cs = view.get("changeset", first["changeset"], include_deleted=True) if first.get("changeset") else None
    rule = cs.data.get("by_rule") if cs is not None else None
    if maker is not None:
        who = maker
    elif rule:
        who = "rule"
    elif first["actor"] == _PERSON:
        who = "person"
    elif cs is not None:
        # Made as part of a change (the engine records a question a held item asks, for one): the change's own maker.
        who = _maker_of_changeset(cs)
    elif first["actor"] == _ASSISTANT:
        who = "assistant"
    else:
        return None
    source = record.data.get("source") or _request_source(view, first.get("request"))
    return _build(
        view,
        kind=who,
        state=state,
        rule=rule,
        source=source,
        inferred=kind == "action" and record.data.get("basis") == "inferred",
        answered=_answered(view, record, zone) if kind == "question" else None,
    )


def of_change(
    view: Any, changeset_id: str | None, *, state: str, op: dict[str, Any] | None = None, zone: Any = None
) -> dict[str, Any] | None:
    """The maker of an item that is one op of a change: the change's own maker. An op that was held for a question the
    person has since answered says so (the person kept it)."""
    cs = view.get("changeset", changeset_id, include_deleted=True) if changeset_id else None
    if cs is None:
        return None
    who = _maker_of_changeset(cs)
    answered = None
    asked = view.get("question", op["question"]) if op and op.get("question") else None
    if asked is not None and asked.data.get("status") == "answered":
        found = _answered(view, asked, zone)
        if found is not None:
            answered = {"how": "kept", "on": found["on"], "answer": None}
            state = "suggested"
    return _build(
        view,
        kind=who,
        state=state,
        rule=cs.data.get("by_rule"),
        source=_request_source(view, cs.data.get("request")),
        inferred=bool(op) and (op.get("op") or {}).get("basis") == "inferred",
        answered=answered,
    )


def _one_applied(view: Any, changeset_id: str, subject: str | None) -> dict[str, Any] | None:
    """The one applied op a review line is about: the only applied one, else the one whose label is the line's."""
    cs = view.get("changeset", changeset_id, include_deleted=True)
    applied = [o for o in (cs.data["ops"] if cs is not None else []) if o.get("status") == "applied"]
    if len(applied) == 1:
        return applied[0]
    return next((o for o in applied if subject and o.get("label") == subject), None)


def of_line(view: Any, line: Any, zone: Any = None) -> dict[str, Any] | None:
    """The maker of the one item a Today line is about, or None for a line about several things, about no item, or
    about an item no maker is known for."""
    kind = line.kind
    if kind in ("decision", "question", "who_is") and line.question:
        return of_record(view, "question", line.question, state="suggested", zone=zone)
    if kind == "owner" and len(line.actions) == 1:
        return of_record(view, "action", line.actions[0], state="suggested", zone=zone)
    if kind == "escalate":
        if line.questions:
            return of_record(view, "question", line.questions[0], state="suggested", zone=zone, maker="assistant")
        if line.actions:
            return of_record(view, "action", line.actions[0], state="suggested", zone=zone, maker="assistant")
        return None
    if kind in ("promise", "reminder", "reply") and len(line.actions) == 1:
        return of_record(view, "action", line.actions[0], state="added", zone=zone)
    if kind in ("overdue", "stale") and line.count == 1 and len(line.actions) == 1:
        return of_record(view, "action", line.actions[0], state="added", zone=zone)
    if kind == "held" and line.changeset and line.op is not None:
        cs = view.get("changeset", line.changeset, include_deleted=True)
        outcome = next((o for o in (cs.data["ops"] if cs is not None else []) if o["index"] == line.op), None)
        return of_change(view, line.changeset, state="suggested", op=outcome, zone=zone)
    if kind == "review" and line.did and line.changeset:
        return of_change(
            view, line.changeset, state="added", op=_one_applied(view, line.changeset, line.subject), zone=zone
        )
    return None
