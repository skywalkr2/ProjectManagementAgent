"""Every open action and every open question, in one place each (design 7.5).

An open action comes with its owners as the workspace writes them, its due date, its project and that project's parent,
its notes, where it came from, its state, and the open action it most nearly repeats. An open question comes with who it
waits on, since when and its state. The states are for the screen's filter; a row has exactly one. Nothing here calls
AI or changes anything, apart from `merge_actions`, which is the person's own change, applied like any other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any

from engine.applier import _similar, apply_as_person
from engine.blocked import Blocker, blocker_of, own_wait
from engine.followups import ROUTING, actions_to_send, held_until_day
from engine.names import People, render_owner
from engine.origin import origins
from engine.storage import StoreError
from engine.today import zone

#: An action's state, in the order a row takes the first that applies.
ACTION_STATES = ("no_owner", "on_hold", "overdue", "stale", "open")
#: A question's state.
QUESTION_STATES = ("yours", "waiting", "not_sent", "later")


@dataclass(frozen=True)
class OwnerName:
    person: str
    name: str
    team: str | None = None


@dataclass(frozen=True)
class Alike:
    """The open action another one most nearly repeats: its id, text and version as read."""

    id: str
    text: str
    version: int


@dataclass
class OpenAction:
    id: str
    version: int
    text: str
    state: str
    owners: list[OwnerName]
    due: str | None
    project: str | None
    project_name: str
    parent_name: str | None
    notes: str | None
    since: str
    on_hold: str | None = None
    blocker: Blocker | None = None
    duplicate: Alike | None = None
    origin: dict[str, Any] | None = None
    #: The days since anything changed on it, for a row the screen says is stale.
    untouched_days: int | None = None
    #: For an action with no owner, the open question asking who owns it.
    owner_question: str | None = None
    #: An owner other than the person hasn't been told about it yet (design 6.10).
    to_send: bool = False


@dataclass
class OpenQuestion:
    id: str
    version: int
    title: str
    text: str
    kind: str
    state: str
    to: str
    to_name: str
    project_name: str
    since: str
    projects: list[str] = field(default_factory=list)
    waiting_days: int | None = None
    chases: int = 0
    held_until: str | None = None
    origin: dict[str, Any] | None = None


def _day(stamp: str | None, here: Any) -> date | None:
    if not stamp:
        return None
    moment = datetime.fromisoformat(str(stamp))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(here).date()


def _moment(stamp: str) -> datetime:
    at = datetime.fromisoformat(stamp)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def open_actions(
    store: Any, cfg: Any, today: date, *, now: datetime | None = None, light: bool = False
) -> list[OpenAction]:
    """Every action still to do (open or waiting for an owner), overdue first, then by date, undated last. With `light`,
    the rows leave out what costs a pass over all of them (the near-duplicate each offers and where it came from), for a
    caller that only needs their states."""
    now = now or datetime.combine(today, time.max, tzinfo=UTC)
    here = zone(cfg)
    view = store.read()
    people = People(store, cfg)
    projects = {p.id: p.data for p in view.list("project")}
    changed = view.last_changes("action")
    created = view.creators("action")
    stale_after = cfg.ui.today.stale_after_days
    me = cfg.workspace.user.person
    asking_owner = {
        (q.data.get("resolves") or {}).get("action"): q.id
        for q in view.list("question")
        if q.data["status"] == "open" and (q.data.get("resolves") or {}).get("kind") == "owner"
    }
    rows: list[OpenAction] = []
    to_send = actions_to_send(store, cfg)
    for a in view.list("action"):
        d = a.data
        if d["status"] not in ("open", "held"):
            continue
        hold = d.get("on_hold")
        blocker = blocker_of(view, hold, people, here)
        if blocker is not None and blocker.resolved:
            hold = None  # what it waited on is over, so it is due again by its own date
        elif own_wait(view, d, people.pm):
            hold, blocker = None, None  # it waits on the person themselves: their own to-do, not blocked
        due = date.fromisoformat(str(d["due"])) if d.get("due") else None
        project = projects.get(d.get("project") or "")
        parent = projects.get((project or {}).get("parent") or "")
        owners = [
            OwnerName(
                o["person"],
                render_owner(people.owner_format, people.name(o["person"]), people.team_names.get(o.get("team") or "")),
                o.get("team"),
            )
            for o in d.get("owners") or []
        ]
        untouched = (now - _moment(changed[a.id])).days if a.id in changed else None
        own = bool(me) and any(o["person"] == me for o in d.get("owners") or [])
        if d["status"] == "held":
            state = "no_owner"
        elif hold:
            state = "on_hold"
        elif due is not None and due < today:
            state = "overdue"
        elif (
            stale_after
            and own
            and due is None
            and not d.get("remind_at")
            and not d.get("reply_owed")
            and untouched is not None
            and untouched >= stale_after
        ):
            state = "stale"
        else:
            state = "open"
        rows.append(
            OpenAction(
                id=a.id,
                version=a.version,
                text=d["text"],
                state=state,
                owners=owners,
                due=due.isoformat() if due else None,
                project=d.get("project"),
                project_name=(project or {}).get("name", ""),
                parent_name=(parent or {}).get("name"),
                notes=d.get("notes") or None,
                since=(_day(created[a.id][1], here) or today).isoformat() if a.id in created else "",
                on_hold=hold["waiting_for"] if hold else None,
                blocker=blocker,
                untouched_days=untouched if state == "stale" else None,
                owner_question=asking_owner.get(a.id) if state == "no_owner" else None,
                to_send=a.id in to_send,
            )
        )
    if not light:
        _offer_duplicates(rows, cfg, view)
        found = origins(view, "action", [r.id for r in rows])
        for r in rows:
            r.origin = found.get(r.id)
    order = {state: n for n, state in enumerate(ACTION_STATES)}
    return sorted(rows, key=lambda r: (r.state != "overdue", r.due is None, r.due or "", order[r.state], r.text))


def _offer_duplicates(rows: list[OpenAction], cfg: Any, view: Any) -> None:
    """Give each action the one most like it among those of the same project and the same owners, when it is as alike
    as the near-duplicate lint says. An action waiting for an owner, or on hold, is not offered: it isn't the same
    work."""
    needed = cfg.checks.tuning.near_duplicate_action.similarity
    groups: dict[tuple[Any, frozenset[str]], list[OpenAction]] = {}
    for r in rows:
        if r.state in ("no_owner", "on_hold"):
            continue
        groups.setdefault((r.project, frozenset(o.person for o in r.owners)), []).append(r)
    for group in groups.values():
        for r in group:
            best: tuple[float, OpenAction] | None = None
            for other in group:
                if other is r:
                    continue
                score = _similar(r.text, other.text)
                if score >= needed and (best is None or score > best[0]):
                    best = (score, other)
            if best is not None:
                r.duplicate = Alike(best[1].id, best[1].text, best[1].version)


def stale_actions(store: Any, cfg: Any, now: datetime) -> list[OpenAction]:
    """The person's own open to-dos with no date that nothing has touched for `ui.today.stale_after_days`, the longest
    untouched first. None when the setting is zero."""
    if not cfg.ui.today.stale_after_days:
        return []
    today = now.astimezone(zone(cfg)).date()
    found = [r for r in open_actions(store, cfg, today, now=now, light=True) if r.state == "stale"]
    return sorted(found, key=lambda r: (-(r.untouched_days or 0), r.id))


def open_questions(store: Any, cfg: Any, today: date) -> list[OpenQuestion]:
    """Every question still waiting: those to the person first, then what was sent (longest wait first), then what is
    not sent yet, then what is held for later. A question asked only to place a name or pick an owner is answered where
    that waits, so it isn't here."""
    here = zone(cfg)
    view = store.read()
    people = People(store, cfg)
    projects = {p.id: p.data["name"] for p in view.list("project")}
    created = view.creators("question")
    rows: list[OpenQuestion] = []
    for q in view.list("question"):
        d = q.data
        if d["status"] not in ("open", "sent") or (d.get("resolves") or {}).get("kind") in ROUTING:
            continue
        sent = _day(d.get("sent_at"), here) if d.get("sent_at") else None
        chased = sorted(date.fromisoformat(str(c)) for c in d.get("followed_up") or [])
        last_word = chased[-1] if chased else sent
        held_until, _name = held_until_day(view, d.get("held_for"), today, here)
        if d["status"] == "sent":
            state = "waiting"
        elif d["to"] == people.pm:
            state = "yours"
        elif held_until is not None and held_until > today:
            state = "later"
        else:
            state = "not_sent"
        began = sent or (_day(created[q.id][1], here) if q.id in created else None)
        rows.append(
            OpenQuestion(
                id=q.id,
                version=q.version,
                title=d["title"],
                text=d.get("text", ""),
                kind=d["kind"],
                state=state,
                to=d["to"],
                to_name=people.name(d["to"]),
                project_name=", ".join(projects[p] for p in d.get("projects", []) if p in projects),
                projects=[p for p in d.get("projects", []) if p in projects],
                since=began.isoformat() if began else "",
                waiting_days=max(0, (today - last_word).days) if last_word and state == "waiting" else None,
                chases=len(chased),
                held_until=held_until.isoformat() if state == "later" and held_until else None,
            )
        )
    found = origins(view, "question", [r.id for r in rows])
    for r in rows:
        r.origin = found.get(r.id)
    order = {state: n for n, state in enumerate(QUESTION_STATES)}
    return sorted(rows, key=lambda r: (order[r.state], -(r.waiting_days or 0), r.since, r.id))


