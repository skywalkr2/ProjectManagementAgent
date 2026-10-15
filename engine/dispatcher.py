"""Processing a request: build the packet, call the AI, read and check its answer, send problems back for a fix round,
then apply (design 6.6, 6.7). One input per call."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from engine import learn, new_terms, quality
from engine import search as workspace_search
from engine.ai.pauses import when_text
from engine.ai.router import (
    LEVELS,
    AccountPaused,
    BudgetReached,
    Independence,
    NetworkOffline,
    NoProvider,
    Router,
    choices,
    escalation_tier,
    route,
)
from engine.ai.task import AiError, AiTask, provider_reason
from engine.applier import Context, Inputs, apply_changeset, check, feedback, needs_another_round, undo
from engine.cleaning import quoted_messages
from engine.config import Config
from engine.learning import offered_ops, request_learns
from engine.moments import localize_ops
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, ChangesetIn
from engine.packet import PacketRefused, build, target_of
from engine.projects import budget_problem
from engine.rule_use import record_applied, record_named
from engine.storage import Store, StoreError, WriteContext
from engine.storage.store import Stored, Tx
from engine.tasks import settings as task_settings
from engine.text_shape import error_problem
from engine.today import zone
from engine.workspace import Workspace

log = logging.getLogger(__name__)

_ENGINE = WriteContext(actor="engine", trust="trusted", op="request.state")


class Unreadable(Exception):
    pass


def _json_object(text: str) -> object:
    """The JSON in model output, repairing the usual damage first: fences, prose, trailing commas."""
    body = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", body, re.S)
    if fence:
        body = fence.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        raise Unreadable("the answer has no JSON object in it")
    body = re.sub(r",\s*([}\]])", r"\1", body[start : end + 1])
    try:
        return json.loads(body)
    except json.JSONDecodeError as err:
        raise Unreadable(f"the JSON is broken ({err.msg} at character {err.pos})") from None


def parse(text: str, op_models: dict | None = None) -> ChangesetIn:
    """Read a changeset from model output."""
    data = _json_object(text)
    models = op_models if op_models is not None else OP_MODELS
    if isinstance(data, dict):
        # Only the summary, the topic, the ops, the ask flag and the two lists of what it applied and what it lacked
        # mean anything at the top; a model's extra remarks are left out.
        data = {
            key: value for key, value in data.items() if key in ("summary", "topic", "ops", "ask", "applied", "missing")
        }
    _drop_unused_evidence(data, models)
    try:
        return CHANGESET.validate_python(data, context={"op_models": op_models} if op_models is not None else None)
    except ValidationError as err:
        first = err.errors()[:5]
        detail = "; ".join(_describe_error(e, data, models) for e in first)
        raise Unreadable(f"the JSON doesn't match the op reference ({detail})") from None


def _drop_unused_evidence(data: object, models: dict) -> None:
    """Models often attach evidence to every op. On an op that takes none it carries no claim, so it is left out."""
    ops = data.get("ops") if isinstance(data, dict) else None
    for op in ops if isinstance(ops, list) else []:
        model = models.get(op.get("op")) if isinstance(op, dict) else None
        if model is not None and "evidence" in op and "evidence" not in model.model_fields:
            del op["evidence"]


def _describe_error(error: dict, data: object, models: dict) -> str:
    """One validation error in words the assistant can act on: for an unknown field, name the fields the op takes."""
    where = ".".join(map(str, error["loc"]))
    if error["type"] == "extra_forbidden" and error["loc"] and error["loc"][0] == "ops":
        key = error["loc"][-1]
        ops = data.get("ops", []) if isinstance(data, dict) else []
        for index, op in enumerate(ops):
            model = models.get(op.get("op")) if isinstance(op, dict) else None
            if model is not None and key in op and key not in model.model_fields:
                fields = ", ".join(name for name in model.model_fields if name != "group")
                return f"op {index} ({op['op']}) has a field {key!r} it doesn't take; it takes: {fields}"
    return error_problem(error) or f"{where}: {error['msg'].removeprefix('Value error, ')}"


def hidden_words(cfg: Config) -> list[str]:
    words = list(cfg.language.never_shown)
    for provider in cfg.ai.providers.values():
        words += [m for m in provider.models.values() if m and m not in ("scripted", "default")]
    return words


def process(
    ws: Workspace, store: Store, cfg: Config, router: Router, request_id: str, *, now: datetime | None = None
) -> str | None:
    """Run one queued request through the assistant. Returns the changeset id, or None if it needs the PM."""
    now = now or datetime.now(UTC)
    req = store.read().get("request", request_id)
    if req is None:
        raise KeyError(request_id)
    if req.data.get("superseded_by") or req.data["state"] in ("done", "review"):
        return None  # a try is only run while its request is open: not applied, finished or replaced
    if learn.is_learning(req.data["task"]) and (why := learn.skip_reason(store, cfg, req.data)) is not None:
        learn.close(store, request_id, why)  # nothing to learn from any more: no packet, no estimate, no call
        return None
    if req.data.get("approval") == "required":
        from engine.stages import wording

        return needs_you(store, request_id, wording(cfg, "waiting"))
    if not person_is_set(store, cfg):
        # Nothing is estimated or asked before the person is named: the assistant's work needs someone to address.
        return needs_you(store, request_id, SAY_WHO_FIRST, cause={"kind": "no_person"})
    before = req.data.get("cause") or {}
    offline_since = before.get("since") if before.get("kind") == "offline" else None
    _set(
        store,
        request_id,
        state="running",
        waiting="With the assistant now",
        cause=None,
        attempts=req.data["attempts"] + 1,
    )

    try:
        # Today in the person's time zone, as the received date beside it is, so the two never disagree by a day.
        packet = build(ws, store, cfg, request_id, now.astimezone(zone(cfg)).date())
    except PacketRefused as err:
        return needs_you(store, request_id, str(err))
    if packet.too_long:
        return needs_you(
            store,
            request_id,
            (
                f"Too long for one call ({len(packet.cleaned.text):,} characters; the limit is "
                f"{cfg.dispatch.max_input_chars:,}). Split it, or raise the largest input in Settings, What comes in."
            ),
        )
    # Work the PM didn't start (stage tasks, plugin requests, outside inputs) carries no words from the PM, so nothing
    # in it is trusted.
    scheduled = req.data["origin"] != "pm"
    # An input is outside content unless its saved source is marked as the person's own words.
    saved = store.read().get("source", req.data["source"]) if req.data.get("source") else None
    outside = bool(req.data.get("source")) and (saved is None or saved.data["trust"] != "trusted")
    trust = "untrusted" if outside or scheduled or packet.untrusted_material else "trusted"
    inputs = Inputs(request_id, req.data.get("source"), packet.raw_input, packet.note, trust, cites=packet.cites)
    allowed = store.plugins.task_kind(req.data["task"]).ops
    learns = request_learns(store, req.data)
    if req.data["task"] == "notes":
        allowed = offered_ops(ops_for_level(store, allowed, _data_level(store, req.data)), learns)
    people = People.for_input(
        store,
        cfg,
        request_id,
        packet.raw_input if req.data.get("source") else "",
        learns=learns,
    )
    ctx = Context(store, cfg, people, allowed, inputs, hidden_words(cfg), searched=False)

    previous_ops = _previous_ops(store, req.data.get("previous"))
    level = _data_level(store, req.data)
    if packet.data_level and LEVELS.index(packet.data_level) > LEVELS.index(level):
        level = packet.data_level
    ctx.data_level = level
    tier = route(
        cfg,
        packet.task.kind,
        input_chars=packet.input_chars,
        quoted_messages=quoted_messages(packet.cleaned.text),
        data_level=level,
        default=task_settings(cfg, store.plugins.task_kind(req.data["task"])).tier,
    )
    use = req.data.get("use")
    content = content_levels(store, req.data)
    independent = independence(store, cfg, req.data)
    estimate = router.estimate(
        packet.task, tier=tier, data_level=level, use=use, content=content, independent=independent
    )
    budgets = cfg.ai.budgets
    if estimate is not None and estimate > budgets.per_run_usd:
        return needs_you(
            store,
            request_id,
            f"This would cost about ${estimate:.2f}, above the per-run limit of ${budgets.per_run_usd:.2f}. "
            "Hand in less, or raise “Most one run may cost” in Settings, AI spending.",
        )
    over = budget_problem(store, req.data, estimate)
    if over:
        return needs_you(store, request_id, over)
    unpriced = estimate is None and budgets.confirm_unpriced
    if unpriced and req.data.get("approval") != "granted":
        _set(store, request_id, state="needs_you", approval="required", waiting=UNPRICED_GO)
        return None
    if (
        budgets.first_go
        and req.data.get("approval") != "granted"
        and (estimate is None or estimate > 0)
        and not store.read().has("run")
        and has_account(cfg, packet.task.kind, level, tier, use, content, independent)
    ):
        # Nothing has run in this workspace yet: the first runs wait for one go that covers all of them. A request
        # no account can take isn't held for a go it couldn't use; the run says what is missing.
        held: dict[str, object] = {"state": "needs_you", "approval": "required", "waiting": FIRST_GO}
        if estimate is not None:
            held["estimate_usd"] = round(estimate, 4)
        _set(store, request_id, **held)
        return None
    if estimate is not None and estimate > budgets.confirm_above_usd and req.data.get("approval") != "granted":
        # Spending above the configured amount is the person's choice: wait for their go with the estimate shown.
        _set(
            store,
            request_id,
            state="needs_you",
            approval="required",
            estimate_usd=round(estimate, 4),
            waiting=f"About ${estimate:.2f}. Waiting for your go.",
        )
        return None
    kind = store.plugins.task_kind(req.data["task"])
    draft = None
    if kind.output == "draft" and packet.about is not None:
        draft = {
            "kind": packet.about[0],
            "id": packet.about[1],
            "field": kind.field,
            "base": packet.draft_base,
            "anchors": packet.anchor_units if kind.anchored else None,
            "questions": kind.questions,
            "part": req.data.get("part"),
        }
        if draft["part"]:
            from engine.texts import current, long_text_fields, read_text, units_of

            latest = current(store.read(), packet.about[0], packet.about[1], kind.field)
            base_text = read_text(store, latest.data["sha256"]) if latest else ""
            fmt = long_text_fields(store.plugins.records[packet.about[0]])[kind.field]
            draft["base_text"] = base_text
            draft["units"] = packet.anchor_units or (units_of(store, fmt, base_text) if base_text.strip() else [])
            draft["split"] = lambda text, fmt=fmt: units_of(store, fmt, text)
    waited = offline_since is not None  # already waiting for the network: a repeat miss adds no run record
    # What a follow-up call after a search may cost: the per-run limit, and the amount that needs the person's go unless
    # they gave it.
    spend_limit = budgets.per_run_usd
    if req.data.get("approval") != "granted":
        spend_limit = min(spend_limit, budgets.confirm_above_usd)
    first = _rounds(
        store,
        cfg,
        router,
        packet.task,
        tier,
        request_id,
        ctx,
        previous_ops,
        level,
        use,
        content,
        draft,
        independent,
        offline_known=waited,
        ws=ws,
        spend_limit=spend_limit,
    )
    if first.abandoned:
        return None
    outcome = first
    # The person's pick of account is theirs: no escalation away from it.
    stronger = escalation_tier(cfg, tier) if use is None else None
    second_estimate = (
        router.estimate(packet.task, tier=stronger, data_level=level, content=content, independent=independent)
        if first.escalate and stronger
        else None
    )
    within = second_estimate is None or second_estimate <= min(budgets.per_run_usd, budgets.confirm_above_usd)
    if first.escalate and stronger and stronger != tier and within and not _closed(store, request_id):
        # One re-run on the stronger tier when checks still fail; it counts toward budgets like any run.
        second = _rounds(
            store,
            cfg,
            router,
            packet.task,
            stronger,
            request_id,
            ctx,
            previous_ops,
            level,
            None,
            content,
            draft,
            independent,
            offline_known=waited,
            ws=ws,
            spend_limit=spend_limit,
        )
        if second.abandoned:
            return None
        if second.changeset is not None or first.changeset is None:
            outcome = second if second.stop is None or first.changeset is None else first
    if _closed(store, request_id):
        return None  # the request was closed or replaced while the assistant worked: nothing of this run is written
    if outcome.cause and outcome.cause.get("kind") == "offline":
        # The network is down: the request stays in line, no try is counted, and it is looked at again after a short
        # wait. Since when is kept from the first time it found no network.
        return wait_for_network(store, cfg, request_id, now, since=offline_since)
    if outcome.cause and outcome.cause.get("kind") == "paused":
        # Every account that could take it is waiting for a limit to reset: it stays in line and runs by itself then.
        _set(store, request_id, state="queued", waiting=outcome.stop, cause=outcome.cause)
        return None
    if outcome.changeset is None:
        return stop_or_retry(store, cfg, request_id, outcome, now)
    if outcome.stop is not None:
        return needs_you(store, request_id, outcome.stop, cause=outcome.cause)
    changeset, problems, run_id = outcome.changeset, outcome.problems, outcome.run_id
    assert changeset is not None
    ctx.searched = outcome.searched
    trust = ctx.inputs.trust  # material a search brought in from outside content makes the work untrusted
    own_note = req.data["task"] == "notes" and trust == "trusted" and not req.data.get("source")
    if own_note and changeset.ask and not changeset.ops:
        # The person's own note is a question to the assistant: the same request becomes an ask, answered from the
        # guide and the records (6.25). Pasted or outside material never does this.
        _set(store, request_id, task="ask", state="queued", waiting="With the assistant, starting now")
        return None
    changeset = changeset.model_copy(update={"ops": localize_ops(changeset.ops, cfg)})
    if learn.is_learning(kind.name):
        changeset = learn.link_signal(changeset, learn.signal_of(req.data) or "")
    extra = quality.claims(store, run_id, changeset.applied, changeset.missing)
    if outcome.fallback is not None and quality.first_run_on(store, run_id) == outcome.fallback:
        extra["first_on_account"] = outcome.fallback
    cs_id = apply_changeset(
        changeset,
        problems,
        ctx,
        run=run_id,
        now=now,
        extra=extra,
        all_or_nothing=getattr(kind, "all_or_nothing", False),
    )
    if run_id is not None:
        record_applied(store, run_id, cs_id)
    _set(store, request_id, state="review", waiting=None, changeset=cs_id)
    if learn.is_learning(kind.name):
        learn.finish(store, request_id, cs_id)
    if kind.name == "notes" and learns:
        new_terms.scan(store, cfg, request_id, f"{packet.raw_input}\n{packet.note}", now, trust=trust)
    if _applied_something(store, cs_id):
        retire_earlier_attempts(store, request_id)
    return cs_id


def person_is_set(store: Store, cfg: Config) -> bool:
    """Whether the workspace has a person it is for: one set in the settings whose record exists."""
    person = cfg.workspace.user.person
    return bool(person) and store.read().get("person", person) is not None


def has_account(
    cfg: Config,
    kind: str,
    level: str,
    tier: str,
    use: str | None,
    content: frozenset[str],
    independent: Independence | None,
) -> bool:
    """Whether some account is set up to take this work."""
    try:
        choices(cfg, kind, level, tier=tier, use=use, content=content, independent=independent)
    except NoProvider:
        return False
    return True


def _data_level(store: Store, request: dict) -> str:
    """How sensitive the material in a request is: work on a record (named, or whose stage entry started it) carries
    that record, at its record type's level, or the level kept on it when it is a file or a source; the person's choice
    on the request and the level kept on its source only raise it."""
    about = target_of(store, request)
    model = store.plugins.records.get(about[0]) if about else None
    level = model.data_level if model is not None else "internal"
    for said in (_target_level(store, about), request.get("sensitivity"), _source_level(store, request)):
        if said in LEVELS and LEVELS.index(said) > LEVELS.index(level):
            level = said
    return level


def _target_level(store: Store, about: tuple[str, str] | None) -> str | None:
    """The data level kept on the file or source a request is about, if that is what it is about."""
    if about is None or about[0] not in ("file", "source"):
        return None
    target = store.read().get(*about)
    return target.data.get("sensitivity") if target is not None else None


def _source_level(store: Store, request: dict) -> str | None:
    """The data level kept on the source a request is about, if it has one."""
    source = store.read().get("source", request["source"]) if request.get("source") else None
    return source.data.get("sensitivity") if source is not None else None


def ops_for_level(store: Store, ops: tuple[str, ...], level: str) -> tuple[str, ...]:
    """The ops a run at this data level may use: an op that writes a record type more sensitive than the run's
    material isn't offered, so a note handed in as internal never feeds restricted records."""
    allowed = []
    for name in ops:
        writes = getattr(store.plugins.ops.get(name), "writes", {}) or {}
        levels = [getattr(store.plugins.records.get(kind), "data_level", "internal") for kind in writes]
        if all(lv not in LEVELS or LEVELS.index(lv) <= LEVELS.index(level) for lv in levels):
            allowed.append(name)
    return tuple(allowed)


