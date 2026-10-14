"""Today's queue: what needs the person, ranked (design 7.7).

One line per thing to do, each starting with what to do. Lines fall in groups, in this order: decide (decisions and
everything held for the person), risk (work that failed, the person's overdue to-dos), review (the assistant's work and
incoming changes to look over), send (messages to send and people to follow up with). Within a group the line that
has waited longest, or is due first, comes first. Nothing here calls AI or reaches a service; it reads records only.
Plugin Today lines and stage lines are added by the screen into their groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.followups import ROUTING, sections
from engine.names import People
from engine.titles import Title, head_of, title_for
from engine.today import zone

GROUPS = ("decide", "risk", "review", "send")

# What a changeset's ops did, by the outcome word the screen uses.
_OUTCOME = {
    "action.add": "actions_added",
    "action.close": "actions_closed",
    "question.add": "questions",
    "note": "notes",
    "fact": "recorded",
    "event.add": "recorded",
    "record.set": "recorded",
    "record.log": "recorded",
    "person.add": "people",
    "project.add": "projects",
    "text.draft": "drafts",
    "report.draft": "drafts",
    "text.propose": "drafts",
}


@dataclass
class Line:
    """One line of the queue. `key` is stable while the thing it stands for waits. `kind`: decision, question (one
    the person was asked), who_is (a name the assistant couldn't place), owner (an action with no owner), held (an
    item waiting for the person's yes), go (a run waiting for the person's go), first_go (every run waiting for the
    first go in the workspace, as one line: `estimate_usd` is their total estimate and `unpriced` how many have
    none), refused, restart (work held until the person restarts the app: `count` is how many requests wait), handover
    (the synced folder can't be used until the person settles it: `state` is diverged, chosen or elsewhere and `text`
    the other computer), failed,
    paused (an AI account waiting for its usage limit to reset: `account`, `until` and `count` waiting), offline (work
    that has waited for the network longer than the configured time: `count` waiting and `waiting_since`, when the
    oldest began), overdue,
    review, rule_review (standing rules to look over: `count` flagged as never applying in `days`, their ids in `rules`,
    the always-sent section's `stable_size` against its `stable_budget`, and `moved` rules sent only with the runs they
    cover), learned (proposals of what the assistant learned from inputs and from the person's corrections, to look
    over: `count` of them, `origins` counted by where they came from and `expired` how many from inputs expired since
    the person last looked), catch_up (what the assistant learned from corrections made before it could: `count`
    waiting and `left_out`, how many kinds of correction were too many for one list), send or nudge. `count` is how
    many things the line covers; `text` the decision, question or held item in one line; `title` the input the line
    is about; `outcome` what the assistant did, counted by kind; `waiting` why the work stopped, as the engine said
    it."""

    key: str
    group: str
    kind: str
    count: int = 1
    text: str | None = None
    title: Title | None = None
    person: str | None = None
    project: str | None = None
    due: str | None = None
    waiting_days: int | None = None
    waiting: str | None = None
    request: str | None = None
    changeset: str | None = None
    question: str | None = None
    op: int | None = None
    actions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    outcome: dict[str, int] = field(default_factory=dict)
    untrusted: bool = False
    estimate_usd: float | None = None
    unpriced: int = 0
    account: str | None = None
    until: str | None = None
    waiting_since: str | None = None
    state: str | None = None
    rules: list[str] = field(default_factory=list)
    stable_size: int | None = None
    stable_budget: int | None = None
    moved: int | None = None
    days: int | None = None
    origins: dict[str, int] = field(default_factory=dict)
    expired: int | None = None
    left_out: int | None = None
    since: str = ""


def queue(ws: Any, store: Any, cfg: Any, now: datetime, handover: tuple[str, str] | None = None) -> list[Line]:
    """Every line that needs the person now, in rank order. `handover`: what stops the synced folder from being used,
    as the worker reports it (state and the other computer's name), which is a line of its own."""
    today = now.astimezone(zone(cfg)).date()
    people = People(store, cfg)
    reader = store.read()
    sources = {s.id: s.data for s in reader.list("source")}
    changesets = {c.id: c.data for c in reader.list("changeset")}
    kinds = watched_kinds(reader)
    skip = list(cfg.language.title_skip)

    def title(request: dict[str, Any], cs: dict[str, Any] | None) -> Title:
        source = sources.get(request.get("source") or "")
        watched = (source or {}).get("watched") or {}
        head = head_of(ws.sources_dir, (source or {}).get("content_hash"))
        return title_for(
            request,
            source,
            cs,
            people=people,
            skip=skip,
            head=head,
            watched_kind=kinds.get((watched.get("source"), watched.get("key"))),
        )

    lines: list[Line] = []
    requests = {r.id: r for r in reader.list("request")}
    by_changeset: dict[str, Any] = {}
    for req in requests.values():
        if req.data.get("changeset"):
            by_changeset[req.data["changeset"]] = req

    # Decide: questions to the person (decisions, questions, who-is and owner questions).
    for q in reader.list("question"):
        d = q.data
        if d.get("to") != people.pm or people.pm is None or d.get("status") != "open":
            continue
        resolves = d.get("resolves") or {}
        about = resolves.get("kind")
        line = Line(key=f"question:{q.id}", group="decide", kind="question", text=d["title"], question=q.id)
        line.project = (d.get("projects") or [None])[0]
        line.since = _created(reader, "question", q.id)
        if about == "held-op":
            cs_id = resolves.get("changeset")
            line.kind, line.changeset, line.op = "who_is", cs_id, resolves.get("op")
            line.text = resolves.get("name") or d["title"]
            req = by_changeset.get(cs_id)
            if req is not None:
                line.request = req.id
                line.title = title(req.data, changesets.get(cs_id))
                line.untrusted = (changesets.get(cs_id) or {}).get("trust") == "untrusted"
        elif about == "owner":
            line.kind = "owner"
            action = reader.get("action", resolves.get("action"))
            if action is not None:
                line.actions = [action.id]
                line.text = action.data["text"]
                line.due = str(action.data["due"]) if action.data.get("due") else None
                line.project = action.data.get("project")
        elif about in ROUTING:
            continue
        else:
            line.kind = "decision" if d.get("kind") == "decision" else "question"
        lines.append(line)

    # Decide: held items with no question (they wait for the person's yes), and runs waiting for a go.
    for cs_id, cs in changesets.items():
        req = by_changeset.get(cs_id)
        if req is None or req.data.get("dismissed"):
            continue
        for outcome in cs.get("ops", []):
            if outcome.get("status") != "held" or outcome.get("question"):
                continue
            lines.append(
                Line(
                    key=f"held:{cs_id}:{outcome['index']}",
                    group="decide",
                    kind="held",
                    text=outcome.get("label") or _op_text(outcome.get("op") or {}),
                    title=title(req.data, cs),
                    request=req.id,
                    changeset=cs_id,
                    op=outcome["index"],
                    waiting=outcome.get("reason"),
                    untrusted=cs.get("trust") == "untrusted",
                    since=str(req.data.get("created_at") or ""),
                )
            )
    from engine.dispatcher import FIRST_GO, waits_on_first_go

    first_go: list[Any] = []
    for req in requests.values():
        d = req.data
        if d.get("dismissed") or d.get("state") not in ("needs_you", "failed"):
            continue
        if waits_on_first_go(d):
            first_go.append(req)
            continue
        if d["state"] == "failed":
            kind, group = "failed", "risk"
        elif d.get("approval") == "required":
            kind, group = "go", "decide"
        else:
            kind, group = "refused", "decide"
        lines.append(
            Line(
                key=f"{kind}:{req.id}",
                group=group,
                kind=kind,
                title=title(d, changesets.get(d.get("changeset") or "")),
                request=req.id,
                waiting=d.get("waiting"),
                since=str(d.get("created_at") or ""),
            )
        )

    if handover is not None:
        # The folder not being written is never a silent stop; the line opens the page that settles it.
        lines.append(
            Line(key="handover", group="decide", kind="handover", text=handover[1], state=handover[0], since="")
        )

    from engine.worker import RESTART_NEEDED

    held = [
        r
        for r in requests.values()
        if r.data.get("state") == "queued" and not r.data.get("dismissed") and r.data.get("waiting") == RESTART_NEEDED
    ]
    if held:
        # Work held until a restart is never a silent stop: the first line of the day, with the count. It only asks;
        # the restart is the person's to start.
        lines.append(
            Line(
                key="restart",
                group="decide",
                kind="restart",
                count=len(held),
                waiting=RESTART_NEEDED,
                since=min(str(r.data.get("created_at") or "") for r in held),
            )
        )

    if first_go:
        from engine.watch import first_go_sorting

        priced = [r.data["estimate_usd"] for r in first_go if r.data.get("estimate_usd") is not None]
        # The go also makes the sorting run for mail handed in unsorted; the person approves that spend with it.
        _runs, sorting_usd, sorting_unpriced = first_go_sorting(ws, store, cfg)
        total = sum(priced) + (sorting_usd or 0.0)
        lines.append(
            Line(
                key="first_go",
                group="decide",
                kind="first_go",
                count=len(first_go),
                estimate_usd=round(total, 4) if priced or sorting_usd is not None else None,
                unpriced=len(first_go) - len(priced) + sorting_unpriced,
                waiting=FIRST_GO,
                since=min(str(r.data.get("created_at") or "") for r in first_go),
            )
        )

    # Risk: an AI account paused until its usage limit resets, with the work waiting on it.
    from engine.ai.pauses import Pauses, pauses_path, waiting_text

    for account, until in sorted(Pauses(pauses_path(store), lambda: now).active().items(), key=lambda x: (x[1], x[0])):
        waiting = [
            r
            for r in requests.values()
            if r.data.get("state") == "queued"
            and not r.data.get("dismissed")
            and (r.data.get("cause") or {}).get("kind") == "paused"
            and (r.data.get("cause") or {}).get("account") == account
        ]
        if waiting:
            lines.append(
                Line(
                    key=f"paused:{account}",
                    group="risk",
                    kind="paused",
                    count=len(waiting),
                    text=account,
                    account=account,
                    until=until.isoformat(),
                    waiting=waiting_text(cfg, account, until, now),
                    since=until.isoformat(),
                )
            )

    # Risk: work that has waited for the network longer than the configured time, as one line.
    from engine.dispatcher import OFFLINE_WAITING, is_waiting_for_network

    offline = [r for r in requests.values() if is_waiting_for_network(r.data)]
    if offline:
        began = min(_aware(str(r.data["cause"]["since"])) for r in offline)
        if now - began >= timedelta(minutes=cfg.dispatch.offline_line_after_minutes):
            lines.append(
                Line(
                    key="offline",
                    group="risk",
                    kind="offline",
                    count=len(offline),
                    waiting=OFFLINE_WAITING,
                    waiting_since=began.isoformat(),
                    since=began.isoformat(),
                )
            )

    # Risk: the person's own overdue to-dos, as one line.
    overdue = []
    for action in reader.list("action"):
        d = action.data
        if d.get("status") != "open" or not d.get("due") or d.get("on_hold") or people.pm is None:
            continue
        if not any(o.get("person") == people.pm for o in d.get("owners") or []):
            continue
        due = date.fromisoformat(str(d["due"]))
        if due < today:
            overdue.append((due, action.id))
    if overdue:
        overdue.sort()
        lines.append(
            Line(
                key="overdue",
                group="risk",
                kind="overdue",
                count=len(overdue),
                actions=[a for _, a in overdue],
                due=overdue[0][0].isoformat(),
                waiting_days=(today - overdue[0][0]).days,
                since=overdue[0][0].isoformat(),
            )
        )

    # Review: the assistant's work waiting for a look.
    for req in requests.values():
        d = req.data
        if d.get("dismissed") or d.get("state") != "review" or not d.get("changeset"):
            continue
        cs = changesets.get(d["changeset"]) or {}
        if cs.get("reviewed"):
            continue
        outcome: dict[str, int] = {}
        for o in cs.get("ops", []):
            status = o.get("status")
            if status in ("held", "refused"):
                outcome[status] = outcome.get(status, 0) + 1
            if status != "applied" and status != "held":
                continue
            word = _OUTCOME.get((o.get("op") or {}).get("op", ""), "other")
            outcome[word] = outcome.get(word, 0) + 1
        lines.append(
            Line(
                key=f"review:{req.id}",
                group="review",
                kind="review",
                count=sum(1 for o in cs.get("ops", []) if o.get("status") in ("applied", "held")),
                title=title(d, cs),
                request=req.id,
                changeset=d["changeset"],
                outcome=outcome,
                untrusted=cs.get("trust") == "untrusted",
                since=str(d.get("created_at") or ""),
            )
        )

    # Review: the standing rules to look over, offered at most once a period.
    from engine.rule_review import due, last_acted, review

    found = review(reader, cfg.dispatch.knowledge, now)
    if due(reader, cfg.dispatch.knowledge, now, found):
        acted = last_acted(reader)
        lines.append(
            Line(
                key="rule_review",
                group="review",
                kind="rule_review",
                count=len(found.flagged),
                rules=[f.id for f in found.flagged],
                stable_size=found.stable_chars,
                stable_budget=found.stable_budget,
                moved=found.moved,
                days=found.days,
                since=acted.isoformat() if acted else "",
            )
        )

    # Review: what the assistant learned, as one line for the proposals from inputs and from corrections, and one for
    # the catch-up list of corrections made before it could learn from them.
    from engine import catch_up
    from engine.proposals import expired_since, last_reviewed, proposals

    state = catch_up.load(store)
    listed = catch_up.proposal_ids(reader, state)
    waiting = proposals(reader)
    daily = [p for p in waiting if p.stored.id not in listed]
    if daily:
        origins: dict[str, int] = {}
        for p in daily:
            origins[p.came_from] = origins.get(p.came_from, 0) + 1
        lines.append(
            Line(
                key="learned",
                group="review",
                kind="learned",
                count=len(daily),
                origins=origins,
                expired=expired_since(reader, last_reviewed(reader)),
                since=str(daily[0].stored.data.get("learned_at") or ""),
            )
        )
    on_list = [p for p in waiting if p.stored.id in listed]
    if on_list:
        lines.append(
            Line(
                key="catch_up",
                group="review",
                kind="catch_up",
                count=len(on_list),
                left_out=state.left_out if state is not None else 0,
                since=str(on_list[0].stored.data.get("learned_at") or ""),
            )
        )

    # Send and follow up: who has something to send, then who hasn't answered for a while.
    for s in sections(store, cfg, today):
        if s.is_pm:
            continue
        if s.to_send:
            lines.append(
                Line(
                    key=f"send:{s.person}",
                    group="send",
                    kind="send",
                    count=s.to_send,
                    person=s.person,
                    questions=[q["id"] for q in s.questions if q["status"] == "open"],
                    actions=[a["id"] for a in s.actions if a["told"] is None],
                    since=s.name.lower(),
                )
            )
        waiting = [q for q in s.questions if q["chase_due"]]
        told = [a for a in s.actions if a["chase_due"]]
        if waiting or told:
            longest = max([q["waiting_days"] or 0 for q in waiting] + [a["told_days"] or 0 for a in told])
            lines.append(
                Line(
                    key=f"nudge:{s.person}",
                    group="send",
                    kind="nudge",
                    count=len(waiting) + len(told),
                    person=s.person,
                    questions=[q["id"] for q in waiting],
                    actions=[a["id"] for a in told],
                    waiting_days=longest,
                    since=s.name.lower(),
                )
            )

    return sorted(lines, key=_rank)


_KIND_ORDER = {
    "handover": -3,
    "restart": -2,
    "first_go": -1,
    "decision": 0,
    "who_is": 1,
    "owner": 2,
    "held": 3,
    "go": 4,
    "refused": 5,
    "question": 6,
    "failed": 0,
    "paused": 1,
    "offline": 1,
    "overdue": 2,
    "review": 0,
    "rule_review": 1,
    "learned": 2,
    "catch_up": 3,
    "send": 0,
    "nudge": 1,
}


def _aware(stamp: str) -> datetime:
    """A stored time as a moment with a zone."""
    at = datetime.fromisoformat(stamp)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _rank(line: Line) -> tuple[Any, ...]:
    """Group first; then the kind's place in its group; then oldest (or longest waiting) first."""
    if line.kind == "nudge":
        return (GROUPS.index(line.group), _KIND_ORDER[line.kind], -(line.waiting_days or 0), line.since)
    return (GROUPS.index(line.group), _KIND_ORDER.get(line.kind, 9), line.since, line.key)


def watched_kinds(reader: Any) -> dict[tuple[str, str], str]:
    """What each watched item said it was (email or calendar), by its source and key."""
    found = {}
    for snap in reader.list("snapshot"):
        d = snap.data
        if d.get("message"):
            found[(d["source"], d["key"])] = "email"
        elif d.get("event"):
            found[(d["source"], d["key"])] = "calendar"
    return found


def _op_text(op: dict[str, Any]) -> str:
    for key in ("text", "title", "name", "full_name", "answer"):
        if op.get(key):
            return str(op[key])
    return ""


def _created(reader: Any, kind: str, record_id: str) -> str:
    entries = reader.ledger(kind=kind, record_id=record_id)
    return str(entries[0]["at"]) if entries else ""
