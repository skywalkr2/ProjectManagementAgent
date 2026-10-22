"""The morning brief, the evening wrap-up and the Monday briefing (design 6.32), built from the records by rules.

Nothing here calls AI, reaches a service or writes. The brief reads what the other parts already work out (Today's
queue, what changed since yesterday, this week's days, the clash finder, what an invitation changed) and does not
repeat their logic. Every line is data: a kind and its values for the screen to word from the wording sheet, with the
record or Today line it opens. No line reports status or progress.

**The morning brief** has three sections, in this order: *changed* overnight (what someone else did to the person's own
things, and what changed in an invitation), *risk* today (the person's own to-dos due today or late, what others owe
them that is late, and meetings that overlap), and *yes* (what waits for the person's yes, each one Today's own line).
An empty section is left out and a quiet day is one line.

**The evening wrap-up** has *done* today (credited to whoever did it), *moved* (a date moved ahead today, and what is
due today and still open) and *waiting* (what others owe the person, and the questions sent that nobody has answered).
It is quiet when nothing moved and nobody is waited on.

**The Monday briefing** is the weekly form: the person's promises through the last working day, what others promised
them, the questions held to send, the answers to chase and the decisions waiting, overdue first, with nothing that is
already a line on Today repeated (it is counted in `on_today`). It carries the goals for the week, proposed from what is
due and open until the person confirms them, and the message to whoever the person reports to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from engine import clashes as clash_rules
from engine import invitation_changes, since_yesterday, week_plan
from engine.blocked import standing_hold
from engine.config.schema import WEEKDAYS
from engine.connectors import moment as parse_moment
from engine.firm_due import firm_due
from engine.names import People
from engine.records import entry_time
from engine.today import agenda, zone

FORMS = ("morning", "evening", "monday")

#: The kinds of Today line that wait for the person's yes: a decision, a question or a held change, and a message
#: ready to send or a reply drafted.
YES_KINDS = ("decision", "question", "who_is", "owner", "held", "reply", "send", "nudge", "escalate")
#: Of those, the kinds whose line carries a message the assistant already wrote.
READY_KINDS = ("send", "nudge", "escalate")
#: What a change to an invitation says in the brief; the others (who replied, who was added) are not news.
INVITATION_NEWS = (
    "cancelled",
    "restored",
    "moved",
    "now_timed",
    "now_all_day",
    "end_changed",
    "location_changed",
    "location_removed",
    "title_changed",
    "organizer_changed",
)


@dataclass
class Line:
    """One thing in a section: its `kind` (and `change`, `state` or `on` when the kind has variants), the words it
    names (`text`, `person_name`, `other`, `detail`), the days and times it is about (`day`, `at`, and for a move
    `from_day` and `from_at`), how many days (`days`) or minutes (`minutes`) or things (`count`), the Today line it
    opens (`queue`) or the record it opens (`link`), `ready` when a message is already drafted for it and `you` when it
    is the person themselves who owns it or did it."""

    key: str
    kind: str
    text: str | None = None
    person: str | None = None
    person_name: str | None = None
    other: str | None = None
    detail: str | None = None
    change: str | None = None
    state: str | None = None
    day: str | None = None
    at: str | None = None
    from_day: str | None = None
    from_at: str | None = None
    days: int | None = None
    minutes: int | None = None
    count: int | None = None
    queue: str | None = None
    link: tuple[str, str] | None = None
    ready: bool = False
    you: bool = False


@dataclass
class Section:
    """A heading's lines, `more` being how many more there are than the configured most a section shows."""

    key: str
    lines: list[Line] = field(default_factory=list)
    more: int = 0


@dataclass
class Goals:
    """The week's goals: `confirmed` ones the person gave, else `proposed` from what is due and open, between `fewest`
    and `most`."""

    first: date
    last: date
    confirmed: bool
    goals: list[str]
    proposed: list[str]
    fewest: int
    most: int


@dataclass
class Brief:
    """A form of the brief as of a day. `forms` are the forms that can show now, the one shown first; `form` is none
    when nothing is due yet. `quiet` is a day with nothing to say (its one line is the wording sheet's). `on_today`
    counts what the Monday briefing left out because Today holds it."""

    form: str | None
    day: date
    forms: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    quiet: bool = False
    on_today: int = 0
    goals: Goals | None = None
    message: week_plan.Message | None = None


def _clock(text: str) -> time:
    hour, minute = text.split(":")
    return time(int(hour), int(minute))


