"""A held item as a question (design 7.6, 7.7): what the person is asked to confirm, in structured form so the screen
words it as "Close 'X'?" with a button that names the result. Only the holds that rest on an inference, or that would
drop something that already reached someone, are shaped here; any other hold is shown by its label. Reads only."""

from __future__ import annotations

from typing import Any

CLOSE, DATE, OWNER, ROUTING, DROP = "close", "date", "owner", "routing", "drop"


def _text(record: Any) -> str:
    data = record.data
    return " ".join(str(data.get("text") or data.get("title") or "").split())


def _told(view: Any, people: Any, record: Any) -> tuple[list[str], str | None]:
    """The people an action or question already reached, and the earliest day they were told."""
    data = record.data
    if record.kind == "action":
        told = {
            **(data.get("told") or {}),
            **{p: (days or [None])[0] for p, days in (data.get("followed_up") or {}).items()},
        }
        names = [people.name(p) for p in told]
        days = sorted(str(d) for d in told.values() if d)
        return names, days[0] if days else None
    if data.get("status") == "sent" or data.get("sent_at"):
        return [people.name(data["to"])], (str(data["sent_at"])[:10] if data.get("sent_at") else None)
    return [], None


def describe(view: Any, people: Any, op: dict[str, Any]) -> dict[str, Any] | None:
    """The held op as a question, or None when it isn't one of the shaped holds: `ask` (close, date, owner, routing or
    drop), `item` (the words of what it is about), `value` (what it would change to), `from_value` (what it is now),
    `to_name`, `told` (people already reached) and `told_on`, and `quote` (the words the assistant rested it on)."""
    name = op.get("op", "")
    quote = (op.get("evidence") or {}).get("quote")
    if name in ("action.close", "question.done"):
        kind = "action" if name == "action.close" else "question"
        found = view.get(kind, op.get("id", ""))
        return {"ask": CLOSE, "item": _text(found), "quote": quote} if found is not None else None
    if name == "record.set" and op.get("kind") == "action" and op.get("field") in ("due", "owners", "owner"):
        found = view.get("action", op.get("id", ""))
        if found is None:
            return None
        if op["field"] == "due":
            return {
                "ask": DATE,
                "item": _text(found),
                "value": str(op.get("value")),
                "from_value": str(found.data["due"]) if found.data.get("due") else None,
                "quote": quote,
            }
        value = op.get("value")
        first = value[0].get("person") if isinstance(value, list) and value and isinstance(value[0], dict) else value
        resolved = people.resolve(str(first)).person if first else None
        owners = found.data.get("owners") or []
        return {
            "ask": OWNER,
            "item": _text(found),
            "to_name": people.name(resolved) if resolved else None,
            "from_value": people.name(owners[0]["person"]) if owners else None,
            "quote": quote,
        }
    if name == "question.move":
        found = view.get("question", op.get("id", ""))
        target = people.resolve(op.get("to", "")).person
        if found is None or not target:
            return None
        return {
            "ask": ROUTING,
            "item": _text(found),
            "to_name": people.name(target),
            "from_value": people.name(found.data["to"]),
            "quote": quote,
        }
    if name in ("action.drop", "question.drop"):
        kind = "action" if name == "action.drop" else "question"
        found = view.get(kind, op.get("id", ""))
        if found is None:
            return None
        told, on = _told(view, people, found)
        return {"ask": DROP, "item": _text(found), "told": told, "told_on": on, "quote": quote}
    return None
