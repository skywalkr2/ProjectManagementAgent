"""A meeting's agenda (design 5.x, 6.33): the action, question or note something is to be taken up under, listed on a
calendar entry or on a series, linked to the record it came from. Putting an item on an agenda changes nothing else:
the item stays as it was. The words of a call-off that move an action into a meeting are matched to a known meeting
here (a calendar entry still ahead, else a series). Nothing here calls AI."""

from __future__ import annotations

from datetime import date
from typing import Any

from engine.due_phrases import named_entry, names_title

#: The kinds of record an agenda item can come from, with the field of the item that names each.
KINDS = ("action", "question", "note")


def item_of(op: Any) -> tuple[str, str]:
    """The kind and id of the record an `agenda.add` puts on the agenda."""
    for kind in KINDS:
        found = getattr(op, kind, None)
        if found is not None:
            return kind, found
    raise ValueError("an agenda item comes from one action, question or note")


def meeting_of(op: Any) -> tuple[str, str]:
    """The kind and id of the record whose agenda an `agenda.add` adds to: a calendar entry (`event`) or a series."""
    return ("event", op.event) if op.event is not None else ("series", op.series)


def words_of(record: Any) -> str:
    """A record's own words in one line: an action's text, a question's title or a note's text."""
    data = record.data
    return " ".join(str(data.get("text") or data.get("title") or "").split())[:200]


def on_agenda(view: Any, meeting: tuple[str, str], item: tuple[str, str]) -> bool:
    """Whether the record is already listed on the meeting's agenda."""
    found = view.get(*meeting)
    kind, record_id = item
    return found is not None and any(entry.get(kind) == record_id for entry in found.data.get("agenda") or [])


def problem(view: Any, op: Any) -> str | None:
    """Why an `agenda.add` can't stand, in plain words, or None: the meeting and the record must exist, the record must
    not be settled, and it must not be on that agenda already."""
    meeting, item = meeting_of(op), item_of(op)
    if view.get(*meeting) is None:
        return f"there is no {'calendar entry' if meeting[0] == 'event' else 'series'} {meeting[1]}"
    found = view.get(*item)
    if found is None:
        return f"there is no {item[0]} {item[1]}"
    if found.data.get("status") in ("done", "dropped", "answered"):
        return f"{item[0]} {item[1]} is already {found.data['status']}, so it has nothing left to take up"
    if on_agenda(view, meeting, item):
        return f"{item[0]} {item[1]} is already on the agenda of {meeting[1]}"
    return None


def added(view: Any, op: Any, *, by: str | None, at: str) -> dict[str, Any]:
    """The agenda item an `agenda.add` makes: the link, who put it there (None when the assistant did), when and the
    words, the op's own or the record's."""
    kind, record_id = item_of(op)
    words = " ".join((op.text or "").split()) or words_of(view.get(kind, record_id))
    return {kind: record_id, "added_by": by, "added_at": at, "text": words}


def add(tx: Any, op: Any, w: Any, *, by: str | None, at: str) -> tuple[str, str]:
    """Add the item to the end of the meeting's agenda, with the record version read, and return the meeting's kind and
    id."""
    meeting = meeting_of(op)
    current = tx.get(*meeting)
    item = added(tx, op, by=by, at=at)
    tx.update(
        meeting[0],
        meeting[1],
        {"agenda": [*(current.data.get("agenda") or []), item]},
        w,
        read_version=current.version,
    )
    return meeting


def named_meeting(view: Any, phrase: str, today: date) -> tuple[str, str] | None:
    """The one meeting the words name, as its kind and id: a calendar entry still ahead whose title they hold, else a
    series whose title they hold (and no calendar entry did). None when they name none or several."""
    entry = named_entry(view.list("event"), phrase, today.isoformat())
    if entry is not None:
        return "event", entry.id
    titles: dict[str, list[Any]] = {}
    for series in view.list("series"):
        if names_title(phrase, str(series.data["title"])):
            titles.setdefault(str(series.data["title"]).casefold(), []).append(series)
    kept = [t for t in titles if not any(t != o and names_title(o, t) for o in titles)]
    if len(kept) != 1 or len(titles[kept[0]]) != 1:
        return None
    return "series", titles[kept[0]][0].id


def lines(view: Any, meeting_kind: str, meeting_id: str) -> list[dict[str, Any]]:
    """The items on a meeting's agenda, in the order they were put there, for a screen: the kind and id of the record
    each came from, its words, who put it there (None when the assistant did, from what came in) and when."""
    found = view.get(meeting_kind, meeting_id)
    out = []
    for entry in (found.data.get("agenda") if found is not None else None) or []:
        kind = next(k for k in KINDS if entry.get(k))
        by = view.get("person", entry["added_by"], include_deleted=True) if entry.get("added_by") else None
        out.append(
            {
                "kind": kind,
                "id": entry[kind],
                "text": entry["text"],
                "added_by": entry.get("added_by"),
                "added_by_name": by.data["full_name"] if by is not None else None,
                "added_at": str(entry["added_at"]),
            }
        )
    return out


def for_entry(view: Any, entry: Any, today: date, here: Any) -> list[dict[str, Any]]:
    """What is to be taken up at a calendar entry: its own agenda and, when it is the next meeting of its series, the
    series' agenda after it."""
    from engine.series import next_instance

    found = lines(view, "event", entry.id)
    series = entry.data.get("series")
    upcoming = next_instance(view, series, today, here) if series else None
    if series and upcoming is not None and upcoming.id == entry.id:
        found += lines(view, "series", series)
    return found