def available(cfg: Any, now: datetime, goals_confirmed: bool = False) -> list[str]:
    """The forms that can show at `now`, the one to open with first: the evening wrap-up from its time on; before it,
    the Monday briefing on its day and then the morning brief, or the morning brief with the Monday briefing beside it
    on a later working day of the week while the week's goals aren't confirmed (it hasn't been used yet), or only the
    morning brief; none before the morning time."""
    rule = cfg.steward.brief
    if not rule.enabled:
        return []
    local = now.astimezone(zone(cfg))
    clock = local.time().replace(second=0, microsecond=0)
    if clock >= _clock(rule.evening_from):
        return ["evening"]
    if clock < _clock(rule.morning_from):
        return []
    weekly = WEEKDAYS.index(rule.weekly_day)
    if local.weekday() == weekly:
        return ["monday", "morning"]
    first = WEEKDAYS.index(cfg.steward.reminders.working_first_day)
    last = WEEKDAYS.index(cfg.steward.reminders.working_last_day)
    since = (local.weekday() - weekly) % 7
    return ["morning", "monday"] if 0 < since <= (last - first) % 7 and not goals_confirmed else ["morning"]


def overnight_start(cfg: Any, now: datetime) -> datetime:
    """The evening time on the last working day before today: what changed since then is what changed overnight."""
    here = zone(cfg)
    today = now.astimezone(here).date()
    first = WEEKDAYS.index(cfg.steward.reminders.working_first_day)
    last = WEEKDAYS.index(cfg.steward.reminders.working_last_day)
    span = (last - first) % 7
    day = today - timedelta(days=1)
    for _ in range(7):
        if (day.weekday() - first) % 7 <= span:
            break
        day -= timedelta(days=1)
    return datetime.combine(day, _clock(cfg.steward.brief.overnight_from), tzinfo=here)


def _stamp(value: Any) -> datetime | None:
    try:
        found = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


class _Day:
    """What every form reads: the records, the people, the person's clock and Today's lines."""

    def __init__(self, ws: Any, store: Any, cfg: Any, now: datetime) -> None:
        self.ws, self.store, self.cfg, self.now = ws, store, cfg, now
        self.view = store.read()
        self.people = People(store, cfg)
        self.pm = self.people.pm
        self.here = zone(cfg)
        self.today = now.astimezone(self.here).date()
        self.first, self.last = week_plan.week_bounds(cfg, self.today)
        self._queue: list[Any] | None = None

    @property
    def queue(self) -> list[Any]:
        if self._queue is None:
            from engine.today_queue import queue

            self._queue = queue(self.ws, self.store, self.cfg, self.now)
        return self._queue

    def name(self, person: str | None) -> str | None:
        return self.people.name(person) if person else None

    def mine(self, data: dict[str, Any]) -> bool:
        return self.pm is not None and any(o.get("person") == self.pm for o in data.get("owners") or [])

    def open_actions(self) -> list[Any]:
        """The open actions that are not on hold and not a reply owed (which is a line on Today of its own)."""
        return [
            a
            for a in self.view.list("action")
            if a.data.get("status") == "open"
            and not a.data.get("reply_owed")
            and not standing_hold(self.view, a.data, self.people)
        ]

    def local_day(self, stamp: datetime) -> date:
        return stamp.astimezone(self.here).date()

    def clock_of(self, stamp: datetime) -> str:
        return stamp.astimezone(self.here).strftime("%H:%M")


def _cap(lines: list[Line], key: str, rule: Any) -> Section:
    most = rule.max_lines
    return Section(key, lines[:most], max(0, len(lines) - most))


# ---- the morning brief ---------------------------------------------------------------------------------------------


def _event_state(data: dict[str, Any], here: Any) -> invitation_changes.Invitation:
    """An event record as an invitation (attendees are left out: who replied is not news)."""

    def when(value: Any, *, end: bool = False, all_day: bool = False) -> date | datetime | None:
        if not value:
            return None
        found = entry_time(str(value))
        if isinstance(found, datetime):
            return found if found.tzinfo else found.replace(tzinfo=here)
        return found + timedelta(days=1) if end and all_day else found

    start = entry_time(str(data["start"])) if data.get("start") else None
    all_day = start is not None and not isinstance(start, datetime)
    organizer = data.get("organizer") or {}
    return invitation_changes.Invitation(
        summary=data.get("title"),
        start=when(data.get("start")),
        end=when(data.get("end"), end=True, all_day=all_day),
        location=data.get("where"),
        organizer=invitation_changes.Person(organizer["address"], organizer.get("name"))
        if organizer.get("address")
        else None,
        attendees=(),
        cancelled=bool(data.get("cancelled")),
    )


