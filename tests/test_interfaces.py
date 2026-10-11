"""Interfaces between plugins (design 3.9): one plugin defines and uses an interface, another provides it. Items are
read-only copies checked against the definition, events reach the users, a user can request work the provider offers,
and each plugin works alone."""

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B

DEFINER = """
from pydantic import BaseModel
from engine.plugin_api import Settings

class Config(Settings):
    pass

class Source(BaseModel):
    project: str
    title: str
    words: int = 0
    data_level: str = "internal"

class Approved(BaseModel):
    project: str
    title: str

def on_approved(payload, context):
    note = "Write a blurb for " + payload["title"]
    context.request_from("p16/source@1", "blurb", note, ("project", payload["project"]))

def register(registrar):
    registrar.define_interface(
        "p16/source", version="1.0", item=Source, events={"approved": Approved}, task_kinds=("blurb",)
    )
    registrar.subscribe("p16/source.approved", on_approved)
"""

PROVIDER = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import OpModel, Record, RefTo, Settings

class Config(Settings):
    pass

class Work(Record):
    record_kind: ClassVar[str] = "p17/work"
    prefix: ClassVar[str] = "WRK"
    project: Annotated[str | None, RefTo("project")] = None
    title: str
    words: int = 0
    secret: bool = False

class AddWork(OpModel):
    op: Literal["p17/add-work"] = "p17/add-work"
    writes: ClassVar[dict] = {"p17/work": ("*",)}
    project: str
    title: str
    words: int = 0
    secret: bool = False
    bad_event: bool = False

def add_work(op, writer, cfg):
    writer.create("p17/work", {"project": op.project, "title": op.title, "words": op.words, "secret": op.secret})
    payload = {"project": op.project} if op.bad_event else {"project": op.project, "title": op.title}
    writer.emit("p16/source.approved", payload)

def items(view, settings):
    return [
        {
            "project": w.data["project"],
            "title": w.data["title"],
            "words": w.data["words"],
            "data_level": "restricted" if w.data.get("secret") else "internal",
        }
        for w in view.list("p17/work")
    ]

def register(registrar):
    registrar.record_type(Work)
    registrar.op(AddWork, "data", add_work)
    registrar.task_kind("p17/blurb", label="Blurb", ops=("note",), on="project")
    registrar.provide_interface("p16/source@1", items=items, task_kinds={"blurb": "p17/blurb"})
