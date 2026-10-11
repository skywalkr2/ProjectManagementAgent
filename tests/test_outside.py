"""The synced folder's third part: edits made outside come back as proposals (long text pending, fields and deletes
held), collections, paths through a reference, generated files, sources and outputs, working copies taken back from
`working/`, and file bytes in the machine copy."""

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B

TEXT = "The ferry left at dawn.\n\nNobody on the pier waved.\n"

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import LongText, OpModel, Record, RefTo, Settings, TakeBack

class Config(Settings):
    pass

class Section(Record):
    record_kind: ClassVar[str] = "p15/section"
    prefix: ClassVar[str] = "SCT"
    layout: ClassVar[str | None] = "plan/sections/{order:02}-{slug}"
    project: Annotated[str | None, RefTo("project")] = None
    order: int | None = None
    slug: str
    body: Annotated[str | None, LongText("plain")] = None

class Rule(Record):
    record_kind: ClassVar[str] = "p15/rule"
    prefix: ClassVar[str] = "RLE"
    layout: ClassVar[str | None] = "plan/rules"
    layout_collection: ClassVar[bool] = True
    layout_sort: ClassVar[str | None] = "order"
    project: Annotated[str | None, RefTo("project")] = None
    order: int = 0
    text: str

class Entry(Record):
    record_kind: ClassVar[str] = "p15/entry"
    prefix: ClassVar[str] = "ENT"
    layout: ClassVar[str | None] = "bible/sections/{section.order:02}-{section.slug}"
    project: Annotated[str | None, RefTo("project")] = None
    section: Annotated[str | None, RefTo("p15/section")] = None
    summary: str = ""

class Seed(OpModel):
    op: Literal["p15/seed"] = "p15/seed"
    writes: ClassVar[dict] = {"p15/section": ("*",), "p15/rule": ("*",), "p15/entry": ("*",)}
    project: str

def seed(op, writer, cfg):
    section = writer.create("p15/section", {"project": op.project, "order": 3, "slug": "the-crossing"})
    writer.set_text("p15/section", section.id, "body", "The ferry left at dawn.\\n\\nNobody on the pier waved.\\n")
    for order, text in ((2, "Past tense."), (1, "No dream openings."), (3, "Close third person.")):
        writer.create("p15/rule", {"project": op.project, "order": order, "text": text})
    writer.create("p15/entry", {"project": op.project, "section": section.id, "summary": "The crossing."})

def overview(project, view, settings):
    sections = view.list("p15/section", project=project.id)
    return "# Sections\\n" + "".join(f"- {s.data['slug']}\\n" for s in sections) if sections else None

def hand_out(text, context):
    return "\\n".join("\\u00b6 " + p.strip() for p in text.split("\\n\\n") if p.strip()).encode() + b"\\n"

def take_back(data, base_text, context):
    lines = [line[2:] for line in data.decode().splitlines() if line.startswith("\\u00b6 ")]
    return TakeBack("\\n\\n".join(lines) + "\\n", [])

def register(registrar):
    registrar.record_type(Section)
    registrar.record_type(Rule)
    registrar.record_type(Entry)
    registrar.op(Seed, "data", seed)
    registrar.derived_file("p15/overview", path="views/overview.md", depends_on=("p15/section",), render=overview)
    registrar.working_copy(
        "p15/lines", label="Lines", extension=".txt", media_type="text/plain", hand_out=hand_out, take_back=take_back
    )
"""


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    folder = tmp_path / "synced"
    folder.mkdir()
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p15"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(FIXTURE)
    manifest = {
        "name": "p15",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Outside edits fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p15/section", "p15/rule", "p15/entry"],
            "ops": ["p15/seed"],
            "derived_files": ["p15/overview"],
            "working_copies": ["p15/lines"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p15"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    storage = yaml.safe_load((ws.config_dir / "storage.yaml").read_text())
    storage["sync"] = {"folder": str(folder)}
    (ws.config_dir / "storage.yaml").write_text(yaml.safe_dump(storage))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p15"), store.plugins.status["p15"].reason
    yield ws, cfg, store, folder
    store.close()


def apply(env, ops):
    from engine.applier import apply_as_person

    _, cfg, store, _ = env
    return apply_as_person(store, cfg, ops, "Test change")


def book(env):
    _, _, store, _ = env
    apply(env, [{"op": "project.add", "name": "Lake Ferries"}])
    project = store.read().list("project")[-1]
    apply(env, [{"op": "p15/seed", "project": project.id}])
    return project, store.read().list("p15/section")[-1]


def sync(env):
    """One pass of the worker's sync: pick up outside edits, then write what changed."""
    from engine.worker import Events, Worker

    ws, cfg, store, _ = env
    worker = Worker(ws, store, cfg, Events())
    worker.sync_if_changed()
    return worker


def write(env):
    from engine import outside
    from engine.sync import write_folder

    ws, cfg, store, _ = env
    result = write_folder(store, ws, cfg, may_overwrite=outside.settled(store, cfg))
    outside.forget(cfg)
    return result


