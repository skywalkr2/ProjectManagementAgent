"""The synced folder: a readable layout per project from each record type's `layout`, a machine copy that loads back,
atomic writes with a manifest, and files changed outside never overwritten or removed."""

import json

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B

TEXT = "The ferry left at dawn.\n\nNobody on the pier waved.\n"

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import LongText, OpModel, Record, RefTo, Settings

class Config(Settings):
    pass

class Section(Record):
    record_kind: ClassVar[str] = "p14/section"
    prefix: ClassVar[str] = "SEC"
    layout: ClassVar[str | None] = "plan/sections/{order:02}-{slug}"
    project: Annotated[str | None, RefTo("project")] = None
    order: int | None = None
    slug: str
    body: Annotated[str | None, LongText("markdown")] = None

class Rules(Record):
    record_kind: ClassVar[str] = "p14/rules"
    prefix: ClassVar[str] = "RUL"
    layout: ClassVar[str | None] = "plan/rules"
    project: Annotated[str | None, RefTo("project")] = None
    rules: list[str] = []

class AddSection(OpModel):
    op: Literal["p14/add-section"] = "p14/add-section"
    writes: ClassVar[dict] = {"p14/section": ("*",), "p14/rules": ("*",)}
    project: str
    order: int
    slug: str
    text: str

def add_section(op, writer, cfg):
    section = writer.create("p14/section", {"project": op.project, "order": op.order, "slug": op.slug})
    writer.set_text("p14/section", section.id, "body", op.text)
    writer.create("p14/rules", {"project": op.project, "rules": ["Past tense."]})

class RenameSection(OpModel):
    op: Literal["p14/rename-section"] = "p14/rename-section"
    writes: ClassVar[dict] = {"p14/section": ("slug",)}
    section: str
    slug: str

def rename_section(op, writer, cfg):
    section = writer.get("p14/section", op.section)
    writer.update("p14/section", op.section, {"slug": op.slug}, read_version=section.version)

def register(registrar):
    registrar.record_type(Section)
    registrar.record_type(Rules)
    registrar.op(AddSection, "data", add_section)
    registrar.op(RenameSection, "data", rename_section)
