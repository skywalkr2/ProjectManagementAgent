"""Building the packet for an AI task (design 6.6).

Stable parts come first, in a fixed order and with no dates or counts in them, so providers can reuse a cached
prefix: the instructions, the op reference, playbook guidance, the open actions and questions, the people and the
projects. The request part comes last: the date, the PM's note (trusted) and the cleaned input (untrusted).
"""

from __future__ import annotations

import json
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
from engine.storage import Store, Stored, StoreError
from engine.tasks import TaskKind, settings
from engine.workspace import Workspace

DRAFT_RULE = (
    "Answer with the text only, in plain prose: no JSON, no heading before it, no notes about it, no code fence "
    "around it."
)


@dataclass(frozen=True)
class Packet:
    task: AiTask
    raw_input: str  # what evidence may quote
    cleaned: Cleaned
    note: str
    too_long: bool
    untrusted_material: bool = False  # a plugin's packet carried content that isn't the person's own words
    cites: str | None = None  # what quotes from raw_input are cited as, when it isn't a saved source
    about: tuple[str, str] | None = None  # (kind, id) of the record the work is about
    draft_base: int | None = None  # for a draft, the number of the field's version it is made from

    @property
    def input_chars(self) -> int:
        return len(self.cleaned.text) if self.cleaned.text else len(self.raw_input)


class PacketRefused(Exception):
    """A plugin's packet couldn't be built; the message is for the person."""


