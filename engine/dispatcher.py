"""Processing a request: build the packet, call the AI, read and check its answer, send problems back for a fix round,
then apply (design 6.6, 6.7). One input per call."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from pydantic import ValidationError

from engine.ai.router import BudgetReached, NoProvider, Router, escalation_tier, route
from engine.ai.task import AiError, AiTask, provider_reason
from engine.applier import Context, Inputs, apply_changeset, check, feedback, needs_another_round, undo
from engine.cleaning import quoted_messages
from engine.config import Config
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, ChangesetIn
from engine.packet import PacketRefused, build, target_of
from engine.projects import budget_problem
from engine.storage import Store, StoreError, WriteContext
from engine.tasks import settings as task_settings
from engine.workspace import Workspace

_ENGINE = WriteContext(actor="engine", trust="trusted", op="request.state")


class Unreadable(Exception):
    pass


def parse(text: str, op_models: dict | None = None) -> ChangesetIn:
    """Read a changeset from model output, repairing the usual damage first: fences, prose, trailing commas."""
    body = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", body, re.S)
    if fence:
        body = fence.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        raise Unreadable("the answer has no JSON object in it")
    body = re.sub(r",\s*([}\]])", r"\1", body[start : end + 1])
    try:
        data = json.loads(body)
    except json.JSONDecodeError as err:
        raise Unreadable(f"the JSON is broken ({err.msg} at character {err.pos})") from None
    models = op_models if op_models is not None else OP_MODELS
    if isinstance(data, dict):
        # Only the summary and the ops mean anything at the top; a model's extra remarks there are left out.
        data = {key: value for key, value in data.items() if key in ("summary", "ops")}
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
    return f"{where}: {error['msg']}"


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
    if req.data.get("approval") == "required":
        from engine.stages import wording

        return needs_you(store, request_id, wording(cfg, "waiting"))
    _set(store, request_id, state="running", waiting="With the assistant now", attempts=req.data["attempts"] + 1)

    try:
        packet = build(ws, store, cfg, request_id, now.date())
    except PacketRefused as err:
        return needs_you(store, request_id, str(err))
    if packet.too_long:
        return needs_you(
            store,
            request_id,
            (
                f"Too long for one call ({len(packet.cleaned.text):,} characters; the limit is "
                f"{cfg.dispatch.max_input_chars:,}). Split it, or raise dispatch.max_input_chars."
            ),
        )
    # Scheduled work (stage tasks, plugin requests) carries no words from the PM, so nothing in it is trusted.
    scheduled = req.data["origin"] == "schedule"
    trust = "untrusted" if req.data.get("source") or scheduled or packet.untrusted_material else "trusted"
    inputs = Inputs(request_id, req.data.get("source"), packet.raw_input, packet.note, trust, cites=packet.cites)
    ctx = Context(
        store, cfg, People(store, cfg), store.plugins.task_kind(req.data["task"]).ops, inputs, hidden_words(cfg)
    )

    previous_ops = _previous_ops(store, req.data.get("previous"))
    level = _data_level(store, req.data)
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
    estimate = router.estimate(packet.task, tier=tier, data_level=level, use=use, content=content)
    budgets = cfg.ai.budgets
    if estimate is not None and estimate > budgets.per_run_usd:
        return needs_you(
            store,
            request_id,
            f"This would cost about ${estimate:.2f}, above the per-run limit of ${budgets.per_run_usd:.2f}. "
            "Hand in less, or raise budgets.per_run_usd in ai.yaml.",
        )
    over = budget_problem(store, req.data, estimate)
    if over:
        return needs_you(store, request_id, over)
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
        draft = {"kind": packet.about[0], "id": packet.about[1], "field": kind.field, "base": packet.draft_base}
    first = _rounds(store, cfg, router, packet.task, tier, request_id, ctx, previous_ops, level, use, content, draft)
    outcome = first
    # The person's pick of account is theirs: no escalation away from it.
    stronger = escalation_tier(cfg, tier) if use is None else None
    second_estimate = (
        router.estimate(packet.task, tier=stronger, data_level=level, content=content)
        if first.escalate and stronger
        else None
    )
    within = second_estimate is None or second_estimate <= min(budgets.per_run_usd, budgets.confirm_above_usd)
    if first.escalate and stronger and stronger != tier and within:
        # One re-run on the stronger tier when checks still fail; it counts toward budgets like any run.
        second = _rounds(
            store, cfg, router, packet.task, stronger, request_id, ctx, previous_ops, level, None, content, draft
        )
        if second.changeset is not None or first.changeset is None:
            outcome = second if second.stop is None or first.changeset is None else first
    if outcome.changeset is None:
        return needs_you(store, request_id, outcome.stop or "The assistant couldn't finish this.")
    if outcome.stop is not None:
        return needs_you(store, request_id, outcome.stop)
    changeset, problems, run_id = outcome.changeset, outcome.problems, outcome.run_id
    assert changeset is not None
    cs_id = apply_changeset(changeset, problems, ctx, run=run_id, now=now)
    _set(store, request_id, state="review", waiting=None, changeset=cs_id)
    return cs_id


def _data_level(store: Store, request: dict) -> str:
    """How sensitive the material in a request is: work on a record (named, or whose stage entry started it) carries
    that record, at its record type's level."""
    about = target_of(store, request)
    model = store.plugins.records.get(about[0]) if about else None
    return model.data_level if model is not None else "internal"


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