"""


def workspace(tmp_path, name="ws", folder=None, fixture=FIXTURE):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / name, template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p14"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(fixture)
    manifest = {
        "name": "p14",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Synced folder fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"record_types": ["p14/section", "p14/rules"], "ops": ["p14/add-section", "p14/rename-section"]},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p14"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    if folder is not None:
        storage = yaml.safe_load((ws.config_dir / "storage.yaml").read_text())
        storage["sync"] = {"folder": str(folder)}
        (ws.config_dir / "storage.yaml").write_text(yaml.safe_dump(storage))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    folder = tmp_path / "synced"
    folder.mkdir()
    ws, cfg, store = workspace(tmp_path, folder=folder)
    assert store.plugins.active("p14"), store.plugins.status["p14"].reason
    yield ws, cfg, store, folder
    store.close()


def apply(env, ops):
    from engine.applier import apply_as_person

    _, cfg, store, _ = env[:4]
    return apply_as_person(store, cfg, ops, "Test change")


def series_and_book(env):
    """A series project with a book inside it, and one section of the book."""
    _, _, store, _ = env
    apply(env, [{"op": "project.add", "name": "Lake Ferries"}])
    series = store.read().list("project")[-1]
    apply(env, [{"op": "project.add", "name": "One More: Aboard?", "parent": series.id}])
    book = store.read().list("project")[-1]
    apply(env, [{"op": "p14/add-section", "project": book.id, "order": 3, "slug": "the-crossing", "text": TEXT}])
    return series, book, store.read().list("p14/section")[-1]


def write(env):
    from engine.sync import write_folder

    ws, cfg, store, _ = env
    return write_folder(store, ws, cfg)


def test_a_layout_must_be_a_relative_path_of_the_records_fields():
    from engine.plugin_api import Record
    from engine.sync import check_layout

    class Thing(Record):
        record_kind = "p/thing"
        prefix = "THG"
        slug: str = ""

    check_layout("things/{slug}", Thing)
    check_layout("things/{id}", Thing)
    for bad, why in (
        ("/things/{slug}", "relative"),
        ("things/../{slug}", "'..'"),
        ("things/{title}", "isn't a field"),
        ("things/{slug}.md", "extension"),
        (".cockpit/{slug}", "keeps for itself"),
        ("things/{slug", "brace"),
    ):
        with pytest.raises(ValueError, match=why):
            check_layout(bad, Thing)


def test_names_are_safe_on_every_file_system():
    from engine.sync import safe_name

    assert safe_name("One More: Aboard?", "PRJ-1") == "One More- Aboard-"
    assert safe_name("  ...  ", "PRJ-1") == "PRJ-1"
    assert safe_name("con", "PRJ-1") == "_con"
    assert safe_name("a/b\\c", "X") == "a-b-c"


def test_the_folder_reads_one_folder_per_project_nested(env):
    _, _, store, folder = env
    series, book, section = series_and_book(env)
    result = write(env)
    book_dir = folder / "Lake Ferries" / "One More- Aboard-"
    assert (folder / "Lake Ferries" / "project.yaml").is_file() and (book_dir / "project.yaml").is_file()
    page = (book_dir / "plan" / "sections" / "03-the-crossing.md").read_text()
    front, _, body = page.partition("---\n\n")
    assert front.startswith("---\n") and f"id: {section.id}" in front and "slug: the-crossing" in front
    assert "body:" not in front and body == TEXT
    history = book_dir / "plan" / "sections" / ".versions" / "03-the-crossing"
    assert (history / "v1.md").read_text() == TEXT
    listed = yaml.safe_load((history / "versions.yaml").read_text())
    assert listed[0]["number"] == 1 and listed[0]["status"] == "accepted" and listed[0]["words"]["person"] > 0
    assert yaml.safe_load((book_dir / "plan" / "rules.yaml").read_text())["rules"] == ["Past tense."]
    person = store.read().list("person")[0]
    assert (folder / "_workspace" / "people" / f"{person.data['full_name']}.yaml").is_file()
    assert (folder / ".cockpit" / "export" / "ledger.jsonl").is_file()
    assert (folder / ".cockpit" / "config" / "workspace.yaml").is_file()
    manifest = json.loads((folder / ".cockpit" / "manifest.json").read_text())
    assert set(result.written) <= set(manifest) and not result.changed_outside
    assert not list(folder.rglob("*.cockpit-tmp"))


def test_writing_again_changes_nothing(env):
    series_and_book(env)
    write(env)
    again = write(env)
    assert again.written == [] and again.removed == [] and again.changed_outside == []


def test_a_rename_moves_the_file(env):
    _, _, store, folder = env
    _, book, section = series_and_book(env)
    write(env)
    apply(env, [{"op": "p14/rename-section", "section": section.id, "slug": "the-return"}])
    result = write(env)
    sections = folder / "Lake Ferries" / "One More- Aboard-" / "plan" / "sections"
    assert (sections / "03-the-return.md").is_file() and not (sections / "03-the-crossing.md").exists()
    assert any(r.endswith("03-the-crossing.md") for r in result.removed)


def test_a_file_changed_outside_is_never_overwritten(env):
    _, _, store, folder = env
    _, book, section = series_and_book(env)
    write(env)
    page = folder / "Lake Ferries" / "One More- Aboard-" / "plan" / "sections" / "03-the-crossing.md"
    page.write_text(page.read_text() + "\nAdded in another editor.\n")
    ref = {"kind": section.kind, "id": section.id}
    apply(env, [{"op": "text.edit", "record": ref, "field": "body", "text": "Rewritten here.\n"}])
    result = write(env)
    assert "Added in another editor." in page.read_text()
    assert any(r.endswith("03-the-crossing.md") for r in result.changed_outside)
    assert any(r.endswith("v2.md") for r in result.written)


def test_the_folder_loads_back_into_an_empty_workspace(env, tmp_path):
    from engine.storage import Store
    from engine.sync import load_folder, readable_files

    _, _, store, folder = env
    series_and_book(env)
    write(env)
    other_ws, other_cfg, _ = workspace(tmp_path, name="other")
    empty = Store(other_ws.root / "empty.db", cfg=other_cfg)
    try:
        assert load_folder(empty, folder) == sum(len(store.read().list(k)) for k in store.read().kinds())
        assert readable_files(empty, empty.read()) == readable_files(store, store.read())
        assert empty.read().ledger() == store.read().ledger()
    finally:
        empty.close()


def test_the_workspace_may_not_be_inside_the_folder(tmp_path):
    from engine.sync import folder_problem, placement_problem

    ws, cfg, store = workspace(tmp_path, folder=tmp_path)
    store.close()
    assert "inside the synced folder" in placement_problem(ws, cfg)
    ws2, cfg2, store2 = workspace(tmp_path, name="ws2", folder=tmp_path / "ws2" / "sync")
    store2.close()
    assert "inside the workspace" in placement_problem(ws2, cfg2)
    ws3, cfg3, store3 = workspace(tmp_path, name="ws3", folder=tmp_path / "missing")
    store3.close()
    assert placement_problem(ws3, cfg3) is None and "isn't there" in folder_problem(ws3, cfg3)


def test_the_app_refuses_to_start_with_the_workspace_inside_the_folder(tmp_path):
    from api.app import create_app

    ws, cfg, store = workspace(tmp_path, folder=tmp_path)
    store.close()
    with pytest.raises(RuntimeError, match="inside the synced folder"):
        create_app(ws, cfg, "token")


def test_the_worker_writes_after_a_change(env):
    from engine.worker import Events, Worker

    ws, cfg, store, folder = env
    worker = Worker(ws, store, cfg, Events())
    assert worker.sync_if_changed() and not worker.sync_if_changed()
    series_and_book(env)
    assert worker.sync_if_changed() and worker.sync_result.written
    assert (folder / "Lake Ferries").is_dir()


def test_a_plugin_with_a_bad_layout_stays_off(tmp_path):
    broken = FIXTURE.replace('"plan/sections/{order:02}-{slug}"', '"plan/sections/{title}"')
    ws, cfg, store = workspace(tmp_path, fixture=broken)
    assert "isn't a field" in store.plugins.status["p14"].reason
    store.close()


def test_a_snapshot_doesnt_see_writes_made_meanwhile(env):
    import threading

    _, _, store, _ = env
    before = len(store.read().list("project"))
    with store.snapshot() as view:
        assert len(view.list("project")) == before
        writer = threading.Thread(target=lambda: apply(env, [{"op": "project.add", "name": "Later"}]))
        writer.start()
        writer.join()
        assert len(view.list("project")) == before and len(store.read().list("project")) == before
    assert len(store.read().list("project")) == before + 1
