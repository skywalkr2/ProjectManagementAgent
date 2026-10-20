"""Questions after a move, as one thing to look at (design 7.7): the questions a follow-on run asked the person about
one move (a meeting moved, a date changed, a fact replaced) are one group line under the move, with a row inside
for each. A group of one stays a normal row that says what it came after. Questions the run asked other people are
not the person's to answer: they are counted in the group's words and wait in Follow-ups. Two moves of the same
record before the person looks leave one group, for the latest move. Reads only."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from engine import follow_on


def _number(record_id: str) -> int:
    digits = "".join(c for c in record_id if c.isdigit())
    return int(digits) if digits else 0


def _after(view: Any, here: ZoneInfo, request: Any, move: follow_on.Move) -> dict[str, Any]:
    """What a move was, for the words of the group and of a single row: the record's own name, the day it moved to, and
    whether that is earlier than the day it left."""
    found = view.get(move.kind, move.record)
    title = ""
    if found is not None:
        title = " ".join(str(found.data.get("title") or found.data.get("text") or "").split())
    before, after = follow_on._day(move.before, here), follow_on._day(move.after, here)
    return {
        "kind": move.kind,
        "record": move.record,
        "title": title,
        "to": after.isoformat() if after else None,
        "earlier": bool(before and after and after < before),
        "by": "pm" if move.actor == "pm" else "assistant",
        "replaced": move.field == "supersedes",
        "request": request.id,
        "changeset": request.data.get("changeset"),
    }


def _check(view: Any, question: Any, move: follow_on.Move, after: dict[str, Any]) -> dict[str, Any] | None:
    """The one structured answer a question after a move can have, read from the record id the question says it matters
    for (the check on a follow-on run's question already made it name a tied action or the moved record): `date` when it
    names an open action with a day, which the move may bring to the day it moved to (`from_day` the action's own day,
    `to_day` the new one, with the action's `version` for the edit); `plan` when it names the moved record. None for any
    other question, which keeps its own answer form."""
    named = str(question.data.get("matters_for") or "")
    if not named:
        return None
    if after["to"]:
        for record in view.list("action"):
            data = record.data
            if (
                data.get("status") == "open"
                and data.get("due")
                and str(data["due"]) != after["to"]
                and follow_on._names(named, record.id)
            ):
                return {
                    "kind": "date",
                    "action": record.id,
                    "version": record.version,
                    "text": " ".join(str(data["text"]).split()),
                    "from_day": str(data["due"]),
                    "to_day": after["to"],
                }
    if follow_on._names(named, move.record):
        return {"kind": "plan", "record": move.record}
    return None


def group(view: Any, people: Any, here: ZoneInfo, lines: list[Any], make_line: Any) -> list[Any]:
    """`lines` with the person's questions that a follow-on run asked grouped by move. `make_line` builds a group line
    from its keyword fields (the queue's own `Line`). Returns the new list; lines that aren't such questions are kept
    as they are, in order, and a group stands where its first question stood."""
    made = view.creations("question")
    asked: dict[str, tuple[Any, follow_on.Move]] = {}
    newest: dict[tuple[str, str], tuple[int, str]] = {}
    for line in lines:
        if not line.question or line.kind not in ("question", "decision"):
            continue
        _, request_id = made.get(line.question, (None, None))
        request = view.get("request", request_id) if request_id else None
        if request is None or request.data.get("task") != follow_on.TASK:
            continue
        moves = follow_on.moves_of(view, request.data.get("follows"))
        if not moves:
            continue
        asked[line.question] = (request, moves[0])
        key = (moves[0].kind, moves[0].record)
        newest[key] = max(newest.get(key, (0, "")), (_number(request.id), request.id))
    if not asked:
        return lines
    # What the run asked other people, counted by move: it lives in Follow-ups.
    to_others: dict[str, list[str]] = {}
    for q in view.list("question"):
        request_id = made.get(q.id, (None, None))[1]
        if request_id is None or q.data.get("to") == people.pm or q.data.get("status") not in ("open", "sent"):
            continue
        to_others.setdefault(request_id, []).append(people.name(q.data["to"]))
    members: dict[str, list[Any]] = {}
    kept: list[Any] = []
    for line in lines:
        found = asked.get(line.question or "")
        if found is None:
            kept.append(line)
            continue
        request, move = found
        if newest[(move.kind, move.record)][1] != request.id:
            continue  # an earlier move of the same record that the latest one has replaced
        found_after = _after(view, here, request, move)
        line.after_move = {
            **found_after,
            "others": sorted(dict.fromkeys(to_others.get(request.id, []))),
            "check": _check(view, view.get("question", line.question), move, found_after),
        }
        members.setdefault(request.id, []).append(line)
        kept.append(line)
    out: list[Any] = []
    placed: set[str] = set()
    for line in kept:
        after = line.after_move
        request_id = after["request"] if after else None
        if request_id is None or len(members[request_id]) < 2:
            out.append(line)
            continue
        if request_id in placed:
            continue
        placed.add(request_id)
        inside = members[request_id]
        out.append(
            make_line(
                key=f"moved:{request_id}",
                group="decide",
                kind="moved",
                count=len(inside),
                text=after["title"],
                due=after["to"],
                changeset=after["changeset"],
                questions=[m.question for m in inside],
                project=inside[0].project,
                after_move={
                    **{k: v for k, v in after.items() if k != "check"},
                    "rows": [{"question": m.question, "check": m.after_move["check"]} for m in inside],
                },
                since=min(m.since for m in inside),
            )
        )
    return out