@dataclass
class _Outcome:
    changeset: ChangesetIn | None = None
    problems: list = field(default_factory=list)
    run_id: str | None = None
    stop: str | None = None  # why the PM is needed instead of a changeset
    escalate: bool = False  # the answer still fails its checks: a stronger tier may do better


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
) -> _Outcome:
    """Ask on one tier, sending a failing answer back up to `dispatch.fix_rounds` times with what was wrong. A refusal
    stops at once: no fix round, no other account, no escalation."""
    task = base
    out = _Outcome()
    for attempt in range(cfg.dispatch.fix_rounds + 1):
        last = attempt == cfg.dispatch.fix_rounds
        try:
            result, _choice, out.run_id = router.call(
                task, request_id=request_id, tier=tier, data_level=data_level, use=use, content=content
            )
        except (BudgetReached, NoProvider) as err:
            return _Outcome(changeset=out.changeset, problems=out.problems, run_id=out.run_id, stop=str(err))
        except AiError as err:
            stop = _refused(store, None, err.detail) if err.kind == "refused" else _ai_failure(err)
            return _Outcome(changeset=out.changeset, problems=out.problems, run_id=out.run_id, stop=stop)
        if result.refused:
            return _Outcome(run_id=out.run_id, stop=_refused(store, out.run_id, result.refusal or ""))
        if draft is not None:
            text, stop = _drafted(router, task, result, request_id, tier, data_level, use, content)
            if stop:
                return _Outcome(run_id=out.run_id, stop=stop)
            changeset = _draft_changeset(draft, text, out.run_id)
            problems = check(changeset, ctx)
            out = _Outcome(changeset=changeset, problems=problems, run_id=out.run_id)
            if needs_another_round(problems):
                if not last:
                    task = replace(task, request=base.request + "\n\n" + feedback(problems))
                    continue
                out.escalate = True
            return out
        try:
            changeset = parse(result.text, store.plugins.ops)
        except Unreadable as err:
            limit = task.max_output
            if not last:
                why = (
                    f"Your previous answer was cut off at the output limit ({limit} tokens). Answer more briefly."
                    if result.truncated
                    else f"Your previous answer couldn't be read: {err}. Answer with only the JSON object."
                )
                task = replace(task, request=base.request + "\n\n" + why)
                continue
            if result.truncated:
                stop = (
                    f"The assistant's answer was cut off at the output limit ({limit} tokens for this kind of work). "
                    f"Raise tasks.{task.kind}.max_output in ai.yaml, or hand in a shorter piece."
                )
                return _Outcome(run_id=out.run_id, stop=stop)
            return _Outcome(run_id=out.run_id, stop=f"The assistant's answer couldn't be read: {err}.", escalate=True)
        if previous_ops is not None and _ops_of(changeset) == previous_ops:
            if not last:
                task = replace(task, request=base.request + "\n\n" + REPEATED)
                continue
            stop = "The assistant gave the same answer again after your note. Look at it with them."
            return _Outcome(run_id=out.run_id, stop=stop)
        problems = check(changeset, ctx)
        out = _Outcome(changeset=changeset, problems=problems, run_id=out.run_id)
        if needs_another_round(problems):
            if not last:
                task = replace(task, request=base.request + "\n\n" + feedback(problems))
                continue
            out.escalate = True
        return out
    return out


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
                more_task, request_id=request_id, tier=tier, data_level=data_level, use=use, content=content
            )
        except (AiError, BudgetReached, NoProvider) as err:
            return text, f"The draft was cut off at the output limit and couldn't be continued ({err})."
        if more.refused or more.truncated:
            return text, (
                f"The draft was cut off at the output limit twice. Raise tasks.{task.kind}.max_output in ai.yaml, "
                "or ask for less at a time."
            )
        text = text + _unfenced(more.text)
    return text, None