def _local_parts(value: Any) -> tuple[str | None, str | None]:
    """A change's time as a day and a clock time (none for an all-day date)."""
    if isinstance(value, dict) and value.get("at") is not None:
        return value["at"].date().isoformat(), value["at"].strftime("%H:%M")
    if isinstance(value, dict) and value.get("date") is not None:
        return value["date"].isoformat(), None
    return None, None


def _invitation_lines(c: _Day, since: datetime) -> list[tuple[datetime, Line]]:
    """What changed in the invitations the calendar entries came from, since `since`: a new invitation, and for one
    that was already there the changes `describe_change` names that matter."""
    rows: dict[str, list[dict[str, Any]]] = {}
    for row in c.view.ledger(kind="event"):
        if row["op"] == since_yesterday.CALENDAR_RULE:
            rows.setdefault(row["record_id"], []).append(row)
    found: list[tuple[datetime, Line]] = []
    for event in c.view.list("event"):
        data = event.data
        mine = rows.get(event.id)
        if not mine or not data.get("invitation") or not data.get("start"):
            continue
        recent = [r for r in mine if (_stamp(r["at"]) or since) > since]
        if not recent:
            continue
        when = max(_stamp(r["at"]) for r in recent)  # type: ignore[type-var]
        organizer = (data.get("organizer") or {}).get("name")
        try:
            new = _event_state(data, c.here)
            first_day, first_at = _local_parts(
                {"at": new.start.astimezone(c.here)} if isinstance(new.start, datetime) else {"date": new.start}
            )
            if first_day is not None and first_day < c.today.isoformat():
                continue
            if any(r["version"] == 1 for r in recent):
                if not data.get("cancelled"):
                    found.append(
                        (
                            when,
                            Line(
                                f"invitation:{event.id}:new",
                                "invitation",
                                change="new",
                                text=data["title"],
                                person_name=organizer,
                                day=first_day,
                                at=first_at,
                                link=("event", event.id),
                            ),
                        )
                    )
                continue
            before = dict(data)
            for row in sorted(recent, key=lambda r: r["seq"], reverse=True):
                if row["field"] is not None:
                    before[row["field"]] = row["before"]
            old = _event_state(before, c.here)
            changes = invitation_changes.describe_change(old, new, c.here)
            moved_start = any(x.kind in ("moved", "now_timed", "now_all_day") for x in changes)
            for change in changes:
                if change.kind not in INVITATION_NEWS or (change.kind == "end_changed" and moved_start):
                    continue
                values = change.values
                if change.kind in ("moved", "now_timed", "now_all_day"):
                    day, at = _local_parts(values.get("after") or values.get("start"))
                    from_day, from_at = _local_parts(values.get("before"))
                elif change.kind == "end_changed":
                    day, at = _local_parts(values.get("after"))
                    from_day, from_at = _local_parts(values.get("before"))
                else:
                    day, at, from_day, from_at = first_day, first_at, None, None
                found.append(
                    (
                        when,
                        Line(
                            f"invitation:{event.id}:{change.kind}",
                            "invitation",
                            change=change.kind,
                            text=data["title"],
                            person_name=organizer,
                            detail=values.get("location") or values.get("title") or values.get("name"),
                            day=day,
                            at=at,
                            from_day=from_day,
                            from_at=from_at,
                            link=("event", event.id),
                        ),
                    )
                )
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    return found


def _changed(c: _Day) -> list[Line]:
    since = overnight_start(c.cfg, c.now)
    found: list[tuple[datetime, Line]] = []
    plan = since_yesterday.build(c.ws, c.view, c.cfg, c.people, c.now)
    for e in plan.entries:
        when = _stamp(e.when)
        if when is None or when <= since or e.by_you or e.act not in ("closed", "moved", "news"):
            continue
        line = Line(
            f"since:{e.ref}",
            e.act,
            text=e.title,
            person=e.said_by,
            person_name=e.said_by_name,
            change=e.because,
            day=e.day,
            detail=e.detail,
            link=e.record,
        )
        found.append((when, line))
    found += _invitation_lines(c, since)
    found.sort(key=lambda pair: (pair[0], pair[1].key), reverse=True)
    return [line for _, line in found]