def content_levels(store: Store, request: dict) -> frozenset[str]:
    """The content levels a request's material carries: those the person set on the record it is about, and on that
    record's project (or the record itself when it is a project)."""
    about = target_of(store, request)
    record = store.read().get(*about) if about else None
    if record is None:
        return frozenset()
    found: set[str] = set()
    model = store.plugins.records.get(record.kind)
    if model is not None and model.content_levels_field:
        found |= set(record.data.get(model.content_levels_field) or [])
    project_id = record.data.get("project") if record.kind != "project" else None
    project = store.read().get("project", project_id) if isinstance(project_id, str) else None
    if project is not None:
        found |= set(project.data.get("content_levels") or [])
    return frozenset(found)


def independence(store: Store, cfg: Config, request: dict) -> Independence | None:
    """For a check, what it must be independent of: the accounts of the AI runs that wrote the record it is about (its
    accepted, merged and pending text versions, and changes AI runs applied to it, other checks aside), and whether the
    person accepts one of them. None for other work."""
    kind = store.plugins.task_kind(request["task"])
    if kind.role != "check":
        return None
    configured = cfg.ai.tasks.get(kind.name)
    same = configured.same_account if configured is not None and configured.same_account is not None else None
    if same is None:
        same = cfg.ai.roles.check.same_account
    about = target_of(store, request)
    if about is None:
        return Independence(frozenset(), same)
    view = store.read()
    runs: set[str] = set()
    for version in view.find("text_version", {"owner_kind": about[0], "owner_id": about[1]}):
        if version.data.get("run") and version.data["status"] != "discarded":
            runs.add(version.data["run"])
    target = {"kind": about[0], "id": about[1]}
    for changeset in view.list("changeset"):
        if changeset.data.get("run") and any(
            o["status"] == "applied" and target in o.get("records", []) for o in changeset.data["ops"]
        ):
            runs.add(changeset.data["run"])
    accounts = set()
    for run in (view.get("run", r) for r in runs):
        writer = store.plugins.tasks.get(run.data["task"]) if run is not None else None
        if run is not None and (writer is None or writer.role != "check"):
            accounts.add(run.data["provider"])
    return Independence(frozenset(accounts), same)


