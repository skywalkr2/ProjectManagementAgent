"""A series' page (design 7.14): the next meeting with what is open for it, by person, then the meetings that have
passed, each as one line of what was settled and what moved on. Reads only. Building an agenda is not here: this is
record display, so the page shows where an item rolled to and nothing is worked out from the person's words."""

from __future__ import annotations

from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from engine.names import render_owner
from engine.series import SETTLED, instances, next_instance, span

#: The kinds of item that sit on a series' meetings.
KINDS = tuple(SETTLED)


def _text(kind: str, data: dict[str, Any]) -> str:
    return str(data["text"] if kind == "action" else data["title"])


def _rolled(view: Any, kind: str, record_id: str) -> list[tuple[str | None, str | None]]:
    """The moves of an item from one meeting to the next, oldest first: the meeting it left and the one it went to."""
    return [
        (row.get("before"), row.get("after"))
        for row in view.ledger(kind=kind, record_id=record_id)
        if row["field"] == "event" and str(row["op"]).split("#", 1)[0] == "series.roll"
    ]


def page(
    view: Any, series_id: str, today: date, here: ZoneInfo, *, pm: str | None, owner_format: str = "{full_name}"
) -> dict[str, Any] | None:
    found = view.get("series", series_id)
    if found is None:
        return None
    data = found.data
    meetings = instances(view, series_id, here)
    upcoming = next_instance(view, series_id, today, here)
    names: dict[str, str] = {}

    def person(pid: str) -> str:
        if pid not in names:
            record = view.get("person", pid, include_deleted=True)
            names[pid] = render_owner(owner_format, record.data["full_name"] if record else pid, None)
        return names[pid]

    def meeting(entry: Any) -> dict[str, Any]:
        days = span(entry.data, here)
        return {
            "id": entry.id,
            "title": entry.data["title"],
            "start": entry.data["start"],
            "on": days[0].isoformat() if days else None,
        }

    by_id = {m.id: m for m in meetings}
    open_items: list[dict[str, Any]] = []
    past: dict[str, dict[str, Any]] = {}
    for m in meetings:
        days = span(m.data, here)
        if days is not None and days[1] < today:
            past[m.id] = {**meeting(m), "settled": [], "moved": []}
    for kind in KINDS:
        for item in view.list(kind):
            if item.data.get("series") != series_id:
                continue
            settled = item.data.get("status") in SETTLED[kind]
            rolls = _rolled(view, kind, item.id)
            row = {"kind": kind, "id": item.id, "text": _text(kind, item.data), "status": item.data.get("status")}
            if not settled:
                came_from = next(
                    (by_id[b] for b, a in reversed(rolls) if b in by_id and a == (upcoming.id if upcoming else None)),
                    None,
                )
                who = [o["person"] for o in item.data.get("owners") or []] if kind == "action" else [item.data["to"]]
                open_items.append(
                    {
                        **row,
                        "due": str(item.data["due"]) if item.data.get("due") else None,
                        "people": who,
                        "rolled_from": meeting(came_from) if came_from is not None else None,
                    }
                )
            sat_on = item.data.get("event")
            if settled and sat_on in past:
                past[sat_on]["settled"].append(row)
            for before, after in rolls:
                if before in past:
                    past[before]["moved"].append({**row, "to": meeting(by_id[after]) if after in by_id else None})
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in open_items:
        for pid in item["people"] or [""]:
            groups.setdefault(pid, []).append({k: v for k, v in item.items() if k != "people"})
    ordered = sorted(groups, key=lambda pid: (pid == pm, person(pid).casefold() if pid else ""))
    project = view.get("project", data["project"]) if data.get("project") else None
    return {
        "id": series_id,
        "title": data["title"],
        "repeats": data.get("repeats"),
        "project": data.get("project"),
        "project_name": project.data["name"] if project is not None else None,
        "next": (
            {
                **meeting(upcoming),
                "open": len(open_items),
                "groups": [
                    {
                        "person": pid or None,
                        "name": person(pid) if pid else None,
                        "is_pm": pid == pm,
                        "items": groups[pid],
                    }
                    for pid in ordered
                ],
            }
            if upcoming is not None
            else None
        ),
        "past": sorted(past.values(), key=lambda p: (p["start"], p["id"]), reverse=True),
        "open_without_next": len(open_items) if upcoming is None else 0,
    }