def _meeting_time(c: _Day, event_id: str | None, day: date) -> str | None:
    """The clock time of the meeting an action is due at, when it is on that day."""
    found = c.view.get("event", event_id) if event_id else None
    if found is None or not found.data.get("start"):
        return None
    try:
        start = entry_time(str(found.data["start"]))
    except ValueError:
        return None
    if not isinstance(start, datetime):
        return None
    local = start if start.tzinfo else start.replace(tzinfo=c.here)
    local = local.astimezone(c.here)
    return local.strftime("%H:%M") if local.date() == day else None


def _clashes(c: _Day) -> list[Line]:
    items = [a for a in agenda(c.store, c.cfg, c.now, through=c.today) if not a.cancelled and not a.all_day and a.end]
    events: dict[str, Any] = {}
    for a in items:
        try:
            start, end = parse_moment(a.start), parse_moment(a.end)
        except ValueError:
            continue
        key = f"{a.snapshot}#{a.start}"
        events[key] = (a, clash_rules.Event(key, a.source or "own", start, end, "busy", a.where))
    report = clash_rules.clashes([e for _, e in events.values()])
    lines = []
    for clash in report.blocking:
        if clash.overlap_minutes <= 0:
            continue
        first, second = events[clash.first.id][0], events[clash.second.id][0]
        later = max(clash.first.start, clash.second.start).astimezone(c.here)
        lines.append(
            Line(
                f"clash:{first.snapshot}:{second.snapshot}",
                "clash",
                text=first.title,
                other=second.title,
                minutes=round(clash.overlap_minutes),
                day=later.date().isoformat(),
                at=later.strftime("%H:%M"),
                link=("event", first.entry or first.snapshot) if (first.entry or first.own) else None,
            )
        )
    return lines


def _risk(c: _Day) -> list[Line]:
    lines: list[Line] = []
    due: list[tuple[date, str, Line]] = []
    for a in c.open_actions():
        d = a.data
        day = firm_due(d)
        if day is None or day > c.today or not c.mine(d):
            continue
        to = next((p for p in d.get("promised_to") or [] if p != c.pm), None)
        due.append(
            (
                day,
                d["text"].lower(),
                Line(
                    f"own:{a.id}",
                    "own_due",
                    text=d["text"],
                    person=to,
                    person_name=c.name(to),
                    state="today" if day == c.today else "overdue",
                    day=day.isoformat(),
                    days=(c.today - day).days,
                    at=_meeting_time(c, d.get("due_event"), day),
                    link=("action", a.id),
                ),
            )
        )
    lines += [line for _, _, line in sorted(due, key=lambda t: (t[0], t[1], t[2].key))]
    seen: set[str] = set()
    for q in c.queue:
        if q.kind not in ("promise", "nudge", "escalate"):
            continue
        for action_id in q.actions:
            found = c.view.get("action", action_id)
            if found is None or action_id in seen or found.data.get("status") != "open" or c.mine(found.data):
                continue
            day = firm_due(found.data)
            if day is None or day >= c.today:
                continue
            seen.add(action_id)
            who = next((o["person"] for o in found.data.get("owners") or [] if o.get("person")), None)
            lines.append(
                Line(
                    f"owed:{action_id}",
                    "owed_late",
                    text=found.data["text"],
                    person=who,
                    person_name=c.name(who),
                    day=day.isoformat(),
                    days=(c.today - day).days,
                    queue=q.key,
                    link=("action", action_id),
                )
            )
    lines += _clashes(c)
    return lines


def _yes(c: _Day) -> list[Line]:
    lines = []
    for q in c.queue:
        if q.kind not in YES_KINDS:
            continue
        lines.append(
            Line(
                f"yes:{q.key}",
                "yes",
                change=q.kind,
                text=q.text,
                person=q.person,
                person_name=c.name(q.person),
                count=q.count,
                queue=q.key,
                ready=q.kind in READY_KINDS or (q.kind == "reply" and bool(q.reply)),
            )
        )
    return lines


def _morning(c: _Day) -> Brief:
    rule = c.cfg.steward.brief
    sections = [
        _cap(_changed(c), "changed", rule),
        _cap(_risk(c), "risk", rule),
        _cap(_yes(c), "yes", rule),
    ]
    sections = [s for s in sections if s.lines]
    brief = Brief("morning", c.today, sections=sections, quiet=not sections)
    confirmed = week_plan.goals_of(c.view, c.pm, c.first)
    if confirmed:
        brief.goals = Goals(c.first, c.last, True, confirmed, [], rule.goals_min, rule.goals_max)
    return brief


