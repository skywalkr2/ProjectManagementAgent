"""The person's plan for a week (design 6.32, the Monday briefing): the goals they confirm and the message to whoever
they report to.

Both live on one `week_plan` record for the person and the week, named by the week's first working day.

- **Goals** are the person's own words, three to five (`steward.brief.goals_min` and `goals_max`) confirmed at once as
  theirs, with Undo. Nothing proposes them into the record: the briefing offers a few from what is due and open, and the
  person confirms, changes or drops them. A week with fewer than the fewest has no confirmed goals.
- **The message** is a draft the assistant writes to the people the person reports to (stance `report_to`, 6.34), from
  what was done, what moved and what needs them. It is one request of the `monday-message` kind: estimated, held for the
  person's go above the configured amount, filed as a pending draft of the record's `message` text. It is never sent
  from here; the person copies it, which marks it reviewed.

Nothing here reaches a service.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.config.schema import WEEKDAYS
from engine.names import People
from engine.scope import stance_of
from engine.storage import StoreError, WriteContext
from engine.texts import current, read_text, versions
from engine.today import zone

TASK = "monday-message"
_PERSON = WriteContext(actor="pm", trust="trusted", op="week.goals")
_QUEUE = WriteContext(actor="pm", trust="trusted", op="week.message")
#: The request states in which the assistant still has the message, or the person has to act before it can go on.
IN_HAND = ("queued", "running", "needs_you")
#: The most one goal may say; longer is cut at a word.
GOAL_LIMIT = 200


class GoalsError(ValueError):
    """The goals can't be kept as given; the message says why in plain words."""


def week_bounds(cfg: Any, today: date) -> tuple[date, date]:
    """The first and the last working day of the week `today` belongs to: the week that ends on the configured last
    working day on or after today, so a day after it belongs to the next week."""
    first = WEEKDAYS.index(cfg.steward.reminders.working_first_day)
    last = WEEKDAYS.index(cfg.steward.reminders.working_last_day)
    end = today + timedelta(days=(last - today.weekday()) % 7)
    return end - timedelta(days=(last - first) % 7), end


def plan_of(view: Any, person: str | None, week: date) -> Any | None:
    """The person's record for a week, if there is one."""
    for record in view.list("week_plan"):
        if record.data.get("person") == person and str(record.data["week"]) == week.isoformat():
            return record
    return None


def goals_of(view: Any, person: str | None, week: date) -> list[str]:
    """The goals the person confirmed for a week, in their order; none until they have."""
    found = plan_of(view, person, week)
    if found is None or not found.data.get("confirmed_at"):
        return []
    return list(found.data.get("goals") or [])


def _clean(goals: list[str], cfg: Any) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for goal in goals:
        words = " ".join(str(goal).split())
        if len(words) > GOAL_LIMIT:
            words = words[:GOAL_LIMIT].rsplit(" ", 1)[0] or words[:GOAL_LIMIT]
        if words and words.casefold() not in seen:
            seen.add(words.casefold())
            kept.append(words)
    rule = cfg.steward.brief
    if kept and len(kept) < rule.goals_min:
        raise GoalsError(f"Give at least {rule.goals_min} goals for the week, or none to leave them out.")
    if len(kept) > rule.goals_max:
        raise GoalsError(f"Give at most {rule.goals_max} goals for the week: pick the ones that matter most.")
    return kept


def set_goals(store: Any, cfg: Any, goals: list[str], now: datetime) -> list[str]:
    """Confirm the goals for the week `now` falls in, as the person's own. An empty list takes the week's goals back
    out. Returns the goals the week held before, which Undo gives back to this same call."""
    kept = _clean(goals, cfg)
    person = People(store, cfg).pm
    week, _ = week_bounds(cfg, now.astimezone(zone(cfg)).date())
    stamp = now.astimezone(UTC).isoformat()
    with store.transaction() as tx:
        found = plan_of(tx, person, week)
        before = goals_of(tx, person, week)
        values = {"goals": kept, "confirmed_at": stamp if kept else None}
        if found is None:
            if kept:
                tx.create("week_plan", {"person": person, "week": week.isoformat(), **values}, _PERSON)
        else:
            tx.update("week_plan", found.id, values, _PERSON, read_version=found.version)
    return before


def report_to(view: Any, cfg: Any) -> list[str]:
    """The people the person reports to (their stance is "I report to them"), by name."""
    me = cfg.workspace.user.person
    names = {p.id: p.data.get("full_name") or p.id for p in view.list("person")}
    found = [p.id for p in view.list("person") if p.id != me and stance_of(view, cfg.steward, p.id) == "report_to"]
    return sorted(found, key=lambda i: (str(names[i]).lower(), i))


def _requests(view: Any, plan_id: str) -> list[Any]:
    return [
        r
        for r in view.list("request")
        if r.data["task"] == TASK and (r.data.get("about") or {}).get("id") == plan_id and not r.data.get("dismissed")
    ]


