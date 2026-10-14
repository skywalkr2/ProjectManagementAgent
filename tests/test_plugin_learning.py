"""A plugin's packets and the learning loop (design 6.22): the one call that gives a pack's packets the knowledge
section, and `learning: own` for a record type or a task kind. Names and ids come from the fixtures."""

import json
from datetime import UTC, date, datetime

import pytest
import yaml

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config import load_config
from engine.config.schema import KnowledgeSettings
from engine.dispatcher import process
from engine.knowledge_section import stable_section
from engine.learning import learns_on, request_learns
from engine.names import People
from engine.packet import PacketRefused, build
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 14)
PEOPLE = fixture_records(DEMO_B, "person")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
_TEST = WriteContext(actor="pm", trust="trusted", op="test.plugin-learning")

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import OpModel, PacketParts, Part, Record, RefTo, Settings

class Config(Settings):
    pass

class Chapter(Record):
    record_kind: ClassVar[str] = "p52/chapter"
    prefix: ClassVar[str] = "CHP"
    title: str
    text: str = ""
    project: Annotated[str | None, RefTo("project")] = None

class Cast(Record):
    record_kind: ClassVar[str] = "p52/cast"
    prefix: ClassVar[str] = "CST"
    learning: ClassVar[str] = "RECORD_LEARNING"
    name: str
    text: str = ""
    project: Annotated[str | None, RefTo("project")] = None

class Note(OpModel):
    op: Literal["p52/note"] = "p52/note"
    writes: ClassVar[dict] = {"p52/chapter": ("*",)}
    title: str

def note(op, writer, cfg):
    writer.create("p52/chapter", {"title": op.title})

def asks(target, view, settings, note):
    k = view.knowledge(target.data["text"])
    return PacketParts(
        stable=[Part("Style sheet", "Past tense.", trusted=True), k.stable],
        request=[k.per_input, Part("Chapter " + target.id, target.data["text"])],
    )

def silent(target, view, settings, note):
    return PacketParts(
        stable=[Part("Style sheet", "Past tense.", trusted=True)],
        request=[Part("Chapter " + target.id, target.data["text"])],
    )

def wrong(target, view, settings, note):
    k = view.knowledge(target.data["text"])
    return PacketParts(stable=[k.per_input], request=[k.stable])

def register(registrar):
    registrar.record_type(Chapter)
    registrar.record_type(Cast)
    registrar.op(Note, "data", note)
    for name, packet, extra in (
        ("p52/review", asks, {}),
        ("p52/silent", silent, {}),
        ("p52/misplaced", wrong, {}),
        ("p52/own-review", asks, {"learning": "KIND_LEARNING"}),
        ("p52/on-cast", asks, {"on": "p52/cast"}),
    ):
        registrar.task_kind(
            name,
            ops=("p52/note",),
            label=name,
            prompt="p52/review",
            playbook="p52/review",
            **{"on": "p52/chapter", **extra},
            packet=packet,
        )