# ---- the evening wrap-up -------------------------------------------------------------------------------------------


def _done(c: _Day) -> list[Line]:
    found: dict[str, tuple[datetime, Line]] = {}
    for row in c.view.ledger(kind="action"):
        if row["field"] != "status" or row["after"] != "done" or row["version"] == 1:
            continue
        when = _stamp(row["at"])
        if when is None or c.local_day(when) != c.today:
            continue
        action = c.view.get("action", row["record_id"])
        if action is None or action.data.get("status") != "done":
            continue
        d = action.data
        if not (c.mine(d) or c.pm in (d.get("promised_to") or [])):
            continue
        doers = list(d.get("done_by") or [])
        if not doers and d.get("reported_by") and d["reported_by"] != c.pm:
            doers = [d["reported_by"]]
        you = c.pm in doers or (not doers and c.mine(d))
        who = None
        if not you:
            who = next(iter(doers), None) or next((o["person"] for o in d.get("owners") or [] if o.get("person")), None)
        line = Line(
            f"done:{action.id}",
            "done",
            text=d["text"],
            person=who,
            person_name=c.name(who),
            you=you,
            link=("action", action.id),
        )
        found[action.id] = (when, line)
    return [line for _, line in sorted(found.values(), key=lambda pair: (pair[0], pair[1].key))]


def _moved(c: _Day) -> list[Line]:
    lines: list[Line] = []
    seen: set[str] = set()
    for row in c.view.ledger(kind="action"):
        if row["field"] != "due" or row["version"] == 1 or row["before"] is None:
            continue
        when = _stamp(row["at"])
        if when is None or c.local_day(when) != c.today:
            continue
        action = c.view.get("action", row["record_id"])
        if action is None or action.id in seen or action.data.get("status") != "open" or not c.mine(action.data):
            continue
        day = firm_due(action.data)
        if day is None or day <= c.today:
            continue
        seen.add(action.id)
        lines.append(
            Line(
                f"moved:{action.id}",
                "moved_ahead",
                text=action.data["text"],
                day=day.isoformat(),
                link=("action", action.id),
            )
        )
    for a in c.open_actions():
        if a.id not in seen and c.mine(a.data) and firm_due(a.data) == c.today:
            lines.append(
                Line(f"carried:{a.id}", "carried", text=a.data["text"], day=c.today.isoformat(), link=("action", a.id))
            )
    return lines


def _waiting(c: _Day) -> list[Line]:
    lines: list[tuple[date, str, Line]] = []
    far = date.max
    for a in c.open_actions():
        d = a.data
        if c.mine(d) or c.pm not in (d.get("promised_to") or []):
            continue
        who = next((o["person"] for o in d.get("owners") or [] if o.get("person")), None)
        day = firm_due(d)
        lines.append(
            (
                day or far,
                d["text"].lower(),
                Line(
                    f"waiting:{a.id}",
                    "waiting",
                    text=d["text"],
                    person=who,
                    person_name=c.name(who),
                    day=day.isoformat() if day else None,
                    link=("action", a.id),
                ),
            )
        )
    for q in c.view.list("question"):
        d = q.data
        if d.get("status") != "sent" or d.get("to") == c.pm or not d.get("sent_at"):
            continue
        sent = _stamp(d["sent_at"])
        lines.append(
            (
                far,
                d["title"].lower(),
                Line(
                    f"waiting:{q.id}",
                    "waiting_answer",
                    text=d["title"],
                    person=d["to"],
                    person_name=c.name(d["to"]),
                    days=(c.today - c.local_day(sent)).days if sent else None,
                    link=("question", q.id),
                ),
            )
        )
    return [line for _, _, line in sorted(lines, key=lambda t: (t[0], t[1], t[2].key))]


def _evening(c: _Day) -> Brief:
    rule = c.cfg.steward.brief
    moved, waiting = _moved(c), _waiting(c)
    sections = [_cap(_done(c), "done", rule), _cap(moved, "moved", rule), _cap(waiting, "waiting", rule)]
    return Brief("evening", c.today, sections=[s for s in sections if s.lines], quiet=not moved and not waiting)


# ---- the Monday briefing -------------------------------------------------------------------------------------------


def _on_today(c: _Day) -> set[str]:
    """The ids of the actions and questions Today already holds a line for."""
    ids: set[str] = set()
    for q in c.queue:
        ids.update(q.actions)
        ids.update(q.questions)
        if q.question:
            ids.add(q.question)
    return ids