@dataclass
class _Outcome:
    changeset: ChangesetIn | None = None
    problems: list = field(default_factory=list)
    run_id: str | None = None
    stop: str | None = None  # why the PM is needed instead of a changeset
    cause: dict | None = None  # what the screen can offer to clear the stop, when it has a way to
    escalate: bool = False  # the answer still fails its checks: a stronger tier may do better
    abandoned: bool = False  # the request was closed or replaced before a follow-up call: nothing more is asked
    retry: str | None = None  # a run that gave no usable answer or failed: why, in a few words; it is tried again
    searched: bool = False  # the run asked to search the workspace before it answered
    fallback: str | None = None  # the account that answered, when it stands in a tier's fallback chain


def search_request(text: str) -> workspace_search.Query | None:
    """What an answer asks to search for, when it is a search request instead of ops: an object with a `search` and no
    ops. None for any other answer."""
    try:
        data = _json_object(text)
    except Unreadable:
        return None
    if not isinstance(data, dict) or "search" not in data or data.get("ops"):
        return None
    return workspace_search.query_from(data["search"])


def _call(
    store: Store,
    router: Router,
    task: AiTask,
    out: _Outcome,
    request_id: str,
    tier: str,
    data_level: str,
    use: str | None,
    content: frozenset[str],
    independent: Independence | None,
    offline_known: bool,
) -> object | None:
    """One call, recording its run id on `out`. Returns the result, or None when the call ended the work: `out` then
    holds why."""
    try:
        result, choice, out.run_id = router.call(
            task,
            request_id=request_id,
            tier=tier,
            data_level=data_level,
            use=use,
            content=content,
            independent=independent,
            offline_known=offline_known,
        )
    except AccountPaused as err:
        cause = {"kind": "paused", "account": err.account, "until": err.until.isoformat()}
        out.stop, out.cause = str(err), cause
    except NetworkOffline:
        # No account could be reached at all: the work waits for the network, which is no failure and no try.
        out.stop, out.cause = OFFLINE_WAITING, {"kind": "offline"}
    except (BudgetReached, NoProvider) as err:
        out.stop, out.cause = str(err), _data_level_cause(err)
    except AiError as err:
        out.stop = _refused(store, None, err.detail) if err.kind == "refused" else _ai_failure(err)
        out.retry = failure_in_words(err) if err.kind in RETRIED else None
    else:
        tier_account = router.cfg.ai.tiers[choice.tier].use if choice.tier in router.cfg.ai.tiers else ""
        out.fallback = (
            choice.provider if use is None and f"{choice.provider}/{choice.model_key}" != tier_account else None
        )
        return result
    return None