def merge_actions(store: Any, cfg: Any, keep: str, other: str, read_version: int, other_version: int) -> str:
    """Keep the action `keep` and close `other`, which it nearly repeats, as one change with one Undo. The kept action's
    notes gain a line with the other's words (and its notes), it takes the earlier of the two due dates, and the other
    is dropped with a reason naming the one it went into: the person's own drop, so it is a correction the assistant
    learns from. `read_version` and `other_version` are the versions the person saw; if either action changed, is not
    open, or they are the same action, nothing changes. Returns the changeset's id."""
    if keep == other:
        raise StoreError("that is the same action")
    view = store.read()
    kept, closed = view.get("action", keep), view.get("action", other)
    if kept is None or closed is None:
        raise StoreError("one of those actions is gone")
    if kept.data["status"] != "open" or closed.data["status"] != "open":
        raise StoreError("only an open action can be merged")
    if kept.version != read_version or closed.version != other_version:
        raise StoreError("one of those actions changed since it was read")
    words = cfg.language.messages
    line = words.merged_note.format(text=closed.data["text"])
    if closed.data.get("notes"):
        line = f"{line}\n{closed.data['notes']}"
    notes = f"{kept.data['notes']}\n{line}" if kept.data.get("notes") else line
    fields: dict[str, Any] = {"notes": notes}
    dues = sorted(str(x.data["due"]) for x in (kept, closed) if x.data.get("due"))
    if dues and dues[0] != str(kept.data.get("due") or ""):
        fields["due"] = dues[0]
    ops = [
        {"op": "record.edit", "record": {"kind": "action", "id": keep}, "fields": fields, "read_version": read_version},
        {"op": "action.drop", "id": other, "reason": words.merged_reason.format(text=kept.data["text"])},
    ]
    return apply_as_person(store, cfg, ops, "Merged two to-dos", all_or_nothing=True)


__all__ = [
    "ACTION_STATES",
    "QUESTION_STATES",
    "Alike",
    "OpenAction",
    "OpenQuestion",
    "OwnerName",
    "merge_actions",
    "open_actions",
    "open_questions",
    "stale_actions",
]
