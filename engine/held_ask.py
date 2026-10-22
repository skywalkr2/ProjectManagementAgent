"""A held item as a question (design 7.6, 7.7): what the person is asked to confirm, in structured form so the screen
words it as "Close 'X'?" with a button that names the result. Only the holds that rest on an inference, that end or move
a promise, or that would drop something that already reached someone, are shaped here; any other hold is shown by its
label. Reads only."""

from __future__ import annotations

from typing import Any

CLOSE, DATE, OWNER, ROUTING, DROP, MOVE, PART = "close", "date", "owner", "routing", "drop", "move", "part"
#: A guess at how long a to-do takes, held for the person to keep.
EFFORT = "effort"
#: An ending whose words say only "closed": the person is asked whether it is done by its owners or no longer needed.
ENDING = "ending"


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


def _ending(people: Any, found: Any, op: dict[str, Any], reporter: str | None) -> dict[str, Any]:
    """What an ending read from an input says happened, for the line that asks the person to keep it: the `record` it is
    about, who owns it (`owners`, as the workspace writes an owner) and who the input says reported it, and for a move
    its new day (`value`) or the words of it (`due_words`) and the day it has now (`from_value`), for a part what was
    delivered and what is left, and for a drop the reason."""
    owners = [people.owner(o) for o in found.data.get("owners") or []]
    shown: dict[str, Any] = {
        "record": found.id,
        "owners": owners,
        "reporter": people.name(reporter) if reporter else None,
    }
    if op["op"] == "action.move":
        shown |= {
            "value": str(op["due"]) if op.get("due") else None,
            "from_value": str(found.data["due"]) if found.data.get("due") else None,
            "due_words": op.get("due_words"),
        }
        shown["earlier"] = (found.data.get("evidence") or {}).get("quote")
    elif op["op"] == "action.part":
        shown |= {"delivered": op.get("delivered"), "left": op.get("left")}
    elif op["op"] == "action.drop":
        shown["reason"] = op.get("reason")
    return shown


def describe(
    view: Any, people: Any, op: dict[str, Any], *, reporter: str | None = None, choice: bool = False
) -> dict[str, Any] | None:
    """The held op as a question, or None when it isn't one of the shaped holds: `ask` (close, date, owner, routing,
    drop, move or part), `item` (the words of what it is about), `value` (what it would change to), `from_value`
    (what it is now), `to_name`, `told` (people already reached) and `told_on`, and `quote` (the words the
    assistant rested it on). An ending of an action also says what the input says happened (see `_ending`);
    `reporter` is who said it. With `choice`, a close or a drop of an action is the one question "done by its owners, or
    no longer needed?" (`ask` is `ending`), whatever op the assistant proposed."""
    name = op.get("op", "")
    quote = (op.get("evidence") or {}).get("quote")
    if choice and name in ("action.close", "action.drop"):
        found = view.get("action", op.get("id", ""))
        if found is None:
            return None
        return {
            "ask": ENDING,
            "item": _text(found),
            "quote": quote,
            **_ending(people, found, {"op": "action.close"}, reporter),
        }
    if name in ("action.move", "action.part"):
        found = view.get("action", op.get("id", ""))
        if found is None:
            return None
        ask = MOVE if name == "action.move" else PART
        return {"ask": ask, "item": _text(found), "quote": quote, **_ending(people, found, op, reporter)}
    if name in ("action.close", "question.done"):
        kind = "action" if name == "action.close" else "question"
        found = view.get(kind, op.get("id", ""))
        if found is None:
            return None
        shown = {"ask": CLOSE, "item": _text(found), "quote": quote}
        return shown | _ending(people, found, op, reporter) if kind == "action" else shown
    if name == "record.set" and op.get("kind") == "action" and op.get("field") == "effort_minutes":
        found = view.get("action", op.get("id", ""))
        if found is None:
            return None
        before = found.data.get("effort_minutes")
        return {
            "ask": EFFORT,
            "item": _text(found),
            "value": str(op.get("value")),
            "from_value": str(before) if before else None,
            "quote": quote,
        }
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
        shown = {"ask": DROP, "item": _text(found), "told": told, "told_on": on, "quote": quote}
        return shown | _ending(people, found, op, reporter) if kind == "action" else shown
    return None


def reason_of(outcome: dict[str, Any]) -> str | None:
    """Why a held op waits, in the words of today's checks: a hold made before the wording changed shows the same
    reason as one made now. Another kind of hold keeps the reason it was given."""
    from engine.applier import ENDING_WAITS, INFERENCE_WAITS, REACHED_WAITS

    words = {"inference-confirm": INFERENCE_WAITS, "ending-confirm": ENDING_WAITS, "reached-confirm": REACHED_WAITS}
    found = [words[p["check"]] for p in outcome.get("problems") or [] if p.get("check") in words]
    return "; ".join(dict.fromkeys(found)) if found else outcome.get("reason")
