"""The assistant's sorting of mail the rules can't place (design 6.5, step 3).

After the person's rules and the built-in sorting, mail that is still unplaced is sorted by one small run over a batch
of headers: for each message an opaque id, the sender, the subject line and the mail service's own categories, all
marked as outside content. The run never sees a message's text, its thread or its attachments. It answers work,
personal or sales for each id; an answer that is missing or isn't one of those words counts as work, so nothing is
hidden on a guess.

The run goes through the same estimate, configured amount, budgets and escalation rule as any other. When it can't
run (no account for its tier, a budget used up, the person's go not given, an account paused or failing), or its answer
fails the checks even on the stronger tier, the mail is handed in as work and the reason is returned for the person.
The run is made for no request, so its record carries none.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any

from engine.ai.task import AiError, AiTask
from engine.playbook import guidance
from engine.prompts import render
from engine.tasks import settings, task_kind

KIND = "sort-mail"
ANSWERS = ("work", "personal", "sales")
#: The rule name shown for mail the assistant sorted.
RULE = "The assistant's sorting"
#: How much of a sender, a subject or a category a run is shown.
HEADER_CHARS = 200
CATEGORY_CHARS = 40
MAX_CATEGORIES = 8
#: A line of the answer about one message takes about this many tokens.
OUTPUT_TOKENS_PER_MESSAGE = 14
#: What a failing answer is sent back with.
FIX = "Your previous answer had problems: {problems}. Answer again with only the JSON object."
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "answer": {"type": "string", "enum": list(ANSWERS)}},
                "required": ["id", "answer"],
            },
        }
    },
    "required": ["answers"],
}


@dataclass(frozen=True)
class Header:
    """What a sorting run sees of one message."""

    key: str
    sender: str
    subject: str
    categories: tuple[str, ...] = ()


@dataclass
class Sorted:
    """What sorting a read's unplaced mail came to: the messages the assistant set aside by key (to personal or
    sales), and, when some mail wasn't sorted by the assistant, why, in plain words."""

    sections: dict[str, str] = field(default_factory=dict)
    note: str | None = None


@dataclass
class _Try:
    answers: dict[str, str] | None = None  # id to answer, when the answer passed its checks
    why: str | None = None
    stop: bool = False  # the reason holds for every batch of this read, so none is tried


def _clip(text: Any, limit: int = HEADER_CHARS) -> str:
    return " ".join(str(text or "").split())[:limit]


def header_of(key: str, change: dict[str, Any]) -> Header:
    """The headers of a watched mail change, as its triage facts hold them."""
    message = change.get("message") or {}
    categories = tuple(_clip(c, CATEGORY_CHARS) for c in (message.get("categories") or [])[:MAX_CATEGORIES])
    return Header(key, _clip(message.get("sender") or change.get("author")), _clip(change.get("title")), categories)


def build_task(ws: Any, cfg: Any, headers: list[Header]) -> tuple[AiTask, dict[str, str]]:
    """The run for a batch of headers, and the opaque id each message goes by (id to key). Stable parts first, the
    batch last. Each message is one JSON line with its angle brackets escaped, so a subject can't close the block."""
    kind = task_kind(KIND)
    chosen = settings(cfg, kind)
    ids = {f"m{n}": header.key for n, header in enumerate(headers, 1)}
    lines = [
        json.dumps(
            {"id": name, "from": header.sender, "subject": header.subject, "categories": list(header.categories)},
            ensure_ascii=False,
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        for name, header in zip(ids, headers, strict=True)
    ]
    task = AiTask(
        kind=KIND,
        instructions=render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file),
        stable="# Practice\n" + guidance(kind.playbook),
        request='<untrusted source="mail headers">\n' + "\n".join(lines) + "\n</untrusted>",
        output_schema=SCHEMA,
        temperature=chosen.temperature,
        max_output=max(chosen.max_output, 2 * OUTPUT_TOKENS_PER_MESSAGE * len(headers)),
        expected_output=OUTPUT_TOKENS_PER_MESSAGE * len(headers) + 20,
    )
    return task, ids


def read_answers(text: str, ids: set[str], truncated: bool = False) -> tuple[dict[str, str], list[str]]:
    """The answer per message id from a run's text, and what is wrong with it. The check refuses an answer that can't
    be read, one that was cut off, an id that isn't in the batch and an id answered twice. A message left out, or
    answered with another word than work, personal or sales, is not a problem: it counts as work."""
    body = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", body, re.S)
    if fence:
        body = fence.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    if truncated:
        return {}, ["the answer was cut off; answer more briefly"]
    try:
        data = json.loads(body[start : end + 1]) if start != -1 and end > start else None
    except json.JSONDecodeError:
        data = None
    rows = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}, ['the answer is not a JSON object with an "answers" list']
    found: dict[str, str] = {}
    problems: list[str] = []
    for row in rows:
        name = row.get("id") if isinstance(row, dict) else None
        if not isinstance(name, str):
            problems.append("an entry has no id")
        elif name not in ids:
            problems.append(f"{name} is not one of the messages")
        elif name in found:
            problems.append(f"{name} is answered twice")
        else:
            word = str(row.get("answer", "")).strip().lower()
            found[name] = word if word in ANSWERS else "work"
    return found, problems[:5]


