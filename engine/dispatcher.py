"""Processing a request: build the packet, call the AI, read and check its answer, send problems back for a fix round,
then apply (design 6.6, 6.7). One input per call."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import UTC, datetime

from pydantic import ValidationError

from engine.ai.router import BudgetReached, NoProvider, Router
from engine.ai.task import AiError, AiTask
from engine.applier import Context, Inputs, apply_changeset, check, feedback, needs_another_round, undo
from engine.config import Config
from engine.names import People
from engine.ops import CHANGESET, ChangesetIn
from engine.packet import build
from engine.storage import Store, WriteContext
from engine.tasks import task_kind
from engine.workspace import Workspace

_ENGINE = WriteContext(actor="engine", trust="trusted", op="request.state")


class Unreadable(Exception):
    pass


def parse(text: str) -> ChangesetIn:
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
    try:
        return CHANGESET.validate_python(data)
    except ValidationError as err:
        first = err.errors()[:5]
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in first)
        raise Unreadable(f"the JSON doesn't match the op reference ({detail})") from None


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
    trust = "untrusted" if req.data.get("source") else "trusted"
    inputs = Inputs(request_id, req.data.get("source"), packet.raw_input, packet.note, trust)
    ctx = Context(store, cfg, People(store, cfg), task_kind(req.data["task"]).ops, inputs, hidden_words(cfg))

    previous_ops = _previous_ops(store, req.data.get("previous"))
    task: AiTask = packet.task
    changeset: ChangesetIn | None = None
    problems = []
    run_id = None
    for attempt in range(cfg.dispatch.fix_rounds + 1):
        try:
            result, _choice, run_id = router.call(task, request_id=request_id)
        except (BudgetReached, NoProvider) as err:
            return needs_you(store, request_id, str(err))
        except AiError as err:
            return needs_you(store, request_id, _ai_failure(err))
        try:
            changeset = parse(result.text)
        except Unreadable as err:
            changeset = None
            if attempt < cfg.dispatch.fix_rounds:
                task = replace(
                    task,
                    request=packet.task.request
                    + "\n\n"
                    + (f"Your previous answer couldn't be read: {err}. Answer with only the JSON object."),
                )
                continue
            return needs_you(store, request_id, f"The assistant's answer couldn't be read: {err}.")
        if previous_ops is not None and _ops_of(changeset) == previous_ops:
            if attempt < cfg.dispatch.fix_rounds:
                task = replace(task, request=packet.task.request + "\n\n" + REPEATED)
                continue
            return needs_you(
                store, request_id, "The assistant gave the same answer again after your note. Look at it with them."
            )
        problems = check(changeset, ctx)
        if needs_another_round(problems) and attempt < cfg.dispatch.fix_rounds:
            task = replace(task, request=packet.task.request + "\n\n" + feedback(problems))
            continue
        break
    assert changeset is not None
    cs_id = apply_changeset(changeset, problems, ctx, run=run_id, now=now)
    _set(store, request_id, state="review", waiting=None, changeset=cs_id)
    return cs_id


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
    return f"{plain}{when}. Check the account in ai.yaml, then try again."


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
        if cur.data["state"] not in ("needs_you", "failed"):
            raise ValueError("this isn't waiting on you")
        tx.update(
            "request",
            request_id,
            {"state": "queued", "waiting": "With the assistant, next in line"},
            _ENGINE,
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
