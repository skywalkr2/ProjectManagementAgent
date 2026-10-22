"""An action handed to the assistant (design 6.7, 7.5): the person asks for the work an action stands for (a message, a
list, a page) to be drafted.

Handing one over queues one request for the `action-work` kind, which goes the usual way: estimated, held for the
person's go above the configured amount, run on the account the work's tier names. The answer is prose, filed as a
pending draft of the action's `work` text; nothing else changes. The action's words, owners, day and status stay the
person's, and the draft is theirs only once they accept it. Whatever the person does with the draft (keep part of it,
set it aside) is a correction, recorded where the text ops are applied.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from engine.storage import StoreError, WriteContext
from engine.texts import current, read_text, versions

TASK = "action-work"
_QUEUE = WriteContext(actor="pm", trust="trusted", op="action.hand_over")
#: The request states in which the assistant still has the work, or the person has to act before it can go on.
IN_HAND = ("queued", "running", "needs_you")


def _requests(view: Any, action_id: str) -> list[Any]:
    return [
        r
        for r in view.list("request")
        if r.data["task"] == TASK and (r.data.get("about") or {}).get("id") == action_id and not r.data.get("dismissed")
    ]


def pending_draft(view: Any, action_id: str) -> Any | None:
    """The draft of the action's work that waits for the person's review, if there is one."""
    waiting = [v for v in versions(view, "action", action_id, "work") if v.data["status"] == "pending"]
    return waiting[-1] if waiting else None


def with_the_assistant(view: Any, action_id: str) -> bool:
    """Whether the assistant has this action's work in hand: a request not finished with, or a draft awaiting review."""
    for r in _requests(view, action_id):
        if r.data["state"] in IN_HAND or (r.data["state"] == "review" and pending_draft(view, action_id) is not None):
            return True
    return False


def hand_over(store: Any, action_id: str, note: str | None = None) -> str:
    """Queue the request for the work an open action stands for; returns its id. Nothing about the action changes."""
    words = " ".join((note or "").split())[:2000] or None
    with store.transaction() as tx:
        found = tx.get("action", action_id)
        if found is None:
            raise StoreError(f"there is no action {action_id}")
        if found.data["status"] != "open":
            raise StoreError("Only an open action can be handed to the assistant.")
        if with_the_assistant(tx, action_id):
            raise StoreError("The assistant already has this action's work in hand.")
        made = tx.create(
            "request",
            {
                "task": TASK,
                "about": {"kind": "action", "id": action_id},
                "note": words,
                "origin": "pm",
                "state": "queued",
                "waiting": "With the assistant, starting now",
                "created_at": store.clock(),
            },
            _QUEUE,
        )
    return made.id


@dataclass(frozen=True)
class Handed:
    """An action the assistant has in hand. `state`: working (queued or running), needs_go (held for the person's go,
    with the estimate when there is one) or draft (a draft waits for the person's review: `draft` is its version)."""

    action: str
    request: str
    state: str
    draft: str | None = None
    estimate_usd: float | None = None


def handed(view: Any) -> list[Handed]:
    """Every action the assistant has in hand, in the order they were handed over."""
    found = []
    for r in sorted(view.list("request"), key=lambda r: (str(r.data["created_at"]), r.id)):
        about = r.data.get("about") or {}
        if r.data["task"] != TASK or about.get("kind") != "action" or r.data.get("dismissed"):
            continue
        action = about["id"]
        draft = pending_draft(view, action)
        if r.data["state"] in ("queued", "running"):
            found.append(Handed(action, r.id, "working"))
        elif r.data["state"] == "needs_you" and r.data.get("approval") == "required":
            found.append(Handed(action, r.id, "needs_go", estimate_usd=r.data.get("estimate_usd")))
        elif r.data["state"] == "review" and draft is not None:
            found.append(Handed(action, r.id, "draft", draft=draft.id))
    return found


def _marked(text: str) -> str:
    """Text that can't close the marking it sits in."""
    return text.replace("</untrusted", "</ untrusted")


def _day(value: Any) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def describe(store: Any, cfg: Any, found: Any) -> str:
    """The action as the assistant is shown it: its words, day, project, who does it and is owed it, its notes and the
    words it came from. It is data, never instruction."""
    from engine.names import People

    view = store.read()
    people = People(store, cfg)
    d = found.data
    project = view.get("project", d["project"]) if d.get("project") else None
    lines = [f"Action {found.id}: {d['text']}"]
    if d.get("due"):
        lines.append(f"Due: {_day(d['due'])}")
    if project is not None:
        lines.append(f"Project: {project.data['name']}")
    owners = [people.name(o["person"]) for o in d.get("owners") or [] if o.get("person")]
    if owners:
        lines.append("Done by: " + ", ".join(owners))
    promised = [people.name(p) for p in d.get("promised_to") or []]
    if promised:
        lines.append("Promised to: " + ", ".join(promised))
    if d.get("notes"):
        lines.append(f"Notes: {d['notes']}")
    quote = (d.get("evidence") or {}).get("quote")
    if quote:
        lines.append(f'The words it came from: "{quote}"')
    return "\n".join(lines)


def build(ws: Any, store: Any, cfg: Any, req: Any, kind: Any, today: date) -> Any:
    """The packet for one run. Stable first: the instructions, the practice, what has been learned, the people and the
    projects. Then the request: the action as it is now (data, marked as from outside), the text kept so far when there
    is one, and the person's note."""
    from engine import areas
    from engine.cleaning import Cleaned
    from engine.dispatcher import _data_level
    from engine.names import People
    from engine.packet import DRAFT_RULE, Packet, PacketRefused, _guidance, _learned, _people, _projects, _task
    from engine.prompts import render

    about = req.data.get("about") or {}
    found = store.read().get("action", about.get("id")) if about.get("kind") == "action" else None
    if found is None:
        raise PacketRefused("the action this work was for is gone")
    if found.data["status"] != "open":
        raise PacketRefused("the action is no longer open")
    note = req.data.get("note") or ""
    shown = describe(store, cfg, found)
    kept = current(store.read(), "action", found.id, "work")
    kept_text = read_text(store, kept.data["sha256"]) if kept is not None else ""
    people = People(store, cfg)
    learned = _learned(
        store,
        cfg,
        kind,
        people,
        projects=[found.data["project"]] if found.data.get("project") else [],
        source=None,
        text=f"{shown}\n{note}",
        today=today,
    )
    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    stable = "\n\n".join(
        part
        for part in (
            "# Practice\n" + _guidance(kind),
            learned.stable,
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store, None, areas.reach(store.read(), [found.data.get("project")])),
        )
        if part.strip()
    )
    parts = [
        f"Today is {today.isoformat()} ({today.strftime('%A')}).",
        learned.per_input,
        f'# The action\n<untrusted source="records">\n{_marked(shown)}\n</untrusted>',
        f"# The text so far, which you revise\n<text>\n{kept_text.strip()}\n</text>" if kept_text.strip() else "",
        f"# The person's note\n<note>\n{note}\n</note>" if note else "",
        DRAFT_RULE,
    ]
    request = "\n\n".join(p for p in parts if p)
    task = replace(_task(cfg, store, kind, instructions, stable, request), knowledge=learned.log.model_dump())
    return Packet(
        task,
        request,
        Cleaned("", 0, 0, False, 0),
        note,
        too_long=False,
        untrusted_material=True,
        cites=f"action:{found.id}",
        about=("action", found.id),
        draft_base=kept.data["number"] if kept is not None else None,
        data_level=_data_level(store, req.data),
        knowledge=learned.log,
    )