def _unfenced(text: str) -> str:
    match = re.fullmatch(r"\s*```[\w-]*\n(.*?)\n```\s*", text, re.S)
    return match.group(1) + "\n" if match else text


def _draft_changeset(draft: dict, text: str, run_id: str | None) -> ChangesetIn:
    op = {
        "op": "text.draft",
        "record": {"kind": draft["kind"], "id": draft["id"]},
        "field": draft["field"],
        "text": text,
        "base": draft["base"],
        "run": run_id,
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


def _ai_failure(err: AiError) -> str:
    plain = {
        "rate_limited": "The AI account is rate limited",
        "quota": "The AI account is out of credit",
        "auth": "The AI account refused the key",
        "no_key": "The AI account's key wasn't found",
        "timeout": "The AI account didn't answer in time",
        "provider_down": "The AI service is down",
    }.get(err.kind, "The AI call failed")
    when = f"; it can try again in {int(err.retry_after)} seconds" if err.retry_after else ""
    reason = provider_reason(err.detail)
    why = f" ({reason})" if reason else ""
    return f"{plain}{when}{why}. Check the account in ai.yaml, then try again."


def _set(store: Store, request_id: str, **changes: object) -> None:
    with store.transaction() as tx:
        cur = tx.get("request", request_id)
        tx.update("request", request_id, changes, _ENGINE, read_version=cur.version)


def needs_you(store: Store, request_id: str, why: str) -> None:
    _set(store, request_id, state="needs_you", waiting=why)
    return None


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
        changes: dict[str, object] = {"state": "queued", "waiting": "With the assistant, next in line"}
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


def signal(store: Store, kind: str, refs: list[str], note: str | None = None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    with store.transaction() as tx:
        return tx.create("signal", {"kind": kind, "refs": refs, "note": note, "at": now.isoformat()}, _PM).id


def undo_changeset(store: Store, changeset_id: str, indices: list[int] | None = None):
    report = undo(store, changeset_id, indices)
    if report.restored:
        signal(store, "undone", [changeset_id], note=f"ops {report.restored}")
    return report


def send_back(store: Store, changeset_id: str, note: str, now: datetime | None = None) -> str:
    """Undo the assistant's work and queue it again with the PM's note. Returns the new request id."""
    if not note.strip():
        raise ValueError("Say what the assistant should change.")
    now = now or datetime.now(UTC)
    cs = store.read().get("changeset", changeset_id)
    undo(store, changeset_id)
    signal(store, "sent_back", [changeset_id], note=note, now=now)
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
