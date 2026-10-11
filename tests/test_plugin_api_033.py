"""Plugin API 0.3.3: finding development installs, a workspace copy winning over an installed one, notes for file
kinds narrowed by the workspace, labels that read records, and Undo after an undo."""

import sys
from types import SimpleNamespace

import yaml

from engine.config import load_config
from tests.conftest import DEMO_B, fixture_records
from tests.test_plugin_api_02 import apply, env  # noqa: F401 - the fixture is reused


def test_an_editable_install_is_found_in_its_checkout(tmp_path, monkeypatch):
    from engine.plugin_manifest import installed_manifest

    package = tmp_path / "src" / "devplugin"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "plugin.yaml").write_text("name: devplugin\n")
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    site = tmp_path / "site-packages"
    entry = SimpleNamespace(value="devplugin:register", dist=SimpleNamespace(locate_file=lambda m: site / m))
    assert installed_manifest(entry) == package / "plugin.yaml"
    assert "devplugin" not in sys.modules  # found without importing the plugin's code


def test_the_workspace_copy_wins_over_an_installed_one_with_a_note(env, monkeypatch):  # noqa: F811
    import engine.plugin_host as host
    from engine.storage import Store

    ws, _, _ = env
    fake = SimpleNamespace(name="p02", value="p02:register")
    monkeypatch.setattr(host, "entry_points", lambda group: [fake])
    monkeypatch.setattr(host, "installed_manifest", lambda ep: ws.root / "elsewhere" / "plugin.yaml")
    other = Store(ws.root / "other.db", cfg=load_config(ws.config_dir, env={}))
    assert other.plugins.active("p02")
    assert "workspace's plugins folder is used" in other.plugins.status["p02"].notes[0]
    other.close()


def test_a_file_kind_narrowed_by_the_workspace_says_so(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p06"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(
        "from engine.plugin_api import Settings\n"
        "class Config(Settings):\n    pass\n"
        "def register(registrar):\n"
        "    registrar.file_kind('p06/art', accept=('image/svg+xml', 'image/png'))\n"
        "    registrar.file_kind('p06/scan', accept=('image/tiff',))\n"
    )
    manifest = {
        "name": "p06",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "File kind notes fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"file_kinds": ["p06/art", "p06/scan"]},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p06"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    notes = store.plugins.status["p06"].notes
    assert store.plugins.active("p06")
    assert any("p06/art" in n and "accepts image/png" in n for n in notes)
    assert any("p06/scan" in n and "no files at all" in n for n in notes)
    store.close()


def test_an_ops_label_may_read_records(env):  # noqa: F811
    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "labelled"}])
    entry = store.read().list("p02/entry")[-1]
    cs_id, _ = apply(env, [{"op": "p02/decide", "slug": "labelled"}], pm=True)
    assert store.read().get("changeset", cs_id).data["ops"][0]["label"] == f"Decide {entry.id}"


def test_undo_an_older_change_after_undoing_a_newer_one(env):  # noqa: F811
    from engine.applier import undo

    _, _, store = env
    project = fixture_records(DEMO_B, "project")[0]["id"]
    original = store.read().get("project", project).data["summary"]

    def set_summary(text):
        return apply(
            env, [{"op": "record.set", "kind": "project", "id": project, "field": "summary", "value": text}], pm=True
        )[0]

    first, second = set_summary("First summary."), set_summary("Second summary.")
    assert undo(store, second).restored == [0]
    assert store.read().get("project", project).data["summary"] == "First summary."
    report = undo(store, first)
    assert report.restored == [0] and not report.skipped
    assert store.read().get("project", project).data["summary"] == original


def test_undo_still_refuses_when_a_later_change_stands(env):  # noqa: F811
    from engine.applier import undo

    _, _, store = env
    project = fixture_records(DEMO_B, "project")[0]["id"]
    op = {"op": "record.set", "kind": "project", "id": project, "field": "summary"}
    first, _ = apply(env, [{**op, "value": "First summary."}], pm=True)
    apply(env, [{**op, "value": "Second summary."}], pm=True)
    assert undo(store, first).skipped


def test_a_field_called_kind_can_be_looked_up():
    import inspect

    from engine.plugin_api import ReadView

    for name in ("get", "list", "find"):
        first = list(inspect.signature(getattr(ReadView, name)).parameters.values())[1]
        assert first.kind == first.POSITIONAL_ONLY, name


def test_a_plugin_ops_own_evidence_field_is_left_alone():
    from pydantic import BaseModel

    from engine.applier import _evidence
    from engine.ops import EvidenceIn, OpModel

    class Theirs(BaseModel):
        page: int

    class PluginOp(OpModel):
        op: str = "x/op"
        evidence: Theirs

    class CoreLike(OpModel):
        op: str = "y/op"
        evidence: EvidenceIn

    assert _evidence(PluginOp(evidence=Theirs(page=3))) is None
    assert _evidence(CoreLike(evidence=EvidenceIn(quote="the exact words"))).quote == "the exact words"


def test_references_inside_nested_models_are_found():
    from typing import Annotated, ClassVar

    from pydantic import BaseModel

    from engine.records import Record, RefTo, ref_fields

    class Relationship(BaseModel):
        person: Annotated[str, RefTo("person")]
        note: str = ""

    class Character(Record):
        record_kind: ClassVar[str] = "x/character"
        prefix: ClassVar[str] = "CHR"
        relationships: list[Relationship] = []
        mentor: Relationship | None = None

    assert ("relationships[].person", "person") in ref_fields(Character)
    assert ("mentor.person", "person") in ref_fields(Character)


def test_a_view_reads_a_saved_sources_text(env):  # noqa: F811
    from engine.intake import hand_in
    from engine.plugin_api import ReadView

    ws, _, store = env
    handed = hand_in(ws, store, note="", pasted="The launch moves to spring.")
    view = store.plugins._with_files(ReadView(store.read(), "p02"))
    assert view.source_text(handed.source) == "The launch moves to spring."
    assert view.source_text("SRC-999") == ""