def pick_up(env):
    from engine import outside

    ws, cfg, store, _ = env
    return outside.pick_up(store, ws, cfg)


def page(folder):
    return folder / "Lake Ferries" / "plan" / "sections" / "03-the-crossing.md"


def test_long_text_edited_outside_comes_back_as_a_pending_version(env):
    from engine.texts import read_text

    _, cfg, store, folder = env
    _, section = book(env)
    write(env)
    edited = page(folder).read_text().replace("at dawn", "before dawn")
    page(folder).write_text(edited)
    assert pick_up(env) == ["Lake Ferries/plan/sections/03-the-crossing.md"]
    version = [v for v in store.read().list("text_version") if v.data["status"] == "pending"][-1]
    assert version.data["source"] == "proposal" and version.data["note"] == "edited outside the cockpit"
    assert version.data["base"] == 1 and "before dawn" in read_text(store, version.data["sha256"])
    assert pick_up(env) == []  # handled once
    write(env)
    assert "before dawn" in page(folder).read_text()  # still the person's file while the proposal waits
    apply(env, [{"op": "text.accept", "version": version.id, "read_version": version.version, "choices": {}}])
    write(env)
    assert "before dawn" in page(folder).read_text()
    from engine.outside import pending

    assert pending(cfg) == {}


def test_fields_edited_outside_wait_for_the_person(env):
    from engine.applier import release

    _, cfg, store, folder = env
    _, section = book(env)
    write(env)
    page(folder).write_text(page(folder).read_text().replace("order: 3", "order: 4"))
    pick_up(env)
    changeset = [c for c in store.read().list("changeset") if c.data["summary"].startswith("Edited outside")][-1]
    held = changeset.data["ops"][0]
    assert held["status"] == "held" and held["op"]["op"] == "record.edit" and held["op"]["fields"] == {"order": 4}
    assert store.read().get("p15/section", section.id).data["order"] == 3
    release(store, cfg, changeset.id, 0)
    assert store.read().get("p15/section", section.id).data["order"] == 4
    write(env)
    assert (folder / "Lake Ferries" / "plan" / "sections" / "04-the-crossing.md").is_file()


def test_a_file_the_cockpit_cant_read_is_reported_and_kept(env):
    from engine.outside import pending

    _, cfg, store, folder = env
    book(env)
    write(env)
    page(folder).write_text(page(folder).read_text().replace("id: SCT-", "id: XYZ-"))
    pick_up(env)
    assert "id at the top was changed" in pending(cfg)["Lake Ferries/plan/sections/03-the-crossing.md"]["problem"]
    write(env)
    assert "XYZ-" in page(folder).read_text()


def test_a_collection_is_one_sorted_file_and_edits_come_back_per_entry(env):
    from engine.outside import pending

    _, cfg, store, folder = env
    book(env)
    write(env)
    rules_file = folder / "Lake Ferries" / "plan" / "rules.yaml"
    rules = yaml.safe_load(rules_file.read_text())
    assert [r["text"] for r in rules] == ["No dream openings.", "Past tense.", "Close third person."]
    rules[0]["text"] = "No dreams at all."
    removed = rules.pop(1)
    rules.append({"text": "Brand new rule."})
    rules_file.write_text(yaml.safe_dump(rules))
    pick_up(env)
    changeset = [c for c in store.read().list("changeset") if c.data["summary"].startswith("Edited outside")][-1]
    ops = {o["op"]["op"]: o for o in changeset.data["ops"]}
    assert ops["record.edit"]["status"] == "held" and ops["record.edit"]["op"]["fields"] == {
        "text": "No dreams at all."
    }
    assert ops["record.delete"]["status"] == "held" and ops["record.delete"]["op"]["record"]["id"] == removed["id"]
    assert "1 new entry" in pending(cfg)["Lake Ferries/plan/rules.yaml"]["problem"]


def test_a_path_can_use_a_field_of_the_record_it_refers_to(env):
    _, _, store, folder = env
    book(env)
    write(env)
    assert (folder / "Lake Ferries" / "bible" / "sections" / "03-the-crossing.yaml").is_file()


def test_generated_files_are_written_and_rebuilt_when_edited(env):
    _, _, store, folder = env
    book(env)
    write(env)
    view = folder / "Lake Ferries" / "views" / "overview.md"
    assert view.read_text() == "# Sections\n- the-crossing\n"
    view.write_text("changed by hand\n")
    apply(env, [{"op": "project.add", "name": "Another"}])
    result = write(env)
    assert "Lake Ferries/views/overview.md" in result.rebuilt and view.read_text().startswith("# Sections")
    assert not (folder / "Another" / "views").exists()  # no sections there, so nothing to generate