def build(ws: Workspace, store: Store, cfg: Config, request_id: str, today: date) -> Packet:
    req = store.read().get("request", request_id)
    if req is None:
        raise KeyError(request_id)
    kind = store.plugins.task_kind(req.data["task"])
    if kind.packet is not None:
        return _plugin_packet(ws, store, cfg, req, kind, today)
    raw = source_text(ws, store, req.data.get("source"))
    known = _known_texts(ws, store, exclude=req.data.get("source"))
    cleaned = clean(raw, cfg.dispatch.cleaning, known)
    note = req.data.get("note") or ""

    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    stable = "\n\n".join(
        part
        for part in (
            "# Op reference\n" + reference_for(list(kind.ops), store.plugins.ops),
            "# Practice\n" + _guidance(kind),
            "# Open actions\n" + _open_actions(store, People(store, cfg)),
            "# Open questions\n" + _open_questions(store, People(store, cfg)),
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )
    request_parts = [f"Today is {today.isoformat()} ({today.strftime('%A')})."]
    if req.data.get("stage_start"):
        origin = req.data["stage_start"]
        record = store.read().get(origin["kind"], origin["record"])
        context = {
            "stage_start": origin,
            "record": record.data if record else None,
            "read_version": record.version if record else None,
        }
        # Record content is data, not new instructions, even after the person approves a task.
        request_parts.append("<untrusted>\n" + json.dumps(context, ensure_ascii=False) + "\n</untrusted>")
    if note and req.data["origin"] == "schedule":
        # A note on scheduled work was written by a plugin or a job, not the PM: data, not instructions.
        request_parts.append(f'<untrusted source="note">\n{note}\n</untrusted>')
    elif note:
        request_parts.append(f"<note>\n{note}\n</note>")
    if cleaned.text:
        src = req.data.get("source") or ""
        request_parts.append(f'<untrusted source="{src}">\n{cleaned.text}\n</untrusted>')
    request = "\n\n".join(request_parts)
    task = _task(cfg, store, kind, instructions, stable, request)
    return Packet(task, raw, cleaned, note, too_long=len(cleaned.text) > cfg.dispatch.max_input_chars)


def _task(cfg: Config, store: Store, kind: TaskKind, instructions: str, stable: str, request: str) -> AiTask:
    chosen = settings(cfg, kind)
    drafting = kind.output == "draft"
    return AiTask(
        kind=kind.name,
        instructions=instructions,
        stable=stable,
        request=request,
        output_schema={} if drafting else schema_for(list(kind.ops), store.plugins.ops),
        temperature=chosen.temperature,
        max_output=chosen.max_output,
        output="text" if drafting else "json",
    )


def _guidance(kind: TaskKind) -> str:
    if kind.guidance_file is not None:
        return kind.guidance_file.read_text(encoding="utf-8").strip()
    return guidance(kind.playbook)


REFERENCE_RULE = (
    'Parts marked <reference quote="no"> are there to inform the work. Never quote or reproduce their words in your '
    "answer, and never cite them as evidence."
)


def target_of(store: Store, request: dict) -> tuple[str, str] | None:
    """(kind, id) of the record a request is about: the one it names, or the one whose stage entry started it."""
    if request.get("about"):
        return request["about"]["kind"], request["about"]["id"]
    if request.get("stage_start"):
        return request["stage_start"]["kind"], request["stage_start"]["record"]
    return None


def _plugin_packet(ws: Workspace, store: Store, cfg: Config, req: Stored, kind: TaskKind, today: date) -> Packet:
    """A run of a plugin's task kind sees its instructions, the op reference, its guidance and the parts the plugin's
    packet function returns: stable parts first, this run's parts last. Content is marked by trust; reference-only
    parts are marked not to be quoted."""
    from engine.plugin_api import PacketParts, ReadView

    plugin = kind.name.split("/", 1)[0]
    about = target_of(store, req.data)
    target = store.read().get(*about) if about else None
    if kind.on is not None and (target is None or target.kind != kind.on):
        raise PacketRefused(f"this work needs a {kind.on} to work on, and the one it was asked for is gone")
    note = req.data.get("note") or ""
    view = store.plugins._with_files(ReadView(store.read(), plugin))
    config = store.plugins.registrars[plugin].config.model_copy(deep=True)
    try:
        parts = kind.packet(target, view, config, note)
    except StoreError as err:
        raise PacketRefused(str(err)) from None
    except Exception as err:
        store.plugins.disable(plugin, f"packet for {kind.name} failed: {err}")
        raise PacketRefused("the add-on this work belongs to failed, and was turned off") from None
    if not isinstance(parts, PacketParts):
        store.plugins.disable(plugin, f"packet for {kind.name} returned something other than PacketParts")
        raise PacketRefused("the add-on this work belongs to failed, and was turned off")
    every = [*parts.stable, *parts.request]
    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    drafting = kind.output == "draft"
    stable_parts = [
        "" if drafting else "# Op reference\n" + reference_for(list(kind.ops), store.plugins.ops),
        "# Practice\n" + _guidance(kind),
        f"Write in {view.language(target)}: its spelling, punctuation and date style." if target is not None else "",
        REFERENCE_RULE if any(p.reference_only for p in every) else "",
        *(_render_part(p) for p in parts.stable),
    ]
    request_parts = [f"Today is {today.isoformat()} ({today.strftime('%A')})."]
    if note and req.data["origin"] == "schedule":
        request_parts.append(f'<untrusted source="note">\n{note}\n</untrusted>')
    elif note:
        request_parts.append(f"<note>\n{note}\n</note>")
    request_parts += [_render_part(p) for p in parts.request]
    if drafting:
        request_parts.append(DRAFT_RULE)
    task = _task(
        cfg,
        store,
        kind,
        instructions,
        "\n\n".join(p for p in stable_parts if p.strip()),
        "\n\n".join(request_parts),
    )
    base = None
    if drafting:
        from engine.texts import current

        now = current(store.read(), target.kind, target.id, kind.field)
        base = now.data["number"] if now else None
    quotable = "\n\n".join(p.text for p in every if not p.reference_only)
    empty = Cleaned("", 0, 0, False, 0)
    return Packet(
        task,
        quotable,
        empty,
        note,
        too_long=False,
        untrusted_material=any(not p.trusted for p in every),
        cites=f"{target.kind}:{target.id}" if target is not None else kind.name,
        about=(target.kind, target.id) if target is not None else None,
        draft_base=base,
    )


def _render_part(part: object) -> str:
    title = " ".join(str(part.title).split()).replace('"', "'")
    if part.reference_only:
        return f'<reference quote="no" source="{title}">\n{part.text}\n</reference>'
    if not part.trusted:
        return f'<untrusted source="{title}">\n{part.text}\n</untrusted>'
    return f"# {title}\n{part.text}"


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