def _record_search(store: Store, run_id: str | None, query: workspace_search.Query, found: int) -> None:
    """Add a search to the knowledge log of the run that asked for it."""
    if run_id is None:
        return
    with store.transaction() as tx:
        run = tx.get("run", run_id)
        if run is None:
            return
        log_ = dict(run.data.get("knowledge") or {})
        searches = [*log_.get("searches", []), {"words": query.words, "kinds": list(query.kinds), "results": found}]
        tx.update("run", run_id, {"knowledge": {**log_, "searches": searches}}, _ENGINE, read_version=run.version)


def _record_refusals(store: Store, run_id: str | None, problems: list) -> None:
    """Add the checks that refused an answer to the knowledge log of the run that gave it, whether or not a fix round
    later repairs it."""
    names = {p.check for p in problems if p.severity == "refuse"}
    if run_id is None or not names:
        return
    with store.transaction() as tx:
        run = tx.get("run", run_id)
        if run is None:
            return
        log_ = dict(run.data.get("knowledge") or {})
        seen = sorted({*log_.get("refused_checks", []), *names})
        tx.update("run", run_id, {"knowledge": {**log_, "refused_checks": seen}}, _ENGINE, read_version=run.version)


def _rounds(
    store: Store,
    cfg: Config,
    router: Router,
    base: AiTask,
    tier: str,
    request_id: str,
    ctx: Context,
    previous_ops: list | None,
    data_level: str = "internal",
    use: str | None = None,
    content: frozenset[str] = frozenset(),
    draft: dict | None = None,
    independent: Independence | None = None,
    offline_known: bool = False,
    ws: Workspace | None = None,
    spend_limit: float | None = None,
) -> _Outcome:
    """Ask on one tier, sending a failing answer back up to `dispatch.fix_rounds` times with what was wrong. A refusal
    stops at once: no fix round, no other account, no escalation. An answer that asks to search the workspace is
    answered with the results and asked again, up to `dispatch.knowledge.search_rounds` times; a search is no failure
    and uses up no fix round, but each call is recorded and counted like any other."""
    task = base
    shown = base.request  # the request as every round of this task starts from it: with the search results so far
    out = _Outcome()
    searches = 0
    for attempt in range(cfg.dispatch.fix_rounds + 1):
        last = attempt == cfg.dispatch.fix_rounds
        if attempt and _closed(store, request_id):
            return _Outcome(run_id=out.run_id, abandoned=True)  # a fix round only runs while its cause stands
        result = _call(store, router, task, out, request_id, tier, data_level, use, content, independent, offline_known)
        if result is None:
            return _Outcome(
                changeset=out.changeset,
                problems=out.problems,
                run_id=out.run_id,
                stop=out.stop,
                cause=out.cause,
                retry=out.retry,
            )
        while draft is None and not result.refused and ws is not None:
            query = search_request(result.text)
            if query is None or searches >= cfg.dispatch.knowledge.search_rounds:
                break
            limits = cfg.dispatch.knowledge
            hits = workspace_search.search(
                ws,
                store,
                query,
                limit=limits.search_results,
                level=data_level,
                exclude_sources=[ctx.inputs.source] if ctx.inputs.source else (),
            )
            _record_search(store, out.run_id, query, len(hits))
            searches += 1
            if any(hit.untrusted for hit in hits):
                ctx.inputs.trust = "untrusted"  # what comes back from outside content keeps everything after it so
            shown = shown + "\n\n" + workspace_search.render(hits, query, searches, limits.search_rounds - searches)
            task = replace(task, request=shown)
            if spend_limit is not None:
                again = router.estimate(
                    task, tier=tier, data_level=data_level, use=use, content=content, independent=independent
                )
                if again is not None and again > spend_limit:
                    return _Outcome(
                        run_id=out.run_id,
                        stop=f"Searching first would make this cost about ${again:.2f}, above the amount you allowed. "
                        "Hand in less, or raise the amount in Settings, AI spending.",
                    )
            result = _call(
                store, router, task, out, request_id, tier, data_level, use, content, independent, offline_known
            )
            if result is None:
                return _Outcome(
                    changeset=out.changeset,
                    problems=out.problems,
                    run_id=out.run_id,
                    stop=out.stop,
                    cause=out.cause,
                    retry=out.retry,
                    searched=True,
                )
            if _closed(store, request_id):
                return _Outcome(run_id=out.run_id, abandoned=True)
        out.searched = searches > 0
        ctx.searched = out.searched
        if result.refused:
            return _Outcome(run_id=out.run_id, stop=_refused(store, out.run_id, result.refusal or ""))
        if draft is not None:
            text, stop = _drafted(router, task, result, request_id, tier, data_level, use, content, independent)
            if stop:
                return _Outcome(run_id=out.run_id, stop=stop, retry=stop.rstrip(".") if not text.strip() else None)
            from engine.texts import AnchorProblem, parse_anchored, splice_after, splice_span, split_questions

            mapping: list = []
            asked: list[str] = []
            try:
                if draft.get("questions"):
                    text, asked = split_questions(text, draft["questions"])
                part = draft.get("part")
                if draft.get("anchors") is not None and part:
                    start, end = part["first"], part["last"]
                    revised, span_map = parse_anchored(text, draft["anchors"][start - 1 : end], start)
                    text, mapping = splice_span(draft["base_text"], draft["units"], start, end, revised, span_map)
                elif draft.get("anchors") is not None:
                    text, mapping = parse_anchored(text, draft["anchors"])
                elif part:
                    added = len(draft["split"](text)) if text.strip() else 0
                    text, mapping = splice_after(draft["base_text"], draft["units"], part["after"], text, added)
            except AnchorProblem as err:
                if not last:
                    why = f"Your draft doesn't follow the format asked for: {err}. Write it all again."
                    task = replace(task, request=shown + "\n\n" + why)
                    continue
                return _Outcome(
                    run_id=out.run_id, stop=f"The draft didn't follow the format asked for: {err}.", escalate=True
                )
            changeset = _draft_changeset(draft, text, out.run_id, mapping, asked)
            problems = check(changeset, ctx)
            _record_refusals(store, out.run_id, problems)
            out = _Outcome(
                changeset=changeset,
                problems=problems,
                run_id=out.run_id,
                searched=searches > 0,
                fallback=out.fallback,
            )
            if needs_another_round(problems):
                if not last:
                    task = replace(task, request=shown + "\n\n" + feedback(problems))
                    continue
                out.escalate = True
            return out
        try:
            if search_request(result.text) is not None:
                raise Unreadable(
                    "it asks to search, and searching is over for this input. Answer now with the JSON object of ops"
                )
            changeset = parse(result.text, store.plugins.ops)
        except Unreadable as err:
            limit = task.max_output
            if not last:
                why = (
                    f"Your previous answer was cut off at the output limit ({limit} tokens). Answer more briefly."
                    if result.truncated
                    else f"Your previous answer couldn't be read: {err}. Answer with only the JSON object."
                )
                task = replace(task, request=shown + "\n\n" + why)
                continue
            if result.truncated:
                stop = (
                    f"The assistant's answer was cut off at the output limit ({limit} tokens for this kind of work). "
                    "Raise the output limit for this kind of work in the AI settings, or hand in a shorter piece."
                )
                log.warning("Output limit reached; it is set at ai.tasks.%s.max_output", task.kind)
                return _Outcome(run_id=out.run_id, stop=stop)
            log.warning("The assistant's answer couldn't be read after a second try: %s", err)
            return _Outcome(run_id=out.run_id, stop=UNREADABLE, escalate=True, retry=UNREADABLE_WHY)
        if previous_ops is not None and _ops_of(changeset) == previous_ops:
            if not last:
                task = replace(task, request=shown + "\n\n" + REPEATED)
                continue
            stop = "The assistant gave the same answer again after your note. Look at it with them."
            return _Outcome(run_id=out.run_id, stop=stop)
        problems = check(changeset, ctx)
        _record_refusals(store, out.run_id, problems)
        out = _Outcome(
            changeset=changeset, problems=problems, run_id=out.run_id, searched=searches > 0, fallback=out.fallback
        )
        if needs_another_round(problems):
            if not last:
                task = replace(task, request=shown + "\n\n" + feedback(problems))
                continue
            out.escalate = True
        return out
    return out