"""

KINDS = ["p52/review", "p52/silent", "p52/misplaced", "p52/own-review", "p52/on-cast"]


def make_env(tmp_path, *, record_learning="own", kind_learning="own"):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p52"
    (plugin / "prompts").mkdir(parents=True)
    (plugin / "guidance").mkdir()
    (plugin / "prompts" / "review.md").write_text("You review one chapter for {{assistant_name}}'s writer.")
    (plugin / "guidance" / "review.md").write_text("Point to the exact passage for every finding.")
    manifest = {
        "name": "p52",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Plugin learning fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p52/chapter", "p52/cast"],
            "ops": ["p52/note"],
            "ai_task_kinds": KINDS,
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    code = FIXTURE.replace("RECORD_LEARNING", record_learning).replace("KIND_LEARNING", kind_learning)
    (plugin / "fixture.py").write_text(code)
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p52"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = make_env(tmp_path)
    assert store.plugins.active("p52"), store.plugins.status["p52"].reason
    yield ws, cfg, store
    store.close()
    set_responder(None)


def make(store, kind, data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def knowledge(store, kind, text, **fields) -> str:
    data = {"origin": "person", "trust": "trusted", "status": "active", "learned_at": NOW.isoformat(), **fields}
    data |= {"kept_by": PEOPLE[0]["id"], "kept_at": NOW.isoformat(), "text": text}
    return make(store, kind, data)


def rule(store, name, text, **scope) -> str:
    return make(
        store,
        "rule",
        {"name": name, "text": text, "applies_to": scope, "origin": "person", "status": "active", "check": None},
    )


def chapter(store, text="The ferry left at dawn.", project=PROJECT) -> str:
    return make(store, "p52/chapter", {"title": "The Crossing", "text": text, "project": project})


def start(store, task, record_id, kind="p52/chapter", **more) -> str:
    return make(
        store,
        "request",
        {
            "task": task,
            "about": {"kind": kind, "id": record_id},
            "origin": "pm",
            "state": "queued",
            "created_at": NOW.isoformat(),
            **more,
        },
    )


def packet_for(env, task, record_id):
    ws, cfg, store = env
    return build(ws, store, cfg, start(store, task, record_id), TODAY)


def test_a_packet_that_asks_gets_the_stable_and_per_input_knowledge_and_its_run_logs_it(env):
    ws, cfg, store = env
    wide = rule(store, "wide-rule", "Never open a chapter with weather.")
    aimed = knowledge(store, "lesson", "Keep the narrator close.", applies_to={"task_kinds": ["p52/review"]})
    for_project = knowledge(
        store, "lesson", "This book runs long.", applies_to={"scope": "projects", "projects": [PROJECT]}
    )
    known = make(store, "fact", {"text": "The ferry runs on weekdays.", "project": PROJECT, "as_of": "2026-09-01"})
    record = chapter(store)

    packet = packet_for(env, "p52/review", record)

    stable, request = packet.task.stable, packet.task.request
    assert "Never open a chapter with weather." in stable and "Keep the narrator close." in stable
    assert stable.index("Past tense.") < stable.index("# Standing rules")  # the plugin places it; stable parts first
    assert "This book runs long." in request and "The ferry runs on weekdays." in request
    assert "This book runs long." not in stable
    assert request.index("# Lessons for this input") < request.index("The ferry left at dawn.")
    assert "Never open a chapter" not in packet.raw_input and "The ferry runs" not in packet.raw_input  # not evidence
    assert packet.knowledge.given == [wide, aimed, for_project, known]
    assert packet.knowledge.stable_chars == len(stable_section(store.read(), "p52/review", KnowledgeSettings()).text)
    assert packet.task.knowledge == packet.knowledge.model_dump()

    set_responder(lambda task: json.dumps({"summary": "Nothing to do.", "ops": []}))
    request_id = start(store, "p52/review", record)
    process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)
    runs = store.read().list("run")
    assert runs and runs[0].data["knowledge"]["given"] == packet.knowledge.given
    assert runs[0].data["knowledge"]["stable_chars"] == packet.knowledge.stable_chars


def test_a_packet_that_doesnt_ask_is_unchanged(env):
    _, _, store = env
    rule(store, "wide-rule", "Never open a chapter with weather.")
    packet = packet_for(env, "p52/silent", chapter(store))
    assert "Never open a chapter with weather." not in packet.task.stable + packet.task.request
    assert packet.knowledge is None and packet.task.knowledge is None


def test_a_lesson_aimed_at_a_plugin_task_kind_reaches_it_and_not_a_core_run(env):
    _, _, store = env
    aimed = knowledge(store, "lesson", "Keep the narrator close.", applies_to={"task_kinds": ["p52/review"]})
    chapter_id = chapter(store)
    assert aimed in packet_for(env, "p52/review", chapter_id).knowledge.given
    assert "Keep the narrator close." not in packet_for(env, "p52/silent", chapter_id).task.stable
    assert aimed not in stable_section(store.read(), "notes", KnowledgeSettings()).ids


def test_a_rule_whose_scope_excludes_the_records_project_leaves_the_packet_and_is_logged(env):
    _, _, store = env
    excluded = rule(store, "not-for-this", "Chase on Fridays.", **{"except": [PROJECT]})
    elsewhere = make(store, "project", {"name": "Another project"})
    only_other = rule(store, "other-only", "Only for the other book.", scope="projects", projects=[elsewhere])
    packet = packet_for(env, "p52/review", chapter(store))
    assert "Chase on Fridays." not in packet.task.stable + packet.task.request
    assert "Only for the other book." not in packet.task.stable + packet.task.request
    assert set(packet.knowledge.left_out_by_scope) >= {excluded, only_other}
    assert excluded not in packet.knowledge.given and only_other not in packet.knowledge.given


def test_a_knowledge_part_in_the_wrong_list_turns_the_plugin_off(env):
    _, _, store = env
    with pytest.raises(PacketRefused):
        packet_for(env, "p52/misplaced", chapter(store))
    assert not store.plugins.active("p52")


def test_learning_own_work_gets_no_facts_and_no_people_matched(env):
    _, _, store = env
    person = PEOPLE[0]
    about_person = knowledge(
        store, "lesson", "Ask before naming them.", applies_to={"people": [person["id"]], "scope": "workspace"}
    )
    fact = make(store, "fact", {"text": "The ferry runs on weekdays.", "project": PROJECT, "as_of": "2026-09-01"})
    kept = knowledge(
        store, "lesson", "Keep the narrator close.", applies_to={"scope": "projects", "projects": [PROJECT]}
    )
    record = chapter(store, text=f"{person['full_name']} watched the ferry leave.")

    core = packet_for(env, "p52/review", record).knowledge.given
    own = packet_for(env, "p52/own-review", record).knowledge.given
    assert fact in core and about_person in core
    assert fact not in own and about_person not in own
    assert kept in own  # the person's lessons and rules still reach a pack that learns on its own


def test_learns_on_says_which_work_the_cores_learning_runs_on(env):
    _, _, store = env
    plugins = store.plugins
    assert learns_on(plugins, task_kind="notes") and learns_on(plugins, task_kind="p52/review")
    assert not learns_on(plugins, task_kind="p52/own-review")
    assert not learns_on(plugins, record_type="p52/cast") and learns_on(plugins, record_type="p52/chapter")
    assert not learns_on(plugins, task_kind="p52/on-cast")  # works on a record type that learns on its own
    assert learns_on(plugins, task_kind="notes", record_type="p52/chapter")
    assert not learns_on(plugins, task_kind="notes", record_type="p52/cast")
    assert learns_on(plugins, task_kind="no-such-kind", record_type="no/such-type")
    about = {"kind": "p52/cast", "id": "CST-1"}
    assert not request_learns(store, {"task": "notes", "about": about})
    assert not request_learns(store, {"task": "notes", "stage_start": {"kind": "p52/cast", "record": "CST-1"}})
    assert request_learns(store, {"task": "notes"})


def test_first_names_resolve_only_for_work_the_core_learns_on(env):
    _, cfg, store = env
    pm = store.read().get("person", cfg.workspace.user.person)
    first = pm.data["full_name"].split()[0]
    assert People.for_input(store, cfg, "REQ-0", "").resolve(first).person == pm.id
    assert People.for_input(store, cfg, "REQ-0", "", learns=False).resolve(first).status != "ok"
    assert People.for_input(store, cfg, "REQ-0", "", learns=False).resolve(pm.data["full_name"]).person == pm.id


def test_a_core_run_about_a_learning_own_record_gets_no_facts_either(env):
    ws, cfg, store = env
    fact = make(store, "fact", {"text": "The ferry runs on weekdays.", "project": PROJECT, "as_of": "2026-09-01"})
    cast = make(store, "p52/cast", {"name": "The harbor master", "project": PROJECT})
    own = build(ws, store, cfg, start(store, "notes", cast, kind="p52/cast", project=PROJECT), TODAY)
    plain = build(ws, store, cfg, start(store, "notes", chapter(store), project=PROJECT), TODAY)
    assert fact not in own.knowledge.given and fact in plain.knowledge.given


def test_a_scope_naming_a_parent_project_covers_its_children_at_any_depth_for_projects_and_except(env):
    ws, cfg, store = env
    series = make(store, "project", {"name": "A series"})
    book = make(store, "project", {"name": "A book", "parent": series})
    draft = make(store, "project", {"name": "A draft", "parent": book})
    reaches = rule(store, "series-rule", "Keep to the series style.", scope="projects", projects=[series])
    excluded = rule(store, "not-the-series", "Chase on Fridays.", **{"except": [series]})
    series_fact = make(
        store, "fact", {"text": "The series is set in autumn.", "project": series, "as_of": "2026-09-01"}
    )
    packet = packet_for(env, "p52/review", chapter(store, project=draft))
    assert "Keep to the series style." in packet.task.request and reaches in packet.knowledge.given
    assert "Chase on Fridays." not in packet.task.stable + packet.task.request
    assert excluded in packet.knowledge.left_out_by_scope and excluded not in packet.knowledge.given
    assert series_fact not in packet.knowledge.given  # facts stay per exact project
    core = build(ws, store, cfg, start(store, "notes", chapter(store, project=book), project=book), TODAY)
    assert reaches in core.knowledge.given and excluded in core.knowledge.left_out_by_scope


@pytest.mark.parametrize("which", ["record_learning", "kind_learning"])
def test_a_learning_other_than_core_or_own_is_refused(tmp_path, which):
    _, _, store = make_env(tmp_path, **{which: "sometimes"})
    try:
        assert not store.plugins.active("p52") and "learning" in store.plugins.status["p52"].reason
    finally:
        store.close()