def sort(ws: Any, store: Any, cfg: Any, router: Any, headers: list[Header], level: str, go: bool = False) -> Sorted:
    """Sort these headers, one run per `watch.sorting_batch` of them, at the data level of their source. Returns the
    messages set aside and a note when any wasn't sorted by the assistant. `go`: the person has just given the first go,
    which covers the checks that wait for a go (the first go, an unpriced run, the amount to ask above)."""
    out = Sorted()
    if not headers:
        return out
    if router is None:
        from engine.ai.router import Router

        router = Router(cfg, store, env=os.environ)
    size = cfg.watch.sorting_batch
    unsorted = 0
    stopped = False
    why = None
    for start in range(0, len(headers), size):
        batch = headers[start : start + size]
        if stopped:
            unsorted += len(batch)
            continue
        tried = _sort_batch(ws, store, cfg, router, batch, level, go)
        if tried.answers is None:
            unsorted += len(batch)
            why, stopped = tried.why, tried.stop
            continue
        for name, answer in tried.answers.items():
            if answer != "work":
                out.sections[batch[int(name[1:]) - 1].key] = answer
    if unsorted:
        out.note = _note(unsorted, why)
    return out


def _note(count: int, why: str | None) -> str:
    these = "1 message wasn't" if count == 1 else f"{count} messages weren't"
    return f"{these} sorted by the assistant ({why}), so {'it was' if count == 1 else 'they were'} handed in as work."


def _sort_batch(ws: Any, store: Any, cfg: Any, router: Any, batch: list[Header], level: str, go: bool = False) -> _Try:
    from engine.ai.router import route
    from engine.dispatcher import has_account

    task, ids = build_task(ws, cfg, batch)
    tier = route(
        cfg,
        KIND,
        input_chars=task.size,
        quoted_messages=0,
        data_level=level,
        default=settings(cfg, task_kind(KIND)).tier,
    )
    budgets = cfg.ai.budgets
    estimate = router.estimate(task, tier=tier, data_level=level)
    if estimate is None and budgets.confirm_unpriced and not go:
        return _Try(why="its cost can't be estimated and your go wasn't given", stop=True)
    if estimate is not None and estimate > budgets.per_run_usd:
        return _Try(why=f"it would cost about ${estimate:.2f}, above the most one run may cost", stop=True)
    if (
        budgets.first_go
        and not go
        and (estimate is None or estimate > 0)
        and not store.read().has("run")
        and has_account(cfg, KIND, level, tier, None, frozenset(), None)
    ):
        return _Try(why="your first go in this workspace wasn't given yet", stop=True)
    if estimate is not None and estimate > budgets.confirm_above_usd and not go:
        return _Try(why=f"it would cost about ${estimate:.2f} and your go wasn't given", stop=True)
    first = _rounds(cfg, router, task, ids, tier, level)
    if first.answers is not None or first.stop:
        return first
    # The answer still fails its checks: one more run on the stronger tier, when its estimate is within the caps.
    from engine.ai.router import escalation_tier

    stronger = escalation_tier(cfg, tier)
    if not stronger or stronger == tier:
        return first
    second = router.estimate(task, tier=stronger, data_level=level)
    if second is not None and second > min(budgets.per_run_usd, budgets.confirm_above_usd):
        return first
    return _rounds(cfg, router, task, ids, stronger, level)


def _rounds(cfg: Any, router: Any, task: AiTask, ids: dict[str, str], tier: str, level: str) -> _Try:
    """Ask on one tier, sending a failing answer back up to `dispatch.fix_rounds` times with what was wrong."""
    from engine.ai.router import AccountPaused, BudgetReached, NoProvider
    from engine.dispatcher import failure_in_words

    current = task
    problems: list[str] = []
    for _ in range(cfg.dispatch.fix_rounds + 1):
        try:
            result, _choice, _run = router.call(current, request_id=None, tier=tier, data_level=level)
        except (AccountPaused, BudgetReached, NoProvider) as err:
            return _Try(why=str(err).rstrip("."), stop=True)
        except AiError as err:
            return _Try(why=failure_in_words(err), stop=True)
        if result.refused:
            return _Try(why="the AI account refused it", stop=True)
        answers, problems = read_answers(result.text, set(ids), result.truncated)
        if not problems:
            return _Try(answers=answers)
        current = replace(task, request=task.request + "\n\n" + FIX.format(problems="; ".join(problems)))
    return _Try(why="its answer didn't pass the checks: " + "; ".join(problems))