def _proposed(c: _Day) -> list[str]:
    """Up to the most goals, from the person's own open to-dos due through the week, soonest first."""
    found = []
    for a in c.open_actions():
        day = firm_due(a.data)
        if c.mine(a.data) and day is not None and day <= c.last:
            found.append((day, a.data["text"].lower(), a.data["text"]))
    seen: set[str] = set()
    proposed = []
    for _, key, text in sorted(found):
        if key not in seen:
            seen.add(key)
            proposed.append(text)
    return proposed[: c.cfg.steward.brief.goals_max]


def _monday(c: _Day) -> Brief:
    rule = c.cfg.steward.brief
    held = _on_today(c)
    left_out = 0
    yours: list[tuple[date, str, Line]] = []
    owed: list[tuple[date, str, Line]] = []
    for a in c.open_actions():
        d = a.data
        day = firm_due(d)
        if day is None or day > c.last:
            continue
        if a.id in held:
            left_out += 1
            continue
        mine = c.mine(d)
        to = next((p for p in d.get("promised_to") or [] if p != c.pm), None)
        who = next((o["person"] for o in d.get("owners") or [] if o.get("person") and o["person"] != c.pm), None)
        if not mine and c.pm not in (d.get("promised_to") or []):
            continue
        person = to if mine else who
        line = Line(
            f"week:{a.id}",
            "week_promise",
            text=d["text"],
            person=person,
            person_name=c.name(person),
            state="overdue" if day < c.today else "due",
            day=day.isoformat(),
            days=max(0, (c.today - day).days),
            you=mine,
            link=("action", a.id),
        )
        (yours if mine else owed).append((day, d["text"].lower(), line))
    send: list[Line] = []
    chase: list[Line] = []
    decide: list[Line] = []
    for q in c.view.list("question"):
        d = q.data
        if d.get("status") not in ("open", "sent"):
            continue
        if q.id in held:
            left_out += 1
            continue
        about_me = d.get("to") == c.pm
        if d["status"] == "open" and about_me and d.get("kind") == "decision":
            decide.append(Line(f"week:{q.id}", "decision", text=d["title"], link=("question", q.id)))
        elif d["status"] == "open" and not about_me:
            held_for = (d.get("held_for") or {}).get("on")
            if held_for and held_for > c.last.isoformat():
                continue
            send.append(
                Line(
                    f"week:{q.id}",
                    "send_question",
                    text=d["title"],
                    person=d["to"],
                    person_name=c.name(d["to"]),
                    link=("question", q.id),
                )
            )
        elif d["status"] == "sent" and not about_me:
            sent = _stamp(d.get("sent_at"))
            chase.append(
                Line(
                    f"week:{q.id}",
                    "chase_answer",
                    text=d["title"],
                    person=d["to"],
                    person_name=c.name(d["to"]),
                    days=(c.today - c.local_day(sent)).days if sent else None,
                    link=("question", q.id),
                )
            )
    ordered = [sorted(group, key=lambda t: (t[0], t[1], t[2].key)) for group in (yours, owed)]
    sections = [
        _cap([line for _, _, line in ordered[0]], "yours", rule),
        _cap([line for _, _, line in ordered[1]], "owed", rule),
        _cap(send, "send", rule),
        _cap(chase, "chase", rule),
        _cap(decide, "decide", rule),
    ]
    sections = [s for s in sections if s.lines]
    confirmed = week_plan.goals_of(c.view, c.pm, c.first)
    goals = Goals(
        c.first, c.last, bool(confirmed), confirmed, [] if confirmed else _proposed(c), rule.goals_min, rule.goals_max
    )
    return Brief(
        "monday",
        c.today,
        sections=sections,
        quiet=not sections,
        on_today=left_out,
        goals=goals,
        message=week_plan.message_of(c.view, c.cfg, c.store, c.now),
    )


def build(ws: Any, store: Any, cfg: Any, now: datetime, form: str | None = None) -> Brief:
    """A form of the brief as of `now`: the one due now when none is named, or the one asked for. Reads only."""
    c = _Day(ws, store, cfg, now)
    forms = available(cfg, now, bool(week_plan.goals_of(c.view, c.pm, c.first)))
    chosen = form if form is not None else (forms[0] if forms else None)
    if chosen is None:
        return Brief(None, c.today, forms=forms)
    if chosen not in FORMS:
        raise ValueError(f"there is no {chosen} form of the brief")
    made = {"morning": _morning, "evening": _evening, "monday": _monday}[chosen](c)
    made.forms = forms or [chosen]
    return made
