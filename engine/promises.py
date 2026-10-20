"""Promises on Today and on screen (design 6.33): which open actions are late with nothing heard, and the one view of a
promise every screen shows (its words, who owes it to whom, its date and where that came from, how it is known, what was
heard since), with the one correction that changes it. Promises are actions; nothing here is a new kind of record.
Reads, except `correct`, which applies the person's own edit."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.blocked import standing_hold
from engine.origin import origins
from engine.scope import stance_of

#: The ops that end a promise or move its date; one held for the person's Keep stands for its action.
ENDING_NAMES = ("action.close", "action.drop", "action.move", "action.part")


def is_promise(data: dict[str, Any]) -> bool:
    """Whether an action was read as a promise: it says who it was promised to, or how it is known."""
    return bool(data.get("promised_to")) or data.get("basis") is not None


@dataclass(frozen=True)
class Late:
    """An open action that needs a line: its `action`, the `due` day (none when undated), its `text`, `owner`, the
    person to chase (none when it is the person's own), `stance` (who that person is to the person, design 6.34: none
    for the person's own and for a reply owed, which a stance never gates), `quiet` days: past its date (negative
    while the date is still ahead), or, for an undated one, since it was made or last heard of, and `replies`: how many
    replies that didn't answer it has had since its line began, shown with the line (design 6.33)."""

    action: str
    due: date | None
    text: str
    owner: str | None
    project: str | None
    quiet: int
    since: date
    stance: str | None = None
    replies: int = 0


def held_endings(changesets: dict[str, dict[str, Any]], live: set[str]) -> set[str]:
    """The actions an ending waits on for the person's Keep, from the changesets in `live` (those whose request is
    still open)."""
    found: set[str] = set()
    for changeset_id, cs in changesets.items():
        if changeset_id not in live:
            continue
        for outcome in cs.get("ops", []):
            op = outcome.get("op") or {}
            if outcome.get("status") == "held" and op.get("op") in ENDING_NAMES and op.get("id"):
                found.add(str(op["id"]))
    return found


def late(
    reader: Any, cfg: Any, pm: str | None, today: date, pending: set[str], made: Callable[[str], date | None]
) -> list[Late]:
    """The open actions that need a line, never one on hold or with an ending waiting for the person.
    - The person's own, once read as promises (a plain to-do stays on the overdue line): past their date with no news
      since that day.
    - Owed by someone else, which the person waits on: with a date, from `steward.chase_dated_days` before it and once
      it has passed (a past one with no news since its day); with none, after `steward.chase_undated_days` with no news
      since it was made or since its latest news. One chased lately waits as long again.
    - A reply that didn't answer (a non-answer, written by the news op) is news that mustn't silence the chase: the
      first restarts the clock once, for the dated window (`steward.chase_dated_days`) of a dated promise and the
      undated wait of an undated one, and a second brings the line back at once with `replies` counted.
    Each waiting-on carries the owner's stance (the screens word it by that, and Today leaves out a watched one).
    `made` gives the day an action was made. Oldest first."""
    found: list[Late] = []
    if pm is None:
        return found
    rule = cfg.steward
    wait = cfg.ui.followups.question_after_days

    def stance(owner: str, data: dict[str, Any]) -> str | None:
        return None if data.get("reply_owed") else stance_of(reader, rule, owner)

    for record in reader.list("action"):
        d = record.data
        if d.get("status") != "open" or standing_hold(reader, d) or record.id in pending:
            continue
        owners = [o["person"] for o in d.get("owners") or [] if o.get("person")]
        if not owners:
            continue
        due = date.fromisoformat(str(d["due"])) if d.get("due") else None
        entries = [(date.fromisoformat(str(n["on"])), bool(n.get("non_answer"))) for n in d.get("news") or []]
        news = [on for on, _ in entries]
        mine = pm in owners
        text, project = str(d["text"]), d.get("project")
        if mine:
            if due is None or due >= today or not is_promise(d) or any(n >= due for n in news):
                continue
            found.append(Late(record.id, due, text, None, project, (today - due).days, due))
            continue
        chased = [date.fromisoformat(str(d["told"][p])) for p in owners if (d.get("told") or {}).get(p)]
        if due is not None:
            if (due - today).days > rule.chase_dated_days:
                continue
            start = due if due < today else due - timedelta(days=rule.chase_dated_days)
            heard = [(on, non) for on, non in entries if on >= start]
            replies = [on for on, non in heard if non]
            if len(replies) < len(heard):
                continue  # news that wasn't a non-answer ends the wait for its day
            if len(replies) == 1 and (today - replies[0]).days < rule.chase_dated_days:
                continue  # one non-answer restarts the clock once
            if chased and (today - max(chased)).days < wait:
                continue
            found.append(
                Late(
                    record.id,
                    due,
                    text,
                    owners[0],
                    project,
                    (today - due).days,
                    due,
                    stance(owners[0], d),
                    len(replies),
                )
            )
            continue
        began = made(record.id)
        since = max([*news, *chased, *([began] if began else [])], default=None)
        last_chase = max(chased, default=None)
        replies = [on for on, non in entries if non and (last_chase is None or on > last_chase)]
        if len(replies) < 2 and since is not None and (today - since).days < rule.chase_undated_days:
            continue
        found.append(
            Late(
                record.id,
                None,
                text,
                owners[0],
                project,
                (today - since).days if since else 0,
                since or today,
                stance(owners[0], d),
                len(replies),
            )
        )
    return sorted(found, key=lambda x: (x.since, x.action))