def pending_draft(view: Any, plan_id: str) -> Any | None:
    """The draft of the message that waits for the person's review, if there is one."""
    waiting = [v for v in versions(view, "week_plan", plan_id, "message") if v.data["status"] == "pending"]
    return waiting[-1] if waiting else None


def with_the_assistant(view: Any, plan_id: str) -> bool:
    """Whether the assistant has the message in hand: a request not finished with, or a draft awaiting review."""
    for r in _requests(view, plan_id):
        if r.data["state"] in IN_HAND or (r.data["state"] == "review" and pending_draft(view, plan_id) is not None):
            return True
    return False


@dataclass(frozen=True)
class Message:
    """Where the Monday message stands. `state`: none (nobody has asked for it), working (queued or running),
    needs_go (held for the person's go, with the estimate when there is one), draft (a draft waits: `draft` is its
    version, `read_version` the version of that record, `text` its words) or kept (the person copied it: `text` is what
    they kept). `to` are the people it is for."""

    state: str
    to: tuple[str, ...]
    request: str | None = None
    draft: str | None = None
    read_version: int | None = None
    text: str | None = None
    estimate_usd: float | None = None


def message_of(view: Any, cfg: Any, store: Any, now: datetime) -> Message | None:
    """The message's state for this week, or None when the person reports to nobody (so no message is written)."""
    to = tuple(report_to(view, cfg))
    if not to:
        return None
    person = People(store, cfg).pm
    week, _ = week_bounds(cfg, now.astimezone(zone(cfg)).date())
    plan = plan_of(view, person, week)
    if plan is None:
        return Message("none", to)
    draft = pending_draft(view, plan.id)
    for r in sorted(_requests(view, plan.id), key=lambda r: (str(r.data["created_at"]), r.id), reverse=True):
        if r.data["state"] in ("queued", "running"):
            return Message("working", to, request=r.id)
        if r.data["state"] == "needs_you" and r.data.get("approval") == "required":
            return Message("needs_go", to, request=r.id, estimate_usd=r.data.get("estimate_usd"))
        if r.data["state"] == "review" and draft is not None:
            return Message(
                "draft",
                to,
                request=r.id,
                draft=draft.id,
                read_version=draft.version,
                text=read_text(store, draft.data["sha256"]),
            )
    kept = current(view, "week_plan", plan.id, "message")
    if kept is not None:
        return Message("kept", to, text=read_text(store, kept.data["sha256"]))
    return Message("none", to)


def ask_for_message(store: Any, cfg: Any, now: datetime, note: str | None = None) -> str:
    """Queue the request for this week's message to the people the person reports to; returns its id. The record for the
    week is made when there is none. Nothing is sent or kept until the person reads the draft."""
    words = " ".join((note or "").split())[:2000] or None
    person = People(store, cfg).pm
    week, _ = week_bounds(cfg, now.astimezone(zone(cfg)).date())
    with store.transaction() as tx:
        if not report_to(tx, cfg):
            raise StoreError("There is nobody marked as someone you report to, so there is no message to write.")
        found = plan_of(tx, person, week)
        plan_id = (
            found.id
            if found is not None
            else tx.create("week_plan", {"person": person, "week": week.isoformat()}, _PERSON).id
        )
        if with_the_assistant(tx, plan_id):
            raise StoreError("The assistant already has this week's message in hand.")
        made = tx.create(
            "request",
            {
                "task": TASK,
                "about": {"kind": "week_plan", "id": plan_id},
                "note": words,
                "origin": "pm",
                "state": "queued",
                "waiting": "With the assistant, starting now",
                "created_at": store.clock(),
            },
            _QUEUE,
        )
    return made.id


def copied(store: Any, cfg: Any, now: datetime) -> bool:
    """The person copied the message: the draft waiting for review is theirs as it is. Returns whether there was one."""
    from engine.applier import apply_as_person

    person = People(store, cfg).pm
    week, _ = week_bounds(cfg, now.astimezone(zone(cfg)).date())
    view = store.read()
    plan = plan_of(view, person, week)
    draft = pending_draft(view, plan.id) if plan is not None else None
    if draft is None:
        return False
    op = {"op": "text.accept", "version": draft.id, "read_version": draft.version, "choices": {}}
    apply_as_person(store, cfg, [op], "Copied the Monday message")
    return True


# ---- the packet ---------------------------------------------------------------------------------------------------


def _marked(text: str) -> str:
    """Text that can't close the marking it sits in."""
    return text.replace("</untrusted", "</ untrusted")


