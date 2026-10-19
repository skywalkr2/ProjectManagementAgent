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

from engine import (
    held_ask,
    move_groups,
    promises,
    release_hours,
    reminder_lines,
    reply_lines,
    sent_version,
    since_yesterday,
    source_intake,
    watch,
)
from engine.followups import ROUTING, sections
from engine.names import People
from engine.owners import suggest_owner
from engine.plugin_api import TODAY_GROUPS
from engine.scope import stance_of
from engine.titles import Title, head_of, title_for
from engine.today import zone

GROUPS = TODAY_GROUPS

# What a changeset's ops did, by the outcome word the screen uses.
_OUTCOME = {
    "action.add": "actions_added",
    "action.close": "actions_closed",
    "question.add": "questions",
    "note": "notes",
    "fact": "recorded",
    "event.add": "recorded",
    "event.set": "recorded",
    "series.add": "recorded",
    "series.link": "recorded",
    "record.set": "recorded",
    "record.log": "recorded",
    "person.add": "people",
    "project.add": "projects",
    "project.role": "recorded",
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
    none), catch_up_go (the learning runs for the catch-up list, held together for one go: `count` runs, their total
    `estimate_usd` and `unpriced` how many have none), intake_go (a newly added `source`, `subject` its label, taken in
    quietly: its `count` items held together for one go, their total `estimate_usd`, `unpriced` how many have none and
    `days` how far back its mail was read, none for a source with no mail), intake_review (what was found in a newly
    added `source`: `count` items with something to look over and their results counted in `outcome`, which replace
    the lines each would have had until the person opens the list), refused, restart (work held until the person
    restarts the app: `count` is how many requests wait), handover (the synced folder can't be used until the person
    settles it: `state` is diverged, chosen or elsewhere and `text` the other computer), failed,
    paused (an AI account waiting for its usage limit to reset: `account`, `until` and `count` waiting), borrow (a
    question: every account a kind of work can use is paused, so may another kind of work's free `account` (with its
    `model`) take that work, the `tier`'s, until `until`, when the paused account `text` resets? `count` waiting items
    it would take, their `estimate_usd` together and `unpriced` how many have no price), offline (work
    that has waited for the network longer than the configured time: `count` waiting and `waiting_since`, when the
    oldest began), overdue, account_check (an AI account in a fallback chain that can't stand in yet: its `account`, the
    `tier` whose chain it is in, its `model`, and `check_failed` when its last check failed rather than it never having
    been checked),
    switch_failed (a switch of the `tier`'s account or model whose check found problems, or couldn't finish: the new
    `account`, the earlier one in `text`, `count` cases that didn't come out right with the first of them in `names`,
    and `check_failed` when the check couldn't finish),
    credential (a key or sign-in that stops working on `due`, or already has: `credential_kind` is account or
    sign_in, `credential_name` its name, `waiting_days` the days left, below zero once it has passed, and `places`
    every place the same credential is used),
    moved (the questions a follow-on run asked the person about one move, as one line: `count` of them in
    `questions`, the move in `after_move`), review, unfiled (what the assistant filed under no project: `count` of
    them), rule_review (standing rules to look over: `count` flagged as never applying in `days`, their ids in `rules`,
    the always-sent section's `stable_size` against its `stable_budget`, and `moved` rules sent only with the runs they
    cover), learned (proposals of what the assistant learned from inputs and from the person's corrections, to look
    over: `count` of them, `origins` counted by where they came from and `expired` how many from inputs expired since
    the person last looked), catch_up (what the assistant learned from corrections made before it could: `count`
    waiting and `left_out`, how many kinds of correction were too many for one list), extractor (a kind of file that
    isn't being read: `file_kind` is the kind, and `text` why), source_unread (a source that has failed for longer than
    its usual gap: `source` is its id, `subject` its label, `problem_kind` the kind of failure, `text` what went wrong
    and what to do, and `waiting_since` when it was last read, or first tried when it never was), promise (one open
    action that needs a look: its id in `actions`, its words in `text`, its day in `due` (none when undated),
    `waiting_days` (days past its date, below zero while the date is ahead, or days with nothing heard when undated),
    and in `person` the one to chase, none when it is the person's own, with `stance`: who they are to the person, so
    the line says Chase or Waiting on; none for the person's own), reminder (an open action whose reminder has
    reached the person: its id in `actions`, its words in `text`, the moment it was set for in `at` on the person's
    clock, `late` when it came due while the app or the computer was not running, and in `snoozes` the choices that
    still have a time, each `choice` with the `at` it resolves to), reminder_digest (reminders that fell in quiet hours,
    or, by the person's choice, were missed while the computer slept, arriving together: `reminders` lists each with
    its action, words and `at`, and `late` says which of the two it is), reply (a reply owed, one open action: its id in
    `actions`, its words in `text`, the message's `subject`, who it is to in `person` or, for nobody known, `sender`
    as written, and the drafted `reply` with `reply_reviewed`; ranked by when the message came, oldest first),
    sent_check (a message the person copied that no sent message has matched, asked about once a sent folder is
    being read: its copy's id in `sent_copy`, who it was for in `person`, what it covered in `questions` and
    `actions`),
    since_yesterday (what the assistant or a rule did that the person hasn't looked over, one line for all of it:
    `count` entries, counted by act in `outcome`; Look over opens the list), away (one row for the lines that waited for
    the person's working hours and arrived together with them: `count` is how many, and `since` the moment the hours
    began; it is at the top of the first group any of them is in, and goes with the day), send or nudge.
    `count` is how many things the line covers; `text` the decision, question or held item in one line; `subject` the
    one thing's own words when a review or overdue line covers exactly one (the screen titles it by them); `title`
    the input the line is about; `outcome` what the assistant did, counted by kind; `waiting` why the work stopped, as
    the engine said it."""

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
    subject: str | None = None
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
    suggestion: dict[str, Any] | None = None
    held: dict[str, Any] | None = None
    after_move: dict[str, Any] | None = None
    tier: str | None = None
    model: str | None = None
    check_failed: bool | None = None
    file_kind: str | None = None
    source: str | None = None
    problem_kind: str | None = None
    credential_kind: str | None = None
    credential_name: str | None = None
    places: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    at: str | None = None
    late: bool | None = None
    snoozes: list[dict[str, str]] = field(default_factory=list)
    reminders: list[dict[str, str]] = field(default_factory=list)
    reply: str | None = None
    reply_reviewed: bool | None = None
    sender: str | None = None
    stance: str | None = None
    sent_copy: str | None = None
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
    # A source failing for longer than its usual gap is one line of its own, which stands in for the question the
    # watcher files about the same source.
    unread: dict[str, Any] = {}
    for watched_source in cfg.watch.sources:
        found = watch.unread(store, cfg, watched_source, now)
        if found is not None:
            unread[watched_source.id] = found
    requests = {r.id: r for r in reader.list("request")}
    # What a newly added source's intake found has one line for the whole source, not one for each item, until the
    # person opens the list.
    on = {s.id for s in cfg.watch.sources}
    intake_unseen = {source: found for source, found in source_intake.unseen(reader).items() if source in on}
    hidden = {r.id for found in intake_unseen.values() for r in found}
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
                found = suggest_owner(reader, cfg, action.id)
                line.suggestion = found.shown(people) if found is not None else None
        elif about in ROUTING or (about == "watch" and resolves.get("source") in unread):
            continue
        else:
            line.kind = "decision" if d.get("kind") == "decision" else "question"
        lines.append(line)
    lines = move_groups.group(reader, people, zone(cfg), lines, Line)

    # Decide: held items with no question (they wait for the person's yes), and runs waiting for a go.
    for cs_id, cs in changesets.items():
        req = by_changeset.get(cs_id)
        if req is None or req.data.get("dismissed") or req.id in hidden:
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
                    held=held_ask.describe(
                        reader,
                        people,
                        outcome.get("op") or {},
                        reporter=outcome.get("reporter"),
                    ),
                    untrusted=cs.get("trust") == "untrusted",
                    since=str(req.data.get("created_at") or ""),
                )
            )
    from engine import catch_up
    from engine.dispatcher import FIRST_GO, waits_on_first_go

    first_go: list[Any] = []
    catch_up_go: list[Any] = []
    intake_go: dict[str, list[Any]] = {}
    for req in requests.values():
        d = req.data
        if d.get("dismissed") or d.get("state") not in ("needs_you", "failed"):
            continue
        if waits_on_first_go(d):
            first_go.append(req)
            continue
        if catch_up.waits_on_go(d):
            catch_up_go.append(req)
            continue
        if source_intake.waits_on_go(d):
            intake_go.setdefault(d["intake"], []).append(req)
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

    from engine.extract import health

    for problem in health.problems(ws):
        # A kind of file that can't be read is never a silent stop: nothing in such files reaches the assistant.
        lines.append(
            Line(
                key=f"extractor:{problem.kind}",
                group="risk",
                kind="extractor",
                text=problem.reason,
                file_kind=problem.kind,
                since=problem.since,
            )
        )

    for watched_source in cfg.watch.sources:
        found = unread.get(watched_source.id)
        if found is None:
            continue
        # A source that can't be read is never a silent stop or a clean "nothing needs you":
        # the line says which, and since when.
        lines.append(
            Line(
                key=f"source_unread:{watched_source.id}",
                group="risk",
                kind="source_unread",
                source=watched_source.id,
                subject=watched_source.label or watched_source.id,
                problem_kind=found.kind,
                text=found.problem,
                waiting_since=found.since,
                since=found.since,
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

    if catch_up_go:
        _, total, unpriced = catch_up.total_waiting(reader)
        lines.append(
            Line(
                key="catch_up_go",
                group="decide",
                kind="catch_up_go",
                count=len(catch_up_go),
                estimate_usd=total,
                unpriced=unpriced,
                waiting=catch_up.WAITING,
                since=min(str(r.data.get("created_at") or "") for r in catch_up_go),
            )
        )

    for source_id, held_for_go in sorted(intake_go.items()):
        # One line for each newly added source, with the total of everything its go starts.
        count, total, unpriced = source_intake.total_waiting(ws, store, cfg, source_id)
        label = next((s.label or s.id for s in cfg.watch.sources if s.id == source_id), source_id)
        lines.append(
            Line(
                key=f"intake_go:{source_id}",
                group="decide",
                kind="intake_go",
                count=count or len(held_for_go),
                source=source_id,
                subject=label,
                days=source_intake.days_taken(reader, source_id),
                estimate_usd=total,
                unpriced=unpriced,
                waiting=source_intake.WAITING,
                since=min(str(r.data.get("created_at") or "") for r in held_for_go),
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

    # Decide: every account a kind of work can use is paused and another kind of work's account is free: ask before
    # borrowing it, once for the pause. Nothing is borrowed without the person's yes.
    if cfg.ai.borrow_other_tier == "ask":
        lines.extend(_borrow_questions(ws, store, cfg, now, requests))

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

    # Risk: an account in a fallback chain that is neither checked for that work nor accepted unchecked, or whose last
    # check failed; its line goes once its check passes.
    from engine.ai.checked import cannot_stand_in

    for found in cannot_stand_in(ws, cfg):
        lines.append(
            Line(
                key=f"account_check:{found.tier}:{found.ref}",
                group="risk",
                kind="account_check",
                account=found.account,
                tier=found.tier,
                model=found.model,
                check_failed=found.failed,
            )
        )

    # Risk: a switch of account or model whose check found problems, or couldn't finish, until the person decides.
    from engine.ai import switch_check

    for tier, entry in sorted(switch_check.failed(store).items()):
        names = list(entry.get("failed") or [])
        lines.append(
            Line(
                key=f"switch_failed:{tier}",
                group="risk",
                kind="switch_failed",
                count=len(names),
                text=str(entry["before"]).partition("/")[0],
                account=str(entry["after"]).partition("/")[0],
                tier=tier,
                names=names[: switch_check.NAMED],
                check_failed=bool(entry.get("unfinished")),
                since=str(entry.get("at") or ""),
            )
        )

    # Risk: a key or sign-in with a known end that is near or past, with every place the same one is used.
    from engine.credentials import expiring

    for found in expiring(ws, cfg, store, now):
        lines.append(
            Line(
                key=f"credential:{found.kind}:{found.name}",
                group="risk",
                kind="credential",
                credential_kind=found.kind,
                credential_name=found.name,
                due=found.ends.isoformat(),
                waiting_days=found.days_left,
                places=found.places,
                since=found.ends.isoformat(),
            )
        )

    # Risk: a kind of work with no AI account to do it, which waits until the person picks one. A workspace with no
    # account at all is a new one: the setup line says so, so this line is for work an account stopped doing.
    unserved = [
        name
        for name, tier in cfg.ai.tiers.items()
        if not tier.use or tier.use.partition("/")[0] not in cfg.ai.providers
    ]
    if unserved and cfg.ai.providers:
        lines.append(
            Line(
                key="no_account",
                group="risk",
                kind="no_account",
                count=len(unserved),
                tier=unserved[0],
                names=unserved,
            )
        )

    # A promise past its date with nothing heard since is a line of its own, with its choices (design 6.33). It is on no
    # other line of the queue: not the overdue line, and not the follow-up line.
    live = {
        cs_id
        for cs_id, req in by_changeset.items()
        if cs_id in changesets and not req.data.get("dismissed") and req.id not in hidden
    }

    def made(action_id: str) -> date | None:
        stamp = _created(reader, "action", action_id)
        return _aware(stamp).astimezone(zone(cfg)).date() if stamp else None

    # What each is to the person decides the line (design 6.33, 6.34): one only watched has none, but is still
    # covered, so no other line picks it up.
    covered = promises.late(reader, cfg, people.pm, today, promises.held_endings(changesets, live), made)
    on_a_line = {x.action for x in covered}
    for x in covered:
        if x.stance == "watch":
            continue
        lines.append(
            Line(
                key=f"promise:{x.action}",
                group="send" if x.owner else "risk",
                kind="promise",
                text=x.text,
                person=x.owner,
                project=x.project,
                due=x.due.isoformat() if x.due else None,
                waiting_days=x.quiet,
                actions=[x.action],
                subject=x.text,
                stance=x.stance,
                since=x.since.isoformat(),
            )
        )

    # Reminders that have reached the person: one line each, and the ones that waited (quiet hours, or a summary of
    # those missed while the computer slept) together as one.
    here = zone(cfg)
    snoozes = [{"choice": choice, "at": at.isoformat()} for choice, at in reminder_lines.choices(cfg, now)]
    reminded = reminder_lines.plan(reader, cfg, now)
    for item in [*reminded.now, *reminded.late]:
        lines.append(
            Line(
                key=f"reminder:{item.action}",
                group="risk",
                kind="reminder",
                text=item.text,
                subject=item.text,
                project=item.project,
                actions=[item.action],
                at=item.due.isoformat(),
                late=item in reminded.late,
                snoozes=snoozes,
                since=item.at.isoformat(),
            )
        )
    for key, group, late in (("quiet", reminded.kept, False), ("missed", reminded.missed, True)):
        if group:
            lines.append(
                Line(
                    key=f"reminder_digest:{key}",
                    group="risk",
                    kind="reminder_digest",
                    count=len(group),
                    late=late,
                    snoozes=snoozes,
                    actions=[x.action for x in group],
                    reminders=[
                        {"action": x.action, "text": x.text, "at": x.due.astimezone(here).isoformat()} for x in group
                    ],
                    since=min(x.at for x in group).isoformat(),
                )
            )

    # Send and follow up: a reply the person owes, one line each, with the draft and its choices (design 6.35). The
    # oldest message comes first.
    for owed in reply_lines.plan(ws, reader):
        lines.append(
            Line(
                key=f"reply:{owed.action}",
                group="send",
                kind="reply",
                text=owed.text,
                subject=owed.subject,
                person=owed.asker,
                sender=owed.sender,
                project=owed.project,
                actions=[owed.action],
                reply=owed.reply,
                reply_reviewed=owed.reviewed,
                since=owed.received.isoformat(),
            )
        )

    # A message the person copied that no sent message matched, asked about once, only while a sent folder is read.
    for item in sent_version.unsent(reader, cfg, now):
        lines.append(
            Line(
                key=f"sent_check:{item.copy}",
                group="send",
                kind="sent_check",
                person=item.person,
                questions=item.questions,
                actions=item.actions,
                sent_copy=item.copy,
                since=item.at.isoformat(),
            )
        )

    # What the assistant or a rule did since yesterday that the person hasn't looked over: one line, in the risk group
    # below promises, which goes when the list is opened and comes back with the next change.
    done = since_yesterday.build(ws, reader, cfg, people, now)
    if done.unseen:
        lines.append(
            Line(
                key="since_yesterday",
                group="risk",
                kind="since_yesterday",
                count=len(done.unseen),
                outcome=done.counts(),
                since=min(e.when for e in done.unseen),
            )
        )

    # Risk: the person's own overdue to-dos, as one line.
    overdue = []
    for action in reader.list("action"):
        d = action.data
        if d.get("status") != "open" or not d.get("due") or d.get("on_hold") or people.pm is None:
            continue
        if action.id in on_a_line:
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
                subject=_one_text(reader, overdue[0][1]) if len(overdue) == 1 else None,
                since=overdue[0][0].isoformat(),
            )
        )

    # Review: the assistant's work waiting for a look.
    for req in requests.values():
        d = req.data
        if d.get("dismissed") or d.get("state") != "review" or not d.get("changeset") or req.id in hidden:
            continue
        cs = changesets.get(d["changeset"]) or {}
        if cs.get("reviewed"):
            continue
        outcome, shown = _outcome_of(cs)
        counted = len(shown)
        if not counted and not outcome.get("refused"):
            continue  # nothing applied, held or refused, so nothing to look over
        # When everything was refused, the line counts what was refused, so the work never waits without a line.
        counted = counted or outcome["refused"]
        lines.append(
            Line(
                key=f"review:{req.id}",
                group="review",
                kind="review",
                count=counted,
                title=title(d, cs),
                subject=(shown[0].get("label") or _op_text(shown[0].get("op") or {}) or None)
                if len(shown) == 1
                else None,
                request=req.id,
                changeset=d["changeset"],
                outcome=outcome,
                untrusted=cs.get("trust") == "untrusted",
                since=str(d.get("created_at") or ""),
            )
        )

    # Review: what a newly added source's intake found, as one line for the source once all of its work is finished.
    for source_id, found in sorted(intake_unseen.items()):
        if any(source_intake.unfinished(r.data) for r in found):
            continue
        total: dict[str, int] = {}
        items = 0
        for req in found:
            cs = changesets.get(req.data.get("changeset") or "")
            if not cs or req.data.get("set_aside") or req.data.get("folded_into"):
                continue
            outcome, shown = _outcome_of(cs)
            if cs.get("reviewed"):
                outcome = {"held": outcome["held"]} if outcome.get("held") else {}
            elif not shown and not outcome.get("refused"):
                continue
            if not outcome:
                continue
            items += 1
            for word, n in outcome.items():
                total[word] = total.get(word, 0) + n
        if items:
            lines.append(
                Line(
                    key=f"intake_review:{source_id}",
                    group="review",
                    kind="intake_review",
                    count=items,
                    source=source_id,
                    subject=next((s.label or s.id for s in cfg.watch.sources if s.id == source_id), source_id),
                    outcome=total,
                    since=min(str(r.data.get("created_at") or "") for r in found),
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
                until=(now + timedelta(days=cfg.dispatch.knowledge.rule_review_every_days))
                .astimezone(zone(cfg))
                .isoformat(),
                since=acted.isoformat() if acted else "",
            )
        )

    # Review: what the assistant learned, as one line for the proposals from inputs and from corrections, and one for
    # the catch-up list of corrections made before it could learn from them.
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

    # Review: what the assistant filed under no project, as one line while there is any.
    from engine.unfiled import unfiled

    loose = unfiled(reader)
    if loose:
        lines.append(
            Line(
                key="unfiled",
                group="review",
                kind="unfiled",
                count=len(loose),
                since=min(i.created_at for i in loose),
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
        # Nothing is chased for someone the person reports to or only watches (design 6.34), so no follow-up is drafted.
        chased = stance_of(reader, cfg.steward, s.person) not in ("report_to", "watch")
        told = [a for a in s.actions if chased and a["chase_due"] and a["id"] not in on_a_line]
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

    if cfg.steward.hold_outside_hours:
        # What the assistant or a rule added on its own waits for the person's hours; what waited arrives under one row.
        caused = release_hours.causes(lines, reader, requests, by_changeset, sources)
        lines = release_hours.keep_hours(lines, caused, cfg, now, Line)
    return sorted(lines, key=_rank)


def _borrow_questions(ws: Any, store: Any, cfg: Any, now: datetime, requests: dict[str, Any]) -> list[Line]:
    """One question per tier whose work waits on paused accounts while an account of another tier is free to take it
    and the person has not answered for this pause: which account, how many waiting items it would take, what they
    would cost together there and when the paused account's limit resets."""
    import os

    from engine.ai.borrow import Borrowed, borrowed_path, lendable
    from engine.ai.checked import cannot_stand_in
    from engine.ai.pauses import Pauses, pauses_path
    from engine.ai.router import Router
    from engine.dispatcher import _data_level, estimate_request

    paused = Pauses(pauses_path(store), lambda: now).active()
    waiting: dict[str, list[Any]] = {}
    for req in requests.values():
        cause = req.data.get("cause") or {}
        if (
            req.data.get("state") == "queued"
            and not req.data.get("dismissed")
            and cause.get("kind") == "paused"
            and cause.get("tier")
            and cause.get("account") in paused
        ):
            waiting.setdefault(cause["tier"], []).append(req)
    if not waiting:
        return []
    answers = Borrowed(borrowed_path(store), lambda: now)
    unchecked = {(s.tier, s.ref) for s in cannot_stand_in(ws, cfg)}
    router = Router(cfg, store, env=os.environ, now=lambda: now)
    found: list[Line] = []
    for tier, reqs in sorted(waiting.items()):
        if answers.get(tier) is not None or tier not in cfg.ai.tiers:
            continue
        offered = lendable(cfg, tier, [_data_level(store, r.data) for r in reqs], set(paused), unchecked)
        if offered is None:
            continue
        ref, _ = offered
        provider, _, model = ref.partition("/")
        takes = [r for r in reqs if _fits(cfg, provider, _data_level(store, r.data))]
        if not takes:
            continue  # nothing the account could take, so nothing to ask about
        priced: list[float] = []
        # An estimate builds the request's packet, so it is kept with the store for as long as the request, its
        # price and the account stay as they are.
        kept: dict[tuple[str, int, str, str], float | None] = store.__dict__.setdefault("_borrow_estimates", {})
        for req in takes:
            key = (req.id, req.version, ref, repr(cfg.ai.prices.get(ref)))
            if key not in kept:
                if len(kept) > 2000:
                    kept.clear()
                try:
                    kept[key] = estimate_request(ws, store, cfg, router, req.id, now, use=ref)
                except Exception:
                    kept[key] = None
            if kept[key] is not None:
                priced.append(kept[key])
        first = min(reqs, key=lambda r: (r.data.get("cause") or {}).get("until") or "")
        cause = first.data.get("cause") or {}
        found.append(
            Line(
                key=f"borrow:{tier}",
                group="decide",
                kind="borrow",
                count=len(takes),
                text=cause.get("account"),
                account=provider,
                model=model,
                tier=tier,
                until=paused[cause["account"]].isoformat(),
                estimate_usd=round(sum(priced), 4) if priced else None,
                unpriced=len(takes) - len(priced),
                since=paused[cause["account"]].isoformat(),
            )
        )
    return found


def _fits(cfg: Any, provider: str, level: str) -> bool:
    """Whether an account may see material at a data level."""
    from engine.ai.router import LEVELS

    return LEVELS.index(level) <= max(LEVELS.index(lv) for lv in cfg.ai.providers[provider].allowed_data)


_KIND_ORDER = {
    "borrow": 1,
    "handover": -3,
    "restart": -2,
    "first_go": -1,
    "decision": 0,
    "who_is": 1,
    "owner": 2,
    "held": 3,
    "go": 4,
    "catch_up_go": 4,
    "intake_go": 4,
    "refused": 5,
    "question": 6,
    "failed": 0,
    "paused": 1,
    "offline": 1,
    "overdue": 2,
    "promise": 2,
    "reminder": 0,
    "reminder_digest": 1,
    "reply": -1,
    "sent_check": 2,
    "since_yesterday": 3,
    "away": -1.5,
    "account_check": 1,
    "switch_failed": 1,
    "credential": 1,
    "no_account": 0,
    "extractor": 1,
    "review": 0,
    "intake_review": 0,
    "rule_review": 1,
    "learned": 2,
    "catch_up": 3,
    "unfiled": 4,
    "moved": 6,
    "send": 0,
    "nudge": 1,
}


def _outcome_of(cs: dict[str, Any]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """What a changeset did, counted by the outcome word the screen uses (held and refused ops counted as such), and
    the ops that were applied or are held."""
    outcome: dict[str, int] = {}
    for o in cs.get("ops", []):
        status = o.get("status")
        if status in ("held", "refused"):
            outcome[status] = outcome.get(status, 0) + 1
        if status != "applied" and status != "held":
            continue
        word = _OUTCOME.get((o.get("op") or {}).get("op", ""), "other")
        outcome[word] = outcome.get(word, 0) + 1
    return outcome, [o for o in cs.get("ops", []) if o.get("status") in ("applied", "held")]


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


def _one_text(reader: Any, action_id: str) -> str | None:
    action = reader.get("action", action_id)
    return str(action.data["text"]) if action is not None and action.data.get("text") else None


def _created(reader: Any, kind: str, record_id: str) -> str:
    entries = reader.ledger(kind=kind, record_id=record_id)
    return str(entries[0]["at"]) if entries else ""