def waiting_on(store: Any, cfg: Any, today: date, hidden: frozenset[str] | set[str] = frozenset()) -> list[Late]:
    """The open actions that need a line, read from the store the way Today reads them: with the endings that wait for
    the person's Keep taken from the requests still open (`hidden`: requests Today holds back, which leave nothing
    waiting) and the day each action was made from the ledger. Follow-ups use the same list for who is due a chase."""
    from engine.names import People
    from engine.today import zone

    reader = store.read()
    changesets = {c.id: c.data for c in reader.list("changeset")}
    live = {
        str(r.data["changeset"])
        for r in reader.list("request")
        if r.data.get("changeset") in changesets and not r.data.get("dismissed") and r.id not in hidden
    }

    def made(action_id: str) -> date | None:
        entries = reader.ledger(kind="action", record_id=action_id)
        stamp = str(entries[0]["at"]) if entries else ""
        if not stamp:
            return None
        at = datetime.fromisoformat(stamp)
        return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(zone(cfg)).date()

    return late(reader, cfg, People(store, cfg).pm, today, held_endings(changesets, live), made)


def is_follow_up(item: Late) -> bool:
    """Whether a waiting-on is chased with the person's one follow-up message to whoever owes it (design 6.33, 6.34): it
    is owed by someone else who is neither reported to nor only watched. The rest keep a line of their own."""
    return item.owner is not None and item.stance not in ("report_to", "watch")


def view(store: Any, cfg: Any, action_id: str) -> dict[str, Any] | None:
    """One promise as its screens show it, or None when there is no such action: the exact words and where they came
    from, who owes it (in the owner format) and to whom, the date with the words it was read from, whether it was said
    or worked out, and what was heard since, newest first, a delivered part credited to the owners."""
    from engine.names import People

    reader = store.read()
    record = reader.get("action", action_id)
    if record is None:
        return None
    d = record.data
    people = People(store, cfg)
    owners = d.get("owners") or []
    names = [people.owner(o) for o in owners]
    news = [
        {
            "on": n["on"],
            "text": n["text"],
            "quote": n.get("quote"),
            "delivered": bool(n.get("delivered")),
            "credited": names if n.get("delivered") else [],
        }
        for n in sorted(d.get("news") or [], key=lambda n: str(n["on"]), reverse=True)
    ]
    return {
        "action": record.id,
        "version": record.version,
        "text": d["text"],
        "status": d["status"],
        "quote": (d.get("evidence") or {}).get("quote"),
        "owners": [{"id": o["person"], "name": n} for o, n in zip(owners, names, strict=True)],
        "mine": people.pm is not None and any(o["person"] == people.pm for o in owners),
        "promised_to": [{"id": p, "name": people.name(p)} for p in d.get("promised_to") or []],
        "due": d.get("due"),
        "due_words": d.get("due_words"),
        "due_check": bool(d.get("due_check")),
        "basis": d.get("basis"),
        "said_by": people.name(d["said_by"]) if d.get("said_by") else None,
        "origin": origins(reader, "action", [action_id]).get(action_id),
        "news": news,
    }


def correction(
    current: dict[str, Any],
    *,
    owner: str | None = None,
    promised_to: list[str] | None = None,
    basis: str | None = None,
    due: date | None = None,
) -> dict[str, Any]:
    """The fields of one correction to a promise, for the person's own `record.edit`. A new date drops the words the old
    one was read from and the doubt about them, since the person chose this one. Only what differs is returned."""
    fields: dict[str, Any] = {}
    if owner is not None and [o.get("person") for o in current.get("owners") or []] != [owner]:
        fields["owners"] = [{"person": owner}]
    if promised_to is not None:
        fields["promised_to"] = list(promised_to)
    if basis is not None:
        fields["basis"] = basis
    if due is not None:
        fields |= {"due": due.isoformat(), "due_words": None, "due_check": False}
    return {k: v for k, v in fields.items() if k == "owners" or current.get(k) != v}
