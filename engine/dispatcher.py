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
from engine.packet import build
from engine.storage import Store, StoreError, WriteContext
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

    packet = build(ws, store, cfg, request_id, now.date())
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
    trust = "untrusted" if req.data.get("source") or req.data["origin"] == "schedule" else "trusted"
    inputs = Inputs(request_id, req.data.get("source"), packet.raw_input, packet.note, trust)
    ctx = Context(
        store, cfg, People(store, cfg), store.plugins.task_kind(req.data["task"]).ops, inputs, hidden_words(cfg)
    )

    previous_ops = _previous_ops(store, req.data.get("previous"))
    level = _data_level(store, req.data)
    tier = route(
        cfg,
        packet.task.kind,
        input_chars=len(packet.cleaned.text),
        quoted_messages=quoted_messages(packet.cleaned.text),
        data_level=level,
    )
    estimate = router.estimate(packet.task, tier=tier, data_level=level)
    budgets = cfg.ai.budgets
    if estimate is not None and estimate > budgets.per_run_usd:
        return needs_you(
            store,
            request_id,
            f"This would cost about ${estimate:.2f}, above the per-run limit of ${budgets.per_run_usd:.2f}. "
            "Hand in less, or raise budgets.per_run_usd in ai.yaml.",
        )
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
    first = _rounds(store, cfg, router, packet.task, tier, request_id, ctx, previous_ops, level)
    outcome = first
    stronger = escalation_tier(cfg, tier)
    second_estimate = (
        router.estimate(packet.task, tier=stronger, data_level=level) if first.escalate and stronger else None
    )
    within = second_estimate is None or second_estimate <= min(budgets.per_run_usd, budgets.confirm_above_usd)
    if first.escalate and stronger and stronger != tier and within:
        # One re-run on the stronger tier when checks still fail; it counts toward budgets like any run.
        second = _rounds(store, cfg, router, packet.task, stronger, request_id, ctx, previous_ops, level)
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
    """How sensitive the material in a request is: a stage task carries its record, at that record type's level."""
    origin = request.get("stage_start")
    model = store.plugins.records.get(origin["kind"]) if origin else None
    return model.data_level if model is not None else "internal"


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
) -> _Outcome:
    """Ask on one tier, sending a failing answer back up to `dispatch.fix_rounds` times with what was wrong."""
    task = base
    out = _Outcome()
    for attempt in range(cfg.dispatch.fix_rounds + 1):
        last = attempt == cfg.dispatch.fix_rounds
        try:
            result, _choice, out.run_id = router.call(task, request_id=request_id, tier=tier, data_level=data_level)
        except (BudgetReached, NoProvider) as err:
            return _Outcome(changeset=out.changeset, problems=out.problems, run_id=out.run_id, stop=str(err))
        except AiError as err:
            return _Outcome(changeset=out.changeset, problems=out.problems, run_id=out.run_id, stop=_ai_failure(err))
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


def retry(store: Store, request_id: str) -> None:
    """Queue a request that stopped (an AI account problem, an unreadable answer) to be processed again."""
    with store.transaction() as tx:
        cur = tx.get("request", request_id)
        if cur.data.get("approval") == "required":
            from engine.stages import wording

            raise ValueError(wording(store.plugins.cfg, "retry_blocked"))
        if cur.data["state"] not in ("needs_you", "failed"):
            raise ValueError("this isn't waiting on you")
        tx.update(
            "request",
            request_id,
            {"state": "queued", "waiting": "With the assistant, next in line"},
            _ENGINE,
            read_version=cur.version,
        )


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
