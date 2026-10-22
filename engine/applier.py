"""The applier (design 6.7): check a proposed changeset, resolve names, hold what needs the PM, apply the rest in one
transaction with a ledger entry per field, and undo by op group.

Checks are invariants (always refuse the op) or lints (severity from config/checks.yaml). Refusals and lints that
would refuse or return are fed back to the AI by the dispatcher first; what still fails is decided here: refused ops are
dropped and shown, returned lints hold an op that would reach another person and only warn otherwise.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from email.utils import parseaddr
from typing import Any, Literal

from pydantic import ValidationError

from engine import (
    acts,
    audience,
    draft_checks,
    endings,
    id_words,
    knowledge,
    learn,
    outward,
    proposals,
    reminder_entries,
    reply_lines,
    scope,
    sides,
    signature_contact,
    standing_yes,
)
from engine import agenda as agenda_module
from engine import search as workspace_search
from engine import series as series_module
from engine.blocked import blocker_problem
from engine.check_text import numbered_questions, quoted_passages, without_links, words_of
from engine.cleaning import normalize
from engine.config import Config, ConfigError, load_config
from engine.config.yaml_edit import set_key
from engine.intake import is_reported, source_text
from engine.learning import request_learns
from engine.names import People
from engine.ops import (
    ACT_OPS,
    ACT_PUBLISHER_OPS,
    EVIDENCE_FIELDS,
    KNOWLEDGE_ADD_OPS,
    KNOWLEDGE_OPS,
    NEEDS_EVIDENCE,
    PERSON_ONLY_OPS,
    SETTABLE,
    STANDING_YES_OPS,
    ActApproveOp,
    ActDraftOp,
    ActEditOp,
    ActionAddOp,
    ActionCloseOp,
    ActionDropOp,
    ActionHoldOp,
    ActionMoveOp,
    ActionNewsOp,
    ActionPartOp,
    ActionRepeatOp,
    ActionReplyOp,
    ActionUnholdOp,
    AgendaAddOp,
    AnswerOp,
    ChangesetIn,
    EventAddOp,
    EventSetOp,
    EvidenceIn,
    FactOp,
    FileAddOp,
    ListMergeOp,
    MailRestoreOp,
    NoteOp,
    OpModel,
    PersonAddOp,
    PersonContactOp,
    PersonStanceOp,
    ProjectAddOp,
    ProjectRoleOp,
    QuestionAddOp,
    QuestionDoneOp,
    QuestionDropOp,
    QuestionMarkSentOp,
    QuestionMoveOp,
    QuestionUpdateOp,
    RecordDeleteOp,
    RecordEditOp,
    RecordLogOp,
    RecordSetOp,
    ReminderEntryOp,
    ReportDraftOp,
    RoutingAddOp,
    RuleAddOp,
    RuleRetireOp,
    SeriesAddOp,
    SeriesLinkOp,
    SettingProposeOp,
    SourceLimitOp,
    SourceWidenOp,
    StageMoveOp,
    TextAcceptOp,
    TextDiscardOp,
    TextDraftOp,
    TextEditOp,
    TextProposeOp,
    reach_choices,
    reach_problem,
)
from engine.plugin_api import NeedsPerson
from engine.records import REGISTRY, entry_problem, model_for
from engine.reply_split import split_message
from engine.rule_use import RULE_CHECK, failing_rules
from engine.storage import Store, StoreError, WriteContext
from engine.storage.store import Tx
from engine.text_shape import error_problem, items_problem, text_problem
from engine.titles import title_for
from engine.today import local_day, zone
from engine.workspace import Workspace

Severity = Literal["refuse", "return", "hold", "warn"]


@dataclass(frozen=True)
class Problem:
    check: str
    severity: Severity
    op: int | None
    message: str
    passage: str | None = None  # the exact words it is about, when a lint names them
    guidance: str | None = None  # how to fix it
    rule: str | None = None  # the rule record whose check found it


@dataclass
class Inputs:
    """What a changeset may cite as evidence, and who it came from."""

    request: str
    source: str | None
    raw_input: str
    note: str
    trust: Literal["trusted", "untrusted"]
    cites: str | None = None  # what the input is cited as when it isn't a saved source, e.g. "<kind>:<id>"

    def evidence_source(self, quote: str) -> str | None:
        """The source id (or what the input is cited as, or "note") that contains the quote, if any does."""
        q = normalize(quote)
        cited = self.source or self.cites
        if cited and q and q in normalize(self.raw_input):
            return cited
        if q and q in normalize(self.note):
            return "note"
        return None


@dataclass
class Context:
    store: Store
    cfg: Config
    people: People
    allowed_ops: tuple[str, ...]
    inputs: Inputs
    hidden_words: list[str] = field(default_factory=list)
    confirmed_by_pm: bool = False
    # "pm" for a person action, whose exact proposal the person saw; "publisher" for the publisher's own state changes
    # "reminders" for the engine's own reminders: they draft a reminder act and, under the person's standing yes,
    # approve one that matches it exactly (design 6.12), and may do nothing else.
    actor: Literal["assistant", "pm", "publisher", "reminders"] = "assistant"
    via: str | None = None  # "handler" or "job" for ops a plugin staged; otherwise worked out from the inputs
    # For an AI run: whether it searched the workspace before answering. None for anything that isn't one, which the
    # search-first check leaves alone.
    searched: bool | None = None
    data_level: str = "restricted"  # the most sensitive material a search may quote back, for an AI run
    reporter: str | None = None  # who reported a held ending, as worked out when it was held; set when it is kept
    run: str | None = None  # the AI run that wrote the changeset, set by `apply_changeset`


# ---- checks ----------------------------------------------------------------------------------------------------------


def restatements(cs: ChangesetIn, ctx: Context) -> ChangesetIn:
    """A promise said again with a date outside the merge window is a move of the open promise, never a second one
    (design 6.33): each such `action.add` becomes an `action.move` on the open promise, with the new words and quote.
    A phone number in a known sender's signature that the answer doesn't offer is added as a `person.contact` op (held
    for the person like any). An action, question, fact or note naming no project is filed under the personal or
    business side by the people it names and the sender (`engine/sides.py`, design 6.32). The same changeset always
    gives the same result, so a check and the apply that follows see the same ops."""
    view = ctx.store.read()
    ops = list(cs.ops)
    for i, op in enumerate(ops):
        if not isinstance(op, ActionAddOp) or op.due_at_event or op.waiting_for:
            continue
        same = _same_promise(view, ctx, op)
        if same is None:
            continue
        due, _ = _due(view, ctx, ctx.inputs.source, op.due_words, op.due)
        if due is None or _within_window(same.data.get("due"), due, ctx):
            continue
        ops[i] = ActionMoveOp(
            id=same.id,
            due_words=op.due_words,
            due=None if (op.due_words or "").strip() else op.due,
            evidence=op.evidence,
            group=op.group,
        )
    if ctx.actor != "pm" and not ctx.confirmed_by_pm and "person.contact" in ctx.allowed_ops:
        ops += signature_contact.proposals(
            ctx.inputs.raw_input, view, ctx.cfg, ctx.people, contact_kind(ctx.cfg, "phone"), ops
        )
    if ctx.actor != "pm" and not ctx.confirmed_by_pm:
        ops = sides.file_by_people(ops, view, ctx.cfg, ctx.people, _reporter(ctx), ctx.inputs.raw_input)
    else:
        # Only the filing above says why an item was filed; a reason arriving any other way is not kept.
        ops = sides.without_filed_by(ops)
    return cs if ops == list(cs.ops) else cs.model_copy(update={"ops": ops})


def check(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    cs = endings.read_endings(restatements(cs, ctx), ctx)
    problems: list[Problem] = _validate_in_order(cs, ctx)
    problems += _required_ops(cs, ctx)
    problems += _too_many_ops(cs, ctx)
    problems += _learning_reach(cs, ctx)
    problems += _learning_question(cs, ctx)
    problems += _miss_left_unlearned(cs, ctx)
    problems += _follow_on_reach(cs, ctx)
    problems += _thread_promise_unanswered(cs, ctx)
    problems += _owner_mail_unanswered(cs, ctx)
    problems += _own_promise_missed(cs, ctx)
    problems += _promise_as_fact(cs, ctx)
    problems += _due_move_missed(cs, ctx)
    problems += _project_start_as_fact(cs, ctx)
    problems += _claim_asked_of_the_person(cs, ctx)
    view = ctx.store.read()
    plugins = ctx.store.plugins
    lints = ctx.cfg.checks.lints
    known_actions = view.list("action")
    similarity = ctx.cfg.checks.tuning.near_duplicate_action.similarity
    first_week = _FirstWeek(ctx, view)
    assistant_names = outward.assistant_names(view, ctx.cfg.workspace.assistant_name)
    id_prefixes = id_words.prefixes(plugins.records)
    origin = origin_of(ctx)
    about = origin.get("about") or {}
    about_record = view.get(about["kind"], about["id"]) if about.get("kind") and about.get("id") else None
    about_project = (
        about_record.id
        if about_record is not None and about_record.kind == "project"
        else (about_record.data.get("project") if about_record is not None else None)
    )

    def refuse(i: int, check_name: str, message: str) -> None:
        problems.append(Problem(check_name, "refuse", i, message))

    def lint(i: int, name: str, message: str) -> None:
        severity = lints.get(name, "off")
        if severity == "return" and name in WORDING_LINTS and not _reaches_someone_else(cs.ops[i], ctx):
            severity = "warn"  # wording on an item that stays internal only warns; no fix round is spent on it
        if severity == "return" and name in OWNER_WORDING_LINTS and not _owned_by_someone_else(cs.ops[i], ctx):
            severity = "warn"  # an action only the person reads is theirs to word; the lint says so without a fix round
        if severity != "off":
            problems.append(Problem(name, severity, i, message))

    for i, op in enumerate(cs.ops):
        name = op.op
        if name not in ctx.allowed_ops:
            refuse(i, "allowed-ops", f"{name} isn't an op this task may use")
            continue
        # The outward act (design 6.12): only the person says yes, only the publisher records what happened outside,
        # and content from outside never adds an act or a recipient.
        if name in ACT_OPS:
            if isinstance(op, ActApproveOp):
                if op.by_standing is None and ctx.actor != "pm":
                    refuse(
                        i,
                        "act-approval",
                        "only the person's own yes approves an act; the assistant and add-ons may only draft",
                    )
                    continue
                if op.by_standing is not None:
                    # The one approval that isn't a click on the act: the engine's reminders, under the standing yes,
                    # for an act that matches it in every respect (checked here, not by the caller).
                    why = (
                        "only the engine's reminders approve under a standing yes"
                        if ctx.actor != "reminders"
                        else standing_yes.approval_problem(
                            ctx.store, ctx.cfg, view, ctx.people, view.get("act", op.id), op.by_standing
                        )
                    )
                    if why is not None:
                        refuse(i, "act-approval", why)
                        continue
            if isinstance(op, ActDraftOp) and (
                why := standing_yes.draft_problem(ctx.store, ctx.cfg, view, ctx.people, ctx.actor, op)
            ):
                refuse(i, "act-reminder", why)
                continue
            if name in ACT_PUBLISHER_OPS and ctx.via != "publisher":
                refuse(i, "act-publisher-only", f"{name} is the publisher's alone: it records what happened to an act")
                continue
            if name in ("act.draft", "act.edit") and ctx.actor != "pm" and ctx.inputs.trust == "untrusted":
                refuse(
                    i,
                    "act-from-outside",
                    "content from outside never adds an act or a recipient: the person drafts it, or says to",
                )
                continue
            if isinstance(op, ActDraftOp) and ctx.actor != "pm" and (why := acts.stranger_problem(ctx, op)) is not None:
                refuse(i, "act-recipient", why)
                continue
            if isinstance(op, (ActDraftOp, ActEditOp)):
                held = view.get("act", op.id) if isinstance(op, ActEditOp) else None
                drawn = (
                    [*op.sources, *([op.in_reply_to] if op.in_reply_to else [])]
                    if isinstance(op, ActDraftOp)
                    else (held.data["sources"] if held is not None else [])
                )
                who = acts.op_recipients(op)
                if who and (why := acts.audience_problem(view, ctx.people, drawn, who)) is not None:
                    refuse(i, "audience", why)
                    continue
        # The person's own note saying they already asked is theirs to file; outside content never is.
        if name in PERSON_ONLY_OPS and ctx.actor != "pm" and not (name == "question.mark_sent" and _from_pm(view, ctx)):
            refuse(i, "person-only", f"only the person can use {name}")
            continue
        # What others read never names the assistant, whoever wrote it but the person on their own screen.
        if ctx.actor != "pm" and (why := outward.op_problem(op, assistant_names)) is not None:
            refuse(i, "names-assistant", why)
            continue
        # A title is never a record's id: an id is how the product refers to a record, not a word for a person.
        if ctx.actor != "pm" and (why := id_words.id_problem(op, view, id_prefixes)) is not None:
            refuse(i, "id-in-title", why)
            continue
        if isinstance(op, (TextEditOp, TextProposeOp, TextDraftOp)):
            why = _text_target(ctx.store, view, op.record.kind, op.record.id, op.field)
            if why:
                refuse(i, "targets", why)
                continue
        if isinstance(op, (TextAcceptOp, TextDiscardOp)):
            pending = view.get("text_version", op.version)
            if pending is None or pending.data["status"] != "pending":
                refuse(i, "targets", f"{op.version} isn't a version waiting for review")
                continue
            if pending.version != op.read_version:
                refuse(i, "record-changed", f"{op.version} changed since it was reviewed")
                continue
        if isinstance(op, RecordDeleteOp):
            target = view.get(op.record.kind, op.record.id)
            if target is None or target.version != op.read_version:
                refuse(i, "record-changed", f"{op.record.kind} {op.record.id} is gone or changed since it was read")
                continue
            users = ctx.store.plugins._referrers(view)(op.record.kind, op.record.id)
            if users:
                refuse(
                    i,
                    "still-referred-to",
                    f"{op.record.kind} {op.record.id} is still referred to by {users[0][0]} {users[0][1]}",
                )
                continue
        if isinstance(op, StageMoveOp):
            from engine.stages import validate_move, wording

            # Even a trusted PM note interpreted by AI is a proposal, never consent.
            messages = [wording(ctx.cfg, "confirm")]
            try:
                validate_move(ctx.store, op, view)
            except StoreError as err:
                messages.append(str(err))
            problems.append(Problem("stage-confirm", "hold", i, "; ".join(messages)))
        if isinstance(op, FactOp) and (why := _fact_problem(op, ctx)) is not None:
            refuse(i, "targets", why)
        # evidence
        evidence = _evidence(op)
        needs = (
            name in NEEDS_EVIDENCE
            or (isinstance(op, RecordSetOp) and op.field in EVIDENCE_FIELDS)
            # A status is an evidence field wherever it is set: one nobody stated stays unknown.
            or (isinstance(op, ProjectAddOp) and op.status is not None)
        )
        # Evidence backs claims taken from inputs; the person's own change (actor pm) isn't one.
        if needs and evidence is None and ctx.actor != "pm":
            refuse(i, "evidence", f"{name} needs evidence: the exact words from the input that justify it")
        if evidence is not None and ctx.inputs.evidence_source(evidence.quote) is None:
            refuse(i, "evidence", f"the quote {evidence.quote!r} isn't in the input; copy the words exactly")
        if isinstance(op, AnswerOp):
            for cite in op.cites:
                if ctx.inputs.evidence_source(cite.quote) is None:
                    refuse(i, "evidence", f"the quote {cite.quote!r} isn't in the material; copy the words exactly")
        if isinstance(op, SettingProposeOp):
            why = setting_problem(ctx.store, op.setting, op.value)
            if why:
                refuse(i, "targets", why)
        if name in KNOWLEDGE_OPS and (why := knowledge.problem(view, op)) is not None:
            refuse(i, "targets", why)
        if (
            ctx.inputs.trust == "untrusted"
            and isinstance(op, RecordSetOp)
            and op.kind == "question"
            and op.field in ("title", "text")
        ):
            refuse(
                i,
                "outside-reword",
                "only the person rewords a question; add what the input says as a note on the question (note with "
                "its question id), quoting both when it contradicts",
            )
        if ctx.inputs.trust == "untrusted" and isinstance(op, RoutingAddOp) and op.person is not None:
            sender = _reporter(ctx)
            if op.person == ctx.people.pm or (not op.negative and sender is not None and op.person == sender):
                refuse(
                    i,
                    "outside-routing",
                    "content from outside never routes work away from the person: record what it asks as a fact and "
                    'ask the person one decision; a sender\'s own "not me, ask someone else" is the only routing it '
                    "may propose",
                )
        if isinstance(op, RoutingAddOp) and not (ctx.actor == "pm" or ctx.confirmed_by_pm or _from_pm(view, ctx)):
            discarded = proposals.discarded_routing(
                view,
                op.topic,
                op.person,
                op.team,
                op.negative,
                ctx.cfg.dispatch.knowledge.routing_match,
            )
            if discarded is not None:
                refuse(
                    i,
                    "discarded-routing",
                    f"you discarded {discarded[0].id}, which says the same, on {discarded[1].date().isoformat()}; "
                    "only your own words bring it back",
                )
        reach = getattr(op, "applies_to", None)
        if reach is not None and (why := reach_problem(reach, reach_choices(plugins), plugins.records)) is not None:
            refuse(i, "targets", why)
        if isinstance(op, ReportDraftOp) and learn.rule_in_report(ctx.cfg, op.title, op.text) is not None:
            refuse(
                i,
                "rule-not-report",
                "This reads as a standing rule for the assistant, not a request for a change to the product. Don't "
                "report it to the maintainers: propose it as a rule, which waits for the person.",
            )
        # targets
        for project in _projects_of(op):
            if view.get("project", project) is None:
                refuse(i, "targets", f"there is no project {project}")
        if isinstance(op, EventAddOp) and (why := entry_problem(op.start, op.end)) is not None:
            refuse(i, "targets", f"calendar entry {op.title!r}: {why}")
        if isinstance(op, EventAddOp) and op.series is not None and view.get("series", op.series) is None:
            refuse(i, "targets", f"there is no series {op.series}")
        if isinstance(op, EventSetOp):
            entry = view.get("event", op.id)
            if entry is None:
                refuse(i, "targets", f"there is no calendar entry {op.id}")
            elif (why := entry_problem(op.start or entry.data["start"], op.end or entry.data.get("end"))) is not None:
                refuse(i, "targets", f"calendar entry {op.id}: {why}")
        if isinstance(op, (FactOp, ActionAddOp, QuestionAddOp)) and (
            why := series_module.item_problem(view, op.event, op.series)
        ):
            refuse(i, "targets", why)
        if isinstance(op, SeriesAddOp):
            for entry in op.events:
                found = view.get("event", entry)
                if found is None:
                    refuse(i, "targets", f"there is no calendar entry {entry}")
                elif found.data.get("series"):
                    refuse(i, "targets", f"calendar entry {entry} is already part of a series")
            if len(set(op.events)) != len(op.events):
                refuse(i, "targets", "a calendar entry is named twice in events")
        if isinstance(op, SeriesLinkOp) and (why := series_module.link_problem(view, op.event, op.series)):
            refuse(i, "targets", why)
        if isinstance(op, AgendaAddOp) and (why := agenda_module.problem(view, op)):
            refuse(i, "targets", why)
        if isinstance(op, ActionCloseOp):
            target = view.get("action", op.id)
            if target is None:
                refuse(i, "targets", f"there is no action {op.id}")
            elif target.data["status"] == "done":
                refuse(i, "targets", f"action {op.id} is already done")
            elif target.data["status"] == "dropped":
                refuse(i, "targets", f"action {op.id} was dropped, so it can't be closed")
            elif evidence is not None and not _about_action(evidence.quote, target, view, ctx):
                lint(i, "evidence-fit", f"the quote doesn't seem to be about action {op.id}")
        if isinstance(op, (ActionMoveOp, ActionPartOp, ActionNewsOp)):
            why = action_hold_problem(view, op)
            if why:
                refuse(i, "targets", why)
            elif evidence is not None and not _about_action(evidence.quote, view.get("action", op.id), view, ctx):
                lint(i, "evidence-fit", f"the quote doesn't seem to be about action {op.id}")
        if isinstance(op, ActionRepeatOp):
            from engine import repeats

            if op.id.startswith("@"):
                why = _repeat_ref_problem(cs.ops, i)
            elif op.words is not None:
                why = None  # read in order, against what the earlier ops made (`_validate_in_order`)
            else:
                why = repeats.problem(view, op)
            if why:
                refuse(i, "targets", why)
            elif not _persons_own(view, ctx):
                # A repeat read from an input waits for the person's yes, like an ending read from one.
                said = f' The words: "{" ".join(op.words.split())}".' if op.words else ""
                problems.append(Problem("repeat-confirm", "hold", i, REPEAT_WAITS + said))
        if endings.asks(op, ctx):
            # Closed with no delivery words or call-off words (or both) is one choice, even in the person's own note.
            problems.append(Problem(endings.CHOICE_CHECK, "hold", i, endings.CHOICE_WAITS))
        if isinstance(op, ENDING_OPS) and not _persons_own(view, ctx):
            # How a promise ends is the person's to keep when it was read from what came in (design 6.33).
            problems.append(Problem("ending-confirm", "hold", i, ENDING_WAITS))
        if isinstance(op, (ActionHoldOp, ActionDropOp)):
            why = action_hold_problem(view, op)
            if not why and isinstance(op, ActionHoldOp) and op.on:
                why = blocker_problem(view, op.id, op.on)
            if why:
                refuse(i, "targets", why)
            elif evidence is not None and not _shares_words(evidence.quote, view.get("action", op.id).data["text"]):
                lint(i, "evidence-fit", f"the quote doesn't seem to be about action {op.id}")
            if isinstance(op, ActionDropOp) and not why and _waits_for_a_look(view, ctx, "action", op.id):
                problems.append(Problem("reached-confirm", "hold", i, REACHED_WAITS))
            if isinstance(op, ActionDropOp) and not why and (op.event or op.series):
                why = agenda_module.problem(view, AgendaAddOp(event=op.event, series=op.series, action=op.id))
                if why:
                    refuse(i, "targets", why)
        if isinstance(op, ActionUnholdOp):
            why = action_unhold_problem(view, op)
            if why:
                refuse(i, "targets", why)
            elif evidence is not None:
                held = view.get("action", op.id).data
                if not _shares_words(evidence.quote, f"{held['text']} {held['on_hold']['waiting_for']}"):
                    lint(i, "evidence-fit", f"the quote doesn't seem to be about action {op.id}")
        if isinstance(op, QuestionDoneOp):
            target = view.get("question", op.id)
            if target is None:
                refuse(i, "targets", f"there is no question {op.id}")
            elif target.data["status"] in ("answered", "dropped"):
                refuse(i, "targets", f"question {op.id} is already closed")
            elif evidence is not None and not _shares_words(evidence.quote, target.data["title"] + " " + op.answer):
                lint(i, "evidence-fit", f"the quote doesn't seem to answer question {op.id}")
        if isinstance(op, ActionReplyOp):
            why = action_reply_problem(view, op)
            if why:
                refuse(i, "targets", why)
        if isinstance(op, (QuestionUpdateOp, QuestionMoveOp, QuestionDropOp, QuestionMarkSentOp)):
            why = question_correction_problem(ctx, view, op)
            if why:
                refuse(i, "targets", why)
            elif isinstance(op, QuestionDropOp) and _waits_for_a_look(view, ctx, "question", op.id):
                problems.append(Problem("reached-confirm", "hold", i, REACHED_WAITS))
        if isinstance(op, ListMergeOp):
            from engine import lists

            why = lists.merge_problem(view, op)
            if why:
                refuse(i, "targets", why)
        if isinstance(op, MailRestoreOp):
            from engine import set_aside

            why = set_aside.restore_problem(view, op.snapshot)
            if why:
                refuse(i, "targets", why)
        if isinstance(op, RecordEditOp):
            why = edit_problem(ctx.store, view, op)
            if why:
                refuse(i, "targets", why)
        if isinstance(op, RecordSetOp):
            target = view.get(op.kind, op.id)
            if target is None:
                refuse(i, "targets", f"there is no {op.kind} {op.id}")
            elif op.field not in SETTABLE[op.kind]:
                refuse(i, "targets", f"{op.kind}.{op.field} can't be changed this way")
            elif op.kind == "action" and op.field == "due" and target.data.get("status") not in ("open", "held"):
                refuse(
                    i,
                    "targets",
                    f"action {op.id} is {target.data.get('status')}, so it has no day to move: a new day goes on the "
                    "open action the words are about",
                )
            else:
                try:
                    model_for(op.kind).model_validate({**target.data, op.field: op.value})
                except ValidationError as err:
                    first = err.errors()[0]
                    refuse(
                        i,
                        "targets",
                        error_problem(first, f"{op.kind}.{op.field}") or f"{op.kind}.{op.field}: {first['msg']}",
                    )
                else:
                    if op.kind == "project" and op.field == "parent" and op.value is not None:
                        why = parent_problem(view, op.id, op.value)
                        if why:
                            refuse(i, "targets", why)
                    if op.field in ("event", "series"):
                        merged = {**target.data, op.field: op.value}
                        why = series_module.item_problem(view, merged.get("event"), merged.get("series"))
                        if why:
                            refuse(i, "targets", why)
        if isinstance(op, PersonContactOp):
            why = contact_problem(view, ctx.cfg, op)
            if why:
                refuse(i, "targets", why)
            elif ctx.actor != "pm" and not ctx.confirmed_by_pm:
                # Whoever proposes it, a way to reach someone waits for the person.
                problems.append(Problem("contact-confirm", "hold", i, CONTACT_WAITS))
        if isinstance(op, PersonStanceOp):
            if view.get("person", op.id) is None:
                refuse(i, "targets", f"there is no person {op.id}")
            elif op.id == ctx.people.pm:
                refuse(i, "targets", "a stance is toward someone else, never yourself")
        if isinstance(op, ProjectAddOp):
            taken = {p.data["name"].strip().lower() for p in view.list("project")}
            if op.name.strip().lower() in taken:
                refuse(i, "targets", f"there is already a project called {op.name}")
            if op.parent is not None and view.get("project", op.parent) is None:
                refuse(i, "targets", f"there is no project {op.parent}")
            if op.language is not None and not re.fullmatch(LANGUAGE_TAG, op.language):
                refuse(i, "targets", f"{op.language} isn't a language tag such as en-US")
            from engine.projects import chain

            above = {p.id for p in chain(view, op.parent)} if op.parent else set()
            for child in op.children:
                if view.get("project", child) is None:
                    refuse(i, "targets", f"there is no project {child}")
                elif child in above:
                    refuse(i, "targets", f"{child} can't go inside a project that is inside it")
            if len(set(op.children)) != len(op.children):
                refuse(i, "targets", "a project is named twice in children")
        if isinstance(op, ProjectRoleOp):
            who = ctx.people.resolve(op.person)
            if who.status != "ok":
                refuse(i, "targets", f"{op.person} isn't one known person, so a role can't be set for them")
        # a question or report from a run that never searched: is it already answered by what the workspace knows?
        asked = _asked_subject(op, name)
        if (
            asked is not None
            and ctx.actor != "pm"
            and ctx.searched is False
            and lints.get("already-known", "off") != "off"
        ):
            known = workspace_search.known_answer(
                ctx.store,
                asked,
                similarity=ctx.cfg.checks.tuning.already_known.similarity,
                asking_words=ctx.cfg.language.asking_words,
                level=ctx.data_level,
            )
            if known is not None:
                lint(
                    i,
                    "already-known",
                    (
                        f"{known.id} looks like the answer: {known.text} Draft the reply from it, naming where it "
                        "comes from in words (never the id)."
                        if isinstance(op, ActionAddOp)
                        else f"this looks answered by {known.id}: {known.text} If it doesn't answer this, search for "
                        "what is missing before asking."
                    ),
                )
        # a draft to someone goes only to people a limited message it draws on may go to (design 6.35)
        if (isinstance(op, (QuestionAddOp, QuestionMoveOp)) or (isinstance(op, ActionAddOp) and op.reply)) and (
            why := _audience_problem(view, ctx, op)
        ) is not None:
            refuse(i, "audience", why)
        if isinstance(op, SourceLimitOp) and (found := source_limit_problem(view, ctx, op)) is not None:
            refuse(i, found[0], found[1])
        if isinstance(op, SourceWidenOp) and (why := source_widen_problem(view, ctx, op)) is not None:
            refuse(i, "targets", why)
        # questions to other people
        if isinstance(op, QuestionAddOp):
            resolved = ctx.people.resolve(op.to)
            to_pm = resolved.person == ctx.people.pm
            if not to_pm:
                if not op.links:
                    refuse(i, "question-links", "a question to someone else needs a link to what it is about")
                for link in op.links:
                    if not _openable(link.url):
                        refuse(i, "question-links", f"{link.url} isn't a link the recipient can open")
            _wording(i, op.title + " " + op.text, ctx, lint, _quotes_in(op, ctx))
            _item_text(i, op.title, ctx, lint, _quotes_in(op, ctx), asks=True)
            if not to_pm:
                _for_reader(i, op.title + " " + op.text, ctx, lint)
            minimum = ctx.cfg.checks.tuning.several_questions.minimum
            if numbered_questions(op.text) >= minimum:
                lint(
                    i,
                    "several-questions",
                    f"the text holds {minimum} or more numbered questions; ask each as its own question, so each has "
                    "its own answer and follow-through",
                )
            if not to_pm and not (op.matters_for or "").strip():
                lint(
                    i,
                    "question-without-stake",
                    "a question to someone else names which of the PM's decisions, designs or dated items depends on "
                    "the answer (matters_for); without one, record it as a fact and say so in the change's note",
                )
            if lints.get("near-duplicate-question", "off") != "off":
                match = _near_duplicate_question(ctx, view, op.title, resolved.person)
                if match is not None:
                    state = "answered question" if match.data["status"] == "answered" else "open question"
                    lint(i, "near-duplicate-question", f"looks like {state} {match.id}: {match.data['title']}")
        if isinstance(op, ActionAddOp):
            quotes = _quotes_in(op, ctx)
            reads = words_of(op.text, quotes)
            _wording(i, op.text, ctx, lint, quotes)
            if op.reply:
                _wording(i, op.reply, ctx, lint, quotes)
                _for_reader(i, op.reply, ctx, lint)
            if any(sep in reads for sep in ctx.cfg.language.run_on_separators):
                lint(i, "run-on-list", "the action crams several items into one line; make one action per task")
            _item_text(i, op.text, ctx, lint, quotes)
            if not _stands_alone(without_links(op.text), ctx):
                lint(
                    i,
                    "action-stands-alone",
                    "the action leans on something the reader can't see: say what it is about, by name, so it reads "
                    'on its own ("Send the proof to the printer", not "Send it")',
                )
            if op.promised_to and len(op.owners) > 1:
                refuse(
                    i,
                    "one-owner",
                    "one promise per owner: for two people who each owe it, add one action each; for work they do "
                    'together, keep one action with both owners and leave "promised_to" out',
                )
            if op.due_at_event and not (op.event or op.series):
                refuse(i, "targets", "a date at a calendar entry needs the entry: give its event or series")
            if op.reply_owed and (why := _reply_owed_problem(view, ctx, op)) is not None:
                refuse(i, "reply-not-owed", why)
            if (level := _team_word_one_owner_level(op, ctx)) != "off":
                problems.append(
                    Problem(
                        "team-we-one-owner",
                        level,
                        i,
                        'the words say "we", not who: leave "owners" empty so the person picks one, unless the '
                        "words name who does it",
                    )
                )
            if readers := _owed_to_readers(op, ctx):
                names = ", ".join(ctx.people.name(r) for r in readers)
                ids = ", ".join(f'"{r}"' for r in readers)
                problems.append(
                    Problem(
                        "promise-owed-to-reader",
                        ctx.cfg.checks.projects.get(op.project or "", {}).get("promise-owed-to-reader")
                        or ctx.cfg.checks.lints.get("promise-owed-to-reader", "off"),
                        i,
                        f"the sender promised this in mail to {names}, so it is owed to them: give "
                        f'"promised_to" [{ids}]',
                    )
                )
            if (owed := _possessed_by(op, ctx)) is not None:
                problems.append(
                    Problem(
                        "owed-to-missing",
                        ctx.cfg.checks.projects.get(op.project or "", {}).get("owed-to-missing")
                        or ctx.cfg.checks.lints.get("owed-to-missing", "off"),
                        i,
                        f"the words name {ctx.people.name(owed)} as the one it belongs to: if the person owes it to "
                        f'them, give "promised_to" ["{owed}"]',
                    )
                )
            if (level := _someone_owner_level(op, ctx)) != "off":
                problems.append(
                    Problem(
                        "someone-given-owner",
                        level,
                        i,
                        'the words say "someone", not who: leave "owners" empty so the person picks one (or ask them '
                        "who takes it), unless the words name who does it",
                    )
                )
            if (level := _own_request_level(op, ctx, view)) != "off":
                problems.append(
                    Problem(
                        "own-request-not-promise",
                        level,
                        i,
                        "the person asked someone else to do this, so it isn't their promise: a request nobody has "
                        "accepted is no action",
                    )
                )
            for existing in [] if _same_promise(view, ctx, op) is not None else known_actions:
                if _similar(op.text, existing.data["text"]) >= similarity:
                    state = {"done": "done action", "dropped": "dropped action"}.get(
                        existing.data["status"], "open action"
                    )
                    lint(i, "near-duplicate-action", f"looks like {state} {existing.id}: {existing.data['text']}")
                    break
        if isinstance(op, (QuestionAddOp, ActionAddOp)) and ctx.actor != "pm" and _guessed_recipient(ctx, view, op):
            lint(
                i,
                "unnamed-recipient",
                "the input says it was already sent but not to whom, so this names a recipient it doesn't give; "
                "don't pick the nearest name. Ask the person who it went to, as a decision.",
            )
        if ctx.actor != "pm":
            problems += first_week.problems(i, op, lints)
            # The person's own note decides what they track; the scope checks read what came in.
            if not _from_pm(view, ctx):
                for found_name, found in scope.findings(
                    op,
                    view,
                    ctx.people,
                    ctx.cfg.language,
                    (_projects_of(op) or [about_project])[0],
                ):
                    lint(i, found_name, found)
                for found_name, found in scope.stance_findings(op, view, ctx.people, ctx.cfg.steward):
                    lint(i, found_name, found)
            if (
                isinstance(op, QuestionAddOp)
                and about_record is not None
                and about_record.kind == "question"
                and ctx.people.resolve(op.to).person == about_record.data.get("to")
                and _rejects_asking(ctx)
            ):
                lint(
                    i,
                    "rejected-ask",
                    "the note rejects asking this at all, not its wording: drop the question with question.drop and "
                    "the note's own words as the reason, instead of asking them again in other words",
                )
        # plugins' lints: soft checks on the assistant's proposals (never the person's own changes), with the
        # severity the workspace sets, or sets for this project's work (never a refusal by default)
        if ctx.actor != "pm":
            own = _projects_of(op) or ([about_project] if about_project else [])
            per_project = ctx.cfg.checks.projects.get(own[0], {}) if own else {}

            def severity(name: str, default: str, per_project: dict = per_project) -> str:
                return per_project.get(name) or lints.get(name, default)

            for name, level, found in ctx.store.plugins.lint_findings(op, view, severity, origin):
                problems.append(Problem(name, level, i, found.message, found.passage, found.guidance))
        # never shown
        text = " ".join(_texts(op)).lower()
        for word in ctx.hidden_words:
            if word and re.search(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?![a-z0-9])", text):
                refuse(i, "never-shown", "text people will see mentions the AI model or service")
                break
        # tiers
        # A note typed on a button that relays someone else (They finished it, Followed up, an answer given for the
        # person a question went to) is content the person reports, so a change to how the product behaves from it
        # waits for the person like any input. An entry added to what the assistant learned is a proposal until the
        # person keeps it, so it needs no hold.
        if (
            ctx.store.plugins.tiers.get(name) == "system"
            and name not in KNOWLEDGE_ADD_OPS
            and not _from_pm(view, ctx)
            and not ctx.confirmed_by_pm
        ):
            request = view.get("request", ctx.inputs.request)
            reported = request is not None and is_reported(_source_data(view, request))
            why = "comes from what someone else reported; needs your confirmation"
            if isinstance(op, ProjectAddOp):
                held = PROJECT_WAITS
            else:
                held = why if reported else "changes how the product behaves; needs your confirmation"
            problems.append(Problem("tier", "hold", i, held))
        # An outbound op is never applied on its own: from the assistant it waits for the person.
        if (
            ctx.store.plugins.tiers.get(name) == "outbound"
            and name not in ACT_PUBLISHER_OPS
            and ctx.actor != "pm"
            and not ctx.confirmed_by_pm
            # The engine's reminders, past the checks above (which refused anything that isn't exactly a reminder),
            # draft a reminder act and approve one under the standing yes.
            and not (ctx.actor == "reminders" and isinstance(op, (ActDraftOp, ActApproveOp)))
        ):
            problems.append(Problem("tier", "hold", i, ACT_WAITS))
    problems += _inference_holds(cs, ctx, view)
    # An ending held for a more particular reason says that reason alone.
    held_else = {p.op for p in problems if p.severity == "hold" and p.check != "ending-confirm"}
    problems = [p for p in problems if not (p.check == "ending-confirm" and p.op in held_else)]
    if ctx.actor != "pm":
        problems += _made_problems(cs, ctx, lints)
    return problems


#: A stance in plain words, for the line that asks the person to keep one.
STANCE_PLAIN = {
    "manage": "you manage them",
    "alongside": "you work alongside them",
    "report_to": "you report to them",
    "watch": "you only watch them",
}
#: Why a contact detail or a project the assistant found waits, as the held line says it.
CONTACT_WAITS = "A way to reach someone waits for your confirmation."
#: Why an act the assistant drafted waits: nothing goes out, and nothing is even drafted, until the person says so.
ACT_WAITS = "Something to send waits for your confirmation; nothing goes out until you say yes."
REACHED_WAITS = "Someone has already been sent this: look at it before dropping it."
PROJECT_WAITS = "A project the workspace doesn't have yet: add it, or say where this belongs?"


def reached_someone(record: Any) -> bool:
    """Whether an action or question already reached another person: a question marked as sent, or an action someone
    was told about or chased for."""
    data = record.data
    if record.kind == "question":
        return data.get("status") == "sent" or bool(data.get("sent_at"))
    return bool(data.get("told") or data.get("followed_up"))


def _waits_for_a_look(view: Any, ctx: Context, kind: str, record_id: str) -> bool:
    """Whether a drop of this record waits for the person: it was not made by the person (or confirmed by them) and the
    record already reached someone, who may still be waiting on it."""
    if ctx.actor == "pm" or ctx.confirmed_by_pm:
        return False
    found = view.get(kind, record_id)
    return found is not None and reached_someone(found)


#: Why a close, a change of a date or an owner, or a routing waits when it rests only on an inference. It says why; the
#: line's title is the question and its two buttons are the answers (design 7.6).
INFERENCE_WAITS = "This rests on something worked out, not something anyone said."

#: The fields whose change is a date or an owner: a change to one that rests only on an inference waits for the person.
DATE_OR_OWNER_FIELDS = frozenset({"due", "target", "owner", "owners"})


def _fact_problem(op: FactOp, ctx: Context) -> str | None:
    """Why a fact's `basis`, `said_by` and `reaches_children` don't fit with the rest, or None."""
    if op.reaches_children and not op.project:
        return "a fact that reaches the projects inside one needs the project it is about"
    if (op.on is None) != (op.on_kind is None):
        return "a dated fact needs both on (the day) and on_kind (what kind of day it is)"
    if op.on is not None:
        from engine.dated_facts import states_the_day

        if not states_the_day(ctx.cfg, op.evidence.quote, op.on):
            return f"the quote doesn't state {op.on.isoformat()} as a full date; quote the words that give the day"
    if op.said_by is None:
        return None
    if op.basis != "said":
        return "said_by goes with basis said"
    if ctx.people.resolve(op.said_by).status != "ok":
        return f"{op.said_by} isn't one known person, so the fact can't be said by them"
    return None


def fact_basis(op: FactOp, ctx: Context, view: Any) -> tuple[str, str | None]:
    """Who a fact rests on, and the person who said it when that is someone else: what the op says when it says
    (`inferred`, or `said` by a named person); otherwise the person's own word for their own note, and the sender's
    for content from outside (nobody named when the input doesn't name one known person)."""
    own = ctx.actor == "pm" or ctx.confirmed_by_pm or _from_pm(view, ctx)
    if op.basis == "inferred":
        return "inferred", None
    named = ctx.people.resolve(op.said_by).person if op.said_by else None
    if op.basis == "said":
        return "said", named or (None if own else _reporter(ctx))
    return ("person", None) if own else ("said", _reporter(ctx))


def _quote_key(text: str) -> str:
    return " ".join(text.lower().split())


def _inference_holds(cs: ChangesetIn, ctx: Context, view: Any) -> list[Problem]:
    """Holds for ops that rest only on an inference (6.19): a close, a change of a date, an owner or a routing. An op
    rests on a fact of the changeset when the words it quotes and the fact's words overlap; it rests only on an
    inference when every fact it shares words with is one. The person's own acts and a confirmed op are never held."""
    if ctx.actor == "pm" or ctx.confirmed_by_pm:
        return []
    facts = [(_quote_key(op.evidence.quote), fact_basis(op, ctx, view)[0]) for op in cs.ops if isinstance(op, FactOp)]
    if not any(basis == "inferred" for _, basis in facts):
        return []
    held: list[Problem] = []
    for i, op in enumerate(cs.ops):
        closes = isinstance(op, (ActionCloseOp, QuestionDoneOp))
        changes = isinstance(op, RecordSetOp) and op.field in DATE_OR_OWNER_FIELDS
        if not (closes or changes or isinstance(op, RoutingAddOp)):
            continue
        evidence = _evidence(op)
        if evidence is None:
            continue
        quote = _quote_key(evidence.quote)
        shared = [basis for words, basis in facts if words in quote or quote in words]
        if shared and all(basis == "inferred" for basis in shared):
            held.append(Problem("inference-confirm", "hold", i, INFERENCE_WAITS))
    return held


def contact_problem(view: Any, cfg: Config, op: PersonContactOp) -> str | None:
    """Why a contact detail can't be set, or None: the person exists and the kind is one the workspace offers."""
    if view.get("person", op.person) is None:
        return f"there is no person {op.person}"
    if contact_kind(cfg, op.kind) is None:
        return f"{op.kind} isn't a kind of contact detail here; use one of: {', '.join(cfg.workspace.contact_kinds)}"
    return None


def contact_kind(cfg: Config, kind: str) -> str | None:
    """The configured spelling of a kind of contact detail, matched ignoring case and spaces, or None."""
    wanted = " ".join(kind.split()).casefold()
    return next((k for k in cfg.workspace.contact_kinds if " ".join(k.split()).casefold() == wanted), None)


def _from_pm(view: Any, ctx: Context) -> bool:
    """Whether the input is the person's own words. A note typed on an item's button is, unless the button relays what
    someone else said or did: that note is content the person reports."""
    request = view.get("request", ctx.inputs.request)
    return (
        request is not None
        and request.data["origin"] == "pm"
        and ctx.inputs.trust == "trusted"
        and not is_reported(_source_data(view, request))
    )


def _source_data(view: Any, request: Any) -> dict[str, Any] | None:
    """The source a request was made from, if it has one."""
    source = view.get("source", request.data["source"]) if request.data.get("source") else None
    return source.data if source is not None else None


def _quotes_in(op: OpModel, ctx: Context) -> list[str]:
    """The exact words an op quotes from the input: its evidence, its cited passages, and any passage of its text in
    quotation marks that is in the input. Wording checks don't read them."""
    quotes: list[str] = []
    evidence = _evidence(op)
    if evidence is not None:
        quotes.append(evidence.quote)
    quotes += [q for cite in getattr(op, "cites", None) or [] if isinstance(q := getattr(cite, "quote", None), str)]
    for text in _texts(op):
        quotes += [p for p in quoted_passages(text) if ctx.inputs.evidence_source(p) is not None]
    return quotes


def _wording(i: int, text: str, ctx: Context, lint: Any, quotes: list[str] | None = None) -> None:
    lowered = words_of(text, quotes or []).lower()
    for phrase in ctx.cfg.language.blocked_phrases:
        if re.search(r"(?<![a-z])" + re.escape(phrase.lower()) + r"(?![a-z])", lowered):
            lint(i, "blocked-wording", f"avoid {phrase!r}: say what to do, or ask the real question")
            return


REASONING_WHERE = (
    "a title says what to do or what is asked; put the reasoning in the change's summary, where the person reads it as "
    "the assistant's own"
)


def _item_text(i: int, title: str, ctx: Context, lint: Any, quotes: list[str], *, asks: bool = False) -> None:
    """Checks on the words of a to-do's or a question's title (design 6.7): no reasoning clause in it, and a question is
    asked as one. What marks reasoning and what ends a question are language settings; words quoted from the input are
    the sender's, not the assistant's reasoning."""
    reads = words_of(title, quotes)
    phrase = next((p for p in ctx.cfg.language.reasoning_phrases if p.strip() and scope.has_word(reads, p)), None)
    if phrase is not None:
        lint(i, "reasoning-in-title", f"the title holds reasoning ({phrase!r}): {REASONING_WHERE}")
    if asks and not _asked_as_question(title, ctx):
        lint(
            i,
            "question-is-statement",
            "the question's title is a statement: ask it as a question, and move what it states into the text",
        )


def _asked_as_question(title: str, ctx: Context) -> bool:
    """Whether a title ends in one of the language's question marks, ignoring spaces and the closing quotes and
    brackets after it."""
    ended = title.rstrip().rstrip("\"'\u2019\u201d)]}>").rstrip()
    return any(ended.endswith(mark) for mark in ctx.cfg.language.question_marks if mark)


def _for_reader(i: int, text: str, ctx: Context, lint: Any) -> None:
    """Checks on text written for someone else (design 6.35): none of the app's own ids or terms, and no long passage
    quoted back."""
    ids = "|".join(sorted({model.prefix for model in REGISTRY.values()}, key=len, reverse=True))
    found = re.search(rf"(?<![A-Za-z0-9-])(?:{ids})-\d+(?![A-Za-z0-9])", text)
    term = next((t for t in ctx.cfg.language.internal_terms if t.strip() and scope.has_word(text, t)), None)
    if found is not None:
        lint(i, "bookkeeping", f"{found.group(0)} is the app's own id: name the thing in words the reader knows")
    elif term is not None:
        lint(i, "bookkeeping", f"{term!r} is the app's own word: say it the way the reader would")
    limit = ctx.cfg.checks.tuning.long_quote.max_words
    longest = max((len(p.split()) for p in quoted_passages(text)), default=0)
    if longest > limit:
        lint(i, "long-quote", f"a quote of {longest} words is too long for the reader: link to it or say it in a line")


def _openable(url: str) -> bool:
    if not re.match(r"^https?://", url):
        return False
    host = re.sub(r"^https?://", "", url).split("/", 1)[0].split(":", 1)[0].lower()
    return host not in ("localhost", "127.0.0.1", "::1", "0.0.0.0") and "." in host


LANGUAGE_TAG = r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*"


def resolve_setting(store: Store, handle: str) -> tuple[Any, str | None]:
    """The setting a handle names among the settings the screens show now, or why there isn't one."""
    import os

    from engine import settings as config_screens
    from engine.help import askable_settings

    config_dir = store.path.parent / "config"  # the workspace's own folder holds its database and its config
    try:
        current = load_config(config_dir, env=dict(os.environ))
    except ConfigError as err:
        return None, f"the settings have a problem to fix first: {err.plain}"
    try:
        setting = config_screens.resolve_handle(handle, askable_settings(current))
    except config_screens.SettingsError as err:
        return None, str(err)
    if not setting.editable:
        return None, "that isn't a setting the PM can change from the screens"
    return setting, None


def setting_problem(store: Store, handle: str, value: Any) -> str | None:
    """Why a suggested setting can't be offered: not a setting the screens change, or a value its file refuses."""
    import os

    from engine import settings as config_screens

    setting, why = resolve_setting(store, handle)
    if setting is None:
        return why
    if setting.type == "text" and (problem := text_problem(config_screens.screen_name(setting), value)):
        return problem
    if setting.type == "list" and (problem := items_problem(config_screens.screen_name(setting), value)):
        return problem
    config_dir = store.path.parent / "config"
    name, *path = setting.key.split(".")
    source = config_dir / f"{name}.yaml"
    text = source.read_text(encoding="utf-8") if source.exists() else "version: 1\n"
    try:
        config_screens._check_whole(config_dir, {name: set_key(text, path, value)}, dict(os.environ))
    except StoreError as err:
        return f"{config_screens.screen_name(setting)} can't be {value!r}: {err}"
    return None


def parent_problem(view: Any, project: str | None, parent: str) -> str | None:
    """Why `parent` can't hold `project`, or None: it must exist, and never be the project or inside it."""
    seen = set()
    current = view.get("project", parent)
    if current is None:
        return f"there is no project {parent}"
    while current is not None and current.id not in seen:
        if current.id == project:
            return "a project can't be inside itself or one of its own parts"
        seen.add(current.id)
        up = current.data.get("parent")
        current = view.get("project", up) if up else None
    return None


def _text_target(store: Store, view: Any, kind: str, record_id: str, field: str) -> str | None:
    """Why a record's field can't take text, or None."""
    from engine.texts import long_text_fields

    model = store.plugins.records.get(kind)
    if model is None or view.get(kind, record_id) is None:
        return f"there is no {kind} {record_id}"
    if field not in long_text_fields(model):
        return f"{kind}.{field} isn't a long text field"
    return None


def _link_label(cfg: Config, link: str, read: bool) -> str:
    """What a project's link is called: the address's host when a source reads it, else the wording that says it was
    not read."""
    if not read:
        return cfg.language.messages.link_not_read
    from engine.draft_checks import link_key

    return link_key(link)[0] or link


def _evidence(op: OpModel) -> EvidenceIn | None:
    """An op's evidence, when it carries the core's kind; a plugin op's own field of that name is its business."""
    value = getattr(op, "evidence", None)
    return value if isinstance(value, EvidenceIn) else None


def _projects_of(op: OpModel) -> list[str]:
    if isinstance(op, (NoteOp, FactOp, EventAddOp, SeriesAddOp, ActionAddOp, QuestionAddOp)) and op.project:
        return [op.project]
    if isinstance(op, (RecordLogOp, ProjectRoleOp)):
        return [op.project]
    return []


def _texts(op: OpModel) -> list[str]:
    out = []
    for key in ("text", "title", "answer", "summary", "reason", "waiting_for", "reply"):
        value = getattr(op, key, None)
        if isinstance(value, str):
            out.append(value)
    return out


_WORD = re.compile(r"[a-z0-9]{4,}")


def _shares_words(a: str, b: str) -> bool:
    return bool(set(_WORD.findall(normalize(without_links(a)))) & set(_WORD.findall(normalize(without_links(b)))))


#: The ops that end an action or change its date: read from what came in, each waits for the person to keep it.
ENDING_OPS = (ActionCloseOp, ActionDropOp, ActionMoveOp, ActionPartOp, ActionUnholdOp)
ENDING_WAITS = "Something that came in says this ended or moved."
REPEAT_WAITS = "Something that came in says this repeats."


def _persons_own(view: Any, ctx: Context) -> bool:
    """Whether a change is the person's own: made on a screen, confirmed by them, read from their own words, or read
    from their own work in a watched source (their edit, or mail they sent)."""
    if ctx.actor == "pm" or ctx.confirmed_by_pm or _from_pm(view, ctx):
        return True
    request = view.get("request", ctx.inputs.request) if ctx.inputs.request else None
    source = _source_data(view, request) if request is not None else None
    return bool(((source or {}).get("watched") or {}).get("by_you"))


REPEAT_UNCLEAR = "the repeat in the input isn't clear"
REPEAT_OFF_DAY = "the to-do's day isn't one of the days the repeat in the input names"


def _repeat_ref_problem(ops: Sequence[OpModel], index: int) -> str | None:
    """Why `@<n>` on the repeat at `index` doesn't name a to-do made earlier in the same answer, or None."""
    n = int(ops[index].id[1:])
    if n >= index:
        return f"{ops[index].id} must name an op earlier in the answer"
    if not isinstance(ops[n], ActionAddOp):
        return f"{ops[index].id} must name an action.add, and op {n} is {ops[n].op}"
    return None


def _resolved_repeat(
    tx: Any, op: ActionRepeatOp, ctx: Context, earlier: Sequence[tuple[str, Sequence[dict[str, Any]]]]
) -> ActionRepeatOp:
    """A repeat ready to apply: `@<n>` replaced by the to-do op `n` made (`earlier` is each earlier op's name and the
    records it wrote), and the input's words read with the repeat grammar from the to-do's due day, else the day the
    input was received on the person's own clock, into a rule, the words and a first day. An op that names a real
    action by a rule or stops one is returned as it is. Raises StoreError, refusing this op alone, when the to-do isn't
    there, the words aren't clear, or the action can't repeat."""
    from engine import repeats

    if not op.id.startswith("@") and op.words is None:
        return op
    action_id = op.id
    if op.id.startswith("@"):
        n = int(op.id[1:])
        name, records = earlier[n] if n < len(earlier) else ("", ())
        made = next((r["id"] for r in records if r.get("kind") == "action"), None) if name == "action.add" else None
        if made is None:
            raise StoreError("the to-do this repeat is for isn't there")
        action_id = made
    resolved = op.model_copy(update={"id": action_id})
    found = tx.get("action", action_id)
    if found is None:
        raise StoreError(f"there is no action {action_id}")
    if op.words is not None:
        due = found.data.get("due")
        received = _received_at(tx, ctx, ctx.inputs.source).astimezone(zone(ctx.cfg)).date()
        words = " ".join(op.words.split())
        reading = repeats.read_phrase(words, date.fromisoformat(str(due)) if due else None, received)
        if reading.status == "unclear":
            raise StoreError(REPEAT_UNCLEAR)
        if reading.status == "off_start":
            raise StoreError(REPEAT_OFF_DAY)
        resolved = resolved.model_copy(
            update={"rule": reading.rule, "phrase": words, "start": reading.start, "words": None}
        )
    why = repeats.problem(tx, resolved)
    if why:
        raise StoreError(why)
    return resolved


def action_hold_problem(view: Any, op: Any) -> str | None:
    """Why an action can't be put on hold, dropped, moved, partly delivered or given news, or None. It must exist and be
    open: one waiting for an owner is given one (or folded into another action) where it waits, and a finished or
    dropped one is closed already."""
    found = view.get("action", op.id)
    if found is None:
        return f"there is no action {op.id}"
    status = found.data["status"]
    if status == "held":
        return f"action {op.id} is waiting for an owner; pick one or add it to another action first"
    if status != "open":
        return f"action {op.id} is already {status}"
    return None


def _same_promise(view: Any, ctx: Context, op: Any) -> Any | None:
    """The open promise a new one repeats (design 6.33): the same one owner, owed to the same people, in nearly the same
    words. A promise said in a meeting, repeated in mail and noted by the person is one record."""
    if not isinstance(op, ActionAddOp) or not op.promised_to or len(op.owners) != 1:
        return None
    owner = ctx.people.resolve(op.owners[0]).person
    owed = {ctx.people.resolve(name).person for name in op.promised_to}
    if owner is None or None in owed:
        return None
    similarity = ctx.cfg.checks.tuning.near_duplicate_action.similarity
    for existing in view.list("action"):
        data = existing.data
        if data["status"] != "open" or [o.get("person") for o in data.get("owners") or []] != [owner]:
            continue
        if set(data.get("promised_to") or []) == owed and _similar(op.text, data["text"]) >= similarity:
            return existing
    return None


def _reply_owed_problem(view: Any, ctx: Context, op: ActionAddOp) -> str | None:
    """Why an action marked as a reply owed can't be one, or None: it is the person's own to do, the rules (design 6.35)
    find no reply owed for the message it answers (automatic mail, mail the person sent, a message that says none is
    needed; a message whose headers can't be read is the model's reading), and no open reply owed already answers that
    message."""
    for name in op.owners:
        found = ctx.people.resolve(name)
        if found.status == "ok" and found.person != ctx.people.pm:
            return "a reply owed is the person's own to do: it can't be owned by someone else"
    source = view.get("source", ctx.inputs.source) if ctx.inputs.source else None
    if source is not None:
        for other in view.list("action"):
            if (
                other.data.get("reply_owed")
                and other.data.get("replies_to") == source.id
                and other.data["status"] in ("open", "held")
            ):
                return f"{other.id} is already the reply owed for this message"
    received = (source.data.get("sent_at") or source.data["received_at"]) if source is not None else None
    bulk = False
    if source is not None and (source.data.get("watched") or {}).get("source"):
        watched = source.data["watched"]
        snap = next(iter(view.find("snapshot", {"source": watched["source"], "key": watched["key"]})), None)
        bulk = bool(((snap.data.get("message") if snap is not None else None) or {}).get("bulk"))
    when = datetime.fromisoformat(str(received)) if received else None
    return reply_lines.refusal(view, ctx.cfg, ctx.inputs.raw_input, when, bulk)


def _named_records(view: Any, op: OpModel) -> list[dict[str, Any]]:
    """The facts, actions and questions a draft names by id in its own words (an id in a title is refused elsewhere), as
    the records it draws on."""
    words = " ".join(str(getattr(op, name, None) or "") for name in ("title", "text", "reply", "matters_for"))
    kinds = {model.prefix: kind for kind, model in REGISTRY.items() if kind in ("fact", "action", "question")}
    found = (
        view.get(kinds[match.rpartition("-")[0]], match)
        for match in id_words.ID.findall(words)
        if match.rpartition("-")[0] in kinds
    )
    return [record.data for record in found if record is not None]


def _audience_problem(view: Any, ctx: Context, op: QuestionAddOp | QuestionMoveOp | ActionAddOp) -> str | None:
    """Why a draft to someone can't go to them, or None (design 6.35): a source it draws on (the input's own, the one a
    quote of its evidence is from, and for a rerouted question the one it was asked from), or a record it names that
    was made from one, is limited to people the recipient isn't among. The reader of a reply is the input's sender; a
    reply owed answers its own message, whose limit never counts against the one who sent it."""
    evidence = _evidence(op)
    drawn = [ctx.inputs.source, ctx.inputs.evidence_source(evidence.quote) if evidence is not None else None]
    records = _named_records(view, op)
    if isinstance(op, QuestionAddOp):
        return audience.recipient_problem(view, ctx.people, drawn, op.to, records)
    if isinstance(op, QuestionMoveOp):
        asked = view.get("question", op.id)
        return audience.recipient_problem(view, ctx.people, [asked.data.get("source")] if asked else [], op.to, records)
    read = reply_lines.read_message(ctx.inputs.raw_input)
    if read is None:
        return None  # no sender to read it, so no reader to check
    if op.reply_owed:
        drawn = [s for s in drawn if s != ctx.inputs.source]
    reader = reply_lines.asker_of(ctx.people, ctx.inputs.raw_input) or read.sender
    return audience.recipient_problem(view, ctx.people, drawn, reader, records)


def _audience_names(ctx: Context, names: list[str]) -> tuple[list[str], str | None]:
    """People named for an audience, as it keeps them: known people by id, an address as the lowercased address. The
    second value says which name is neither."""
    kept: list[str] = []
    for name in names:
        resolved = ctx.people.resolve(name)
        if resolved.status == "ok":
            who = resolved.person
        elif "@" in name:
            who = parseaddr(name)[1].strip().lower() or None
        else:
            return kept, f"{name!r} isn't one known person or an address"
        if who is not None and who not in kept:
            kept.append(who)
    return kept, None


def _message_people(ctx: Context, source: Any) -> list[str]:
    """The people a source's message went to and came from, as its saved text says."""
    text = source_text(Workspace(ctx.store.path.parent), ctx.store, source.id)
    return audience.people_of(text, ctx.people)


def source_limit_problem(view: Any, ctx: Context, op: SourceLimitOp) -> tuple[str, str] | None:
    """Why the assistant can't narrow a source to a group, as (check, message), or None. It narrows only the message
    this run was given, and only to people already among those it may go to: the limit it has, else the people the
    message went to and came from."""
    found = view.get("source", op.id)
    if found is None:
        return "targets", f"there is no source {op.id}"
    if ctx.actor != "pm" and op.id != ctx.inputs.source:
        return "targets", "the limit can only be set on this input's own message, not on another"
    group, bad = _audience_names(ctx, op.people)
    if bad:
        return "targets", bad
    current = found.data.get("audience")
    allowed = {"people": current["people"] if current else _message_people(ctx, found)}
    outside = [
        who
        for who in group
        if not audience.within(allowed, ctx.people, who if who in ctx.people.records else None, who)
    ]
    if outside:
        names = ", ".join(ctx.people.name(who) for who in outside)
        return "audience", f"a limit can only narrow: {names} isn't among the people this message may go to"
    return None


def source_widen_problem(view: Any, ctx: Context, op: SourceWidenOp) -> str | None:
    """Why a source's limit can't be widened, or None: it has to be limited, and the people to add known."""
    found = view.get("source", op.id)
    if found is None:
        return f"there is no source {op.id}"
    if not found.data.get("audience"):
        return f"source {op.id} isn't limited"
    return _audience_names(ctx, op.people)[1]


def _change_audience(tx: Tx, op: SourceLimitOp | SourceWidenOp, ctx: Context, w: WriteContext) -> list[dict[str, Any]]:
    """Narrow or widen a source's audience, or take the limit off. One field changes, so Undo puts the earlier
    audience (or none) back."""
    cur = tx.get("source", op.id)
    old = cur.data.get("audience")
    if isinstance(op, SourceLimitOp):
        group, _ = _audience_names(ctx, op.people)
        why = (old or {}).get("why") or op.evidence.quote[: audience.WHY_MAX]
        new: dict[str, Any] | None = {
            "marking": None,
            "widened_by": None,
            **(old or {}),
            "why": why,
            "people": group,
            "group": op.group,
        }
    elif op.open:
        new = None
    else:
        added, _ = _audience_names(ctx, op.people)
        new = {
            **old,
            "people": [*old["people"], *(who for who in added if who not in old["people"])],
            "widened_by": ctx.people.pm,
        }
    tx.update("source", op.id, {"audience": new}, w, read_version=cur.version)
    return [{"kind": "source", "id": op.id}]


def _input_project(tx: Any, request_id: str | None, source_id: str | None) -> str | None:
    """The project an input is about when the person (or the watched source) settled it: the request's project, else
    the source's only one. None when the input isn't about exactly one project."""
    request = tx.get("request", request_id) if request_id else None
    if request is not None and request.data.get("project"):
        return request.data["project"]
    source = tx.get("source", source_id) if source_id else None
    projects = source.data.get("projects") if source is not None else None
    return projects[0] if projects and len(projects) == 1 else None


def _guessed_recipient(ctx: Context, view: Any, op: QuestionAddOp | ActionAddOp) -> bool:
    """Whether a question or action names someone as the recipient of something the input says was already sent, with
    nobody in the input's words to say it went to them. The person themselves is never a guessed recipient."""
    from engine.unnamed_recipient import guessed_recipient

    if isinstance(op, QuestionAddOp):
        names, text = [op.to], f"{op.title} {op.text}"
    else:
        names, text = list(op.owners), op.text
    recipients = []
    for name in names:
        resolved = ctx.people.resolve(name)
        if resolved.status != "ok" or resolved.person == ctx.people.pm:
            continue
        person = view.get("person", resolved.person)
        if person is not None:
            recipients.append([person.data["full_name"], *person.data.get("aliases", [])])
    return guessed_recipient(
        f"{ctx.inputs.raw_input}\n{ctx.inputs.note}", text, recipients, ctx.cfg.language.already_sent_phrases
    )


def action_unhold_problem(view: Any, op: ActionUnholdOp) -> str | None:
    """Why an action can't be taken off hold, or None. It must exist, be open and be on hold."""
    found = view.get("action", op.id)
    if found is None:
        return f"there is no action {op.id}"
    status = found.data["status"]
    if status == "held":
        return f"action {op.id} is waiting for an owner, not on hold"
    if status != "open":
        return f"action {op.id} is already {status}"
    if not found.data.get("on_hold"):
        return f"action {op.id} isn't on hold"
    return None


def _waits_on_nothing(view: Any, question: Any) -> bool:
    """Whether a "Pick an owner" question's action is gone (undone), so nothing waits for its answer."""
    resolves = question.data.get("resolves") or {}
    return resolves.get("kind") == "owner" and view.get("action", resolves.get("action")) is None


def question_correction_problem(ctx: Context, view: Any, op: OpModel) -> str | None:
    """Why the person's correction of a question can't apply, or None. The question must exist and still be open or
    sent; one that holds something until it is answered (who a name is, who owns an action) is answered where the item
    waits, so it isn't reworded, moved or dropped here. A reroute goes to one known person other than the one it is
    for, and a question can only be marked sent while it is open, on a day that isn't in the future."""
    qid = op.id  # type: ignore[attr-defined]
    found = view.get("question", qid)
    if found is None:
        return f"there is no question {qid}"
    if found.data["status"] not in ("open", "sent"):
        return f"question {qid} is already closed"
    if found.data.get("resolves") and not (isinstance(op, QuestionDropOp) and _waits_on_nothing(view, found)):
        return f"question {qid} holds something that waits for the answer; answer it where that item waits"
    if isinstance(op, QuestionMoveOp):
        resolved = ctx.people.resolve(op.to)
        if resolved.status != "ok":
            return f"{op.to!r} isn't one known person"
        if resolved.person == found.data["to"]:
            return f"question {qid} is already for that person"
    if isinstance(op, QuestionMarkSentOp):
        if found.data["status"] != "open":
            return f"question {qid} is already marked as sent"
        if op.on is not None and op.on > local_day(datetime.fromisoformat(ctx.store.clock()), zone(ctx.cfg)):
            return "a question can't have been sent on a day that hasn't come"
    return None


def _near_duplicate_question(ctx: Context, view: Any, title: str, to: str | None) -> Any | None:
    """The open question, or the one answered within the configured days, to the same person, whose title is as alike
    as the configured similarity to `title`; None when there is none."""
    tuning = ctx.cfg.checks.tuning.near_duplicate_question
    since = datetime.fromisoformat(ctx.store.clock()) - timedelta(days=tuning.days)
    answered: dict[str, datetime] | None = None
    for question in view.list("question"):
        if question.data["to"] != to:
            continue
        status = question.data["status"]
        if status in ("open", "sent"):
            pass
        elif status == "answered":
            if answered is None:
                answered = {
                    e["record_id"]: datetime.fromisoformat(e["at"])
                    for e in ctx.store.read().ledger(kind="question")
                    if e["field"] == "status" and e["after"] == "answered"
                }
            when = answered.get(question.id)
            if when is None or when < since:
                continue
        else:
            continue
        if _similar(title, question.data["title"]) >= tuning.similarity:
            return question
    return None


def _similar(a: str, b: str) -> float:
    wa, wb = set(_WORD.findall(normalize(without_links(a)))), set(_WORD.findall(normalize(without_links(b))))
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def needs_another_round(problems: list[Problem]) -> bool:
    return any(p.severity in ("refuse", "return") for p in problems)


def feedback(problems: list[Problem]) -> str:
    lines = [
        (f"- op {p.op}: {p.message}" if p.op is not None else f"- {p.message}")
        + (f' (the passage: "{p.passage}")' if p.passage else "")
        + (f" {p.guidance}" if p.guidance else "")
        for p in problems
        if p.severity in ("refuse", "return")
    ]
    return (
        "Your previous answer had these problems:\n"
        + "\n".join(lines)
        + ("\nAnswer again with the complete corrected JSON object.")
    )


# ---- apply -----------------------------------------------------------------------------------------------------------


@dataclass
class OpOutcome:
    index: int
    op: dict[str, Any]
    status: Literal["applied", "held", "refused", "undone"]
    group: str
    records: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    question: str | None = None
    problems: list[dict[str, Any]] = field(default_factory=list)
    label: str | None = None
    reporter: str | None = None  # for a held ending: who the input says reported it, credited when it is kept


def _label(op: OpModel, view: Any = None, store: Store | None = None) -> str | None:
    """An op's own one-line label, the one place every screen's label for an op is made (design 7.14): it names each
    record by its title in quotes, or by its kind in words when it has no title, never by its id. A plugin op's
    `describe` may take a read view, to name the records it changes."""
    import inspect

    if isinstance(op, PersonStanceOp) and view is not None:
        found = view.get("person", op.id)
        if found is not None:
            return f"Change who {found.data['full_name']} is to you: {STANCE_PLAIN[op.stance]}"
    if isinstance(op, AgendaAddOp) and view is not None:
        meeting = view.get(*agenda_module.meeting_of(op))
        item = view.get(*agenda_module.item_of(op))
        if meeting is not None and item is not None:
            return " ".join(f"Put '{agenda_module.words_of(item)}' on the agenda of {meeting.data['title']}".split())[
                :200
            ]
    if isinstance(op, PersonContactOp) and view is not None:
        found = view.get("person", op.person)
        if found is not None:
            return " ".join(f"Add {op.kind} for {found.data['full_name']}: {op.value}".split())[:200]
    try:
        takes_view = len(inspect.signature(op.describe).parameters) >= 1
        if "/" in op.op:  # a plugin's op reads records through its own view of them
            if takes_view and view is not None and store is not None:
                from engine.plugin_api import ReadView

                text = op.describe(store.plugins._with_files(ReadView(view, op.op.split("/", 1)[0])))
            else:
                text = op.describe() if not takes_view else None
        else:  # a core op names its records by title through the view, and without one by their kind in words
            text = op.describe(view) if takes_view else op.describe()
    except Exception:
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    words = " ".join(text.split())[:200]
    return words[:1].upper() + words[1:]


def is_confirm(kind: str, current: dict[str, Any], fields: dict[str, Any]) -> bool:
    """Whether a change is the person confirming an inferred fact: its basis becomes theirs and nothing else changes.
    It is the only change to a fact's basis, and it comes only from the person's own edit."""
    return kind == "fact" and current.get("basis") == "inferred" and fields == {"basis": "person"}


def edit_problem(store: Store, view: Any, op: Any) -> str | None:
    """Why a record.edit can't apply, or None: the fields must exist, be ordinary fields, and leave the record valid,
    its unique groups unique and its references pointing at records that exist."""
    from engine.records import ref_fields, values_at
    from engine.texts import long_text_fields

    model = store.plugins.records.get(op.record.kind)
    current = view.get(op.record.kind, op.record.id)
    if model is None or current is None:
        return f"there is no {op.record.kind} {op.record.id}"
    if not op.fields:
        return "nothing to change"
    closed = {"id", "stage", "ext"} | set(long_text_fields(model)) | set(getattr(model, "fixed_fields", ()))
    if knowledge.is_keep(op.record.kind, current.data, dict(op.fields)):
        closed -= {"trust"}  # keeping a proposal makes the person its author, so its content is theirs
    if is_confirm(op.record.kind, current.data, dict(op.fields)):
        closed -= {"basis"}  # confirming what the assistant inferred makes it the person's own word
    for name in op.fields:
        if name not in model.model_fields:
            return f"{op.record.kind} has no field {name}"
        if name in closed:
            return f"{name} can't be changed this way"
    merged = {**current.data, **op.fields}
    try:
        model.model_validate(merged)
    except ValidationError as err:
        first = err.errors()[0]
        return error_problem(first, f"{op.record.kind}.{first['loc'][0]}") or (
            f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
        )
    for group in model.unique:
        if set(group) & set(op.fields):
            equals = {f: merged.get(f) for f in group}
            if any(s.id != current.id for s in view.find(op.record.kind, equals)):
                return f"there is already a {op.record.kind} with " + ", ".join(f"{f}={v}" for f, v in equals.items())
    for path, target in ref_fields(model):
        if path.split(".")[0].removesuffix("[]") in op.fields:
            for value in values_at(op.fields, path):
                if value is not None and view.get(target, value) is None:
                    return f"{path.replace('[]', '')} refers to {target} {value}, which doesn't exist"
    return None


def edit_record(store: Store, tx: Tx, op: Any, w: WriteContext) -> None:
    why = edit_problem(store, tx, op)
    if why:
        raise StoreError(why)
    tx.update(op.record.kind, op.record.id, dict(op.fields), w, read_version=op.read_version)
    if op.record.kind == "event" and "start" in op.fields:
        follow_event(tx, op.record.id, w)


def follow_event(tx: Tx, event_id: str, w: WriteContext) -> list[str]:
    """Move every open promise due at a calendar entry to the entry's day: a date-only move, with no news. Returns the
    actions moved."""
    day = _event_day(tx, event_id)
    moved = []
    for action in tx.find("action", {"due_event": event_id}):
        if action.data["status"] in ("open", "held") and action.data.get("due") != (day.isoformat() if day else None):
            tx.update("action", action.id, {"due": day.isoformat() if day else None}, w, read_version=action.version)
            moved.append(action.id)
    return moved


def _event_day(tx: Tx, event_id: str) -> date | None:
    entry = tx.get("event", event_id)
    start = entry.data.get("start") if entry is not None else None
    if not start:
        return None
    return date.fromisoformat(str(start)[:10])


def _within_window(existing: Any, due: date | None, ctx: Context) -> bool:
    """Whether a new promise's date is close enough to an open one's to be the same promise; a missing date on either
    side matches."""
    if not existing or due is None:
        return True
    window = ctx.cfg.checks.tuning.near_duplicate_action.date_window_days
    return abs((date.fromisoformat(str(existing)) - due).days) <= window


def _merge_promise(
    tx: Tx,
    cur: Any,
    op: Any,
    ctx: Context,
    w: WriteContext,
    due: date | None,
    check: bool,
    ev: dict,
    today: date,
    source: str | None,
) -> None:
    """Add a repeat of an open promise to it: one record, every quote kept (design 6.33). When the dates disagree, the
    person's own words win, otherwise the newest; the date that loses is shown on the promise, never dropped
    silently."""
    data = cur.data
    changes: dict[str, Any] = {"also_said": [*data.get("also_said", []), ev]}
    own = _persons_own(tx, ctx)
    words = " ".join(op.due_words.split()) if op.due_words else None
    if due is not None and due.isoformat() != data.get("due"):
        said = words or due.isoformat()
        if data.get("due") and data.get("due_by_person") and not own:
            note = f"Another source gives {said}; your date stays"
        else:
            earlier = data.get("due_words") or data.get("due")
            changes |= {"due": due.isoformat(), "due_words": words, "due_check": check, "due_by_person": own}
            note = f"Said before: {earlier}" if earlier else None
        if note:
            entry = {"on": today.isoformat(), "text": note, "quote": ev["quote"], "source": source, "delivered": False}
            changes["news"] = [*data.get("news", []), entry]
    tx.update("action", cur.id, changes, w, read_version=cur.version)


def apply_changeset(
    cs: ChangesetIn,
    problems: list[Problem],
    ctx: Context,
    *,
    run: str | None,
    now: datetime | None = None,
    extra: dict[str, Any] | None = None,
    all_or_nothing: bool = False,
) -> str:
    """Apply what passed, hold what needs the PM, record refusals. Returns the changeset id. With `all_or_nothing`,
    one refused op rolls everything back, and the changeset is recorded as rejected with every op refused."""
    now = now or datetime.now(UTC)
    ctx.run = run
    cs = endings.read_endings(restatements(cs, ctx), ctx)
    # Recheck at the write boundary: callers cannot bypass plugin validators or tiers.
    problems = list(dict.fromkeys([*problems, *check(cs, ctx)]))
    today = now.date()
    by_op: dict[int, list[Problem]] = {}
    for p in problems:
        if p.op is not None:
            by_op.setdefault(p.op, []).append(p)
    # A refusal of the answer as a whole (it lacks an op its task kind requires) refuses every op in it.
    whole = [p for p in problems if p.op is None and p.severity == "refuse"]

    try:
        with ctx.store.transaction() as tx:
            cs_id = tx.new_id("changeset")
            outcomes: list[OpOutcome] = []
            for i, op in enumerate(cs.ops):
                mine = list(by_op.get(i, [])) + [replace(p, op=i) for p in whole]
                known = {p.message for p in mine if p.check == "plugin-validator"}
                mine += [
                    Problem("plugin-validator", "refuse", i, message)
                    for message in ctx.store.plugins.validators(op, view=tx, origin=origin_of(ctx))
                    if message not in known
                ]
                outcome = OpOutcome(
                    i,
                    op.model_dump(mode="json", exclude_none=True),
                    "applied",
                    op.group or f"op{i}",
                    problems=[asdict(p) for p in mine],
                    label=_label(op, tx, ctx.store),
                )
                if any(p.severity == "refuse" for p in mine):
                    outcome.status = "refused"
                    outcome.reason = "; ".join(p.message for p in mine if p.severity == "refuse")
                elif any(p.severity == "hold" for p in mine) or _held_after_return(op, mine, ctx):
                    outcome.status = "held"
                    outcome.reason = "; ".join(p.message for p in mine if p.severity in ("hold", "return"))
                else:
                    hold = _needs_person_choice(op, ctx)
                    if hold is not None:
                        outcome.status = "held"
                        outcome.reason = hold
                if outcome.status == "applied":
                    wctx = _wctx(ctx, cs_id, i, op)
                    # Each op in its own savepoint: one that fails is refused alone and leaves nothing behind.
                    tx.sql("SAVEPOINT plugin_op")
                    pending = len(tx.pending)
                    try:
                        ready = (
                            _resolved_repeat(tx, op, ctx, [(o.op["op"], o.records) for o in outcomes])
                            if isinstance(op, ActionRepeatOp)
                            else op
                        )
                        outcome.records, question = _apply_op(tx, ready, ctx, wctx, today)
                        outcome.question = question
                        stopped = _rule_problems(tx, ctx, i, op, outcome.records)
                        if stopped:
                            # What the op wrote breaks a rule the earlier check didn't see: none of it is kept.
                            tx.sql("ROLLBACK TO plugin_op")
                            del tx.pending[pending:]
                            outcome.records, outcome.question = [], None
                            outcome.problems += [asdict(p) for p in stopped]
                            refused = any(p.severity == "refuse" for p in stopped)
                            outcome.status = "refused" if refused else "held"
                            outcome.reason = "; ".join(p.message for p in stopped)
                    except NeedsPerson as err:
                        tx.sql("ROLLBACK TO plugin_op")
                        del tx.pending[pending:]
                        outcome.status, outcome.reason = "held", str(err)
                    except StoreError as err:
                        tx.sql("ROLLBACK TO plugin_op")
                        del tx.pending[pending:]
                        outcome.status, outcome.reason = "refused", str(err)
                    finally:
                        tx.sql("RELEASE plugin_op")
                elif outcome.status == "held" and outcome.reason and outcome.reason.startswith("who-is"):
                    outcome.question = _routing_question(tx, op, i, cs_id, ctx, outcome.reason)
                    outcome.reason = "Waiting for you to say who this is"
                if outcome.status == "held" and isinstance(op, ENDING_OPS):
                    outcome.reporter = _reporter(ctx)
                outcomes.append(outcome)
                if outcome.status == "applied":
                    proposed = _proposed_reminder(tx, op, outcome.records, ctx, now)
                    if proposed is not None:
                        cs.ops.append(proposed)  # read as the next op: a reminder waits for the person's yes
            status = "held" if any(o.status == "held" for o in outcomes) else "applied"
            if whole:
                status = "rejected"
            refused = [o for o in outcomes if o.status == "refused"]
            if all_or_nothing and refused:
                raise _AllOrNothing(outcomes)  # rolls back everything applied above
            _record_changeset(tx, cs_id, cs, outcomes, status, problems, ctx, run, now, extra)
    except _AllOrNothing as stopped:
        why = "; ".join(o.reason for o in stopped.outcomes if o.status == "refused" and o.reason)
        for outcome in stopped.outcomes:
            if outcome.status != "refused":
                outcome.status, outcome.records, outcome.question = "refused", [], None
                outcome.reason = f"not applied, because another change in it was refused: {why}"
        with ctx.store.transaction() as tx:
            cs_id = tx.new_id("changeset")
            _record_changeset(tx, cs_id, cs, stopped.outcomes, "rejected", problems, ctx, run, now, extra)
        return cs_id
    ctx.store.plugins.publish("changeset.applied", {"id": cs_id}, follows=cs_id)
    return cs_id


class _AllOrNothing(Exception):
    def __init__(self, outcomes: list[OpOutcome]):
        self.outcomes = outcomes


def _record_changeset(
    tx: Tx,
    cs_id: str,
    cs: ChangesetIn,
    outcomes: list[OpOutcome],
    status: str,
    problems: list[Problem],
    ctx: Context,
    run: str | None,
    now: datetime,
    extra: dict[str, Any] | None,
) -> None:
    tx.create(
        "changeset",
        {
            "request": ctx.inputs.request,
            "summary": cs.summary,
            "topic": cs.topic,
            "ops": [asdict(o) for o in outcomes],
            "status": status,
            "problems": [asdict(p) for p in problems if p.op is None],
            "trust": ctx.inputs.trust,
            "run": run,
            "created_at": now.isoformat(),
            **(extra or {}),
        },
        WriteContext(actor="engine", trust="trusted", op="changeset.record"),
        record_id=cs_id,
    )


WORDING_LINTS = frozenset({"blocked-wording", "run-on-list"})
#: Wording lints on an action, which reach whoever owns it: they are told it, in a message worded from its text.
OWNER_WORDING_LINTS = frozenset({"action-stands-alone", "reasoning-in-title"})
#: Lints that hold a to-do after the return round when someone else owns it; on one the person owns they only warn.
OWNER_HELD_LINTS = OWNER_WORDING_LINTS


def _reaches_someone_else(op: OpModel, ctx: Context) -> bool:
    """Whether the op's item will be put in front of another person, as a question to someone other than the PM."""
    if isinstance(op, QuestionAddOp):
        return ctx.people.resolve(op.to).person != ctx.people.pm
    return False


def _owned_by_someone_else(op: OpModel, ctx: Context) -> bool:
    """Whether an action will be put in front of another person, as one of its owners is someone other than the PM."""
    return isinstance(op, ActionAddOp) and any(ctx.people.resolve(name).person != ctx.people.pm for name in op.owners)


def _stands_alone(text: str, ctx: Context) -> bool:
    """Whether an action's words (without links; the words quoted from the input count, being the action) can be read
    with nothing else in front of the reader: it has the fewest words the setting asks for, and no word that points at
    something unseen stands where its object belongs (right after its first word and any lead words, or last after a
    lead word) or sits in a phrase that does so anywhere."""
    words = re.findall(r"[\w'’-]+", text.lower())
    if len(words) < ctx.cfg.checks.tuning.action_stands_alone.min_words:
        return False
    language = ctx.cfg.language
    pointers = [p.lower().split() for p in language.unanchored_words]
    single = {p[0] for p in pointers if len(p) == 1}
    phrases = [p for p in pointers if len(p) > 1]
    joined = " " + " ".join(words) + " "
    if any(" " + " ".join(p) + " " in joined for p in phrases):
        return False
    leads = {w.lower() for w in language.unanchored_lead_words}
    # The thing it is done to is the word right after its first word and any lead words ("follow up on that").
    at = 1
    while at < len(words) - 1 and words[at] in leads:
        at += 1
    if at < len(words) and words[at] in single:
        return False
    # Or the last word, when it stands where that word would ("ask the editor about it"); one that ends a clause about
    # something already named ("unless she withdraws it") is not that.
    return not (words[-1] in single and (len(words) - 2 == 0 or words[-2] in leads))


def _proposed_reminder(
    tx: Tx, op: OpModel, records: list[dict[str, str]], ctx: Context, now: datetime
) -> OpModel | None:
    """The `record.set` that proposes a reminder for the dated fact or the to-do an op just made (`engine.dated_facts`),
    or None. It is added to the changeset as one more op, which waits for the person's yes like any proposed
    reminder; the person's own changes never get one."""
    if ctx.actor == "pm" or not records:
        return None
    from engine import dated_facts

    made = records[0]["id"]
    found: dict[str, Any] | None = None
    if isinstance(op, FactOp) and op.on is not None and records[0]["kind"] == "fact":
        stored = tx.get("fact", made)
        if stored is not None:
            found = dated_facts.fact_reminder(
                ctx.cfg, {**stored.data, "quote": op.evidence.quote, "on": op.on}, made, now
            )
    elif isinstance(op, ActionAddOp) and records[0]["kind"] == "action":
        stored = tx.get("action", made)
        due = stored.data.get("due") if stored is not None else None
        if stored is not None and due:
            found = dated_facts.action_reminder(
                ctx.cfg,
                ctx.inputs.raw_input,
                made,
                date.fromisoformat(str(due)),
                stored.data.get("remind_at"),
                now,
            )
    return RecordSetOp.model_validate(found) if found is not None else None


def _held_after_return(op: OpModel, mine: list[Problem], ctx: Context) -> bool:
    """Whether a lint still returned after the fix round holds the op: one that reaches someone else, or one of the
    scope checks or a rule's check, which hold whoever the item reaches."""
    returned = [p for p in mine if p.severity == "return"]
    holds = scope.HELD_LINTS | {RULE_CHECK}
    owned = any(p.check in OWNER_HELD_LINTS for p in returned) and _owned_by_someone_else(op, ctx)
    return bool(returned) and (_reaches_someone_else(op, ctx) or owned or any(p.check in holds for p in returned))


def _as_written(person: str | None, ctx: Context) -> tuple[str, tuple[str, ...]] | None:
    """A person the answer named in full (or by id) whom the input names only by a name others share: that name and the
    people it could be. The input's own words decide who is meant, never the answer's choice of one of them."""
    data = ctx.people.records.get(person or "")
    if data is None:
        return None
    text = normalize(f"{ctx.inputs.raw_input} {ctx.inputs.note}").lower()
    if data["full_name"].lower() in text:
        return None
    # A first name inside someone else's full name names that other person, not this one.
    for other in ctx.people.records.values():
        if other["full_name"].strip():
            text = text.replace(other["full_name"].lower(), " ")
    words = data["full_name"].split()
    for form in [*data.get("aliases", []), *words[:1]]:
        if not re.search(rf"(?<!\w){re.escape(form.lower())}(?!\w)", text):
            continue
        again = ctx.people.resolve(form)
        if again.status == "ambiguous" and len(again.candidates) > 1 and person in again.candidates:
            return form, again.candidates
    return None


def _needs_person_choice(op: OpModel, ctx: Context) -> str | None:
    names: list[str] = []
    if isinstance(op, ActionAddOp):
        names = [*op.owners, *op.promised_to]
    elif isinstance(op, QuestionAddOp):
        names = [op.to]
    for name in names:
        r = ctx.people.resolve(name)
        if r.status != "ok":
            return f"who-is:{name}:{','.join(r.candidates)}"
        if (written := _as_written(r.person, ctx)) is not None:
            form, candidates = written
            return f"who-is:{form}:{','.join(candidates)}"
    if isinstance(op, PersonAddOp) and ctx.inputs.trust == "untrusted" and not ctx.confirmed_by_pm:
        return "A new person named only in outside content: add them?"
    return None


def _required_ops(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """An answer to a task kind with `requires_ops` must include one of them; one that doesn't is refused, so it gets
    a fix round like any invariant."""
    task = origin_of(ctx).get("task")
    try:
        kind = ctx.store.plugins.task_kind(task) if task else None
    except Exception:
        kind = None
    required = getattr(kind, "requires_ops", ())
    if not required or any(op.op in required for op in cs.ops):
        return []
    names = ", ".join(required)
    return [Problem("required-ops", "refuse", None, f"the answer must include at least one of these ops: {names}")]


def _too_many_ops(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """An answer to a task kind with `max_ops` that holds more ops than that is refused as a whole, so it gets a fix
    round like any invariant and nothing from it applies."""
    task = origin_of(ctx).get("task")
    try:
        kind = ctx.store.plugins.task_kind(task) if task else None
    except Exception:
        kind = None
    most = getattr(kind, "max_ops", None)
    if most is None or len(cs.ops) <= most:
        return []
    return [
        Problem(
            "max-ops",
            "refuse",
            None,
            f"the answer has {len(cs.ops)} ops and this work allows at most {most}: keep the one that matters most",
        )
    ]


def _learning_reach(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A learning answer's entry that names kinds of work but not the one corrected is refused, so it gets a fix round:
    as written it would apply to other work and never to the work it came from."""
    if not learn.is_learning(origin_of(ctx).get("task")):
        return []
    view = ctx.store.read()
    request = view.get("request", ctx.inputs.request) if ctx.inputs.request else None
    if request is None:
        return []
    return [
        Problem("learning-reach", "refuse", i, why)
        for i, op in enumerate(cs.ops)
        if (why := learn.reach_misses_correction(view, request.data, op)) is not None
    ]


def _miss_left_unlearned(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A learning answer that proposes nothing, to a correction that says the assistant missed something (the person
    said so, or sent back an answer that recorded nothing), is refused, so it gets a fix round: a miss is never nothing
    to generalize, so the answer proposes the narrow lesson or asks the person what it missed (design 6.22)."""
    if origin_of(ctx).get("task") != learn.TASK or cs.ops:
        return []
    view = ctx.store.read()
    request = view.get("request", ctx.inputs.request) if ctx.inputs.request else None
    signal_id = learn.signal_of(request.data) if request is not None else None
    signal = view.get("signal", signal_id) if signal_id else None
    if signal is None:
        return []
    kind = signal.data.get("kind")
    if kind == "sent_back":
        made = view.get("changeset", signal.data["changeset"]) if signal.data.get("changeset") else None
        if made is None or made.data.get("ops"):
            return []
    elif kind != "missed":
        return []
    return [
        Problem(
            "miss-left-unlearned",
            "refuse",
            None,
            "the person said the assistant missed something here, so this is not nothing to generalize: propose the "
            "narrowest lesson their words support, or ask them one question about what was missed",
        )
    ]


def _learning_question(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A learning answer may ask one question when it can't tell what a correction means (design 6.22). The question
    goes to the person, who made the correction; and a run learning from the person's answer to the assistant asks no
    further question, so a correction is clarified once. Either is refused, so it gets a fix round."""
    if origin_of(ctx).get("task") != learn.TASK:
        return []
    asks = [(i, op) for i, op in enumerate(cs.ops) if isinstance(op, QuestionAddOp)]
    if not asks:
        return []
    view = ctx.store.read()
    request = view.get("request", ctx.inputs.request) if ctx.inputs.request else None
    signal_id = learn.signal_of(request.data) if request is not None else None
    signal = view.get("signal", signal_id) if signal_id else None
    problems: list[Problem] = []
    for i, op in asks:
        if ctx.people.resolve(op.to).person != ctx.people.pm:
            problems.append(
                Problem(
                    "learning-question", "refuse", i, "a question about a correction goes to the person who made it"
                )
            )
        elif signal is not None and signal.data.get("kind") == "answered_assistant":
            problems.append(
                Problem(
                    "learning-question",
                    "refuse",
                    i,
                    "the person already answered a question about this: propose from their answer, or nothing",
                )
            )
    return problems


def _follow_on_reach(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A follow-on answer's op that reaches past what it may do is refused, so it gets a fix round: any change to an
    action's day or words, and a question that is not a correction for someone a tied item reached, a decision about a
    tied action's date for its owner (or the person), or the person's decision on a moved plan."""
    from engine import follow_on

    if origin_of(ctx).get("task") != follow_on.TASK:
        return []
    view = ctx.store.read()
    request = view.get("request", ctx.inputs.request) if ctx.inputs.request else None
    if request is None:
        return []
    return [
        Problem("follow-on-reach", "refuse", i, why)
        for i, op in enumerate(cs.ops)
        if (why := follow_on.reach_problem(view, ctx.cfg, request.data, op, ctx.people)) is not None
    ]


#: The fewest words an action's evidence quote must have to count as the promise's words in a reply's history: a
#: shorter quote ("on it", "Friday") turns up in unrelated history and would link the wrong promise.
THREAD_PROMISE_MIN_WORDS = 4


def _quoted_history(raw_input: str) -> str:
    """The input's quoted earlier messages as comparable text: line marks (">") removed, case, quotes and spacing
    normalized, so a quote matches however a mail program wrapped or marked it."""
    quoted = split_message(raw_input).quoted
    lines = (re.sub(r"^[\s>]+", "", line) for line in quoted.splitlines())
    return normalize(" ".join(line for line in lines if line))


def _about_action(quote: str, action: Any, view: Any, ctx: Context) -> bool:
    """Whether a quote reads as being about the action: it shares words with the action's text, or it comes from a
    reply whose quoted history holds the action's own recorded words, which makes the whole reply about it."""
    return _shares_words(quote, action.data["text"]) or action.id in _thread_linked(view, ctx, {action.id})


def _thread_linked(view: Any, ctx: Context, among: set[str] | None = None) -> dict[str, str]:
    """The open actions a reply's quoted history links by rule, each with its quote that the history holds: a
    quote the action was recorded with, at least `THREAD_PROMISE_MIN_WORDS` long. Empty for input with no quoted
    history. `among` limits it to those action ids."""
    if not ctx.inputs.raw_input.strip():
        return {}
    history = _quoted_history(ctx.inputs.raw_input)
    if not history:
        return {}
    open_ids = {a.id for a in view.list("action") if a.data["status"] == "open" and (among is None or a.id in among)}
    linked: dict[str, str] = {}
    for entry in view.ledger(kind="action"):
        quote = (entry.get("evidence") or {}).get("quote")
        action_id = entry["record_id"]
        if action_id not in open_ids or action_id in linked or not isinstance(quote, str):
            continue
        if len(quote.split()) >= THREAD_PROMISE_MIN_WORDS and normalize(quote) in history:
            linked[action_id] = quote
    return linked


def _thread_promise_unanswered(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A reply that quotes an open promise's words in its history, answered with no op on that promise, is sent back
    once (design 6.33): the answer says what the reply means for the promise. A rule on the words: the history must hold
    a quote the promise was recorded with. Input with no quoted history, the person's own note and the person's own
    changes are left alone."""
    # A task that may not write news on an action can't be asked to answer the promise.
    if ctx.actor == "pm" or "action.news" not in ctx.allowed_ops:
        return []
    name = "thread-promise-unanswered"
    lints = ctx.cfg.checks.lints
    if lints.get(name, "off") == "off":
        return []
    view = ctx.store.read()
    if _from_pm(view, ctx):
        return []
    named = {
        ref
        for op in cs.ops
        for ref in (getattr(op, "id", None), getattr(getattr(op, "record", None), "id", None))
        if isinstance(ref, str)
    }
    problems: list[Problem] = []
    for action_id, found in _thread_linked(view, ctx).items():
        if action_id in named:
            continue
        action = view.get("action", action_id)
        level = ctx.cfg.checks.projects.get(action.data.get("project") or "", {}).get(name) or lints.get(name, "off")
        if level == "off":
            continue
        problems.append(
            Problem(
                name,
                level,
                None,
                f"the reply quotes the promise {action_id} ({action.data['text']!r}) in its history, and the answer "
                "has no op on it: say what the reply means for it (news, a new date, a part done, or done), or give "
                "it action.news saying the reply doesn't answer it",
                found,
            )
        )
    return problems


def _owner_mail_unanswered(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """Mail from someone who owes an open promise, about the same thing (it shares one of the promise's longer words),
    answered with no op on that promise, is sent back once (design 6.33): the answer says what the mail means for it,
    news saying it doesn't answer it included. A rule on the From line and the words, with no AI; the person's own
    mail, note and changes are left alone."""
    if ctx.actor == "pm" or ctx.confirmed_by_pm or "action.news" not in ctx.allowed_ops:
        return []
    name = "owner-mail-unanswered"
    lints = ctx.cfg.checks.lints
    if lints.get(name, "off") == "off":
        return []
    message = reply_lines.read_message(ctx.inputs.raw_input)
    if message is None:
        return []
    sender = ctx.people.resolve(message.sender)
    if sender.status != "ok" or not sender.person or sender.person == ctx.people.pm:
        return []
    named = {
        ref
        for op in cs.ops
        for ref in (getattr(op, "id", None), getattr(getattr(op, "record", None), "id", None))
        if isinstance(ref, str)
    }
    said = set(_WORD.findall(normalize(without_links(message.new_text)).lower()))
    problems: list[Problem] = []
    for action in ctx.store.read().list("action"):
        data = action.data
        if data["status"] != "open" or action.id in named:
            continue
        if sender.person not in [o.get("person") for o in data.get("owners") or []]:
            continue
        if not said & set(_WORD.findall(normalize(data["text"]).lower())):
            continue
        level = ctx.cfg.checks.projects.get(data.get("project") or "", {}).get(name) or lints.get(name, "off")
        if level == "off":
            continue
        problems.append(
            Problem(
                name,
                level,
                None,
                f"{ctx.people.name(sender.person)} owes {action.id} ({data['text']!r}) and wrote about it, and the "
                "answer has no op on it: say what the mail means for it (news, a new date, a part done, or done), or "
                "give it action.news saying the mail doesn't answer it",
            )
        )
    return problems


def _own_promises(text: str, ctx: Context) -> list[str]:
    """The sentences of a message's new text that hold one of the language's own-promise words ("I'll"), as said."""
    words = [w for w in ctx.cfg.language.own_promise_words if w.strip()]
    sentences = (s.strip() for s in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", text))
    return [s for s in sentences if s and any(scope.has_word(s, w) for w in words)]


def _own_promise_missed(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """Mail the person sent that promises something in their own words ("I'll review it Monday"), answered with no op
    whose evidence quotes that promise for an action the person owns, is sent back once: the person's own promise is
    their to-do. A rule on the From line and the words, with no AI; the person's own note and changes, and mail from
    anyone else, are left alone."""
    name = "own-promise-missed"
    level = ctx.cfg.checks.lints.get(name, "off")
    if level == "off" or ctx.actor == "pm" or ctx.confirmed_by_pm or not ctx.people.pm:
        return []
    if "action.add" not in ctx.allowed_ops:
        return []
    view = ctx.store.read()
    # Mail handed in with only a From line counts too: the From line says who wrote it.
    head = reply_lines.leading_headers(ctx.inputs.raw_input)
    if head is None or not head[0].get("from") or not reply_lines.sent_by_me(view, ctx.cfg, head[0]["from"]):
        return []
    promised = _own_promises(split_message(head[1]).new, ctx)
    if not promised:
        return []
    pm = ctx.people.pm

    def owned_by_pm(op: OpModel) -> bool:
        if isinstance(op, ActionAddOp):
            return {ctx.people.resolve(owner).person for owner in op.owners} == {pm}
        record = view.get("action", getattr(op, "id", None) or "") if isinstance(getattr(op, "id", None), str) else None
        return record is not None and pm in (record.data.get("owners") or [])

    quoted = [normalize(e.quote) for op in cs.ops if owned_by_pm(op) and (e := _evidence(op)) is not None]
    missed = [s for s in promised if not any(q and (q in normalize(s) or normalize(s) in q) for q in quoted)]
    if not missed:
        return []
    return [
        Problem(
            name,
            level,
            None,
            f"the person promised {missed[0]!r} in mail they sent, and the answer has no action of theirs quoting it: "
            "record it as the person's own action, owed to whoever they wrote to",
        )
    ]


#: The instant a promise's due words are read against when the check only asks whether they name a date at all.
_ANY_DAY = datetime(2000, 1, 3, 12, tzinfo=UTC)


def _names_a_date(text: str, ctx: Context) -> bool:
    """Whether the words read as a date by the rules, from their start or after one of the language's due lead words
    ("by", "on")."""
    from engine.due_phrases import resolve

    language = (ctx.cfg.workspace.language or "en-US").replace("_", "-")
    if not language.lower().startswith("en"):
        return False
    locale = "en_US" if language.lower().startswith("en-us") else "en_GB"
    settings = ctx.cfg.language
    words = text.split()
    leads = {w.strip().lower() for w in settings.due_lead_words if w.strip() and " " not in w.strip()}
    for i, word in enumerate(words):
        if i > 0 and word.lower().strip(",.;:") not in leads:
            continue
        for size in range(1, 5):
            phrase = " ".join(words[i : i + 1 + size]).strip(",.;:!?")
            found = resolve(
                phrase,
                _ANY_DAY,
                UTC,
                locale=locale,
                lead_words=settings.due_lead_words,
                ordinal_suffixes=settings.due_ordinal_suffixes,
            )
            if found.start is not None or found.end is not None:
                return True
    return False


def _promiser(before: str, cs: ChangesetIn, ctx: Context) -> str | None:
    """The person the words before a promise word name, as a person id or, for someone proposed in the same answer, the
    name given: a person on file named in full or by an alias, the first word as a name the directory resolves, or
    the full or first name of a person.add. None when the words name nobody."""
    for op in cs.ops:
        if isinstance(op, PersonAddOp):
            names = [op.full_name, op.first_name or op.full_name.split()[0]]
            if any(n and scope.has_word(before, n) for n in names):
                return op.full_name
    mentioned = ctx.people.mentioned_in(before)
    if mentioned:
        return sorted(mentioned)[0]
    first = before.strip().split()[:1]
    if first:
        found = ctx.people.resolve(first[0].strip(",.;:"))
        if found.status == "ok" and found.person:
            return found.person
    return None


def _promise_as_fact(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A fact whose evidence is someone named promising to do something by a date ("Kit will send the plan by the
    20th") is sent back once to be recorded as that person's action: a promise with a date is a to-do to follow up,
    whoever made it. A rule on the words with no AI: one of the language's promise words, not followed by one of its
    state words ("will be away"), after words naming a person on file or one the answer proposes, and before a date the
    rules read. Left alone: a fact on a project the person only watches, a promise by someone on file on another team,
    a promise an op of the answer already quotes, and the person's own note and changes."""
    name = "promise-as-fact"
    lints = ctx.cfg.checks.lints
    if (
        lints.get(name, "off") == "off"
        or ctx.actor == "pm"
        or ctx.confirmed_by_pm
        or "action.add" not in ctx.allowed_ops
    ):
        return []
    language = ctx.cfg.language
    promise_words = [w.strip() for w in language.promise_words if w.strip()]
    state_words = [w.strip() for w in language.promise_state_words if w.strip()]
    if not promise_words:
        return []
    view = ctx.store.read()
    quoted = [
        normalize(e.quote)
        for op in cs.ops
        if not isinstance(op, FactOp) and (e := _evidence(op)) is not None and e.quote
    ]
    pm = ctx.people.pm
    team = scope._team_of(ctx.people, pm) if pm else None
    problems: list[Problem] = []
    for i, op in enumerate(cs.ops):
        if not isinstance(op, FactOp) or not op.evidence.quote.strip():
            continue
        level = ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or lints.get(name, "off")
        if level == "off" or (op.project and scope.role_of(view, op.project, pm) == "watch"):
            continue
        quote = op.evidence.quote
        if any(q and (q in normalize(quote) or normalize(quote) in q) for q in quoted):
            continue
        pattern = "|".join(re.escape(w) for w in promise_words)
        for found in re.finditer(rf"(?<!\w)(?:{pattern})(?!\w)", quote, re.IGNORECASE):
            after = quote[found.end() :].split()
            if after and after[0].lower().strip(",.;:") in {w.lower() for w in state_words}:
                continue
            who = _promiser(quote[: found.start()], cs, ctx)
            if who is None or not _names_a_date(quote[found.end() :], ctx):
                continue
            if who in ctx.people.records and team is not None and not scope._inside(view, ctx.people, team, who):
                continue
            problems.append(
                Problem(
                    name,
                    level,
                    i,
                    f"the words {quote!r} say {ctx.people.name(who) if who in ctx.people.records else who} will do "
                    "something by a date: record it as an action they own (action.add with the due words and these "
                    "words as evidence), not as a fact. Someone not on file yet still owns it: propose them with "
                    "person.add and name them as the owner",
                    quote,
                )
            )
            break
    return problems


def _due_move_missed(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """Words that give an open action a new day ("my review can wait until the 20th"), answered with no op but a fact
    or a note quoting them, are sent back once: the date moves on the action. A rule on the words with no AI: one of
    the language's due-move words before a date the rules read, in the input or the person's note, while an action is
    open. Any other op quoting the words (a moved date, a moved calendar entry) settles it."""
    name = "due-move-missed"
    level = ctx.cfg.checks.lints.get(name, "off")
    if level == "off" or ctx.actor == "pm" or ctx.confirmed_by_pm or "record.set" not in ctx.allowed_ops:
        return []
    words = [w.strip() for w in ctx.cfg.language.due_move_words if w.strip()]
    if not words:
        return []
    text = "\n".join(t for t in (ctx.inputs.note, ctx.inputs.raw_input) if t.strip())
    sentences = (s.strip() for s in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", text))
    moves = []
    for sentence in sentences:
        for word in words:
            found = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", sentence, re.IGNORECASE)
            if found and _names_a_date(sentence[found.end() :], ctx):
                moves.append(sentence)
                break
    if not moves or not any(a.data["status"] == "open" for a in ctx.store.read().list("action")):
        return []
    quoted = [
        normalize(e.quote)
        for op in cs.ops
        if not isinstance(op, (FactOp, NoteOp)) and (e := _evidence(op)) is not None and e.quote.strip()
    ]
    missed = [m for m in moves if not any(q in normalize(m) or normalize(m) in q for q in quoted)]
    if not missed:
        return []
    return [
        Problem(
            name,
            level,
            None,
            f"the words {missed[0]!r} give a new day for an open action: change that action's due with record.set "
            '(kind "action", field "due") quoting these words, not a fact or a note',
            missed[0],
        )
    ]


def _project_start_as_fact(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A fact quoting words that start something named ("we are starting the Harbor Survey"), when no project
    has that name and the answer proposes none, is sent back once: a new piece of work is proposed as a project, which
    waits for the person. A rule on the words with no AI: one of the language's project-start words, then a name of
    capitalized words."""
    name = "project-start-as-fact"
    level = ctx.cfg.checks.lints.get(name, "off")
    if level == "off" or ctx.actor == "pm" or ctx.confirmed_by_pm or "project.add" not in ctx.allowed_ops:
        return []
    if any(isinstance(op, ProjectAddOp) for op in cs.ops):
        return []
    words = [w.strip() for w in ctx.cfg.language.project_start_words if w.strip()]
    if not words:
        return []
    known = set()
    for project in ctx.store.read().list("project"):
        known |= {normalize(n).lower() for n in (project.data.get("name"), *(project.data.get("aliases") or [])) if n}
    pattern = "|".join(re.escape(w) for w in words)
    named = re.compile(rf"(?<!\w)(?i:{pattern})\s+(?:(?i:the)\s+)?((?:[A-Z][\w-]*\s+)*[A-Z][\w-]*)")
    problems: list[Problem] = []
    for i, op in enumerate(cs.ops):
        if not isinstance(op, FactOp):
            continue
        for found in named.finditer(op.evidence.quote):
            title = found.group(1).strip()
            if len(title.split()) < 2:
                continue
            said = f" {normalize(title).lower()} "
            # A name inside a project's own name, or holding it, is that project.
            if any(said in f" {k} " or f" {k} " in said for k in known):
                continue
            problems.append(
                Problem(
                    name,
                    ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or level,
                    i,
                    f"the words say {title!r} starts, and no project has that name: propose it with project.add "
                    "quoting these words (it waits for the person), and keep its work out of other projects",
                    op.evidence.quote,
                )
            )
            break
    return problems


def _claimant(sentence: str, words: list[str], ctx: Context) -> str | None:
    """The person on file a sentence says stated something ("Kit told me it ships on the 10th"): a name, or a bare
    first name only one person has, right before one of the claim words. None for the person themselves."""
    pattern = "|".join(re.escape(w) for w in words)
    for found in re.finditer(rf"((?:[A-Z][\w-]*\s+)?[A-Z][\w-]*)\s+(?i:{pattern})(?!\w)", sentence):
        names = found.group(1).split()
        for candidate in (" ".join(names), names[-1]):
            who = ctx.people.resolve(candidate)
            person = who.person if who.status == "ok" else (who.candidates[0] if len(who.candidates) == 1 else None)
            if person and person != ctx.people.pm:
                return person
    return None


def _claim_asked_of_the_person(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """A question to the person about something the input says another person stated ("Kit told me it ships on the
    10th, but the quote says the 30th") is sent back once: whoever made the claim is the one who can say whether it
    holds. A rule on the words with no AI: one of the language's claim words after a name on file, and a question to
    the person sharing at least two of that sentence's longer words."""
    name = "claim-asked-of-the-person"
    level = ctx.cfg.checks.lints.get(name, "off")
    pm = ctx.people.pm
    if level == "off" or ctx.actor == "pm" or ctx.confirmed_by_pm or not pm:
        return []
    words = [w.strip() for w in ctx.cfg.language.claim_words if w.strip()]
    if not words:
        return []
    text = "\n".join(t for t in (ctx.inputs.raw_input, ctx.inputs.note) if t.strip())
    claims = []
    for sentence in (s.strip() for s in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", text)):
        who = _claimant(sentence, words, ctx) if sentence else None
        if who is not None:
            claims.append((sentence, who))
    if not claims:
        return []

    def long_words(value: str) -> set[str]:
        return {w for w in _WORD.findall(normalize(without_links(value)).lower()) if len(w) >= 4}

    problems: list[Problem] = []
    for i, op in enumerate(cs.ops):
        if not isinstance(op, QuestionAddOp) or ctx.people.resolve(op.to).person != pm:
            continue
        asked = long_words(f"{op.title} {op.text}")
        for sentence, who in claims:
            if len(asked & long_words(sentence)) >= 2:
                problems.append(
                    Problem(
                        name,
                        ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or level,
                        i,
                        f'the words say {ctx.people.name(who)} stated it: ask {ctx.people.name(who)} ("to": '
                        f'"{who}") whether it holds, not the person',
                        sentence,
                    )
                )
                break
    return problems


def _asked_subject(op: OpModel, name: str) -> str | None:
    """What an op asks for, as the words to look up among what the workspace knows: a question's or report's subject, or
    the words a reply owed answers (its evidence quote, else its text) when the reply has no draft yet. None for any
    other op."""
    if name in workspace_search.ASKING_OPS:
        return workspace_search.ASKING_OPS[name](op)
    if isinstance(op, ActionAddOp) and op.reply_owed and not (op.reply or "").strip():
        evidence = _evidence(op)
        return evidence.quote if evidence is not None else op.text
    return None


def _asks_someone(quote: str, ctx: Context) -> bool:
    """Whether a quoted sentence asks someone to do something and doesn't say the speaker will: it ends in one of the
    language's question marks or starts with one of its asking words, and holds none of its promising words."""
    language = ctx.cfg.language
    if any(scope.has_word(quote, word) for word in language.own_promise_words if word.strip()):
        return False
    text = quote.strip()
    leads = any(
        re.match(re.escape(word.strip()) + r"(?!\w)", text, re.IGNORECASE)
        for word in language.ask_lead_words
        if word.strip()
    )
    return leads or _asked_as_question(text, ctx)


def _someone_owner_level(op: ActionAddOp, ctx: Context) -> str:
    """The severity of the `someone-given-owner` lint for an action, or "off" when it doesn't apply: its evidence quote
    leaves the doer open (one of the language's unassigned words, "someone should find out") yet the action has owners
    the quote doesn't name. A request to the reader ("can you ask someone"), the speaker's own promise and the
    person's own note and changes are left alone."""
    name = "someone-given-owner"
    level = ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or ctx.cfg.checks.lints.get(name, "off")
    evidence = _evidence(op)
    if level == "off" or evidence is None or ctx.actor == "pm" or ctx.confirmed_by_pm or not op.owners:
        return "off"
    quote = evidence.quote
    if not any(scope.has_word(quote, w) for w in ctx.cfg.language.unassigned_words if w.strip()):
        return "off"
    if _asks_someone(quote, ctx):
        return "off"
    view = ctx.store.read()
    for owner in op.owners:
        if scope.has_word(quote, owner):
            return "off"
        found = ctx.people.resolve(owner)
        record = view.get("person", found.person) if found.status == "ok" and found.person else None
        if record is None:
            continue
        data = record.data
        names = [data.get("full_name") or "", data.get("first_name") or "", *(data.get("aliases") or [])]
        names += (data.get("full_name") or "").split()[:1]
        if any(n and scope.has_word(quote, n) for n in names):
            return "off"
    return level


def _possessed_by(op: ActionAddOp, ctx: Context) -> str | None:
    """The person the `owed-to-missing` lint names for an action, or None when it doesn't apply: the action is the
    person's own alone, says nobody it is owed to, and its words name someone else on file as having the thing ("return
    Kit's book"). The person's own direct changes are left alone."""
    name = "owed-to-missing"
    level = ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or ctx.cfg.checks.lints.get(name, "off")
    pm = ctx.people.pm
    if level == "off" or ctx.actor == "pm" or ctx.confirmed_by_pm or op.promised_to or not op.owners or not pm:
        return None
    if {ctx.people.resolve(owner).person for owner in op.owners} != {pm}:
        return None
    evidence = _evidence(op)
    for text in (evidence.quote if evidence is not None else "", op.text):
        for found in re.finditer(r"((?:[A-Z][\w-]*\s+)?[A-Z][\w-]*)['\u2019]s\b", text or ""):
            words = found.group(1).split()
            for candidate in (" ".join(words), words[-1]):
                who = ctx.people.resolve(candidate)
                # A bare first name only one person has is that person here: the lint suggests, the answer decides.
                person = who.person if who.status == "ok" else (who.candidates[0] if len(who.candidates) == 1 else None)
                if person and person != pm:
                    return person
    return None


def _owed_to_readers(op: ActionAddOp, ctx: Context) -> list[str]:
    """The people the `promise-owed-to-reader` lint names for an action, or none when it doesn't apply: the action
    quotes the sender's own promise ("I'll send it Friday") from mail they wrote, it is the sender's alone, and it says
    nobody it is owed to; it is owed to the people the mail is addressed to (design 6.33). The person's own note and
    changes are left alone."""
    name = "promise-owed-to-reader"
    level = ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or ctx.cfg.checks.lints.get(name, "off")
    evidence = _evidence(op)
    if level == "off" or evidence is None or ctx.actor == "pm" or ctx.confirmed_by_pm or op.promised_to:
        return []
    if not any(scope.has_word(evidence.quote, w) for w in ctx.cfg.language.own_promise_words if w.strip()):
        return []
    head = reply_lines.leading_headers(ctx.inputs.raw_input)
    if head is None or not head[0].get("from"):
        return []
    headers = head[0]
    sender = ctx.people.resolve(headers["from"])
    if sender.status != "ok" or not sender.person:
        return []
    if {ctx.people.resolve(owner).person for owner in op.owners} != {sender.person}:
        return []
    # Mail handed in with no To line reached the person, so it was written to them.
    to = reply_lines._entries(headers["to"]) if headers.get("to") else (ctx.people.pm,)
    readers = []
    for entry in to:
        found = ctx.people.resolve(entry) if entry else None
        ok = found is not None and found.status == "ok" and found.person
        if ok and found.person != sender.person and found.person not in readers:
            readers.append(found.person)
    return readers


def _team_word_one_owner_level(op: ActionAddOp, ctx: Context) -> str:
    """The severity of the `team-we-one-owner` lint for an action, or "off" when it doesn't apply: its evidence quote
    promises for a team (one of the language's team-promise words, "we'll", and none of its own-promise words) and its
    one owner is the message's sender, whom the quote doesn't name. The person's own note and changes are left alone."""
    name = "team-we-one-owner"
    level = ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or ctx.cfg.checks.lints.get(name, "off")
    evidence = _evidence(op)
    if level == "off" or evidence is None or ctx.actor == "pm" or ctx.confirmed_by_pm or len(op.owners) != 1:
        return "off"
    language = ctx.cfg.language
    quote = evidence.quote
    if not any(scope.has_word(quote, w) for w in language.team_promise_words if w.strip()):
        return "off"
    if any(scope.has_word(quote, w) for w in language.own_promise_words if w.strip()):
        return "off"
    head = reply_lines.leading_headers(ctx.inputs.raw_input)
    if head is None or not head[0].get("from"):
        return "off"
    sender = ctx.people.resolve(head[0]["from"])
    owner = ctx.people.resolve(op.owners[0])
    if sender.status != "ok" or owner.status != "ok" or sender.person != owner.person:
        return "off"
    record = ctx.store.read().get("person", owner.person)
    if record is None:
        return "off"
    names = [n for n in (record.data.get("first_name") or "", *(record.data.get("full_name") or "").split()) if n]
    if any(scope.has_word(quote, n) for n in names):
        return "off"
    return level


def _own_request_level(op: ActionAddOp, ctx: Context, view: Any) -> str:
    """The severity of the `own-request-not-promise` lint for an action, or "off" when it doesn't apply: it is owned by
    the person alone, comes from mail the person sent (its From line is one of their own addresses), and quotes a
    request to someone as its evidence. The person's own note and changes are left alone."""
    name = "own-request-not-promise"
    level = ctx.cfg.checks.projects.get(op.project or "", {}).get(name) or ctx.cfg.checks.lints.get(name, "off")
    evidence = _evidence(op)
    if level == "off" or evidence is None or ctx.actor == "pm" or ctx.confirmed_by_pm or not ctx.people.pm:
        return "off"
    if not op.owners or {ctx.people.resolve(owner).person for owner in op.owners} != {ctx.people.pm}:
        return "off"
    head = reply_lines.leading_headers(ctx.inputs.raw_input)
    sender = head[0].get("from") if head else None
    if not sender or not reply_lines.sent_by_me(view, ctx.cfg, sender):
        return "off"
    return level if _asks_someone(evidence.quote, ctx) else "off"


def _rejects_asking(ctx: Context) -> bool:
    """Whether the words handed in reject asking a question at all (the workspace's `rejecting_words`), not only how
    it is worded."""
    said = f"{ctx.inputs.raw_input} {ctx.inputs.note}"
    return any(scope.has_word(said, word) for word in ctx.cfg.language.rejecting_words if word.strip())


def origin_of(ctx: Context) -> dict[str, Any]:
    """Who asked for a change, as plugin validators see it, with the run's `task` kind, the record it is `about`
    ({kind, id} or None), the `request` id and the `part` of the record the request names (or None)."""
    request = ctx.store.read().get("request", ctx.inputs.request) if ctx.inputs.request else None
    run = {
        "task": request.data.get("task") if request else None,
        "about": request.data.get("about") if request else None,
        "request": request.id if request else None,
        "part": request.data.get("part") if request else None,
    }
    if ctx.actor == "pm":
        return {"actor": "pm", "trust": "trusted", "via": "action", **run}
    if ctx.actor == "publisher":
        return {"actor": "rule", "trust": "trusted", "via": "rule", **run}
    if ctx.actor == "reminders":
        # A standing-yes approval is the person's own, given ahead; a reminder draft is the engine's.
        return {
            "actor": "pm" if ctx.via == "standing_yes" else "rule",
            "trust": "trusted",
            "via": ctx.via or "reminders",
            **run,
        }
    if ctx.confirmed_by_pm:
        return {"actor": "pm", "trust": "trusted", "via": "screen", **run}
    via = ctx.via or ("input" if ctx.inputs.source else "task" if ctx.inputs.trust == "untrusted" else "note")
    actor = "plugin" if ctx.via in ("handler", "job") else "assistant"
    return {"actor": actor, "trust": ctx.inputs.trust, "via": via, **run}


def _filed_by(op: Any) -> dict[str, Any] | None:
    """Why the engine filed an item under its project, as the record keeps it; none when it did not choose the project
    (`engine/sides.py`)."""
    return op.filed_by.model_dump(mode="json") if op.filed_by is not None and op.project else None


def _reporter(ctx: Context) -> str | None:
    """The person who said the work was done: the PM for their own note, else the one person the input came from
    (its sender or author); none when that isn't one known person."""
    view = ctx.store.read()
    request = view.get("request", ctx.inputs.request) if ctx.inputs.request else None
    if ctx.reporter is not None:
        return ctx.reporter
    if request is None:
        return None
    if request.data["origin"] == "pm" and ctx.inputs.trust == "trusted":
        return ctx.people.pm
    source = view.get("source", ctx.inputs.source) if ctx.inputs.source else None
    return title_for(
        request.data,
        source.data if source is not None else None,
        None,
        people=ctx.people,
        skip=list(ctx.cfg.language.title_skip),
        min_words=ctx.cfg.language.title_min_words,
        head=ctx.inputs.raw_input,
    ).person


class _DryRun(Exception):
    pass


def _validate_in_order(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    """Run plugin validators op by op against a transaction where the earlier ops are applied, then roll it all back,
    so a validator sees what earlier ops in the same changeset created. The checks of the active rules run on what
    each op wrote there. Nothing is kept and no event is published."""
    found: list[Problem] = []
    try:
        with ctx.store.transaction(notify=False) as tx:
            earlier: list[tuple[str, list[dict[str, Any]]]] = []
            for i, op in enumerate(cs.ops):
                messages = ctx.store.plugins.validators(op, view=tx, origin=origin_of(ctx))
                found += [Problem("plugin-validator", "refuse", i, m) for m in messages]
                if messages or op.op not in ctx.allowed_ops:
                    earlier.append((op.op, []))
                    continue
                tx.sql("SAVEPOINT dry_op")
                written: list[dict[str, Any]] = []
                try:
                    if isinstance(op, ActionRepeatOp):
                        try:
                            op = _resolved_repeat(tx, op, ctx, earlier)
                        except StoreError as err:
                            found.append(Problem("targets", "refuse", i, str(err)))
                            continue
                    written, _ = _apply_op(tx, op, ctx, _wctx(ctx, "dry-run", i, op), datetime.now(UTC).date())
                    found += _rule_problems(tx, ctx, i, op, written)
                except Exception:
                    tx.sql("ROLLBACK TO dry_op")
                    written = []
                finally:
                    tx.sql("RELEASE dry_op")
                    earlier.append((op.op, written))
            raise _DryRun
    except _DryRun:
        pass
    return found


def _rule_problems(tx: Tx, ctx: Context, i: int, op: OpModel, refs: list[dict[str, Any]]) -> list[Problem]:
    """Each active rule whose check fails on what the op wrote (design 6.22): sent back to the assistant once and then
    held for the person, or refused for an outward act. A change the person makes or confirms is theirs to make."""
    if ctx.actor in ("pm", "publisher") or ctx.confirmed_by_pm or not refs:
        return []
    written = [found for ref in refs if (found := tx.get(ref.get("kind", ""), ref.get("id", ""))) is not None]
    severity: Severity = "refuse" if ctx.store.plugins.tiers.get(op.op) == "outbound" else "return"
    task = origin_of(ctx).get("task")
    return [
        Problem(RULE_CHECK, severity, i, f"{rule.data['text']}: {reason}", rule=rule.id)
        for rule, reason in failing_rules(ctx.store, tx, task, written)
    ]


def refusals(cs: ChangesetIn, ctx: Context) -> dict[int, str]:
    """Why each op would be refused if the changeset applied now, by op index: the checks, then a trial apply in
    order (later ops see what earlier ones made). Nothing is kept and no event is published."""
    found: dict[int, str] = {}
    for p in check(cs, ctx):
        if p.severity == "refuse" and p.op is not None:
            found.setdefault(p.op, p.message)
    today = datetime.now(UTC).date()
    try:
        with ctx.store.transaction(notify=False) as tx:
            earlier: list[tuple[str, list[dict[str, Any]]]] = []
            for i, op in enumerate(cs.ops):
                written: list[dict[str, Any]] = []
                if i in found:
                    earlier.append((op.op, written))
                    continue
                tx.sql("SAVEPOINT trial_op")
                try:
                    written, _ = _apply_op(
                        tx,
                        _resolved_repeat(tx, op, ctx, earlier) if isinstance(op, ActionRepeatOp) else op,
                        ctx,
                        _wctx(ctx, "dry-run", i, op),
                        today,
                    )
                except NeedsPerson:
                    tx.sql("ROLLBACK TO trial_op")
                except StoreError as err:
                    tx.sql("ROLLBACK TO trial_op")
                    found[i] = str(err)
                finally:
                    tx.sql("RELEASE trial_op")
                    earlier.append((op.op, written))
            raise _DryRun
    except _DryRun:
        pass
    return found


def _wctx(ctx: Context, cs_id: str, index: int, op: OpModel) -> WriteContext:
    evidence = _evidence(op)
    ev = None
    if evidence is not None:
        ev = {"source": ctx.inputs.evidence_source(evidence.quote), "quote": evidence.quote}
    return WriteContext(
        # The ledger records an approval under the standing yes as the person's, and the act names the yes.
        actor="pm" if ctx.actor == "reminders" and isinstance(op, ActApproveOp) else ctx.actor,
        trust=ctx.inputs.trust,
        op=f"{op.op}#{index}",
        changeset=cs_id,
        request=ctx.inputs.request,
        evidence=ev,
    )


def _apply_op(
    tx: Tx, op: OpModel, ctx: Context, w: WriteContext, today: date
) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(op, StageMoveOp):
        from engine.stages import apply_move

        return apply_move(ctx.store, tx, op, w), None
    if "/" in op.op:
        return ctx.store.plugins.apply(tx, op, w), None
    if op.op in ("list.add", "list.rename", "list.merge", "list.retire"):
        from engine import lists

        return lists.apply(tx, op, w), None
    if isinstance(op, MailRestoreOp):
        from engine import set_aside

        # The workspace is the folder that holds the store's database.
        return set_aside.restore_in(tx, ctx.store, Workspace(ctx.store.path.parent), ctx.cfg, op.snapshot, w), None
    if isinstance(op, ReminderEntryOp):
        return reminder_entries.apply(tx, op, ctx, w), None
    if op.op in STANDING_YES_OPS:
        return standing_yes.apply(tx, op, ctx, w), None
    if op.op in ACT_OPS:
        return acts.apply(tx, op, ctx, w), None
    if isinstance(op, (QuestionUpdateOp, QuestionMoveOp, QuestionDropOp, QuestionMarkSentOp)):
        return _correct_question(tx, op, ctx, w), None
    if isinstance(op, ActionReplyOp):
        return _review_reply(tx, op, ctx, w), None
    if isinstance(op, (SourceLimitOp, SourceWidenOp)):
        return _change_audience(tx, op, ctx, w), None
    if isinstance(op, RuleAddOp):
        from engine.rules import add_rule

        ev = (
            {"source": w.evidence["source"] or ctx.inputs.source or "note", "quote": op.evidence.quote}
            if op.evidence is not None and w.evidence is not None
            else None
        )
        return add_rule(tx, ctx.store, op, w, _standing(tx, ctx), evidence=ev), None
    if isinstance(op, RuleRetireOp):
        from engine.rules import retire_rule

        return [{"kind": "rule", "id": retire_rule(tx, op, w)}], None
    if isinstance(op, RecordEditOp):
        edit_record(ctx.store, tx, op, w)
        return [{"kind": op.record.kind, "id": op.record.id}], None
    if isinstance(op, RecordDeleteOp):
        kind, rid = op.record.kind, op.record.id
        users = ctx.store.plugins._referrers(tx)(kind, rid)
        if users:
            raise StoreError(f"{kind} {rid} is still referred to by {users[0][0]} {users[0][1]}")
        tx.delete(kind, rid, w, read_version=op.read_version)
        return [{"kind": kind, "id": rid}], None
    if isinstance(op, (TextEditOp, TextProposeOp)):
        from engine.texts import new_version

        proposal = isinstance(op, TextProposeOp)
        version = new_version(
            ctx.store,
            tx,
            w,
            op.record.kind,
            op.record.id,
            op.field,
            op.text,
            source="proposal" if proposal else "edit",
            by="person",
            base=op.base if proposal else None,
            note=op.note if proposal else None,
            accept=not proposal,
            unmapped=op.unmapped if proposal else None,
        )
        return [{"kind": op.record.kind, "id": op.record.id}, {"kind": "text_version", "id": version.id}], None
    if isinstance(op, TextDraftOp):
        from engine.texts import new_version

        version = new_version(
            ctx.store,
            tx,
            w,
            op.record.kind,
            op.record.id,
            op.field,
            op.text,
            source="draft",
            by="assistant",
            run=op.run,
            base=op.base,
            paragraph_map=op.paragraph_map,
            questions=op.questions,
        )
        return [{"kind": "text_version", "id": version.id}], None
    if isinstance(op, TextAcceptOp):
        from engine.texts import accept

        pending = tx.get("text_version", op.version)
        version = accept(ctx.store, tx, w, op.version, op.read_version, dict(op.choices))
        if version.data["status"] != "discarded" and (pending.data["owner_kind"], pending.data["field"]) == (
            "action",
            "work",
        ):
            # Approving the draft made for an action leaves the action open; the approved text is the message to send.
            from engine import sent_version
            from engine.texts import read_text as _read

            owner = tx.get("action", pending.data["owner_id"])
            sha = owner.data.get("work") if owner is not None else None
            if sha:
                sent_version.keep_work_in(tx, ctx.store, owner.id, _read(ctx.store, sha), ctx.store.clock())
        if version.data["status"] == "discarded":
            _record_draft_correction(tx, ctx, pending, "dropped", None)
        elif "reject" in op.choices.values():
            from engine.texts import read_text

            _record_draft_correction(tx, ctx, pending, "draft_edited", read_text(ctx.store, version.data["sha256"]))
        return [{"kind": "text_version", "id": op.version}, {"kind": "text_version", "id": version.id}], None
    if isinstance(op, TextDiscardOp):
        from engine.texts import discard

        pending = tx.get("text_version", op.version)
        discard(tx, w, op.version, op.read_version)
        _record_draft_correction(tx, ctx, pending, "dropped", None)
        return [{"kind": "text_version", "id": op.version}], None
    if isinstance(op, ProjectAddOp):
        data = {
            "name": op.name.strip(),
            "summary": op.summary,
            "parent": op.parent,
            "language": op.language,
            "area": op.area,
        }
        if op.status is not None:
            data["status"] = op.status
        if op.link:
            # An address nothing set up can open is kept as a link that says so; nothing is read from it.
            from engine.projects import source_for_link

            read = source_for_link(ctx.cfg, op.link) is not None
            data["links"] = [{"label": _link_label(ctx.cfg, op.link, read), "url": op.link}]
        made = tx.create("project", data, w)
        moved = []
        for child in op.children:
            current = tx.get("project", child)
            if current is None:
                raise StoreError(f"there is no project {child}")
            tx.update("project", child, {"parent": made.id}, w, read_version=current.version)
            moved.append({"kind": "project", "id": child})
        return [{"kind": "project", "id": made.id}, *moved], None
    if isinstance(op, FileAddOp):
        from engine.files import blob_matches, check_file, level_for

        if not blob_matches(ctx.store, op.sha256, op.size):
            raise StoreError(f"the bytes for {op.name} aren't stored")
        name, details = check_file(
            ctx.store,
            ctx.cfg,
            tx,
            name=op.name,
            media_type=op.media_type,
            size=op.size,
            file_kind=op.file_kind,
            meta=op.meta,
            project=op.project,
            replaces=op.replaces,
        )
        data = {
            "name": name,
            "media_type": op.media_type,
            "size": op.size,
            "sha256": op.sha256,
            "file_kind": op.file_kind,
            "project": op.project,
            "meta": details,
            "origin": "tool",
            "trust": "untrusted",
            "replaces": op.replaces,
            "added_at": ctx.store.clock(),
            "sensitivity": level_for(ctx.store.plugins.file_kinds().get(op.file_kind), None),
        }
        return [{"kind": "file", "id": tx.create("file", data, w, record_id=op.id).id}], None
    if op.op in KNOWLEDGE_OPS:
        return knowledge.apply(tx, op, w, _standing(tx, ctx)), None
    trust = ctx.inputs.trust
    source = ctx.inputs.source
    touched: list[dict[str, Any]] = []

    def made(kind: str, rid: str) -> None:
        touched.append({"kind": kind, "id": rid})

    if isinstance(op, AnswerOp):
        cites = [{"quote": c.quote, "source": ctx.inputs.evidence_source(c.quote)} for c in op.cites]
        data = {"request": ctx.inputs.request, "text": op.text, "cites": cites}
        made("answer", tx.create("answer", data, w).id)
    elif isinstance(op, SettingProposeOp):
        setting, _ = resolve_setting(ctx.store, op.setting)
        data = {"request": ctx.inputs.request, "key": setting.key, "value": op.value, "why": op.why}
        made("setting_proposal", tx.create("setting_proposal", data, w).id)
    elif isinstance(op, ReportDraftOp):
        data = {"request": ctx.inputs.request, "title": " ".join(op.title.split()), "text": op.text}
        made("report", tx.create("report", data, w).id)
    elif isinstance(op, NoteOp):
        made(
            "note",
            tx.create(
                "note",
                {
                    "text": op.text,
                    "project": op.project,
                    "question": op.question,
                    "source": source,
                    "trust": trust,
                    "filed_by": _filed_by(op),
                },
                w,
            ).id,
        )
    elif isinstance(op, FactOp):
        from engine.facts import check_replaces, received_on

        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        check_replaces(tx, op.supersedes)
        basis, said_by = fact_basis(op, ctx, tx)
        as_of = op.as_of or received_on(tx, ctx.inputs.request, source, zone(ctx.cfg))
        data = {
            "text": op.text,
            "project": op.project,
            "source": source,
            "filed_by": _filed_by(op),
            "evidence": ev,
            "trust": trust,
            "key": op.key,
            "as_of": as_of.isoformat() if as_of else None,
            "supersedes": op.supersedes,
            "basis": basis,
            "said_by": said_by,
            "event": series_module.placement(tx, op.event, op.series, today, zone(ctx.cfg)),
            "series": op.series,
            "reaches_children": op.reaches_children,
            "on": op.on.isoformat() if op.on else None,
            "on_kind": op.on_kind,
        }
        made("fact", tx.create("fact", data, w).id)
    elif isinstance(op, EventAddOp):
        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        data = {
            "title": op.title,
            "start": op.start,
            "end": op.end,
            "project": op.project or _input_project(tx, ctx.inputs.request, source),
            "series": op.series,
            "source": source,
            "evidence": ev,
            "trust": trust,
        }
        made("event", tx.create("event", data, w).id)
    elif isinstance(op, EventSetOp):
        cur = tx.get("event", op.id)
        moved = {k: v for k, v in (("start", op.start), ("end", op.end)) if v is not None}
        tx.update("event", op.id, moved, w, read_version=cur.version)
        made("event", op.id)
        for action_id in follow_event(tx, op.id, w):
            made("action", action_id)
    elif isinstance(op, SeriesAddOp):
        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        data = {
            "title": op.title,
            "project": op.project or _input_project(tx, ctx.inputs.request, source),
            "repeats": " ".join(op.repeats.split()) if op.repeats else None,
            "source": source,
            "evidence": ev,
            "trust": trust,
        }
        made_series = tx.create("series", data, w)
        made("series", made_series.id)
        for entry in op.events:
            cur = tx.get("event", entry)
            tx.update("event", entry, {"series": made_series.id}, w, read_version=cur.version)
            made("event", entry)
    elif isinstance(op, SeriesLinkOp):
        cur = tx.get("event", op.event)
        tx.update("event", op.event, {"series": op.series}, w, read_version=cur.version)
        made("event", op.event)
    elif isinstance(op, AgendaAddOp):
        by = ctx.people.pm if _persons_own(tx, ctx) else None
        made(*agenda_module.add(tx, op, w, by=by, at=ctx.store.clock()))
    elif isinstance(op, RecordSetOp):
        cur = tx.get(op.kind, op.id)
        value = op.value
        if op.kind == "person" and op.field == "org":
            from engine.organizations import resolve

            value = resolve(tx, value, w)  # the assistant names an organization; people refer to it by id
        if w.actor != "pm" and model_for(op.kind).needs_person(op.field, value):
            raise NeedsPerson(f"only you can set {op.field} on a {op.kind}")
        changes = {op.field: value}
        if op.field == "series" and value is not None and cur.data.get("event") is None:
            changes["event"] = series_module.placement(tx, None, value, today, zone(ctx.cfg))
        tx.update(op.kind, op.id, changes, w, read_version=cur.version)
        made(op.kind, op.id)
    elif isinstance(op, ProjectRoleOp):
        cur = tx.get("project", op.project)
        who = ctx.people.resolve(op.person).person
        roles = [r for r in cur.data.get("roles", []) if r.get("person") != who]
        tx.update(
            "project", op.project, {"roles": [*roles, {"person": who, "role": op.role}]}, w, read_version=cur.version
        )
        made("project", op.project)
    elif isinstance(op, RecordLogOp):
        cur = tx.get("project", op.project)
        log = [*cur.data.get("log", []), {"on": today.isoformat(), "text": op.text}]
        tx.update("project", op.project, {"log": log}, w, read_version=cur.version)
        made("project", op.project)
    elif isinstance(op, ActionAddOp):
        owners = [{"person": ctx.people.resolve(n).person} for n in op.owners]
        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        due, check = _due(tx, ctx, source, op.due_words, op.due)
        placed = series_module.placement(tx, op.event, op.series, today, zone(ctx.cfg))
        due_event = placed if op.due_at_event and placed else None
        started_on_hold = None
        if due_event:
            due, check = _event_day(tx, due_event), False
        elif (op.due_words or "").strip() and due is None:
            # Words that wait for something to happen put the promise on hold from the start; "before <a known
            # entry>" is due at that entry.
            kind, entry = _condition(tx, ctx, source, op.due_words, today)
            if kind == "event" and entry:
                due, check, due_event = _event_day(tx, entry), False, entry
            elif kind == "hold":
                started_on_hold = {"waiting_for": " ".join(op.due_words.split()), "since": today.isoformat()}
        same = _same_promise(tx, ctx, op)
        if same is not None and _within_window(same.data.get("due"), due, ctx):
            _merge_promise(tx, same, op, ctx, w, due, check, ev, today, source)
            made("action", same.id)
            return touched, None
        said = ctx.people.resolve(op.said_by) if op.said_by else None
        data = {
            "text": op.text,
            "owners": owners,
            "due": due.isoformat() if due else None,
            "due_words": " ".join(op.due_words.split()) if op.due_words else None,
            "due_check": check,
            "promised_to": [ctx.people.resolve(n).person for n in op.promised_to],
            "basis": op.basis,
            "said_by": said.person if said is not None and said.status == "ok" else None,
            "due_event": due_event,
            "due_by_person": due is not None and _persons_own(tx, ctx),
            "on_hold": {"waiting_for": " ".join(op.waiting_for.split()), "since": today.isoformat()}
            if op.waiting_for and op.waiting_for.strip()
            else started_on_hold,
            "project": op.project,
            "filed_by": _filed_by(op),
            "event": placed,
            "series": op.series,
            "source": source,
            "evidence": ev,
            "status": "open" if owners else "held",
            "reply": op.reply,  # a draft: it stays unreviewed until the person approves or rewords it
            "reply_reviewed": False,
            "reply_owed": op.reply_owed,
            "replies_to": source if op.reply_owed else None,
            "asker": reply_lines.asker_of(ctx.people, ctx.inputs.raw_input) if op.reply_owed else None,
        }
        action = tx.create("action", data, w)
        made("action", action.id)
        if not owners:
            q = _pm_question(
                tx,
                w,
                ctx,
                f"Pick an owner: {op.text}",
                "routing",
                options=[],
                resolves={"kind": "owner", "action": action.id, "changeset": w.changeset},
                projects=[op.project] if op.project else None,  # the question sits where the action it asks about does
            )
            made("question", q)
            return touched, q
    elif isinstance(op, ActionCloseOp):
        cur = tx.get("action", op.id)
        credit = {
            "status": "done",
            "done_by": [o["person"] for o in cur.data.get("owners", [])],
            "reported_by": _reporter(ctx),
        }
        tx.update("action", op.id, credit, w, read_version=cur.version)
        made("action", op.id)
        _next_occurrence(tx, ctx, cur, w, made)
    elif isinstance(op, ActionHoldOp):
        cur = tx.get("action", op.id)
        hold = {"waiting_for": " ".join(op.waiting_for.split()), "since": today.isoformat()}
        if op.on:
            hold["on"] = op.on
        tx.update("action", op.id, {"on_hold": hold}, w, read_version=cur.version)
        made("action", op.id)
    elif isinstance(op, ActionUnholdOp):
        cur = tx.get("action", op.id)
        changes = {"on_hold": None}
        if op.due_words or op.due:
            # Taking it off hold with its new date is one step.
            due, check = _due(tx, ctx, source, op.due_words, op.due)
            words = " ".join(op.due_words.split()) if op.due_words else None
            changes |= {"due": due.isoformat() if due else None, "due_words": words, "due_check": check}
            changes |= {"due_event": None, "due_by_person": due is not None and _persons_own(tx, ctx)}
        tx.update("action", op.id, changes, w, read_version=cur.version)
        made("action", op.id)
    elif isinstance(op, ActionDropOp):
        cur = tx.get("action", op.id)
        reason = " ".join(op.reason.split())
        tx.update("action", op.id, {"status": "dropped", "dropped_reason": reason}, w, read_version=cur.version)
        made("action", op.id)
        _next_occurrence(tx, ctx, cur, w, made)
        if op.event or op.series:
            # Called off because it moved into a meeting: it goes on that meeting's agenda, linked, so it isn't lost.
            moved = AgendaAddOp(event=op.event, series=op.series, action=op.id)
            by = ctx.people.pm if _persons_own(tx, ctx) else None
            made(*agenda_module.add(tx, moved, w, by=by, at=ctx.store.clock()))
        for draft in endings.called_off_notices(tx, ctx, cur):
            # Whoever was already told gets one line, drafted for the person to send; nothing goes out by itself.
            made("question", tx.create("question", draft, w).id)
        if ctx.actor == "pm":
            # Dropping a reply the assistant said was owed says none was: its own kind of correction.
            _record_dropped(
                tx, ctx, "action", op.id, reason, "no_reply_needed" if cur.data.get("reply_owed") else "dropped"
            )
    elif isinstance(op, ActionRepeatOp):
        if op.id.startswith("@") or op.words is not None:
            raise StoreError("the repeat was not read before it was applied")
        cur = tx.get("action", op.id)
        changes: dict[str, Any] = {"repeat": None}
        if op.rule is not None:
            changes = {
                "repeat": {"rule": op.rule, "phrase": " ".join(op.phrase.split()), "start": op.start.isoformat()}
            }
            if cur.data.get("due") is None:
                # A repeat starts on a day: a to-do with none is due on it.
                changes |= {"due": op.start.isoformat(), "due_words": None, "due_check": False, "due_event": None}
                changes["due_by_person"] = _persons_own(tx, ctx)
        tx.update("action", op.id, changes, w, read_version=cur.version)
        made("action", op.id)
    elif isinstance(op, ActionMoveOp):
        cur = tx.get("action", op.id)
        due, check = _due(tx, ctx, source, op.due_words, op.due)
        words = " ".join(op.due_words.split()) if op.due_words else None
        changes = {"due": due.isoformat() if due else None, "due_words": words, "due_check": check}
        changes |= {"due_event": None, "due_by_person": due is not None and _persons_own(tx, ctx)}
        tx.update("action", op.id, changes, w, read_version=cur.version)
        made("action", op.id)
    elif isinstance(op, (ActionPartOp, ActionNewsOp)):
        cur = tx.get("action", op.id)
        quote = op.evidence.quote if op.evidence is not None else None
        heard = op.delivered if isinstance(op, ActionPartOp) else op.text
        entry = {
            "on": today.isoformat(),
            "text": " ".join(heard.split()),
            "quote": quote,
            "source": source,
            "delivered": isinstance(op, ActionPartOp),
            "non_answer": isinstance(op, ActionNewsOp),
        }
        changes: dict[str, Any] = {"news": [*cur.data.get("news", []), entry]}
        if isinstance(op, ActionPartOp):
            changes["text"] = " ".join(op.left.split())
        tx.update("action", op.id, changes, w, read_version=cur.version)
        made("action", op.id)
    elif isinstance(op, QuestionAddOp):
        to = ctx.people.resolve(op.to).person
        data = {
            "to": to,
            "title": op.title,
            "text": op.text,
            "links": [link.model_dump() for link in op.links],
            "projects": [op.project] if op.project else [],
            "filed_by": _filed_by(op),
            "event": series_module.placement(tx, op.event, op.series, today, zone(ctx.cfg)),
            "series": op.series,
            "kind": op.kind,
            "source": source,
            "matters_for": " ".join(op.matters_for.split()) if op.matters_for else None,
        }
        made("question", tx.create("question", data, w).id)
    elif isinstance(op, QuestionDoneOp):
        cur = tx.get("question", op.id)
        tx.update("question", op.id, {"status": "answered", "answer": op.answer}, w, read_version=cur.version)
        made("question", op.id)
        projects = cur.data.get("projects") or [None]
        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        from engine.facts import received_on

        as_of = received_on(tx, ctx.inputs.request, source, zone(ctx.cfg))
        fact = tx.create(
            "fact",
            {
                "text": f"{cur.data['title']} {op.answer}",
                "project": projects[0],
                "source": source,
                "evidence": ev,
                "trust": trust,
                "as_of": as_of.isoformat() if as_of else None,
            },
            w,
        )
        made("fact", fact.id)
    elif isinstance(op, PersonAddOp):
        from engine.organizations import resolve

        org = resolve(tx, op.org, w)
        data = {
            "full_name": op.full_name,
            "role": op.role,
            "org": org,
            "aliases": op.aliases,
            # The spelling is verified when the person gave it: their own change or their own note.
            "name_verified": ctx.actor == "pm" or _from_pm(tx, ctx),
        }
        if op.first_name:
            data["first_name"] = " ".join(op.first_name.split())
        made("person", tx.create("person", data, w).id)
    elif isinstance(op, PersonStanceOp):
        found = tx.get("person", op.id)
        if found is None:
            raise StoreError(f"there is no person {op.id}")
        tx.update("person", op.id, {"stance": op.stance}, w, read_version=found.version)
        made("person", op.id)
    elif isinstance(op, PersonContactOp):
        found = tx.get("person", op.person)
        kind = contact_kind(ctx.cfg, op.kind)
        if found is None or kind is None:
            raise StoreError(contact_problem(tx, ctx.cfg, op) or "that contact detail can't be set")
        reach = {**found.data.get("how_to_reach", {}), kind: op.value}
        tx.update("person", op.person, {"how_to_reach": reach}, w, read_version=found.version)
        made("person", op.person)
    return touched, None


def _next_occurrence(tx: Tx, ctx: Context, ended: Any, w: WriteContext, made: Any) -> None:
    """When an action that repeats ends, its next occurrence is made in the same change, so Undo takes both back."""
    from engine import repeats

    if ended.data.get("repeat"):
        found = repeats.make_next(tx, ended, w, repeats.local_today(ctx.store, ctx.cfg))
        if found:
            made("action", found)


def _due(tx: Tx, ctx: Context, source: str | None, words: str | None, given: date | None) -> tuple[date | None, bool]:
    """An action's due date and whether the person should check it. Words are read by the rules
    (`engine/due_phrases.py`, with the language settings' own words) against when the input was received, and their
    reading wins over a date the model gave. Words that tie the due to something that happens ("once the keys arrive")
    have no date, whatever date the model gave. Other words the rules can't read keep the model's own date, marked for
    the person to check. Without words, the given date stands. A workspace whose language the rules don't read keeps
    the given date."""
    from engine.due_phrases import is_condition, load_holidays, resolve

    language = (ctx.cfg.workspace.language or "en-US").replace("_", "-")
    if not (words or "").strip() or not language.lower().startswith("en"):
        return given, False
    locale = "en_US" if language.lower().startswith("en-us") else "en_GB"
    received, where = _received_at(tx, ctx, source), zone(ctx.cfg)
    saved = tx.get("source", source) if source else None
    sent = saved.data.get("sent_at") if saved is not None else None
    if sent:
        # A message's "tomorrow" is the day after it was sent, where its sender was.
        received = datetime.fromisoformat(str(sent))
        where = received.tzinfo or where
    settings = ctx.cfg.language
    found = resolve(
        words,
        received,
        where,
        locale=locale,
        lead_words=settings.due_lead_words,
        ordinal_suffixes=settings.due_ordinal_suffixes,
        phrase_words=settings.due_phrase_words,
        number_words=settings.due_number_words,
        time_zones=settings.time_zone_abbreviations,
        sender_zone=zone(ctx.cfg),
        holidays=load_holidays(settings.holiday_calendar or language),
    )
    day = found.end or found.start
    if day is None:
        if given is None or is_condition(words, settings.due_condition_words):
            return None, False
        return given, True
    # One day read with doubt ("next Friday", a year-less date far ahead) is checked; a range is due at its end.
    return day, not found.exact and found.start == found.end


def _condition(tx: Tx, ctx: Context, source: str | None, words: str, today: date) -> tuple[str | None, str | None]:
    """What due words the rules can't read as a date still say (design 6.33, the language settings): `hold` for words
    that wait for something to happen ("once the keys arrive"), `event` with the entry's id for "before <an entry
    still ahead>" when the words name exactly one, `open` for the rest of the condition words (and for a "before" that
    names no known entry, or several), and none for words that aren't a condition."""
    from engine.due_phrases import after_marker, is_condition, named_entry

    settings = ctx.cfg.language
    language = (ctx.cfg.workspace.language or "en-US").replace("_", "-")
    if not language.lower().startswith("en") or not is_condition(words, settings.due_condition_words):
        return None, None
    if is_condition(words, settings.due_hold_words):
        return "hold", None
    named = after_marker(words, settings.due_before_words)
    if named:
        found = named_entry(tx.list("event"), named, today.isoformat())
        if found is not None:
            return "event", found.id
    return "open", None


def _received_at(tx: Tx, ctx: Context, source: str | None) -> datetime:
    """When the input was received: its source's time, else when its request was made, else now."""
    saved = tx.get("source", source) if source else None
    request = tx.get("request", ctx.inputs.request) if ctx.inputs.request else None
    for stored, key in ((saved, "received_at"), (request, "created_at")):
        value = stored.data.get(key) if stored is not None else None
        if value:
            stamp = datetime.fromisoformat(str(value))
            return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _made_by(tx: Tx, kind: str, record_id: str) -> tuple[str | None, str | None]:
    """The changeset that made a record, and the AI run that wrote that changeset; each None when there isn't one."""
    first = next(iter(tx.ledger(kind=kind, record_id=record_id)), None)
    changeset = first["changeset"] if first is not None else None
    made = tx.get("changeset", changeset) if changeset else None
    return changeset, (made.data.get("run") if made is not None else None)


def _correct_question(tx: Tx, op: OpModel, ctx: Context, w: WriteContext) -> list[dict[str, Any]]:
    """The person's correction of a question: reword it, ask someone else, drop it with a reason, or mark it as sent.
    Reword, reroute and drop each record a signal naming the question and the changeset and run that made it. The
    signal is written apart from the change, so Undo puts the question back and leaves the signal as it was."""
    cur = tx.get("question", op.id)  # type: ignore[attr-defined]
    qid = cur.id
    changeset, run = _made_by(tx, "question", qid)
    people = ctx.people
    kind: str | None = None
    refs = [qid]
    note: str | None = None
    if isinstance(op, QuestionUpdateOp):
        changes = {k: v for k, v in (("title", op.title), ("text", op.text)) if v is not None}
        kind = "reworded"
        note = "\n".join(f"{k}: was {cur.data.get(k) or ''!r}, now {v!r}" for k, v in changes.items())
    elif isinstance(op, QuestionMoveOp):
        person = people.resolve(op.to).person
        changes = {"to": person}
        if cur.data["status"] == "sent":
            changes |= {"status": "open", "sent_at": None}  # it hasn't gone to the new person yet
        kind = "routed"
        refs = [*([changeset] if changeset else []), qid, person]
        note = f"asked of {people.name(cur.data['to'])}, now of {people.name(person)}"
    elif isinstance(op, QuestionDropOp):
        changes = {"status": "dropped", "dropped_reason": " ".join(op.reason.split())}
        kind = "dropped"
        note = changes["dropped_reason"]
    else:
        assert isinstance(op, QuestionMarkSentOp)
        when = (
            datetime(op.on.year, op.on.month, op.on.day, 12, tzinfo=UTC)
            if op.on is not None
            else datetime.fromisoformat(ctx.store.clock())
        )
        changes = {"status": "sent", "sent_at": when.isoformat()}
    tx.update("question", qid, changes, w, read_version=cur.version)
    # A drop the assistant proposes is its own work, not a correction; only the person's own drop is one.
    if kind is not None and (kind != "dropped" or ctx.actor == "pm"):
        learn.record(
            tx,
            ctx.cfg,
            {
                "kind": kind,
                "refs": refs,
                "changeset": changeset,
                "run": run,
                "note": note,
                "at": ctx.store.clock(),
            },
            WriteContext(actor="pm", trust="trusted", op=kind),
            ctx.store.clock(),
        )
    return [{"kind": "question", "id": qid}]


def action_reply_problem(view: Any, op: ActionReplyOp) -> str | None:
    """Why the person's approval or rewording of an action's drafted reply can't apply, or None. The action must exist
    and not be closed; approving needs a draft to approve."""
    found = view.get("action", op.id)
    if found is None:
        return f"there is no action {op.id}"
    if found.data["status"] in ("done", "dropped"):
        return f"action {op.id} is already {found.data['status']}"
    if op.text is None and not found.data.get("reply"):
        return f"action {op.id} has no drafted reply to approve"
    return None


def _review_reply(tx: Tx, op: ActionReplyOp, ctx: Context, w: WriteContext) -> list[dict[str, Any]]:
    """The person approves an action's drafted reply or replaces it: either way it is reviewed. Rewording a draft the
    assistant wrote records a `draft_edited` signal with the text as the person used it, naming the action and the
    changeset and run that made it; writing a reply where there was none, or approving as is, corrects nothing. The
    signal is written apart from the change, so Undo puts the reply back and leaves the signal as it was."""
    cur = tx.get("action", op.id)
    draft = cur.data.get("reply")
    text = op.text.strip() if op.text is not None else draft
    tx.update("action", op.id, {"reply": text, "reply_reviewed": True}, w, read_version=cur.version)
    if draft and not cur.data.get("reply_reviewed") and normalize(text) != normalize(draft):
        changeset, run = _made_by(tx, "action", op.id)
        learn.record(
            tx,
            ctx.cfg,
            {
                "kind": "draft_edited",
                "refs": [op.id],
                "changeset": changeset,
                "run": run,
                "note": text,
                "at": ctx.store.clock(),
            },
            WriteContext(actor="pm", trust="trusted", op="draft_edited"),
            ctx.store.clock(),
        )
    return [{"kind": "action", "id": op.id}]


def _record_draft_correction(tx: Tx, ctx: Context, pending: Any, signal: str, note: str | None) -> None:
    """The person's own review of a draft the assistant wrote that changes it or sets it aside: a `draft_edited` signal
    with the text as they kept it, or a `dropped` one with no note (setting a draft aside gives no reason), naming the
    record the text belongs to and the changeset and run that wrote it. Taking a draft as it is corrects nothing. It is
    written apart from the change, so Undo leaves it as it was."""
    if pending is None or pending.data.get("source") != "draft" or not pending.data.get("run"):
        return
    changeset, _ = _made_by(tx, "text_version", pending.id)
    learn.record(
        tx,
        ctx.cfg,
        {
            "kind": signal,
            "refs": [pending.data["owner_id"]],
            "changeset": changeset,
            "run": pending.data["run"],
            "note": note,
            "at": ctx.store.clock(),
        },
        WriteContext(actor="pm", trust="trusted", op=signal),
        ctx.store.clock(),
    )


def _record_dropped(tx: Tx, ctx: Context, kind: str, record_id: str, reason: str, signal: str = "dropped") -> None:
    """The person's own drop of something the assistant may have made: a `dropped` signal (or the `signal` given)
    naming it and, when the assistant made it, the changeset and run. It is written apart from the change, so Undo
    leaves it as it was."""
    changeset, run = _made_by(tx, kind, record_id)
    learn.record(
        tx,
        ctx.cfg,
        {
            "kind": signal,
            "refs": [record_id],
            "changeset": changeset,
            "run": run,
            "note": reason,
            "at": ctx.store.clock(),
        },
        WriteContext(actor="pm", trust="trusted", op="dropped"),
        ctx.store.clock(),
    )


def _standing(tx: Tx, ctx: Context) -> knowledge.Standing:
    """Who a knowledge op comes from, as the entry it adds records it: the person's own words or act, content they
    report or that came in, or the assistant's own generalization."""
    person = ctx.actor == "pm" or ctx.confirmed_by_pm or _from_pm(tx, ctx)
    request = tx.get("request", ctx.inputs.request) if ctx.inputs.request else None
    reported = request is not None and request.data["origin"] in ("input", "pm")
    if not person and request is not None and learn.is_learning(request.data["task"]):
        # Learning from a correction restates it in the assistant's own words: a proposal the person reads, and
        # whose wording is theirs once they keep it.
        return knowledge.Standing(False, ctx.people.pm, "assistant", "trusted", None, request.id, ctx.store.clock())
    if person:
        origin = "person"
    elif reported or ctx.inputs.source or ctx.inputs.trust == "untrusted":
        origin = "input"
    else:
        origin = "assistant"
    return knowledge.Standing(
        person=person,
        pm=ctx.people.pm,
        origin=origin,
        trust=ctx.inputs.trust,
        source=ctx.inputs.source,
        request=ctx.inputs.request or None,
        now=ctx.store.clock(),
        hold_days=ctx.cfg.dispatch.knowledge.discards_hold_days,
        alike=ctx.cfg.dispatch.knowledge.discard_similarity,
    )


def _pm_question(
    tx: Tx,
    w: WriteContext,
    ctx: Context,
    title: str,
    kind: str,
    *,
    options: list[str],
    resolves: dict[str, Any],
    projects: list[str] | None = None,
) -> str:
    pm = ctx.people.pm
    if pm is None:
        raise StoreError("you aren't set as a person in this workspace yet, so there is no one to ask")
    data = {"to": pm, "title": title, "kind": kind, "options": options, "resolves": resolves}
    if projects:
        data["projects"] = projects
    return tx.create("question", data, w).id


def _routing_question(tx: Tx, op: OpModel, index: int, cs_id: str, ctx: Context, reason: str) -> str:
    _, name, candidates = reason.split(":", 2)
    waiting = _open_who_is(tx, cs_id, name)
    if waiting is not None:
        return waiting
    options = [c for c in candidates.split(",") if c]
    w = WriteContext(
        actor="engine", trust="trusted", op=f"routing#{index}", changeset=cs_id, request=ctx.inputs.request
    )
    title = f"Who is “{name}”?"
    return _pm_question(
        tx,
        w,
        ctx,
        title,
        "routing",
        options=options,
        resolves={"kind": "held-op", "changeset": cs_id, "op": index, "name": name},
    )


def _same_name(a: Any, b: Any) -> bool:
    """Whether two names as written are the same, ignoring case and surrounding space."""
    return isinstance(a, str) and isinstance(b, str) and a.strip().casefold() == b.strip().casefold()


def _open_who_is(tx: Tx, cs_id: str, name: str) -> str | None:
    """The open "who is this?" question of a changeset for this name, if one was already asked."""
    for q in tx.find("question", {"kind": "routing", "status": "open"}):
        r = q.data.get("resolves") or {}
        if r.get("kind") == "held-op" and r.get("changeset") == cs_id and _same_name(r.get("name"), name):
            return q.id
    return None


# ---- releasing held ops and answering routing questions --------------------------------------------------------------


def release(
    store: Store,
    cfg: Config,
    changeset_id: str,
    index: int,
    *,
    person: str | None = None,
    now: datetime | None = None,
    ws: Workspace | None = None,
    instead: OpModel | None = None,
) -> None:
    """Apply a held op, optionally saying who an unresolved name is. With `instead`, that op is applied in its place and
    written into the changeset as the op that was applied. With `ws`, the names in it are read in the
    context of the input's saved text, as they were when the changeset was made. Saying who a name is also applies
    every other op of the changeset waiting on the same question, and records one signal."""
    now = now or datetime.now(UTC)
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    first = cs.data["ops"][index]
    qid = first.get("question")
    name = (qid and _question_name(store, qid)) or None
    others = []
    if person is not None and name is not None:
        others = [o["index"] for o in cs.data["ops"] if o["index"] != index and o["status"] == "held"]
        others = [i for i in others if cs.data["ops"][i].get("question") == qid]
    routed = {"question": qid, "person": person, "name": name} if person is not None and name is not None else None
    _release_one(store, cfg, changeset_id, index, person=person, now=now, ws=ws, routed=routed, instead=instead)
    for other in others:
        _release_one(store, cfg, changeset_id, other, person=person, now=now, ws=ws)


def _release_one(
    store: Store,
    cfg: Config,
    changeset_id: str,
    index: int,
    *,
    person: str | None,
    now: datetime,
    ws: Workspace | None,
    routed: dict[str, Any] | None = None,
    instead: OpModel | None = None,
) -> None:
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    outcome = outcomes[index]
    if outcome["status"] != "held":
        raise StoreError("that item isn't waiting for you")
    from engine.ops import CHANGESET

    try:
        op = CHANGESET.validate_python({"ops": [outcome["op"]]}, context={"op_models": store.plugins.ops}).ops[0]
    except ValidationError:
        # The op belongs to a plugin that isn't running now; it stays held until the plugin is back.
        raise StoreError("the plugin this belongs to is turned off or failed to start") from None
    name = (outcome.get("question") and _question_name(store, outcome["question"])) or None
    if person is not None and name is not None:
        op = _substitute(op, name, person)
    if instead is not None:
        op = instead
        outcome["op"] = op.model_dump(mode="json", exclude_none=True)
    req = store.read().get("request", cs.data["request"])
    text = source_text(ws, store, req.data.get("source")) if ws is not None and req is not None else ""
    people = People.for_input(
        store, cfg, cs.data["request"], text, learns=request_learns(store, req.data) if req is not None else True
    )
    inputs = Inputs(cs.data["request"], req.data.get("source") if req else None, "", "", cs.data["trust"])
    ctx = Context(store, cfg, people, tuple(), inputs, confirmed_by_pm=True, reporter=outcome.get("reporter"))
    refusals = store.plugins.validators(op)
    if refusals:
        raise StoreError("; ".join(refusals))
    with store.transaction() as tx:
        if outcome.get("question"):
            q = tx.get("question", outcome["question"])
            if q and q.data["status"] == "open":
                tx.update(
                    "question",
                    q.id,
                    {"status": "answered", "answer": person or "added"},
                    WriteContext(actor="pm", trust="trusted", op="question.answer"),
                    read_version=q.version,
                )
        if routed is not None:
            _record_routed(tx, cfg, now, changeset_id, routed["question"], routed["person"], routed["name"])
        still = _needs_person_choice(op, ctx)
        if still is not None and still.startswith("who-is"):
            outcome["op"] = op.model_dump(mode="json", exclude_none=True)
            outcome["question"] = _routing_question(tx, op, index, changeset_id, ctx, still)
            tx.update(
                "changeset",
                changeset_id,
                {"ops": outcomes},
                WriteContext(actor="pm", trust="trusted", op="changeset.release"),
                read_version=cs.version,
            )
            return
        w = WriteContext(
            actor="pm",
            trust="trusted",
            op=f"{op.op}#{index}",
            changeset=changeset_id,
            request=cs.data["request"],
            evidence=outcome["op"].get("evidence")
            and {"source": inputs.source, "quote": outcome["op"]["evidence"]["quote"]},
        )
        if isinstance(op, ActionRepeatOp):
            op = _resolved_repeat(tx, op, ctx, [(o["op"]["op"], o.get("records") or []) for o in outcomes[:index]])
        records, question = _apply_op(tx, op, ctx, w, now.date())
        outcome.update(status="applied", records=records, reason=None)
        if question:
            outcome["question"] = question
        status = "held" if any(o["status"] == "held" for o in outcomes) else "applied"
        tx.update(
            "changeset",
            changeset_id,
            {"ops": outcomes, "status": status},
            WriteContext(actor="pm", trust="trusted", op="changeset.release"),
            read_version=cs.version,
        )

    store.plugins.publish("changeset.applied", {"id": changeset_id}, follows=changeset_id)


DECLINED_REASON = "You kept it as it was."


def decline_held(store: Store, changeset_id: str, index: int, *, now: datetime | None = None) -> None:
    """Keep things as they are for a held op: it is not applied, it leaves the person's list, and one `held_declined`
    signal records the choice for the assistant to learn from. Undo is `undecline_held`."""
    now = now or datetime.now(UTC)
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    if not 0 <= index < len(outcomes) or outcomes[index]["status"] != "held":
        raise StoreError("that item isn't waiting for you")
    outcome = outcomes[index]
    target = outcome["op"].get("id") or outcome["op"].get("question") or ""
    outcome.update(status="undone", held_reason=outcome.get("reason"), reason=DECLINED_REASON)
    still = "held" if any(o["status"] == "held" for o in outcomes) else "applied"
    with store.transaction() as tx:
        tx.update(
            "changeset",
            changeset_id,
            {"ops": outcomes, "status": still},
            WriteContext(actor="pm", trust="trusted", op="changeset.decline"),
            read_version=cs.version,
        )
        learn.record(
            tx,
            store.plugins.cfg,
            {
                "kind": "held_declined",
                "refs": [changeset_id, *([target] if target else [])],
                "changeset": changeset_id,
                "run": cs.data.get("run"),
                "note": f"{outcome['op'].get('op')}: {outcome.get('label') or ''}".strip(),
                "at": now.isoformat(),
            },
            WriteContext(actor="pm", trust="trusted", op="held_declined"),
            now,
        )


def undecline_held(store: Store, changeset_id: str, index: int) -> None:
    """Take back keeping things as they are: the op waits for the person again, and what the assistant would have
    learned from the choice is netted out."""
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    if (
        not 0 <= index < len(outcomes)
        or outcomes[index]["reason"] != DECLINED_REASON
        or outcomes[index]["status"] != "undone"
    ):
        raise StoreError("that item wasn't kept as it was")
    outcome = outcomes[index]
    outcome.update(status="held", reason=outcome.pop("held_reason", None))
    with store.transaction() as tx:
        tx.update(
            "changeset",
            changeset_id,
            {"ops": outcomes, "status": "held"},
            WriteContext(actor="pm", trust="trusted", op="changeset.undecline"),
            read_version=cs.version,
        )
    learn.net_out(store, "held_declined", [changeset_id])


def pick_owner(store: Store, question_id: str, person: str) -> None:
    """Answer a "Pick an owner" question: the held action gets its first owner and opens."""
    q = store.read().get("question", question_id)
    if q is None or (q.data.get("resolves") or {}).get("kind") != "owner":
        raise StoreError("that question isn't asking for an owner")
    action_id = q.data["resolves"]["action"]
    w = WriteContext(actor="pm", trust="trusted", op="action.assign")
    with store.transaction() as tx:
        if tx.get("person", person) is None:
            raise StoreError(f"there is no person {person}")
        a = tx.get("action", action_id)
        if a is None:
            raise StoreError("the action this question asked about was undone, so there is nothing to give an owner")
        tx.update("action", action_id, {"owners": [{"person": person}], "status": "open"}, w, read_version=a.version)
        tx.update("question", question_id, {"status": "answered", "answer": person}, w, read_version=q.version)
        _record_routed(
            tx, store.plugins.cfg, datetime.now(UTC), q.data["resolves"].get("changeset"), question_id, person, None
        )


#: The name a fold's changes are written under in the ledger. Undoing it reopens the owner question too, which
#: undoing any other op leaves as the person answered it.
FOLD_OP = "action.fold"


def fold_unowned(
    store: Store,
    cfg: Config,
    changeset_id: str,
    index: int,
    into: str,
    read_version: int,
    *,
    now: datetime | None = None,
) -> str:
    """Add an action that waits for an owner to the open action it nearly repeats, as one change with Undo. The held
    action is closed as dropped and its "Pick an owner" question with it, the target's notes gain a line with the
    held action's text and the words it came from, and a `held_declined` signal records the person's choice, naming
    the action it went into. `read_version` is the target's version as the person saw it. Returns the new changeset."""
    now = now or datetime.now(UTC)
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    outcome = outcomes[index] if 0 <= index < len(outcomes) else None
    held_id = next((r["id"] for r in (outcome or {}).get("records", []) if r["kind"] == "action"), None)
    qid = (outcome or {}).get("question")
    if outcome is None or outcome["op"].get("op") != "action.add" or outcome["status"] != "applied" or not held_id:
        raise StoreError("that item isn't an action waiting for an owner")
    words = cfg.language.messages
    with store.transaction() as tx:
        held = tx.get("action", held_id)
        question = tx.get("question", qid) if qid else None
        if held is None or held.data["status"] != "held" or question is None or question.data["status"] != "open":
            raise StoreError("that action isn't waiting for an owner any more")
        target = tx.get("action", into)
        if target is None or into == held_id:
            raise StoreError(f"there is no other action {into}")
        if target.data["status"] != "open":
            raise StoreError(f"action {into} isn't open")
        if target.version != read_version:
            raise StoreError(f"action {into} changed since it was read")
        cs_id = tx.new_id("changeset")
        summary = "Combined two to-dos"
        request = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "pm",
                "state": "done",
                "note": summary,
                "created_at": store.clock(),
                "changeset": cs_id,
            },
            WriteContext("pm", "trusted", "screen.request"),
        )
        w = WriteContext("pm", "trusted", f"{FOLD_OP}#0", cs_id, request.id)
        quote = ((held.data.get("evidence") or {}).get("quote")) or ""
        line = words.folded_note.format(text=held.data["text"], quote=quote)
        notes = f"{target.data['notes']}\n{line}" if target.data.get("notes") else line
        tx.update("action", into, {"notes": notes}, w, read_version=target.version)
        reason = words.folded_reason.format(text=target.data["text"])
        tx.update("action", held_id, {"status": "dropped", "dropped_reason": reason}, w, read_version=held.version)
        tx.update("question", qid, {"status": "dropped", "dropped_reason": reason}, w, read_version=question.version)
        learn.record(
            tx,
            store.plugins.cfg,
            {
                "kind": "held_declined",
                "refs": [changeset_id, held_id, into],
                "changeset": changeset_id,
                "run": cs.data.get("run"),
                "note": f"{into}: {target.data['text']}",
                "at": now.isoformat(),
            },
            WriteContext(actor="pm", trust="trusted", op="held_declined"),
            now,
        )
        records = [{"kind": "action", "id": held_id}, {"kind": "action", "id": into}, {"kind": "question", "id": qid}]
        done = OpOutcome(0, {"op": FOLD_OP, "id": held_id, "into": into}, "applied", "op0", records=records)
        tx.create(
            "changeset",
            {
                "request": request.id,
                "summary": summary,
                "ops": [asdict(done)],
                "status": "applied",
                "trust": "trusted",
                "reviewed": True,
                "created_at": store.clock(),
            },
            WriteContext("engine", "trusted", "changeset.record"),
            record_id=cs_id,
        )
    store.plugins.publish("changeset.applied", {"id": cs_id}, follows=cs_id)
    return cs_id


def _record_routed(
    tx: Tx, cfg: Config, now: datetime, changeset_id: str | None, question_id: str, person: str, name: str | None
) -> None:
    """Record that the person said who a name or an owner is, and queue what the assistant learns from it."""
    refs = [r for r in (changeset_id, question_id, person) if r]
    w = WriteContext(actor="pm", trust="trusted", op="routed")
    made = tx.get("changeset", changeset_id) if changeset_id else None
    data = {
        "kind": "routed",
        "refs": refs,
        "changeset": changeset_id,
        "run": made.data.get("run") if made is not None else None,
        "note": name,
        "at": now.isoformat(),
    }
    learn.record(tx, cfg, data, w, now)
    _keep_alias(tx, person, name, w)


def _keep_alias(tx: Tx, person_id: str, name: str | None, w: WriteContext) -> None:
    """A second spelling the person said is someone becomes an alias on that person, so one person's promises never
    split into two lists. Only a name of two or more words: a bare first name could later match the wrong person
    without anyone being asked."""
    spelled = " ".join((name or "").split())
    person = tx.get("person", person_id)
    if person is None or len(spelled.split()) < 2:
        return
    known = [person.data["full_name"], *person.data.get("aliases", [])]
    if spelled.casefold() in {n.casefold() for n in known}:
        return
    aliases = [*person.data.get("aliases", []), spelled]
    tx.update("person", person_id, {"aliases": aliases}, w, read_version=person.version)


def _question_name(store: Store, qid: str) -> str | None:
    q = store.read().get("question", qid)
    return (q.data.get("resolves") or {}).get("name") if q else None


def _substitute(op: OpModel, name: str, person: str) -> OpModel:
    if isinstance(op, ActionAddOp):
        return op.model_copy(update={"owners": [person if _same_name(o, name) else o for o in op.owners]})
    if isinstance(op, QuestionAddOp) and _same_name(op.to, name):
        return op.model_copy(update={"to": person})
    return op


# ---- undo ------------------------------------------------------------------------------------------------------------


@dataclass
class UndoReport:
    restored: list[int] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def undo(store: Store, changeset_id: str, indices: list[int] | None = None) -> UndoReport:
    """Undo applied ops of a changeset by group: all or nothing within a group, skipping a group with a conflict."""
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    wanted = [o for o in outcomes if o["status"] == "applied" and (indices is None or o["index"] in indices)]
    groups: dict[str, list[dict[str, Any]]] = {}
    for o in outcomes:
        if o["status"] == "applied":
            groups.setdefault(o["group"], []).append(o)
    # Newest first, so a later op that refers to what an earlier one made is undone before it.
    chosen = sorted({o["group"] for o in wanted}, key=lambda g: -max(o["index"] for o in groups[g]))
    report = UndoReport()
    entries = [e for e in store.read().ledger() if e["changeset"] == changeset_id]
    with store.transaction() as tx:
        for group in chosen:
            members = groups[group]
            idx = {o["index"] for o in members}
            mine = _with_answers(store, tx, [e for e in entries if _op_index(e["op"]) in idx])
            conflict = acts.undo_problem(tx, mine) or _conflict(tx, mine) or _breaks_rules(store, tx, mine)
            if conflict:
                report.skipped.append({"ops": sorted(idx), "reason": conflict})
                continue
            _revert(tx, mine, changeset_id)
            for o in members:
                o["status"] = "undone"
                report.restored.append(o["index"])
        remaining = [o for o in outcomes if o["status"] in ("applied", "held")]
        status = "undone" if not remaining else ("partly_undone" if report.restored else cs.data["status"])
        tx.update(
            "changeset",
            changeset_id,
            {"ops": outcomes, "status": status},
            WriteContext(actor="pm", trust="trusted", op="changeset.undo"),
            read_version=cs.version,
        )
    if report.restored:
        store.plugins.publish("changeset.undone", {"id": changeset_id, "ops": report.restored}, follows=changeset_id)
    return report


#: The person's answer to a routing question writes its choice onto the op's own record under this op name.
ANSWER_OPS = ("action.assign",)


def _with_answers(store: Store, tx: Tx, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What undoing an op reverts: its own ledger entries, without the routing question it waited on (the person's
    answer stands, and other ops may share the question), and with the person's answer written onto the op's own
    records (an owner picked), which belongs to the op and would otherwise read as a later change."""
    kept = []
    for e in entries:
        if e["kind"] == "question" and not e["op"].startswith(f"{FOLD_OP}#"):
            q = tx.get("question", e["record_id"], include_deleted=True)
            if q is not None and q.data.get("kind") == "routing" and not _unanswered_owner_question(q):
                continue
        kept.append(e)
    # Only an answer to the op's own question belongs to it: an owner picked for an action this op made. An answer
    # given for an action that existed before stays, whatever later op is undone.
    created = {(e["kind"], e["record_id"]) for e in kept if e["kind"] != "question" and e["version"] == 1}
    seen = {e["seq"] for e in kept}
    for kind, rid in sorted(created):
        for e in store.read().ledger(kind=kind, record_id=rid):
            if e["op"] in ANSWER_OPS and e["seq"] not in seen:
                kept.append(e)
    return kept


def _unanswered_owner_question(q: Any) -> bool:
    """Whether a "Pick an owner" question is still waiting: it belongs to the one action it asks about, so undoing
    the op that made that action takes the question away too."""
    return (q.data.get("resolves") or {}).get("kind") == "owner" and q.data.get("status") in ("open", "sent")


def _breaks_rules(store: Store, tx: Tx, entries: list[dict[str, Any]]) -> str | None:
    """Why undoing these entries would break a rule the records declare, or None: bringing back a record whose unique
    values another live record now has, or removing a record something else still refers to."""
    touched = {(e["kind"], e["record_id"]) for e in entries}
    for kind, rid in sorted(touched):
        current = tx.get(kind, rid, include_deleted=True)
        model = store.plugins.records.get(kind)
        if current is None or model is None:
            continue
        rows = [e for e in entries if (e["kind"], e["record_id"]) == (kind, rid)]
        if current.deleted and any(r["field"] is None and r["version"] == current.version for r in rows):
            for group in model.unique:
                equals = {f: current.data.get(f) for f in group}
                if [s for s in tx.find(kind, equals) if s.id != rid]:
                    shown = ", ".join(f"{f}={v}" for f, v in equals.items())
                    return f"another {kind} now has {shown}"
        elif not current.deleted and any(r["version"] == 1 for r in rows):
            users = [u for u in store.plugins._referrers(tx)(kind, rid) if u not in touched]
            if users:
                return f"{kind} {rid} is now referred to by {users[0][0]} {users[0][1]}"
    return None


def _op_index(op_name: str) -> int | None:
    _, _, idx = op_name.rpartition("#")
    return int(idx) if idx.isdigit() else None


def _conflict(tx: Tx, entries: list[dict[str, Any]]) -> str | None:
    """Why undoing these entries would overwrite a later change, or None. A field written again since counts only
    while it holds something other than what these entries set: a later change that was itself undone has left it as
    they left it."""
    by_record: dict[tuple[str, str], dict[str, Any]] = {}
    for e in entries:
        key = (e["kind"], e["record_id"])
        cur = by_record.setdefault(key, {"version": 0, "fields": set(), "set_to": {}})
        cur["version"] = max(cur["version"], e["version"])
        if e["field"]:
            cur["fields"].add(e["field"])
            cur["set_to"][e["field"]] = e["after"]
    for (kind, rid), info in by_record.items():
        current = tx.get(kind, rid, include_deleted=True)
        if current is None:
            continue
        if current.version > info["version"]:
            later = tx.sql(
                "SELECT field FROM ledger WHERE kind=? AND record_id=? AND version>? AND field IS NOT NULL",
                (kind, rid, info["version"]),
            ).fetchall()
            clash = {
                f for f in {r["field"] for r in later} & info["fields"] if current.data.get(f) != info["set_to"].get(f)
            }
            if clash or current.deleted:
                return f"{kind} {rid} changed since ({', '.join(sorted(clash)) or 'deleted'})"
    return None


def _revert(tx: Tx, entries: list[dict[str, Any]], changeset_id: str) -> None:
    w = WriteContext(actor="pm", trust="trusted", op="undo", changeset=changeset_id)
    by_record: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for e in entries:
        by_record.setdefault((e["kind"], e["record_id"]), []).append(e)
    for (kind, rid), rows in by_record.items():
        current = tx.get(kind, rid, include_deleted=True)
        if current is None:
            continue
        if current.deleted:
            # This changeset deleted it (its last row is the delete): bring it back under its own id.
            if any(r["field"] is None and r["version"] == current.version for r in rows):
                tx.undelete(kind, rid, w, read_version=current.version)
            continue
        created = any(r["version"] == 1 for r in rows)
        if created:
            tx.delete(kind, rid, w, read_version=current.version)
            continue
        before: dict[str, Any] = {}
        for r in sorted(rows, key=lambda r: r["seq"]):
            if r["field"] and r["field"] not in before:
                before[r["field"]] = r["before"]
        tx.update(kind, rid, before, w, read_version=current.version)


def move_stage(store: Store, op: StageMoveOp, *, actor: Literal["pm", "rule"] = "pm") -> str:
    """A person's explicit move or a deterministic rule's move, through the same op and ledger."""
    from engine.stages import apply_move

    with store.transaction() as tx:
        cs_id = tx.new_id("changeset")
        request = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "pm" if actor == "pm" else "schedule",
                "state": "done",
                "created_at": store.clock(),
                "changeset": cs_id,
            },
            WriteContext(actor, "trusted", "stage.request"),
        )
        source = {"rule": f"stages/{op.record.kind}/{op.to}"} if actor == "rule" else None
        w = WriteContext(actor, "trusted", "stage.move#0", cs_id, request.id, source)
        records = apply_move(store, tx, op, w)
        tx.create(
            "changeset",
            {
                "request": request.id,
                "ops": [asdict(OpOutcome(0, op.model_dump(mode="json"), "applied", "op0", records=records))],
                "status": "applied",
                "trust": "trusted",
                "reviewed": actor == "pm",
                "created_at": store.clock(),
            },
            WriteContext("engine", "trusted", "changeset.record"),
            record_id=cs_id,
        )
    store.plugins.publish("changeset.applied", {"id": cs_id}, follows=cs_id)
    return cs_id


def apply_as_person(
    store: Store,
    cfg: Config,
    ops: list[dict[str, Any]],
    summary: str,
    task: str = "notes",
    note: str = "",
    *,
    all_or_nothing: bool = False,
) -> str:
    """Apply ops the person made on screen (an edit, a review's choices) as theirs. Returns the changeset id. `note` is
    words the person wrote with the change, which an op may quote as its evidence. With `all_or_nothing`, one op the
    applier refuses leaves every op of the change unapplied."""
    from engine.names import People
    from engine.ops import CHANGESET

    changeset = CHANGESET.validate_python({"summary": summary, "ops": ops}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create(
            "request",
            {"task": task, "origin": "pm", "state": "done", "note": summary, "created_at": store.clock()},
            WriteContext("pm", "trusted", "screen.request"),
        )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request.id, None, "", note, "trusted"),
        confirmed_by_pm=True,
        actor="pm",
    )
    cs_id = apply_changeset(changeset, [], ctx, run=None, extra={"reviewed": True}, all_or_nothing=all_or_nothing)
    refused = [o for o in store.read().get("changeset", cs_id).data["ops"] if o["status"] == "refused"]
    if refused:
        raise StoreError(refused[0].get("reason") or "that couldn't be done")
    with store.transaction() as tx:
        current = tx.get("request", request.id)
        tx.update(
            "request",
            request.id,
            {"changeset": cs_id},
            WriteContext("engine", "trusted", "screen.request"),
            read_version=current.version,
        )
    return cs_id


def apply_for_publisher(store: Store, cfg: Config, op: dict[str, Any], summary: str) -> str:
    """Apply one state change of an outward act as the publisher's own (design 6.12): a changeset in the ledger like any
    other, whose op only the publisher may write. Returns the changeset id; raises StoreError when the op is refused,
    and the act is left as it was."""
    from engine.ops import CHANGESET

    changeset = CHANGESET.validate_python({"summary": summary, "ops": [op]}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create(
            "request",
            {"task": "notes", "origin": "schedule", "state": "done", "note": summary, "created_at": store.clock()},
            WriteContext("publisher", "trusted", "publisher.request"),
        )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(sorted(ACT_PUBLISHER_OPS)),
        Inputs(request.id, None, "", "", "trusted"),
        actor="publisher",
        via="publisher",
    )
    cs_id = apply_changeset(changeset, [], ctx, run=None, extra={"reviewed": False})
    outcome = store.read().get("changeset", cs_id).data["ops"][0]
    if outcome["status"] != "applied":
        raise StoreError(outcome.get("reason") or "that couldn't be done")
    with store.transaction() as tx:
        current = tx.get("request", request.id)
        tx.update(
            "request",
            request.id,
            {"changeset": cs_id},
            WriteContext("publisher", "trusted", "publisher.request"),
            read_version=current.version,
        )
    return cs_id


def apply_for_reminders(store: Store, cfg: Config, op: dict[str, Any], summary: str, *, standing: bool = False) -> str:
    """Apply one op of the engine's own reminders (design 6.12): drafting a reminder act, or approving one under the
    person's standing yes (`standing`). A changeset in the ledger like any other. The applier's checks decide whether it
    stands (`act-reminder` for a draft, `act-approval` for the approval): returns the changeset id, and raises
    StoreError when the op is refused or held, leaving everything as it was."""
    from engine.names import People
    from engine.ops import CHANGESET

    changeset = CHANGESET.validate_python({"summary": summary, "ops": [op]}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create(
            "request",
            {"task": "notes", "origin": "schedule", "state": "done", "note": summary, "created_at": store.clock()},
            WriteContext("reminders", "trusted", "reminders.request"),
        )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        ("act.draft", "act.approve", "reminder.entry"),
        Inputs(request.id, None, "", "", "trusted"),
        actor="reminders",
        via="standing_yes" if standing else "reminders",
    )
    cs_id = apply_changeset(changeset, [], ctx, run=None, extra={"reviewed": False})
    outcome = store.read().get("changeset", cs_id).data["ops"][0]
    if outcome["status"] != "applied":
        raise StoreError(outcome.get("reason") or "that couldn't be done")
    with store.transaction() as tx:
        current = tx.get("request", request.id)
        tx.update(
            "request",
            request.id,
            {"changeset": cs_id},
            WriteContext("reminders", "trusted", "reminders.request"),
            read_version=current.version,
        )
    return cs_id


# ---- the first-week lints: quotes, names, links, version numbers, summaries, things made --------------------------

#: Ops that make a draft, a write-up or a file the person can open. A plugin's own op may make one too.
MAKING_OPS = frozenset({"text.draft", "text.propose", "text.edit", "file.add", "report.draft"})
#: The kinds of record whose text and links count as ones the workspace holds.
LINK_KINDS = ("project", "source", "question", "fact", "note", "action", "event", "organization")


class _FirstWeek:
    """The lints on what a question or a draft says and on a project's summary, with what they compare against read
    once per check: the addresses the workspace holds and the names it knows."""

    def __init__(self, ctx: Context, view: Any):
        self.ctx = ctx
        self.view = view
        self._links: draft_checks.KnownLinks | None = None
        self._terms: list[str] | None = None
        self._people: list[list[str]] | None = None

    def known_links(self) -> draft_checks.KnownLinks:
        if self._links is None:
            known = draft_checks.KnownLinks()
            for text in (self.ctx.inputs.raw_input, self.ctx.inputs.note):
                known.add_text(text)
            for kind in LINK_KINDS:
                for record in self.view.list(kind):
                    known.add_values(record.data)
            for source in self.ctx.cfg.watch.sources:
                known.add_values(source.settings)
            known.add_text(self.ctx.cfg.server.public_url or "")
            self._links = known
        return self._links

    def known_terms(self) -> list[str]:
        """Names the workspace knows that aren't a person's: glossary terms, projects, organizations and teams."""
        if self._terms is None:
            terms = [str(e.data["term"]) for e in self.view.list("glossary_entry")]
            terms += [str(p.data["name"]) for p in self.view.list("project")]
            terms += [str(r.data["name"]) for kind in ("organization", "team") for r in self.view.list(kind)]
            self._terms = terms
        return self._terms

    def people(self) -> list[list[str]]:
        if self._people is None:
            self._people = [draft_checks.person_names(p.data) for p in self.view.list("person")]
        return self._people

    def problems(self, i: int, op: OpModel, lints: dict[str, Any]) -> list[Problem]:
        found: list[Problem] = []

        def add(name: str, message: str, passage: str | None = None, guidance: str | None = None) -> None:
            severity = lints.get(name, "off")
            if severity != "off":
                found.append(Problem(name, severity, i, message, passage, guidance))

        cfg = self.ctx.cfg
        summary = None
        if isinstance(op, ProjectAddOp):
            summary = op.summary
        elif isinstance(op, RecordSetOp) and op.kind == "project" and op.field == "summary":
            summary = op.value if isinstance(op.value, str) else None
        if summary:
            for reason in draft_checks.summary_problems(
                summary, cfg.workspace.project.summary_max_lines, cfg.language.findings_words
            ):
                add(
                    "summary-is-status",
                    f"A project's summary says where the project stands, and {reason}.",
                    guidance="Keep the summary to a few lines of status and record what was found as a fact.",
                )
        if isinstance(op, QuestionAddOp):
            texts, extra = [op.title, op.text], [link.url for link in op.links]
        elif isinstance(op, TextDraftOp):
            texts, extra = [op.text], []
        else:
            return found
        body = "\n".join(t for t in texts if t)
        inputs = self.ctx.inputs
        quotes = _quotes_in(op, self.ctx)
        # Quotation marks in long text are often the work itself (dialogue in a story), so only what the assistant asks
        # of someone is held to verbatim quotes.
        checked = body if isinstance(op, QuestionAddOp) else ""
        for passage in draft_checks.unverified_quotes(
            checked, [inputs.raw_input, inputs.note, *quotes], cfg.checks.tuning.unverified_quote.min_words
        ):
            add(
                "unverified-quote",
                "These words are in quotation marks but are not in the material you were given.",
                passage,
                "Quote the exact words, or say it is a paraphrase and leave the quotation marks off.",
            )
        for link in draft_checks.unknown_links(body, extra, self.known_links()):
            add(
                "unknown-link",
                f"{link} is not a link the input, a record or a configured source holds.",
                link,
                "Link only pages you were given; leave out any other.",
            )
        if _reaches_someone_else(op, self.ctx):
            shown = words_of(body, quotes)
            for number in draft_checks.version_numbers(shown, cfg.language.version_patterns, self.known_terms()):
                add(
                    "version-number",
                    f"{number} is a tool's version number, which doesn't belong in a message to someone else.",
                    number,
                    "Name the page, link it, and say what changed or when.",
                )
            for name in draft_checks.unverified_names(
                shown,
                self.people(),
                self.known_terms(),
                [inputs.raw_input, inputs.note],
                cfg.language.name_skip_words,
                cfg.language.messages.greeting,
            ):
                add(
                    "unverified-name",
                    f"{name} is not spelled as anyone on file or the input spells a name.",
                    name,
                    "Use a name as its person's record or the input has it; if you don't know it, ask instead.",
                )
        return found


def _made_problems(cs: ChangesetIn, ctx: Context, lints: dict[str, Any]) -> list[Problem]:
    """A change whose summary says it made a draft, a write-up or a file but holds nothing it made."""
    severity = lints.get("unlinked-made", "off")
    if severity == "off":
        return []
    phrase = draft_checks.says_it_made(cs.summary, ctx.cfg.language.made_phrases)
    if phrase is None or any(op.op in MAKING_OPS or "/" in op.op for op in cs.ops):
        return []
    return [
        Problem(
            "unlinked-made",
            severity,
            None,
            f"The summary says {phrase!r}, but nothing in this change is a draft, write-up or file it made.",
            guidance="Make it as part of this change so the person can open it, or leave it out of the summary.",
        )
    ]
