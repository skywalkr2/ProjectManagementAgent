"""Follow-ups by person (design 7.5): what each person has from the PM, and one clean message to copy.

The PM comes first (decisions and the PM's own actions), then everyone else A to Z. A copied message has a greeting,
the questions (numbered when there are several), the person's action items with project and due date, and a closing
line; its wording comes from config/language.yaml.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, tzinfo
from typing import Any

from engine import learn, outward, promises, sent_version
from engine.blocked import ViewNames, blocker_of, blocker_problem, holds_up
from engine.cleaning import normalize
from engine.config import Config
from engine.dispatcher import signal
from engine.names import People
from engine.promises import Late
from engine.scope import stance_of
from engine.storage import Store, WriteContext
from engine.today import local_day, zone

_PM = WriteContext(actor="pm", trust="trusted", op="followup")

#: The fields of an action whose change, after a person was told, means they need telling again, and the field that
#: records who was told.
TOLD_FIELDS = ("text", "due", "told")

#: Questions that hold an item until the PM says who: answered on the item itself.
ROUTING = ("held-op", "owner")


def follow_up_due(
    cfg: Config,
    today: date,
    *,
    waiting_days: int | None,
    action: bool = False,
    due: date | None = None,
    on_hold: bool = False,
) -> bool:
    """Whether something sent to a person is due a follow-up. This is the one rule Today's lines and the Follow-ups
    screen both use. `waiting_days` is the days since it went out with no word back (none when it hasn't gone out).
    A question is chased after `question_after_days`. An action is never chased while it is on hold; one with a due
    date is chased only when that date is within `action_due_within_days` or past, and after it has waited as long as a
    question; one with no due date is chased after `undated_after_days`."""
    if waiting_days is None or on_hold:
        return False
    rule = cfg.ui.followups
    if not action:
        return waiting_days >= rule.question_after_days
    if due is None:
        return waiting_days >= rule.undated_after_days
    return (due - today).days <= rule.action_due_within_days and waiting_days >= rule.question_after_days


@dataclass
class LeftOut:
    """Something that went in the same first message as what a nudge lists and was answered (a question) or done (an
    action) since, so the nudge leaves it out: its `kind`, `id` and `text`, and `on`, the day it was settled."""

    kind: str
    id: str
    text: str
    on: str


@dataclass
class Nudge:
    """A follow-up message to one person about what has gone unanswered as long as the follow-up rule says: its `text`,
    which follow-up it is (`round`: 1, or 2 and up once chased before), the ids of what it lists and what it leaves
    out because it was settled since."""

    text: str
    round: int
    question_ids: list[str]
    action_ids: list[str]
    left_out: list[LeftOut] = field(default_factory=list)


#: Stances (design 6.34) whose people are never told their actions in a drafted message.
UNTOLD_STANCES = frozenset({"watch", "report_to"})


@dataclass
class Section:
    person: str
    name: str
    is_pm: bool
    questions: list[dict[str, Any]] = field(default_factory=list)
    #: Open questions held for a meeting or a day, out of To send until it comes (`held_until` on each).
    later: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""
    to_send: int = 0
    nudge: Nudge | None = None


def actions_to_send(store: Store, cfg: Config) -> set[str]:
    """The ids of the open actions that are "to send" (design 6.10): an owner other than the person was never told about
    it, or was told something since changed, and is not someone the person only watches or reports to. The same
    reading as the Follow-ups groups make, for a row to carry as a marker."""
    view = store.read()
    people = People(store, cfg)
    open_actions = [a for a in view.list("action") if a.data["status"] == "open"]
    history = view.field_changes("action", TOLD_FIELDS) if any(a.data.get("told") for a in open_actions) else {}
    found = set()
    for a in open_actions:
        d = a.data
        for owner in d.get("owners", []):
            who = owner["person"]
            if who == people.pm or stance_of(view, cfg.steward, who) in UNTOLD_STANCES:
                continue
            told = d.get("told", {}).get(who)
            if told and changed_since_told(history.get(a.id, []), who, d):
                told = None
            if not told:
                found.add(a.id)
    return found


def _pulled(view: Any, cfg: Config, today: date, held_up: dict[str, list[str]], pm: str | None) -> dict[str, int]:
    """The blockers whose follow-up comes due because of what they hold up, each with how many of those actions are
    overdue. A blocked action is never chased itself; its chase clock goes to the question or action that holds it up,
    which comes due as the blocked action's would have: one the person owes, once its date is within the follow-up
    window or past; one someone else owes, by the follow-up rule on how long they have been told."""
    rule = cfg.ui.followups
    found: dict[str, int] = {}
    for blocker, held in held_up.items():
        for action_id in held:
            data = view.get("action", action_id).data
            due = date.fromisoformat(str(data["due"])) if data.get("due") else None
            would = False
            for owner in data.get("owners") or []:
                who = owner["person"]
                told = (data.get("told") or {}).get(who)
                if who == pm:
                    would = would or (due is not None and (due - today).days <= rule.action_due_within_days)
                elif told:
                    would = would or follow_up_due(
                        cfg,
                        today,
                        waiting_days=max(0, (today - date.fromisoformat(str(told))).days),
                        action=True,
                        due=due,
                    )
            if would:
                found[blocker] = found.get(blocker, 0) + int(due is not None and due < today)
    return found


def sections(store: Store, cfg: Config, today: date, waiting: list[Late] | None = None) -> list[Section]:
    """Each person's questions and actions with what is due a follow-up. An action someone else owes is also due one
    when the promise rule says it is late with nothing heard (design 6.33), so Today's one follow-up line per person and
    the message it opens cover the same things. `waiting`: that rule's list, when the caller already has it."""
    people = People(store, cfg)
    chase_for = {
        x.action: x.owner
        for x in (promises.waiting_on(store, cfg, today) if waiting is None else waiting)
        if promises.is_follow_up(x)
    }
    here = zone(cfg)
    held_up = holds_up(store.read(), people)
    pulled = _pulled(store.read(), cfg, today, held_up, people.pm)
    projects = {p.id: p.data["name"] for p in store.read().list("project")}
    project_links = {p.id: p.data.get("links", []) for p in store.read().list("project")}
    by_person: dict[str, Section] = {}

    def section(pid: str) -> Section:
        if pid not in by_person:
            by_person[pid] = Section(pid, people.name(pid), pid == people.pm)
        return by_person[pid]

    for q in store.read().list("question"):
        d = q.data
        if d["status"] not in ("open", "sent"):
            continue
        if (d.get("resolves") or {}).get("kind") in ROUTING:
            continue  # answered where the item waits (What changed), so it isn't shown twice
        sent = local_day(datetime.fromisoformat(d["sent_at"]), here) if d.get("sent_at") else None
        chased = sorted(str(day) for day in d.get("followed_up") or [])
        # The wait counts from the last word to the person: the message, or the latest chase after it.
        last_word = date.fromisoformat(chased[-1]) if chased else sent
        waiting = max(0, (today - last_word).days) if last_word else None
        held_until, held_name = held_until_day(store.read(), d.get("held_for"), today, here)
        later = d["status"] == "open" and held_until is not None and held_until > today
        (section(d["to"]).later if later else section(d["to"]).questions).append(
            {
                "held_until": held_until.isoformat() if later and held_until else None,
                "held_for_name": held_name if later else None,
                "id": q.id,
                "title": d["title"],
                "text": d.get("text", ""),
                "links": d.get("links", []),
                "kind": d["kind"],
                "status": d["status"],
                "project_name": ", ".join(projects[p] for p in d.get("projects", []) if p in projects),
                "sent": sent.isoformat() if sent else None,
                "followed_up": chased[-1] if chased else None,
                "chases": len(chased),
                "waiting_days": waiting,
                "chase_due": d["status"] == "sent"
                and (follow_up_due(cfg, today, waiting_days=waiting) or q.id in pulled),
                "holds_up": len(held_up.get(q.id, [])),
                "holds_overdue": pulled.get(q.id, 0),
                "options": d.get("options", []),
                "resolves": d.get("resolves"),
            }
        )
    open_actions = [a for a in store.read().list("action") if a.data["status"] == "open"]
    history = store.read().field_changes("action", TOLD_FIELDS) if any(a.data.get("told") for a in open_actions) else {}
    view = store.read()
    for a in open_actions:
        d = a.data
        for owner in d.get("owners", []):
            if owner["person"] != people.pm and stance_of(view, cfg.steward, owner["person"]) in UNTOLD_STANCES:
                continue  # nothing is drafted to someone the person only watches or reports to (design 6.34)
            told = d.get("told", {}).get(owner["person"])
            if told and changed_since_told(history.get(a.id, []), owner["person"], d):
                told = None  # what they were told is out of date, so they need telling again
            chases = (d.get("followed_up") or {}).get(owner["person"]) or []
            last_chase = str(max(chases)) if chases else None
            told_days = max(0, (today - date.fromisoformat(told)).days) if told else None
            hold = d.get("on_hold")
            blocker = blocker_of(view, hold, people, here)
            if blocker is not None and blocker.resolved:
                hold = None  # what it waited on is over, so it is chased by its own dates again
            section(owner["person"]).actions.append(
                {
                    "id": a.id,
                    "text": d["text"],
                    "due": d.get("due"),
                    "project": d.get("project"),
                    "project_name": projects.get(d.get("project"), ""),
                    "links": project_links.get(d.get("project"), []),
                    "told": told,
                    "first_told": _first_told(history.get(a.id, []), owner["person"], told),
                    "told_days": told_days,
                    "followed_up": last_chase,
                    "chases": len(chases),
                    "on_hold": hold["waiting_for"] if hold else None,
                    "blocker": asdict(blocker) if blocker is not None else None,
                    "chase_due": (chase_for.get(a.id) == owner["person"] and not hold)
                    or follow_up_due(
                        cfg,
                        today,
                        waiting_days=told_days,
                        action=True,
                        due=date.fromisoformat(str(d["due"])) if d.get("due") else None,
                        on_hold=bool(hold),
                    )
                    or (a.id in pulled and told_days is not None and owner["person"] != people.pm and not hold),
                    "holds_up": len(held_up.get(a.id, [])),
                    "holds_overdue": pulled.get(a.id, 0),
                }
            )
    for s in by_person.values():
        s.actions.sort(key=lambda a: (a["due"] or "9999", a["text"]))
        if not s.is_pm:
            s.to_send = sum(q["status"] == "open" for q in s.questions) + sum(a["told"] is None for a in s.actions)
            s.message = compose(s, cfg, people)
            s.nudge = compose_nudge(s, cfg, people, today)
    settled: list[dict[str, str]] | None = None
    for s in by_person.values():
        if s.nudge is not None:
            settled = _settled_since_sent(store, here) if settled is None else settled
            s.nudge.left_out = _left_out(s, settled)
    return sorted(by_person.values(), key=lambda s: (not s.is_pm, s.name.lower()))


def _day(stamp: str, here: tzinfo) -> str:
    """The day a stored time falls on where the workspace is, as an ISO date (a bare day stays as it is)."""
    return local_day(datetime.fromisoformat(stamp), here).isoformat() if "T" in stamp else stamp[:10]


def _first_told(history: list[dict[str, Any]], person: str, told: Any) -> str | None:
    """The day an action first went to `person`: the first day the ledger records for them as told, else the day they
    were last told (none when they weren't)."""
    first = next((row for row in history if row["field"] == "told" and person in (row["after"] or {})), None)
    return str(first["after"][person]) if first else (str(told) if told else None)


def _settled_since_sent(store: Store, here: tzinfo) -> list[dict[str, str]]:
    """Every question answered and every action done that had gone out to someone: for each, the person, the day it
    went to them (`sent_on`: a question's own, an action's first told day), its text and the day it was settled."""
    view = store.read()
    out: list[dict[str, str]] = []
    answered = view.field_changes("question", ("status",))
    for q in view.list("question"):
        d = q.data
        if d["status"] != "answered" or not d.get("sent_at"):
            continue
        closed = [row for row in answered.get(q.id, []) if row["after"] == "answered"]
        if closed:
            out.append(
                {
                    "kind": "question",
                    "id": q.id,
                    "person": d["to"],
                    "text": d["title"],
                    "sent_on": _day(str(d["sent_at"]), here),
                    "on": _day(closed[-1]["at"], here),
                }
            )
    finished = view.field_changes("action", ("status", "told"))
    for a in view.list("action"):
        d = a.data
        if d["status"] != "done":
            continue
        rows = finished.get(a.id, [])
        closed = [row for row in rows if row["field"] == "status" and row["after"] == "done"]
        if not closed:
            continue
        for person in d.get("told") or {}:
            first = next(
                (row for row in rows if row["field"] == "told" and person in (row["after"] or {})),
                None,
            )
            out.append(
                {
                    "kind": "action",
                    "id": a.id,
                    "person": person,
                    "text": d["text"],
                    "sent_on": str(first["after"][person]) if first else str(d["told"][person]),
                    "on": _day(closed[-1]["at"], here),
                }
            )
    return out


def _left_out(s: Section, settled: list[dict[str, str]]) -> list[LeftOut]:
    """What went out to this person in the same message as the nudge's items and has been settled since."""
    nudge = s.nudge
    if nudge is None:
        return []
    days = {q["sent"] for q in s.questions if q["id"] in nudge.question_ids and q["sent"]}
    days |= {a["first_told"] for a in s.actions if a["id"] in nudge.action_ids and a.get("first_told")}
    found = [
        LeftOut(x["kind"], x["id"], x["text"], x["on"])
        for x in settled
        if x["person"] == s.person and x["sent_on"] in days
    ]
    return sorted(found, key=lambda x: (x.on, x.id))


def changed_since_told(history: list[dict[str, Any]], person: str, current: dict[str, Any]) -> bool:
    """Whether an action's text or due date differs from what it was when `person` was last told. `history` is the
    ledger's changes to the action's text, due date and told days, oldest first. An action with no record of when the
    person was told, or of an earlier value, counts as unchanged."""

    def day(value: Any) -> str | None:
        return None if value is None else str(value)

    told_at = None
    for row in history:
        if row["field"] == "told" and day((row["after"] or {}).get(person)) != day((row["before"] or {}).get(person)):
            told_at = row["version"] if (row["after"] or {}).get(person) else None
    if told_at is None:
        return False
    for name in ("text", "due"):
        then = [row for row in history if row["field"] == name and row["version"] <= told_at]
        if then and day(then[-1]["after"]) != day(current.get(name)):
            return True
    return False


def compose(s: Section, cfg: Config, people: People) -> str:
    words = cfg.language.messages
    questions = [q for q in s.questions if q["status"] == "open"]
    actions = [a for a in s.actions if a["told"] is None]
    if not questions and not actions:
        return ""
    lines = [words.greeting.format(first_name=people.first_name(s.person)), ""]
    for n, q in enumerate(questions, 1):
        prefix = f"{n}. " if len(questions) > 1 else ""
        lines.append(prefix + q["title"])
        if q["text"]:
            lines.append(q["text"])
        lines += [f"{link['label']}: {link['url']}" for link in q["links"]]
        lines.append("")
    if actions:
        lines.append(words.actions_heading)
        for a in actions:
            bits = [a["project_name"]] if a["project_name"] else []
            if a["due"]:
                bits.append("due " + date.fromisoformat(a["due"]).strftime(words.date_format))
            lines.append(f"- {a['text']}" + (f" ({', '.join(bits)})" if bits else ""))
        lines.append("")
    lines.append(words.closing)
    return "\n".join(lines)


def compose_nudge(s: Section, cfg: Config, people: People, today: date) -> Nudge | None:
    """The follow-up message for one person, built from the settings' wording with no AI run: only what is still
    waiting and due a follow-up, numbered, with when it was first asked and an overdue due date said as a fact. A second
    or later follow-up lists only the longest-waiting few and asks who else to ask, or for a date. None when nothing is
    due."""
    words = cfg.language.messages
    shown = lambda day: date.fromisoformat(str(day)).strftime(words.date_format)  # noqa: E731
    due = [
        *(("question", q["id"], q["title"], q["chases"], q["sent"], None) for q in s.questions if q["chase_due"]),
        *(("action", a["id"], a["text"], a["chases"], a["told"], a["due"]) for a in s.actions if a["chase_due"]),
    ]
    if not due:
        return None
    round_ = 1 + max(item[3] for item in due)
    if round_ > 1:
        due = sorted(due, key=lambda item: (-item[3], item[4] or "9999", item[2]))[
            : cfg.ui.followups.second_nudge_items
        ]
    first = min((item[4] for item in due if item[4]), default=None) or today.isoformat()
    lines = [words.greeting.format(first_name=people.first_name(s.person)), ""]
    if round_ > 1:
        lines.append(words.nudge_second_intro.format(date=shown(first)))
    elif len(due) == 1:
        lines.append(words.nudge_intro_one.format(date=shown(first)))
    else:
        lines.append(words.nudge_intro.format(count=len(due), date=shown(first)))
    lines.append("")
    for n, (kind, _id, text, _chases, _asked, due_on) in enumerate(due, 1):
        line = f"{n}. {text}" if len(due) > 1 else text
        if kind == "action" and due_on and date.fromisoformat(str(due_on)) < today:
            line += " " + words.nudge_overdue.format(date=shown(due_on))
        lines.append(line)
    lines.append("")
    lines.append(words.nudge_second_ask if round_ > 1 else words.nudge_ask if len(due) > 1 else words.nudge_ask_one)
    lines += ["", words.closing]
    return Nudge(
        "\n".join(lines),
        round_,
        [item[1] for item in due if item[0] == "question"],
        [item[1] for item in due if item[0] == "action"],
    )


def message_where(cfg: Config, name: str) -> str:
    """Where a message to one person sits, for the reason a message is held back."""
    return cfg.language.messages.withheld_where.format(name=name)


def _guard_sent_text(store: Store, cfg: Config, person: str, text: str | None) -> None:
    """A message that goes to someone else is refused while it names the assistant (the send step; design 6.12)."""
    if text is None or person == People(store, cfg).pm:
        return
    where = message_where(cfg, People(store, cfg).name(person))
    outward.check_outgoing(store.read(), cfg, {where: text})


def mark_sent(
    store: Store, cfg: Config, person: str, *, sent_text: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Record that the person's open questions and untold actions went out. If the PM edited the message before
    sending, that is recorded as a quality signal. Returns the counts and the ids, which `unmark_sent` takes."""
    now = now or datetime.now(UTC)
    today = local_day(now, zone(cfg))
    _guard_sent_text(store, cfg, person, sent_text)
    current = next((s for s in sections(store, cfg, today) if s.person == person), None)
    if current is None:
        return {"questions": 0, "actions": 0, "question_ids": [], "action_ids": []}
    counts: dict[str, Any] = {"questions": 0, "actions": 0, "question_ids": [], "action_ids": []}
    with store.transaction() as tx:
        for q in current.questions:
            if q["status"] == "open":
                rec = tx.get("question", q["id"])
                tx.update(
                    "question", q["id"], {"status": "sent", "sent_at": now.isoformat()}, _PM, read_version=rec.version
                )
                counts["questions"] += 1
                counts["question_ids"].append(q["id"])
        for a in current.actions:
            if a["told"] is None:
                rec = tx.get("action", a["id"])
                told = {**rec.data.get("told", {}), person: today.isoformat()}
                if person in rec.data.get("told", {}):
                    # Told before and changed since: clear the old day first, so telling again on the same day is
                    # still a change in the ledger and the action no longer counts as changed since it was told.
                    cleared = {k: v for k, v in rec.data["told"].items() if k != person}
                    rec = tx.update("action", a["id"], {"told": cleared}, _PM, read_version=rec.version)
                tx.update("action", a["id"], {"told": told}, _PM, read_version=rec.version)
                counts["actions"] += 1
                counts["action_ids"].append(a["id"])
    if sent_text is not None and normalize(sent_text) != normalize(current.message):
        changeset, run = _written_by(store, counts["question_ids"])
        signal(
            store,
            "draft_edited",
            [person, *counts["question_ids"]],
            note=sent_text,
            now=now,
            changeset=changeset,
            run=run,
        )
    if counts["questions"] or counts["actions"]:
        # What the person copied is kept as it was used, for matching the message that reaches the sent folder.
        sent_version.record_copy(
            store,
            "follow_up",
            person,
            current.message if sent_text is None else sent_text,
            questions=counts["question_ids"],
            actions=counts["action_ids"],
            now=now,
        )
    return counts


def _written_by(store: Store, question_ids: list[str], kind: str = "question") -> tuple[str | None, str | None]:
    """The changeset and the AI run that wrote these questions (or, with `kind`, these records), when they all came from
    the same one; None for what they don't share (records from different runs, or made by no run)."""
    view = store.read()
    made = [next((e["changeset"] for e in view.ledger(kind=kind, record_id=qid)), None) for qid in question_ids]
    runs = []
    for changeset in made:
        record = view.get("changeset", changeset) if changeset else None
        runs.append(record.data.get("run") if record is not None else None)
    return (made[0] if len(set(made)) == 1 else None), (runs[0] if len(set(runs)) == 1 else None)


def unmark_sent(
    store: Store, person: str, question_ids: list[str], action_ids: list[str], *, forget_copy: bool = True
) -> None:
    """Undo a Mark sent: the questions are open again and the person is no longer marked as told, and the copy it kept
    is forgotten unless `forget_copy` is False (the person's own answer that it never went keeps it, settled). If the
    message was edited before it was marked sent, what the assistant would have learned from the edit is dropped with
    it."""
    view = store.read()
    stamps = [
        found.data["sent_at"]
        for qid in question_ids
        if (found := view.get("question", qid)) is not None and found.data.get("sent_at")
    ]
    with store.transaction() as tx:
        for qid in question_ids:
            rec = tx.get("question", qid)
            if rec is not None and rec.data["status"] == "sent":
                tx.update("question", qid, {"status": "open", "sent_at": None}, _PM, read_version=rec.version)
        for aid in action_ids:
            rec = tx.get("action", aid)
            if rec is not None and person in rec.data.get("told", {}):
                told = {k: v for k, v in rec.data["told"].items() if k != person}
                tx.update("action", aid, {"told": told}, _PM, read_version=rec.version)
    if forget_copy:
        sent_version.forget_copy(store, person, question_ids, action_ids)
    if stamps:
        learn.net_out(store, "draft_edited", [person], at=stamps)


def mark_followed_up(
    store: Store,
    cfg: Config,
    person: str,
    question_ids: list[str],
    action_ids: list[str],
    *,
    sent_text: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record that the follow-up went to `person`: today is added to each question's and action's chases, so the wait
    for an answer starts again while a question keeps when it was first sent. Edited before sending, the message is
    recorded as a quality signal, as an edited first message is. Returns what `unmark_followed_up` takes."""
    now = now or datetime.now(UTC)
    day = local_day(now, zone(cfg))
    today = day.isoformat()
    _guard_sent_text(store, cfg, person, sent_text)
    current = next((s for s in sections(store, cfg, day) if s.person == person), None)
    drafted = current.nudge.text if current is not None and current.nudge is not None else None
    previous: dict[str, str | None] = {}
    with store.transaction() as tx:
        for qid in question_ids:
            rec = tx.get("question", qid)
            if rec is None or rec.data["status"] != "sent" or rec.data["to"] != person:
                raise FollowUpError("that question isn't waiting for an answer")
            chases = [*(rec.data.get("followed_up") or []), today]
            tx.update("question", qid, {"followed_up": chases}, _PM, read_version=rec.version)
        for aid in action_ids:
            rec = _owned_open_action(tx, aid, person)
            previous[aid] = str(rec.data["told"][person]) if rec.data.get("told", {}).get(person) else None
            chases = dict(rec.data.get("followed_up") or {})
            chases[person] = [*chases.get(person, []), today]
            told = {**rec.data.get("told", {}), person: today}
            tx.update("action", aid, {"followed_up": chases, "told": told}, _PM, read_version=rec.version)
    signal_at = None
    if sent_text is not None and drafted is not None and normalize(sent_text) != normalize(drafted):
        changeset, run = _written_by(store, question_ids)
        signal(store, "draft_edited", [person, *question_ids], note=sent_text, now=now, changeset=changeset, run=run)
        signal_at = now.isoformat()
    return {
        "questions": len(question_ids),
        "actions": len(action_ids),
        "question_ids": question_ids,
        "action_ids": action_ids,
        "on": today,
        "previous_told": previous,
        "signal_at": signal_at,
    }


def unmark_followed_up(
    store: Store,
    person: str,
    question_ids: list[str],
    action_ids: list[str],
    *,
    on: str,
    previous_told: dict[str, str | None],
    signal_at: str | None = None,
) -> None:
    """Take back a follow-up marked as sent on day `on`: each chase leaves the questions and actions, and an action's
    told day goes back to what it was. What the assistant would have learned from an edit of the message goes with
    it."""
    with store.transaction() as tx:
        for qid in question_ids:
            rec = tx.get("question", qid)
            if rec is None:
                continue
            days = [str(d) for d in rec.data.get("followed_up") or []]
            if on in days:
                days.remove(on)
            tx.update("question", qid, {"followed_up": days}, _PM, read_version=rec.version)
    for aid in action_ids:
        undo_follow_up(store, aid, person, on, previous_told.get(aid))
    if signal_at:
        learn.net_out(store, "draft_edited", [person], at=[signal_at])


class FollowUpError(ValueError):
    """A chase or a finish that can't be recorded; the message says why in plain words."""


def _owned_open_action(tx: Any, action_id: str, person: str) -> Any:
    rec = tx.get("action", action_id)
    if rec is None or rec.data["status"] != "open":
        raise FollowUpError("that action isn't open")
    if person not in [o["person"] for o in rec.data.get("owners", [])]:
        raise FollowUpError("that person doesn't own the action")
    return rec


def follow_up(
    store: Store, action_id: str, person: str, *, now: datetime | None = None, here: tzinfo = UTC
) -> dict[str, str | None]:
    """Record that the PM chased `person` about an open action: today is added to the action's chases and counts as
    told again, so the waiting count starts over. The action stays open. Returns the day recorded and the told day it
    replaced, which `undo_follow_up` takes. The day is the one where the person is (`here`)."""
    today = local_day(now or datetime.now(UTC), here).isoformat()
    with store.transaction() as tx:
        rec = _owned_open_action(tx, action_id, person)
        previous = rec.data.get("told", {}).get(person)
        chases = dict(rec.data.get("followed_up") or {})
        chases[person] = [*chases.get(person, []), today]
        told = {**rec.data.get("told", {}), person: today}
        tx.update("action", action_id, {"followed_up": chases, "told": told}, _PM, read_version=rec.version)
    return {"on": today, "previous_told": str(previous) if previous else None}


def undo_follow_up(store: Store, action_id: str, person: str, on: str, previous_told: str | None) -> None:
    """Take back the chase recorded on day `on`: it leaves the action's chases and the told day goes back to what it
    was."""
    with store.transaction() as tx:
        rec = tx.get("action", action_id)
        if rec is None:
            return
        chases = dict(rec.data.get("followed_up") or {})
        days = [str(d) for d in chases.get(person, [])]
        if on in days:
            days.remove(on)
        if days:
            chases[person] = days
        else:
            chases.pop(person, None)
        told = dict(rec.data.get("told", {}))
        if previous_told:
            told[person] = previous_told
        else:
            told.pop(person, None)
        tx.update("action", action_id, {"followed_up": chases, "told": told}, _PM, read_version=rec.version)


def they_finished(store: Store, cfg: Config, action_id: str, person: str) -> None:
    """Close an open action because the PM was told `person` finished it: the work is credited to that person, and the
    PM is recorded as the one who reported it."""
    with store.transaction() as tx:
        rec = _owned_open_action(tx, action_id, person)
        credit = {"status": "done", "done_by": [person], "reported_by": People(store, cfg).pm}
        tx.update("action", action_id, credit, _PM, read_version=rec.version)


def _open_action(tx: Any, action_id: str) -> Any:
    rec = tx.get("action", action_id)
    if rec is None or rec.data["status"] != "open":
        raise FollowUpError("that action isn't open")
    return rec


def held_until_day(
    view: Any, held_for: dict[str, Any] | None, today: date, here: Any
) -> tuple[date | None, str | None]:
    """The day a held question comes back to To send, and the name of the meeting it waits for (None for a day).
    A calendar entry is read where it is now, so a moved meeting moves the day; a series is its first instance on or
    after the day the question was held. None when it names nothing that can be dated, which leaves the question
    where it is, in To send."""
    from engine.series import next_instance, span

    if not held_for:
        return None, None
    if held_for.get("on"):
        return date.fromisoformat(str(held_for["on"])), None
    entry = None
    if held_for.get("event"):
        entry = view.get("event", held_for["event"])
        name = entry.data["title"] if entry is not None else None
    elif held_for.get("series"):
        since = date.fromisoformat(str(held_for["since"])) if held_for.get("since") else today
        entry = next_instance(view, held_for["series"], since, here)
        found = view.get("series", held_for["series"])
        name = found.data["title"] if found is not None else None
    if entry is None:
        return None, None
    days = span(entry.data, here)
    return (days[0] if days else None), name


def hold_question(
    store: Store, question_id: str, held_for: dict[str, Any] | None, *, today: date | None = None, here: tzinfo = UTC
) -> dict[str, Any] | None:
    """Hold an open question for a meeting or a day, or (with None) send it now. A meeting must be dated, and a day
    must be after today. Returns what it was held for before (or None), which putting it back takes."""
    today = today or local_day(datetime.now(UTC), here)
    with store.transaction() as tx:
        rec = tx.get("question", question_id)
        if rec is None or rec.data["status"] != "open":
            raise FollowUpError("only a question that hasn't gone out can be held")
        previous = rec.data.get("held_for")
        new = None
        if held_for is not None:
            new = {k: v for k, v in held_for.items() if v is not None}
            new.setdefault("since", today.isoformat())
            here = zone(store.plugins.cfg)
            until, _ = held_until_day(tx, new, today, here)
            if until is None:
                raise FollowUpError("that meeting has no day to wait for")
            if until <= today:
                raise FollowUpError("a question is held until a day after today")
        tx.update("question", question_id, {"held_for": new}, _PM, read_version=rec.version)
    return previous


def put_on_hold(
    store: Store,
    action_id: str,
    waiting_for: str = "",
    *,
    on: str | None = None,
    now: datetime | None = None,
    here: tzinfo = UTC,
) -> dict[str, Any] | None:
    """Put an open action on hold, waiting for `waiting_for` (plain words), starting today. With `on` (a person, an
    action or a question) the hold names its blocker, the action is blocked, and the words, when none are given, are
    the blocker's name. A signal records it as the person's own change. Returns what the action was waiting for
    before (or None), which `restore_hold` takes."""
    waiting_for = " ".join(waiting_for.split())
    if not waiting_for and not on:
        raise FollowUpError("say what it is waiting for")
    now = now or datetime.now(UTC)
    with store.transaction() as tx:
        rec = _open_action(tx, action_id)
        if on is not None:
            if (why := blocker_problem(tx, action_id, on)) is not None:
                raise FollowUpError(why)
            if not waiting_for:
                named = blocker_of(tx, {"on": on}, ViewNames(tx))
                waiting_for = named.name if named is not None and named.name else on
        previous = rec.data.get("on_hold")
        hold = {"waiting_for": waiting_for, "since": local_day(now, here).isoformat()}
        if on is not None:
            hold["on"] = on
        tx.update("action", action_id, {"on_hold": hold}, _PM, read_version=rec.version)
    signal(store, "put_on_hold", [action_id], note=waiting_for, now=now)
    return previous


def take_off_hold(store: Store, action_id: str, *, now: datetime | None = None) -> dict[str, Any] | None:
    """Take an open action off hold; it keeps its own due date. A signal records it as the person's own change.
    Returns what it was waiting for, which `restore_hold` takes."""
    now = now or datetime.now(UTC)
    with store.transaction() as tx:
        rec = _open_action(tx, action_id)
        previous = rec.data.get("on_hold")
        if previous is None:
            raise FollowUpError("that action isn't on hold")
        tx.update("action", action_id, {"on_hold": None}, _PM, read_version=rec.version)
    signal(store, "taken_off_hold", [action_id], note=previous["waiting_for"], now=now)
    return previous


def restore_hold(store: Store, action_id: str, hold: dict[str, Any] | None) -> None:
    """Put an action's hold back to exactly `hold` (what it was, or None for off hold). It is how undoing a hold or a
    release works, and it records no signal: taking back the person's own change is not a correction."""
    with store.transaction() as tx:
        rec = tx.get("action", action_id)
        if rec is None:
            return
        tx.update("action", action_id, {"on_hold": hold}, _PM, read_version=rec.version)