#: The failures of a run that are tried again by themselves: no usable answer, or the call itself failed. A limit, a
#: refused key and a refusal are not: they need the account or the person.
RETRIED = ("invalid_output", "no_output", "timeout", "provider_down", "other")
UNREADABLE_WHY = "The assistant's answer wasn't in the form this work needs"
#: What a request waits on when the assistant's answer wasn't in the form the work needs, even when asked again.
UNREADABLE = (
    "The assistant's answer wasn't in the form this work needs, even when asked again. Try again, or pick another "
    "account for this work."
)
#: What a request waits on while no AI account can be reached for want of a network connection.
OFFLINE_WAITING = "Waiting for the network"
#: What a run waits on while the workspace has no person set; the setup step that names them clears it.
SAY_WHO_FIRST = "Say who you are first"
UNPRICED_GO = "Its cost can't be estimated on this account. Waiting for your go."
#: What a run waits on until the person's first go in the workspace; Today gathers every such request into one line.
FIRST_GO = "Waiting for your first go."


def waits_on_first_go(request: dict) -> bool:
    """Whether a request's data says it waits for the person's first go."""
    return (
        request["state"] == "needs_you" and request.get("approval") == "required" and request.get("waiting") == FIRST_GO
    )


CONTINUE = (
    "Your answer was cut off at the output limit. Here is what you wrote so far:\n<so-far>\n{text}\n</so-far>\n"
    "Write only what comes next, starting exactly where it stops, with nothing before it."
)


