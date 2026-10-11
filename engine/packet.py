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
from engine.texts import text_presence
from engine.workspace import Workspace

DRAFT_RULE = (
    "Answer with the text only, in plain prose: no JSON, no heading before it, no notes about it, no code fence "
    "around it."
)


SPAN_RULE = (
    "This is part of a longer text: paragraphs p{first} to p{last}. Revise only these; account for each of them, and "
    "use only their ids."
)
ADD_RULE = "Write only the new part, which goes {place}. Don't repeat any of the text that is already there."

QUESTIONS_RULE = (
    "If something only the person can answer would change the text, end your answer with up to {n} short questions "
    'for them: a line <questions>, one question per line starting with "- ", then a line </questions>. Leave the '
    "block out when you have none."
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
    anchor_units: list | None = None  # for an anchored draft, the base text's units the ids number
    data_level: str | None = None  # the most sensitive level a part declares, when above the record's

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
    if kind.name == "ask":
        return _ask_packet(ws, store, cfg, req, kind, today)
    raw = source_text(ws, store, req.data.get("source"))
    known = _known_texts(ws, store, exclude=req.data.get("source"))
    cleaned = clean(raw, cfg.dispatch.cleaning, known)
    note = req.data.get("note") or ""

    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    from engine.dispatcher import _data_level, ops_for_level

    offered = ops_for_level(store, kind.ops, _data_level(store, req.data)) if kind.name == "notes" else kind.ops
    candidates = store.plugins.note_candidates(offered, req.data.get("project")) if kind.name == "notes" else ""
    stable = "\n\n".join(
        part
        for part in (
            "# Op reference\n" + reference_for(list(offered), store.plugins.ops),
            "# Records you may name\n" + candidates if candidates else "",
            "# Practice\n" + _guidance(kind),
            _value_lists(store),
            "# Open actions\n" + _open_actions(store, People(store, cfg)),
            "# Open questions\n" + _open_questions(store, People(store, cfg)),
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )
    request_parts = [f"Today is {today.isoformat()} ({today.strftime('%A')})."]
    about_project = store.read().get("project", req.data["project"]) if req.data.get("project") else None
    if about_project is not None:
        # The person said which project this is about; their choice, so it is trusted.
        request_parts.append(f"This is about the project {about_project.data['name']} ({about_project.id}).")
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
    if note and req.data["origin"] != "pm":
        # A note on scheduled work or an outside input wasn't written by the PM: data, not instructions.
        request_parts.append(f'<untrusted source="note">\n{note}\n</untrusted>')
    elif note:
        request_parts.append(f"<note>\n{note}\n</note>")
    if cleaned.text:
        src = req.data.get("source") or ""
        request_parts.append(f'<untrusted source="{src}">\n{cleaned.text}\n</untrusted>')
    request = "\n\n".join(request_parts)
    task = _task(cfg, store, kind, instructions, stable, request)
    return Packet(task, raw, cleaned, note, too_long=len(cleaned.text) > cfg.dispatch.max_input_chars)


def _ask_packet(ws: Workspace, store: Store, cfg: Config, req: Stored, kind: TaskKind, today: date) -> Packet:
    """An ask (design 6.25): the stable part holds the op reference, what this install can do, the settings and the
    records; the request holds the guide sections chosen for the question, then the question. All of the material
    may be quoted, and an answer's quotes must come from it."""
    from engine.help import capability_lines, chosen_sections, settings_lines

    question = req.data.get("note") or ""
    people = People(store, cfg)
    records = "\n\n".join(
        part
        for part in (
            "# Open actions\n" + _open_actions(store, people),
            "# Open questions\n" + _open_questions(store, people),
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )
    install = "\n".join(capability_lines(store))
    configured = "\n".join(settings_lines(cfg))
    from engine.help import guide_sections

    every = [*guide_sections(), *store.plugins.help_sections()]
    sections = "\n\n".join(f"## {s.title}\n{s.text}" for s in chosen_sections(question, sections=every))
    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    stable = "\n\n".join(
        (
            "# Op reference\n" + reference_for(list(kind.ops), store.plugins.ops),
            "# What this install can do\n" + install,
            "# Settings\n" + configured,
            records,
        )
    )
    request = "\n\n".join(
        (
            f"Today is {today.isoformat()} ({today.strftime('%A')}).",
            "# From the user guide\n" + sections,
            f"<question>\n{question}\n</question>",
        )
    )
    material = "\n\n".join((install, configured, records, sections))
    task = _task(cfg, store, kind, instructions, stable, request)
    return Packet(task, material, Cleaned("", 0, 0, False, 0), question, too_long=False, cites="help")


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


NO_COPY_RULE = (
    'Parts marked <material copy="no"> may be described and quoted as evidence, but never copy their words into new '
    "text you write."
)

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
    from engine.plugin_api import PacketContext, PacketParts

    plugin = kind.name.split("/", 1)[0]
    about = target_of(store, req.data)
    target = store.read().get(*about) if about else None
    if kind.on is not None and (target is None or target.kind != kind.on):
        raise PacketRefused(f"this work needs a {kind.on} to work on, and the one it was asked for is gone")
    started = req.data["origin"] == "pm" and not req.data.get("part")
    if target is not None:
        texts = text_presence(store, store.read(), target)
        if not (kind.startable_on(target, texts) if started else kind.offered_on(target, texts)):
            raise PacketRefused(f"this work isn't for this {kind.on} any more")
    note = req.data.get("note") or ""
    view = store.plugins._with_files(
        PacketContext(store.read(), plugin, req.data["origin"], request=req.id, part=req.data.get("part"))
    )
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
        NO_COPY_RULE if any(getattr(p, "no_copy", False) for p in every) else "",
        *(_render_part(p) for p in parts.stable),
    ]
    request_parts = [f"Today is {today.isoformat()} ({today.strftime('%A')})."]
    if note and req.data["origin"] != "pm":
        request_parts.append(f'<untrusted source="note">\n{note}\n</untrusted>')
    elif note:
        request_parts.append(f"<note>\n{note}\n</note>")
    request_parts += [_render_part(p) for p in parts.request]
    anchor_units = None
    part = req.data.get("part")
    if drafting:
        from engine.texts import current

        latest = current(store.read(), target.kind, target.id, kind.field)
        if part and part.get("base") is not None and (latest is None or latest.data["number"] != part["base"]):
            raise PacketRefused("The text changed since this part of it was chosen; choose the part again.")
    if drafting and kind.anchored:
        from engine.plugin_api import Part
        from engine.texts import ANCHOR_RULE, anchored_text, units_of

        base_text = view.text(target, kind.field)
        fmt = _field_format(store, target.kind, kind.field)
        anchor_units = units_of(store, fmt, base_text) if base_text else []
        first, last = (part["first"], part["last"]) if part else (1, len(anchor_units))
        if part and last > len(anchor_units):
            raise PacketRefused(
                f"The text has {len(anchor_units)} paragraphs, so paragraphs {first}–{last} aren't there."
            )
        request_parts.append(ANCHOR_RULE)
        if part:
            request_parts.append(SPAN_RULE.format(first=first, last=last))
        shown = anchored_text(base_text, anchor_units[first - 1 : last], first)
        request_parts.append(_render_part(Part("Text to revise", shown)))
    elif drafting and part:
        place = (
            "at the end of the text"
            if part["after"] == "end"
            else ("at the start of the text" if part["after"] == 0 else f"after paragraph {part['after']}")
        )
        request_parts.append(ADD_RULE.format(place=place))
    if drafting:
        request_parts.append(DRAFT_RULE)
    if drafting and kind.questions:
        request_parts.append(QUESTIONS_RULE.format(n=kind.questions))
    task = _task(
        cfg,
        store,
        kind,
        instructions,
        "\n\n".join(p for p in stable_parts if p.strip()),
        "\n\n".join(request_parts),
    )
    task = _sized(cfg, kind, task, parts)
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
        anchor_units=anchor_units,
        data_level=_highest([p.data_level for p in every if p.data_level]),
    )


def _sized(cfg: Config, kind: TaskKind, task: AiTask, parts: object) -> AiTask:
    """The run's output size from its packet's hints, where the workspace hasn't set one for the task kind."""
    from dataclasses import replace

    configured = cfg.ai.tasks.get(kind.name)
    chosen = configured.model_fields_set if configured is not None else set()
    hinted_max = getattr(parts, "max_output", None)
    hinted_typical = getattr(parts, "expected_output", None)
    for value, name in ((hinted_max, "max_output"), (hinted_typical, "expected_output")):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            raise PacketRefused(f"the packet's {name} must be a whole number of tokens")
    if hinted_max is not None and "max_output" not in chosen:
        task = replace(task, max_output=max(256, hinted_max))
    if hinted_typical is not None and "expected_output" not in chosen:
        task = replace(task, expected_output=hinted_typical)
    return task


def _highest(levels: list[str]) -> str | None:
    from engine.ai.router import LEVELS

    known = [level for level in levels if level in LEVELS]
    unknown = [level for level in levels if level not in LEVELS]
    if unknown:
        raise PacketRefused(f"a packet part names an unknown data level {unknown[0]}")
    return max(known, key=LEVELS.index) if known else None


def _field_format(store: Store, kind: str, field: str) -> str:
    from engine.texts import long_text_fields

    return long_text_fields(store.plugins.records[kind])[field]


def _render_part(part: object) -> str:
    title = " ".join(str(part.title).split()).replace('"', "'")
    if part.reference_only:
        return f'<reference quote="no" source="{title}">\n{part.text}\n</reference>'
    if getattr(part, "no_copy", False):
        return f'<material copy="no" source="{title}">\n{part.text}\n</material>'
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


def _value_lists(store: Store) -> str:
    """The values list-bound fields take, so the assistant proposes only values that will be accepted."""
    from engine.records import list_fields

    users: dict[str, list[str]] = {}
    for kind, model in store.plugins.records.items():
        for field, name, _ in list_fields(model):
            users.setdefault(name, []).append(f"{kind}.{field}")
    lines = []
    for r in sorted(store.read().list("value_list"), key=lambda r: r.data["name"]):
        if r.data["name"] in users:
            values = "; ".join(r.data["values"]) or "(none yet)"
            lines.append(f"- {', '.join(users[r.data['name']])}: {values}")
    if not lines:
        return ""
    return (
        "# Values these fields take\n"
        "Use one of these exactly. If none fits, leave the field as it is and say so in a note; the person adds "
        "values to a list.\n" + "\n".join(lines)
    )


def _projects(store: Store) -> str:
    lines = []
    for p in store.read().list("project"):
        d = p.data
        links = "; ".join(f"{link['label']}: {link['url']}" for link in d.get("links", []))
        lines.append(f"- {p.id} | {d['name']}" + (f" | links: {links}" if links else ""))
    return "\n".join(lines) or "(none)"