def test_sources_and_outputs_are_readable_and_their_bytes_travel(env, tmp_path):
    from engine.files import add_file
    from engine.storage import Store
    from engine.sync import load_folder

    ws, cfg, store, folder = env
    project, _ = book(env)
    upload = add_file(
        store, cfg, b"notes from the archive\n", name="archive.txt", media_type="text/plain", project=project.id
    )
    built = add_file(
        store, cfg, b"%PDF-1.4 fake\n", name="book.pdf", media_type="application/pdf", project=project.id, origin="tool"
    )
    result = write(env)
    assert (folder / "Lake Ferries" / "sources" / "archive.txt").read_bytes() == b"notes from the archive\n"
    assert (folder / "Lake Ferries" / "outputs" / "book.pdf").is_file()
    assert (folder / ".cockpit" / "files" / built.data["sha256"]).is_file()
    (folder / "Lake Ferries" / "outputs" / "book.pdf").unlink()
    apply(env, [{"op": "project.add", "name": "Another"}])
    again = write(env)
    assert "Lake Ferries/outputs/book.pdf" in again.removed_outside
    assert not (folder / "Lake Ferries" / "outputs" / "book.pdf").exists()
    assert result.written and upload.id
    other = tmp_path / "other"
    other.mkdir()
    (other / "plugins").symlink_to(ws.root / "plugins")
    empty = Store(other / "cockpit.db", cfg=cfg)
    try:
        load_folder(empty, folder)
        assert (other / "files" / built.data["sha256"][:2] / built.data["sha256"]).read_bytes() == b"%PDF-1.4 fake\n"
    finally:
        empty.close()


def test_a_working_copy_in_the_folder_is_taken_back_when_it_changes(env):
    from engine import working
    from engine.texts import read_text

    _, cfg, store, folder = env
    _, section = book(env)
    copy = working.hand_out(store, cfg, "p15/lines", section.kind, section.id, "body")
    write(env)
    handed = store.read().get("file", copy.data["file"]).data["name"]
    path = folder / "Lake Ferries" / "working" / handed
    assert path.read_text().startswith("¶ The ferry left at dawn.")
    path.write_text(path.read_text().replace("at dawn", "at noon"))
    pick_up(env)
    back = store.read().get("working_copy", copy.id)
    assert back.data["status"] == "returned"
    proposal = store.read().get("text_version", back.data["proposal"])
    assert "at noon" in read_text(store, proposal.data["sha256"])
    write(env)
    assert "at noon" in path.read_text()  # the person's working file is never overwritten


def test_the_worker_picks_up_an_edit_and_writes(env):
    _, _, store, folder = env
    book(env)
    sync(env)
    page(folder).write_text(page(folder).read_text().replace("at dawn", "at dusk"))
    sync(env)
    assert any(v.data["status"] == "pending" for v in store.read().list("text_version"))


def test_record_edit_is_the_persons_and_checks_its_fields(env):
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET
    from engine.storage import StoreError

    _, cfg, store, _ = env
    _, section = book(env)
    ref = {"kind": section.kind, "id": section.id}
    for fields, why in (
        ({"genre": "x"}, "has no field genre"),
        ({"body": "x"}, "can't be changed"),
        ({"stage": "x"}, "can't be changed"),
        ({"order": "many"}, "order"),
    ):
        with pytest.raises(StoreError, match=why):
            apply(env, [{"op": "record.edit", "record": ref, "fields": fields, "read_version": section.version}])
    cs = CHANGESET.validate_python(
        {"ops": [{"op": "record.edit", "record": ref, "fields": {"order": 9}, "read_version": section.version}]},
        context={"op_models": store.plugins.ops},
    )
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-0", None, "", "", "trusted"))
    cs_id = apply_changeset(cs, [], ctx, run=None)
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "refused"
    apply(env, [{"op": "record.edit", "record": ref, "fields": {"order": 9}, "read_version": section.version}])
    assert store.read().get("p15/section", section.id).data["order"] == 9


def test_the_cockpits_own_bookkeeping_is_never_a_conflict_copy(env):
    from engine.handover import conflict_copies

    _, _, store, folder = env
    book(env)
    write(env)
    page(folder).write_text(page(folder).read_text().replace("at dawn", "at dusk"))
    pick_up(env)
    assert (folder / ".cockpit" / "outside.json").is_file() and conflict_copies(folder) == []


def test_a_record_with_no_project_is_placed_through_its_reference(env):
    from engine.sync import check_layout, readable_files

    _, _, store, folder = env
    book(env)
    model = store.plugins.records["p15/entry"]
    try:
        model.layout_project = "section"
        check_layout(model.layout, model, store.plugins.records)
        entry = store.read().list("p15/entry")[-1]
        assert entry.data["project"]  # placed by its own project when it has one
        files, _ = readable_files(store, store.read())
        assert "Lake Ferries/bible/sections/03-the-crossing.yaml" in files
        model.layout_project = "summary"
        with pytest.raises(ValueError, match="isn't a reference"):
            check_layout(model.layout, model, store.plugins.records)
    finally:
        model.layout_project = None


def test_the_current_text_version_is_read_directly(env):
    from engine.plugin_api import ReadView

    _, _, store, _ = env
    _, section = book(env)
    view = store.plugins._with_files(ReadView(store.read(), "p15"))
    assert view.text_version(section, "body").data["number"] == 1