def facts(store: Any, cfg: Any, now: datetime) -> str:
    """What the message is written from, as the assistant is shown it: what was finished and moved in the last seven
    days, what the person has promised for this week and what waits on them. Plain lines, from the records; data, never
    instruction."""
    from engine.blocked import standing_hold
    from engine.firm_due import firm_due

    view = store.read()
    people = People(store, cfg)
    pm = people.pm
    here = zone(cfg)
    today = now.astimezone(here).date()
    _, last = week_bounds(cfg, today)
    since = now - timedelta(days=7)

    def stamp(value: Any) -> datetime | None:
        try:
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        return moment if moment.tzinfo else moment.replace(tzinfo=UTC)

    done: list[str] = []
    moved: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in view.ledger(kind="action"):
        moment = stamp(row["at"])
        if moment is None or not since <= moment <= now:
            continue
        action = view.get("action", row["record_id"])
        if action is None or not any(o.get("person") == pm for o in action.data.get("owners") or []):
            continue
        if row["field"] == "status" and row["after"] == "done" and (row["record_id"], "done") not in seen:
            seen.add((row["record_id"], "done"))
            done.append(action.data["text"])
        if row["field"] == "due" and action.data.get("status") == "open" and (row["record_id"], "due") not in seen:
            seen.add((row["record_id"], "due"))
            moved.append(f"{action.data['text']} (now due {action.data.get('due') or 'with no day'})")
    ahead: list[str] = []
    waiting: list[str] = []
    for action in view.list("action"):
        d = action.data
        if d.get("status") != "open" or standing_hold(view, d, people):
            continue
        day = firm_due(d)
        mine = any(o.get("person") == pm for o in d.get("owners") or [])
        if mine and day is not None and day <= last:
            ahead.append(f"{d['text']} (due {day.isoformat()})")
        if not mine and pm in (d.get("promised_to") or []):
            owner = ", ".join(people.name(o["person"]) for o in d.get("owners") or [] if o.get("person"))
            waiting.append(f"{owner}: {d['text']}" + (f" (due {day.isoformat()})" if day else ""))
    deciding = [
        q.data["title"]
        for q in view.list("question")
        if q.data.get("to") == pm and q.data.get("status") == "open" and q.data.get("kind") == "decision"
    ]
    goals = goals_of(view, pm, week_bounds(cfg, today)[0])
    names = ", ".join(people.name(p) for p in report_to(view, cfg))
    parts = [
        f"The message is for: {names}",
        f"The week ends on {last.isoformat()}.",
        "Finished in the last seven days:\n" + "\n".join(f"- {x}" for x in done) if done else "",
        "Dates that moved in the last seven days:\n" + "\n".join(f"- {x}" for x in moved) if moved else "",
        "Promised for this week:\n" + "\n".join(f"- {x}" for x in ahead) if ahead else "",
        "Promised to the person by others:\n" + "\n".join(f"- {x}" for x in waiting) if waiting else "",
        "Decisions waiting on the person:\n" + "\n".join(f"- {x}" for x in deciding) if deciding else "",
        "Goals the person confirmed for the week:\n" + "\n".join(f"- {x}" for x in goals) if goals else "",
    ]
    return "\n\n".join(p for p in parts if p)


def build(ws: Any, store: Any, cfg: Any, req: Any, kind: Any, today: date) -> Any:
    """The packet for one run. Stable first: the instructions, the practice, what has been learned, the people and the
    projects. Then the request: the week's facts (data, marked as from outside), the text kept so far when there is
    one, and the person's note."""
    from engine.cleaning import Cleaned
    from engine.dispatcher import _data_level
    from engine.packet import DRAFT_RULE, Packet, PacketRefused, _guidance, _learned, _people, _projects, _task
    from engine.prompts import render

    about = req.data.get("about") or {}
    found = store.read().get("week_plan", about.get("id")) if about.get("kind") == "week_plan" else None
    if found is None:
        raise PacketRefused("the week this message was for is gone")
    if not report_to(store.read(), cfg):
        raise PacketRefused("nobody is marked as someone the person reports to")
    note = req.data.get("note") or ""
    moment = datetime.combine(today, datetime.min.time(), tzinfo=zone(cfg)) + timedelta(hours=12)
    shown = facts(store, cfg, moment)
    kept = current(store.read(), "week_plan", found.id, "message")
    kept_text = read_text(store, kept.data["sha256"]) if kept is not None else ""
    people = People(store, cfg)
    learned = _learned(
        store,
        cfg,
        kind,
        people,
        projects=[],
        source=None,
        text=f"{shown}\n{note}",
        today=today,
    )
    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    stable = "\n\n".join(
        part
        for part in (
            "# Practice\n" + _guidance(kind),
            learned.stable,
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )
    parts = [
        f"Today is {today.isoformat()} ({today.strftime('%A')}).",
        learned.per_input,
        f'# The week\n<untrusted source="records">\n{_marked(shown)}\n</untrusted>',
        f"# The text so far, which you revise\n<text>\n{kept_text.strip()}\n</text>" if kept_text.strip() else "",
        f"# The person's note\n<note>\n{note}\n</note>" if note else "",
        DRAFT_RULE,
    ]
    request = "\n\n".join(p for p in parts if p)
    task = replace(_task(cfg, store, kind, instructions, stable, request), knowledge=learned.log.model_dump())
    return Packet(
        task,
        request,
        Cleaned("", 0, 0, False, 0),
        note,
        too_long=False,
        untrusted_material=True,
        cites=f"week_plan:{found.id}",
        about=("week_plan", found.id),
        draft_base=kept.data["number"] if kept is not None else None,
        data_level=_data_level(store, req.data),
        knowledge=learned.log,
    )