def _drafted(
    router: Router,
    task: AiTask,
    result: object,
    request_id: str,
    tier: str,
    data_level: str,
    use: str | None,
    content: frozenset[str],
    independent: Independence | None = None,
) -> tuple[str, str | None]:
    """A draft's text from a prose answer: one surrounding code fence removed, and an answer cut off at the output
    limit continued once. Returns the text and, when it can't be finished, why the person is needed."""
    text = _unfenced(result.text)
    if not text.strip():
        return "", "The assistant's draft came back empty."
    if result.truncated:
        more_task = replace(task, request=task.request + "\n\n" + CONTINUE.format(text=text))
        try:
            more, _choice, _run = router.call(
                more_task,
                request_id=request_id,
                tier=tier,
                data_level=data_level,
                use=use,
                content=content,
                independent=independent,
            )
        except (AiError, BudgetReached, NoProvider) as err:
            return text, f"The draft was cut off at the output limit and couldn't be continued ({err})."
        if more.refused or more.truncated:
            return text, (
                "The draft was cut off at the output limit twice. Raise the output limit for this kind of work in "
                "the AI settings, or ask for less at a time."
            )
        text = text + _unfenced(more.text)
    return text, None


def _unfenced(text: str) -> str:
    match = re.fullmatch(r"\s*```[\w-]*\n(.*?)\n```\s*", text, re.S)
    return match.group(1) + "\n" if match else text


def _draft_changeset(
    draft: dict, text: str, run_id: str | None, mapping: list | None = None, questions: list[str] | None = None
) -> ChangesetIn:
    op = {
        "op": "text.draft",
        "record": {"kind": draft["kind"], "id": draft["id"]},
        "field": draft["field"],
        "text": text,
        "base": draft["base"],
        "run": run_id,
        "paragraph_map": mapping or [],
        "questions": questions or [],
    }
    return CHANGESET.validate_python({"summary": "A draft for your review.", "ops": [op]})


REPEATED = (
    "This answer is the same as the one the PM sent back. The PM's note in this request is an instruction: act on it. "
    "If the note shows the request was based on a misunderstanding, record what the PM said instead of repeating."
)


def _ops_of(changeset: ChangesetIn) -> str:
    return json.dumps([op.model_dump(mode="json", exclude_none=True) for op in changeset.ops], sort_keys=True)


def _previous_ops(store: Store, previous: str | None) -> str | None:
    """The ops of the answer the PM sent back, to refuse the same answer again."""
    old = store.read().get("request", previous) if previous else None
    cs = store.read().get("changeset", old.data["changeset"]) if old and old.data.get("changeset") else None
    if cs is None:
        return None
    return json.dumps([o["op"] for o in cs.data["ops"]], sort_keys=True)


REFUSED = "The AI account refused this under its own rules"


def _refused(store: Store, run_id: str | None, reason: str) -> str:
    """Why a refused request waits: the provider's reason and what the refused run cost, and what the person can do."""
    run = store.read().get("run", run_id) if run_id else None
    cost = run.data.get("cost_usd") if run else 0.0
    said = provider_reason(reason)
    why = f" ({said})" if said else ""
    spent = f" It cost ${cost:.2f}." if cost else ""
    return f"{REFUSED}{why}.{spent} Pick another account to try it, change the request, or set it aside."


_PLAIN_FAILURE = {
    "rate_limited": "The AI account is rate limited",
    "quota": "The AI account is out of credit",
    "auth": "The AI account refused the key",
    "no_key": "The AI account's key wasn't found",
    "timeout": "The AI account didn't answer in time",
    "provider_down": "The AI service is down",
    "offline": "There is no network connection to the AI account",
    "invalid_output": "The AI account's answer couldn't be read",
    "no_output": "The AI account finished without giving an answer",
}


def failure_in_words(err: AiError) -> str:
    """A failed call in a few plain words: what happened and the provider's own reason, if it gave one."""
    reason = provider_reason(err.detail)
    return _PLAIN_FAILURE.get(err.kind, "The AI call failed") + (f" ({reason})" if reason else "")


def _ai_failure(err: AiError) -> str:
    plain = _PLAIN_FAILURE.get(err.kind, "The AI call failed")
    when = f"; it can try again in {int(err.retry_after)} seconds" if err.retry_after else ""
    reason = provider_reason(err.detail)
    why = f" ({reason})" if reason else ""
    if err.hint:
        signed_out = "The AI account isn't signed in" if err.kind == "auth" else plain
        return f"{signed_out}{when}{why}. {err.hint.rstrip('.')}, then try again."
    return f"{plain}{when}{why}. Check the account on the AI accounts screen, then try again."


def _data_level_cause(err: Exception) -> dict | None:
    """When a stop is only that no account may see the material's level: that level and the accounts that would take
    it if allowed."""
    if isinstance(err, NoProvider) and err.level and err.blocked:
        return {"kind": "data_level", "level": err.level, "accounts": list(err.blocked)}
    return None


def _set(store: Store, request_id: str, **changes: object) -> None:
    with store.transaction() as tx:
        cur = tx.get("request", request_id)
        tx.update("request", request_id, changes, _ENGINE, read_version=cur.version)


def is_waiting_for_network(request: dict) -> bool:
    """Whether a request is queued only because no network connection could be made, with when it first found none."""
    cause = request.get("cause") or {}
    return (
        request.get("state") == "queued"
        and not request.get("dismissed")
        and cause.get("kind") == "offline"
        and bool(cause.get("since"))
    )


def _closed(store: Store, request_id: str) -> bool:
    """Whether a request no longer needs anything from the assistant: it was replaced by a later attempt, it applied
    and awaits review, or it is finished."""
    req = store.read().get("request", request_id)
    return req is None or bool(req.data.get("superseded_by")) or req.data["state"] in ("done", "review")


def _applied_something(store: Store, changeset_id: str) -> bool:
    cs = store.read().get("changeset", changeset_id)
    return cs is not None and any(o["status"] == "applied" for o in cs.data["ops"])


