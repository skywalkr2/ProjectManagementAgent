"""Building the packet for an AI task (design 6.6).

Stable parts come first, in a fixed order and with no dates or counts in them, so providers can reuse a cached
prefix: the instructions, the op reference, playbook guidance, the open actions and questions, the people and the
projects. The request part comes last: the date, the PM's note (trusted) and the cleaned input (untrusted).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from engine.ai.task import AiTask
from engine.cleaning import Cleaned, clean
from engine.config import Config
from engine.intake import source_text
from engine.names import People
from engine.ops import reference_for, schema_for
from engine.playbook import guidance
from engine.prompts import render
from engine.storage import Store
from engine.tasks import task_kind
from engine.workspace import Workspace


@dataclass(frozen=True)
class Packet:
    task: AiTask
    raw_input: str
    cleaned: Cleaned
    note: str
    too_long: bool


def build(ws: Workspace, store: Store, cfg: Config, request_id: str, today: date) -> Packet:
    req = store.read().get("request", request_id)
    if req is None:
        raise KeyError(request_id)
    kind = task_kind(req.data["task"])
    raw = source_text(ws, store, req.data.get("source"))
    known = _known_texts(ws, store, exclude=req.data.get("source"))
    cleaned = clean(raw, cfg.dispatch.cleaning, known)
    note = req.data.get("note") or ""

    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root)
    stable = "\n\n".join(
        part
        for part in (
            "# Op reference\n" + reference_for(list(kind.ops)),
            "# Practice\n" + guidance(kind.playbook),
            "# Open actions\n" + _open_actions(store, People(store, cfg)),
            "# Open questions\n" + _open_questions(store, People(store, cfg)),
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )
    request_parts = [f"Today is {today.isoformat()} ({today.strftime('%A')})."]
    if note:
        request_parts.append(f"<note>\n{note}\n</note>")
    if cleaned.text:
        src = req.data.get("source") or ""
        request_parts.append(f'<untrusted source="{src}">\n{cleaned.text}\n</untrusted>')
    request = "\n\n".join(request_parts)
    task_cfg = cfg.ai.tasks.get(kind.name)
    task = AiTask(
        kind=kind.name,
        instructions=instructions,
        stable=stable,
        request=request,
        output_schema=schema_for(list(kind.ops)),
        temperature=task_cfg.temperature if task_cfg else 0.0,
        max_output=task_cfg.max_output if task_cfg else 4000,
    )
    return Packet(task, raw, cleaned, note, too_long=len(cleaned.text) > cfg.dispatch.max_input_chars)


def _known_texts(ws: Workspace, store: Store, exclude: str | None) -> list[str]:
    return [source_text(ws, store, s.id) for s in store.read().list("source") if s.id != exclude]


def _open_actions(store: Store, people: People) -> str:
    lines = []
    for a in store.read().list("action"):
        d = a.data
        if d["status"] == "done":
            continue
        owners = ", ".join(people.name(o["person"]) for o in d.get("owners", [])) or "no owner yet"
        due = f"; due {d['due']}" if d.get("due") else ""
        project = f"[{d['project']}] " if d.get("project") else ""
        lines.append(f"- {a.id} {project}{d['text']} (owners: {owners}{due})")
    return "\n".join(lines) or "(none)"


def _open_questions(store: Store, people: People) -> str:
    lines = []
    for q in store.read().list("question"):
        d = q.data
        if d["status"] in ("answered", "dropped"):
            continue
        lines.append(f"- {q.id} to {people.name(d['to'])}: {d['title']}")
    return "\n".join(lines) or "(none)"


def _people(store: Store, cfg: Config) -> str:
    teams = {t.id: t.data["name"] for t in store.read().list("team")}
    lines = []
    pm = cfg.workspace.user.person
    for p in store.read().list("person"):
        d = p.data
        bits = [p.id, d["full_name"]]
        if d.get("aliases"):
            bits.append("aliases: " + ", ".join(d["aliases"]))
        if d.get("role"):
            bits.append(d["role"])
        if d.get("team") in teams:
            bits.append("team: " + teams[d["team"]])
        if d.get("org"):
            bits.append("org: " + d["org"])
        if p.id == pm:
            bits.append("this is the PM")
        lines.append("- " + " | ".join(bits))
    return "\n".join(lines) or "(none)"


def _projects(store: Store) -> str:
    lines = []
    for p in store.read().list("project"):
        d = p.data
        links = "; ".join(f"{link['label']}: {link['url']}" for link in d.get("links", []))
        lines.append(f"- {p.id} | {d['name']}" + (f" | links: {links}" if links else ""))
    return "\n".join(lines) or "(none)"
