"""The learning round-trip of the account check (design 6.16, 6.22).

An account that stands in for another is a switch nobody chose in the moment, so the check gives it one tiny fixed
correction and expects one proposal back that the app would accept. A loop that learns only on the main account stops
learning silently on the day a fallback answers. One small call, for every account in a chain, command-line agents
included: the proposal is an answer like any other, never a file an agent writes anywhere.

The result says which part failed: reading the answer, what it proposed, or the app's own checks (when a store is
given).
"""

from __future__ import annotations

from typing import Any

from engine.ai.task import AiTask

#: The correction the account is given. Fixed, so a failure is the account's and never the input's.
CHECK_REQUEST = (
    "# The correction\n"
    "The person sent the assistant's work back with a note.\n"
    "<note>\nQuestions about a delivery date go to whoever owns the delivery, not to the head of the project.\n"
    "</note>\n\n"
    "# What the assistant did\n"
    "It asked the head of the project when a delivery would arrive."
)
#: What the check says when the account's answer is a proposal the app accepts.
PASSED = "Gave one proposal the app accepts"


def task(cfg: Any) -> AiTask:
    """The one call: the learning kind's own limits, a short instruction, and the one op it is asked for."""
    from engine.ops import reference_for, schema_for
    from engine.prompts import render
    from engine.tasks import TASKS, settings

    kind = TASKS["learn-correction"]
    try:
        chosen = settings(cfg, kind)
        temperature, limit = chosen.temperature, chosen.max_output
    except AttributeError:  # a trimmed config that carries only the accounts and tiers
        temperature, limit = 0.0, int(kind.defaults.get("max_output", 2000))
    return AiTask(
        kind=kind.name,
        instructions=render("learn-check", {}),
        stable="# Op reference\n" + reference_for(["lesson.add"]),
        request=CHECK_REQUEST,
        output_schema=schema_for(["lesson.add"]),
        temperature=temperature,
        max_output=limit,
    )


def problem(text: str, cfg: Any, store: Any = None) -> str | None:
    """Why an answer to the check fails, saying which part, or None when it passes. With a store, the proposal is also
    tried against the app's own checks, with nothing kept."""
    from engine.applier import Context, Inputs, refusals
    from engine.dispatcher import Unreadable, parse
    from engine.names import People
    from engine.ops import KNOWLEDGE_ADD_OPS
    from engine.tasks import LEARN_OPS

    try:
        answer = parse(text, store.plugins.ops if store is not None else None)
    except Unreadable as err:
        return f"Its answer couldn't be read as the form this work needs ({err})."
    if len(answer.ops) != 1:
        found = "none" if not answer.ops else str(len(answer.ops))
        return f"It was asked for one proposal and gave {found}."
    op = answer.ops[0]
    if op.op not in KNOWLEDGE_ADD_OPS:
        return "What it proposed isn't something to keep as learned."
    if store is None:
        return None
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        LEARN_OPS,
        Inputs("", None, CHECK_REQUEST, "", "untrusted", cites="check:learning"),
    )
    refused = refusals(answer, ctx).get(0)
    if refused is not None:
        return f"The app's own checks refused the proposal ({refused})."
    return None