#: Why an item an earlier attempt proposed is no longer open.
SUPERSEDED = "A later try at the same request replaced this."


def earlier_attempts(store: Store, request_id: str) -> list[str]:
    """The requests this one redoes, nearest first: each names the one before it as `previous`."""
    reader = store.read()
    found: list[str] = []
    current = reader.get("request", request_id)
    while current is not None and current.data.get("previous") and current.data["previous"] not in found:
        found.append(current.data["previous"])
        current = reader.get("request", current.data["previous"])
    return found


def retire_earlier_attempts(store: Store, request_id: str) -> list[str]:
    """A request applied: the attempts before it (the requests it redoes, by `previous`) are retired. Each is done and
    names this request as its replacement, so its Today lines and stopped state close and a try queued for it never
    runs; the items it left waiting (held changes, the questions asked to place them, proposals and reports not yet
    reviewed) are closed. What the earlier attempts applied stays. Returns the requests retired."""
    earlier = earlier_attempts(store, request_id)
    if not earlier:
        return []
    ids = set(earlier)
    with store.transaction() as tx:
        for rid in earlier:
            cur = tx.get("request", rid)
            if cur is None:
                continue
            changes: dict[str, object] = {"superseded_by": request_id, "waiting": None, "cause": None}
            if cur.data["state"] != "done":
                changes["state"] = "done"
            tx.update("request", rid, changes, _ENGINE, read_version=cur.version)
        for cs in tx.list("changeset"):
            if cs.data["request"] in ids:
                _close_held(tx, cs)
        for kind, open_status in (("setting_proposal", "open"), ("report", "draft")):
            for record in tx.list(kind):
                if record.data["request"] in ids and record.data["status"] == open_status:
                    tx.update(kind, record.id, {"status": "dismissed"}, _ENGINE, read_version=record.version)
    return earlier


def _close_held(tx: Tx, cs: Stored) -> None:
    """Refuse the held items of a changeset, with why, and drop the open questions asked to place them."""
    ops = cs.data["ops"]
    held = [o for o in ops if o["status"] == "held"]
    if not held:
        return
    for outcome in held:
        outcome["status"], outcome["reason"] = "refused", SUPERSEDED
        qid = outcome.get("question")
        question = tx.get("question", qid) if qid else None
        if question is not None and question.data["status"] == "open" and question.data.get("kind") == "routing":
            tx.update("question", question.id, {"status": "dropped"}, _ENGINE, read_version=question.version)
    status = "applied" if any(o["status"] == "applied" for o in ops) else "rejected"
    tx.update("changeset", cs.id, {"ops": ops, "status": status}, _ENGINE, read_version=cs.version)


def wait_for_network(store: Store, cfg: Config, request_id: str, now: datetime, since: object = None) -> None:
    """Queue a request that found no network. It says why, since when and until when it is looked at again; `retries`
    is left as it was, so being offline never uses up the tries a failing service gets."""
    started = since if isinstance(since, str) else now.isoformat()
    at = now + timedelta(seconds=cfg.dispatch.offline_check_seconds)
    began = datetime.fromisoformat(started)
    _set(
        store,
        request_id,
        state="queued",
        waiting=(f"{OFFLINE_WAITING} since {when_text(cfg, began, now)}. Checking again at {when_text(cfg, at, now)}."),
        cause={"kind": "offline", "since": started, "until": at.isoformat()},
    )
    return None


def stop_or_retry(store: Store, cfg: Config, request_id: str, outcome: _Outcome, now: datetime) -> None:
    """A run that ended without a changeset. One that gave no usable answer, or failed in a way another try may
    clear, is queued again after a wait that doubles each time, up to `dispatch.retries`; after that, or for any
    other stop, the person is needed, with why. Nothing is retried in a loop: each try waits for its time."""
    tries = store.read().get("request", request_id).data.get("retries", 0)
    limit = cfg.dispatch.retries
    if outcome.retry and tries < limit:
        at = now + timedelta(seconds=cfg.dispatch.retry_wait_seconds * 2**tries)
        why = (
            f"{outcome.retry.rstrip('.')}. Trying again at {when_text(cfg, at, now)} (try {tries + 2} of {limit + 1})."
        )
        _set(
            store,
            request_id,
            state="queued",
            retries=tries + 1,
            waiting=why,
            cause={"kind": "retry", "until": at.isoformat()},
        )
        return None
    stop = outcome.stop or "The assistant couldn't finish this."
    if outcome.retry and limit:
        stop = f"Tried {tries + 1} times without a usable answer. {stop}"
    return needs_you(store, request_id, stop, cause=outcome.cause)


def needs_you(store: Store, request_id: str, why: str, cause: dict | None = None) -> None:
    """Stop a request for the person, with why in plain words and, when the screen can offer an action that clears it,
    the cause. A request that is closed or was replaced by a later attempt is not stopped again."""
    if _closed(store, request_id):
        return None
    _set(store, request_id, state="needs_you", waiting=why, cause=cause)
    return None


def grant_first_go(store: Store) -> int:
    """The person's first go: every request waiting on it is approved and queued. Returns how many were."""
    ctx = WriteContext(actor="pm", trust="trusted", op="request.first_go")
    started = 0
    with store.transaction() as tx:
        for req in tx.list("request"):
            if waits_on_first_go(req.data):
                tx.update(
                    "request",
                    req.id,
                    {"approval": "granted", "state": "queued", "waiting": None},
                    ctx,
                    read_version=req.version,
                )
                started += 1
    return started


def requeue_waiting_for_person(store: Store) -> int:
    """Queue again every request that waited for the workspace to have a person, now that one is set. Returns how
    many."""
    queued = 0
    with store.transaction() as tx:
        for req in tx.list("request"):
            cause = req.data.get("cause") or {}
            if req.data["state"] == "needs_you" and not req.data.get("dismissed") and cause.get("kind") == "no_person":
                tx.update(
                    "request",
                    req.id,
                    {"state": "queued", "waiting": "With the assistant, next in line", "cause": None},
                    _ENGINE,
                    read_version=req.version,
                )
                queued += 1
    return queued