"""


def plugin(ws, name, code, manifest):
    folder = ws.root / "plugins" / name
    folder.mkdir(parents=True)
    (folder / "fixture.py").write_text(code)
    base = {
        "name": name,
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Interfaces fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
    }
    (folder / "plugin.yaml").write_text(yaml.safe_dump({**base, **manifest}))


DEFINER_MANIFEST = {
    "interfaces": {"defines": ["p16/source"], "uses": [{"interface": "p16/source@1", "optional": True}]},
    "subscribes": ["p16/source.approved"],
}
PROVIDER_MANIFEST = {
    "interfaces": {"provides": ["p16/source@1"]},
    "provides": {"record_types": ["p17/work"], "ops": ["p17/add-work"], "ai_task_kinds": ["p17/blurb"]},
}


def workspace(tmp_path, *, definer=DEFINER_MANIFEST, provider=PROVIDER_MANIFEST, enabled=("p16", "p17"), code=None):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin(ws, "p16", DEFINER, definer)
    plugin(ws, "p17", code or PROVIDER, provider)
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], *enabled]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    for name in ("p16", "p17"):
        assert store.plugins.active(name), store.plugins.status[name].reason
    yield ws, cfg, store
    store.close()


def apply(cfg, store, ops):
    from engine.applier import apply_as_person

    return apply_as_person(store, cfg, ops, "Test change")


def a_project(cfg, store, name="Lake Ferries"):
    apply(cfg, store, [{"op": "project.add", "name": name}])
    return store.read().list("project")[-1]


def test_a_user_reads_the_providers_items_as_checked_copies(env):
    _, cfg, store = env
    project = a_project(cfg, store)
    other = a_project(cfg, store, "Tide Tables")
    apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "One More Aboard", "words": 61000}])
    apply(cfg, store, [{"op": "p17/add-work", "project": other.id, "title": "Low Water"}])
    items = store.plugins.read_interface("p16", "p16/source@1")
    assert [(i.provider, i.data["title"]) for i in items] == [("p17", "One More Aboard"), ("p17", "Low Water")]
    only = store.plugins.read_interface("p16", "p16/source@1", project.id)
    assert [i.data["words"] for i in only] == [61000]


def test_items_above_the_users_data_levels_are_left_out(env):
    _, cfg, store = env
    project = a_project(cfg, store)
    apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "Kept Back", "secret": True}])
    assert store.plugins.read_interface("p16", "p16/source@1") == []


def test_an_interface_the_plugin_doesnt_use_is_refused(env):
    from engine.plugin_api import PluginMisuse

    _, _, store = env
    with pytest.raises(PluginMisuse, match="interfaces.uses"):
        store.plugins.read_interface("p17", "p16/source@1")
    with pytest.raises(PluginMisuse):
        store.plugins.read_interface("p16", "p16/other@1")


def test_an_event_reaches_the_user_and_its_request_runs_as_the_providers_task(env):
    _, cfg, store = env
    project = a_project(cfg, store)
    apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "One More Aboard"}])
    request = store.read().list("request")[-1]
    assert request.data["task"] == "p17/blurb" and request.data["about"] == {"kind": "project", "id": project.id}
    assert request.data["origin"] == "schedule" and "One More Aboard" in request.data["note"]


def test_an_event_payload_must_match_the_definition(env):
    from engine.storage import StoreError

    _, cfg, store = env
    project = a_project(cfg, store)
    with pytest.raises(StoreError):
        apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "X", "bad_event": True}])
    assert "broke its contract" in store.plugins.status["p17"].reason


def test_an_optional_interface_with_no_provider_reads_empty(tmp_path):
    ws, cfg, store = workspace(tmp_path, enabled=("p16",))
    try:
        assert store.plugins.active("p16")
        assert store.plugins.read_interface("p16", "p16/source@1") == []
    finally:
        store.close()


def test_a_required_interface_with_no_provider_keeps_the_user_off(tmp_path):
    required = {
        **DEFINER_MANIFEST,
        "interfaces": {**DEFINER_MANIFEST["interfaces"], "uses": [{"interface": "p16/source@1"}]},
    }
    ws, cfg, store = workspace(tmp_path, definer=required, enabled=("p16",))
    try:
        assert "needs p16/source@1" in store.plugins.status["p16"].reason
    finally:
        store.close()


def test_a_newer_minor_version_than_defined_reads_nothing(tmp_path):
    newer = {
        **DEFINER_MANIFEST,
        "interfaces": {**DEFINER_MANIFEST["interfaces"], "uses": [{"interface": "p16/source@1.2", "optional": True}]},
    }
    ws, cfg, store = workspace(tmp_path, definer=newer)
    try:
        assert store.plugins.read_interface("p16", "p16/source@1.2") == []
    finally:
        store.close()


def test_a_provider_whose_items_dont_fit_is_turned_off(tmp_path):
    broken = PROVIDER.replace('"words": w.data["words"],', '"words": "lots",')
    ws, cfg, store = workspace(tmp_path, code=broken)
    try:
        project = a_project(cfg, store)
        apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "X"}])
        assert store.plugins.read_interface("p16", "p16/source@1") == []
        assert "items failed" in store.plugins.status["p17"].reason
    finally:
        store.close()


def test_the_manifest_must_match_what_is_registered(tmp_path):
    wrong = {**PROVIDER_MANIFEST, "interfaces": {"provides": ["p16/source@2"]}}
    ws, cfg, store = workspace(tmp_path, provider=wrong)
    try:
        assert "interfaces.provides" in store.plugins.status["p17"].reason
    finally:
        store.close()