def retry(store: Store, request_id: str, use: str | None = None) -> None:
    """Queue a request that stopped (an AI account problem, an unreadable answer, a refusal) to be processed again,
    optionally on an account the person picked (`use`, a "provider/model" from the AI settings)."""
    if use is not None:
        from engine.ai.router import accounts

        cfg = store.plugins.cfg
        req = store.read().get("request", request_id)
        if req is None or use not in accounts(cfg, _data_level(store, req.data), content_levels(store, req.data)):
            raise ValueError(f"{use} isn't an account set up for this kind of material")
    with store.transaction() as tx:
        cur = tx.get("request", request_id)
        if cur.data.get("approval") == "required":
            from engine.stages import wording

            raise ValueError(wording(store.plugins.cfg, "retry_blocked"))
        if cur.data["state"] not in ("needs_you", "failed"):
            raise ValueError("this isn't waiting on you")
        changes: dict[str, object] = {
            "state": "queued",
            "waiting": "With the assistant, next in line",
            "cause": None,
            "retries": 0,
        }
        if use is not None:
            changes["use"] = use
        tx.update("request", request_id, changes, _ENGINE, read_version=cur.version)


_PM_DISMISS = WriteContext(actor="pm", trust="trusted", op="request.dismiss")


def dismiss(store: Store, request_id: str, read_version: int) -> None:
    """Set aside a request that stopped or waits for a go on its cost, so it no longer needs attention.
    A stage task waiting for a go keeps its Go."""
    from engine.stages import wording

    with store.transaction() as tx:
        cur = tx.get("request", request_id)
        if cur is None:
            raise ValueError("this request doesn't exist")
        if cur.version != read_version:
            raise StoreError(wording(store.plugins.cfg, "request_changed"))
        if cur.data.get("stage_start") and cur.data.get("approval") == "required":
            raise ValueError("this can't be dismissed")
        if cur.data["state"] not in ("needs_you", "failed"):
            raise ValueError("this can't be dismissed")
        tx.update(
            "request",
            request_id,
            {"state": "done", "dismissed": True, "dismissed_from": cur.data["state"]},
            _PM_DISMISS,
            read_version=cur.version,
        )


def undismiss(store: Store, request_id: str, read_version: int) -> None:
    """Put a dismissed request back in the state it had."""
    from engine.stages import wording

    with store.transaction() as tx:
        cur = tx.get("request", request_id)
        if cur is None:
            raise ValueError("this request doesn't exist")
        if cur.version != read_version:
            raise StoreError(wording(store.plugins.cfg, "request_changed"))
        if not cur.data.get("dismissed"):
            raise ValueError("this wasn't dismissed")
        tx.update(
            "request",
            request_id,
            {"state": cur.data.get("dismissed_from") or "needs_you", "dismissed": False, "dismissed_from": None},
            _PM_DISMISS,
            read_version=cur.version,
        )


# ---- review ----------------------------------------------------------------------------------------------------------

_PM = WriteContext(actor="pm", trust="trusted", op="review")


def looks_good(store: Store, changeset_id: str) -> None:
    with store.transaction() as tx:
        cs = tx.get("changeset", changeset_id)
        tx.update("changeset", changeset_id, {"reviewed": True}, _PM, read_version=cs.version)
        req = tx.get("request", cs.data["request"])
        if req is not None:
            tx.update("request", req.id, {"state": "done", "waiting": None}, _PM, read_version=req.version)


def signal(
    store: Store,
    kind: str,
    refs: list[str],
    note: str | None = None,
    now: datetime | None = None,
    *,
    changeset: str | None = None,
    run: str | None = None,
) -> str:
    """Record a correction. `changeset` is the changeset it corrects, and `run` the AI run whose work that was; given
    a changeset, the run is the one that produced it. Both stay empty for a correction of something no run made."""
    now = now or datetime.now(UTC)
    with store.transaction() as tx:
        if changeset is not None and run is None:
            made = tx.get("changeset", changeset)
            run = made.data.get("run") if made is not None else None
        data = {"kind": kind, "refs": refs, "changeset": changeset, "run": run, "note": note, "at": now.isoformat()}
        record_named(tx, run, refs)  # a correction that names a rule counts it as applied on the run it corrects
        return learn.record(tx, store.plugins.cfg, data, _PM, now)  # and each one that teaches queues its learning


def undo_changeset(store: Store, changeset_id: str, indices: list[int] | None = None):
    report = undo(store, changeset_id, indices)
    corrected = [i for i in report.restored if _written_by_assistant(store, changeset_id, i)]
    if corrected:
        signal(store, "undone", [changeset_id], note=f"ops {corrected}", changeset=changeset_id)
    return report


def _written_by_assistant(store: Store, changeset_id: str, index: int) -> bool:
    """Whether the op's changes were made by the assistant or a plugin. An op the person released or ran themselves
    is their own decision, so undoing it is not a correction of the assistant's work."""
    actors = {
        e["actor"]
        for e in store.read().ledger()
        if e["changeset"] == changeset_id and e["op"].rpartition("#")[2] == str(index)
    }
    return not actors or bool(actors & {"assistant", "plugin"})


def send_back(
    store: Store, changeset_id: str, note: str, now: datetime | None = None, *, undo_first: bool = True
) -> str:
    """Queue the work again with the PM's note, first undoing what the assistant did unless the PM keeps it (then
    the old work counts as looked over, and the new run builds on it). Returns the new request id."""
    if not note.strip():
        raise ValueError("Say what the assistant should change.")
    now = now or datetime.now(UTC)
    cs = store.read().get("changeset", changeset_id)
    if undo_first:
        undo(store, changeset_id)
    else:
        with store.transaction() as tx:
            current = tx.get("changeset", changeset_id)
            tx.update("changeset", changeset_id, {"reviewed": True}, _PM, read_version=current.version)
    signal(store, "sent_back", [changeset_id], note=note, now=now, changeset=changeset_id)
    old = store.read().get("request", cs.data["request"])
    with store.transaction() as tx:
        r = tx.get("request", old.id)
        tx.update("request", old.id, {"state": "done", "waiting": None}, _PM, read_version=r.version)
        combined = "\n\n".join(x for x in (old.data.get("note"), f"Sent back by the PM: {note.strip()}") if x)
        return tx.create(
            "request",
            {
                "task": old.data["task"],
                "note": combined,
                "source": old.data.get("source"),
                "origin": "pm",
                "state": "queued",
                "waiting": "With the assistant, next in line",
                "created_at": now.isoformat(),
                "previous": old.id,
            },
            _PM,
        ).id
