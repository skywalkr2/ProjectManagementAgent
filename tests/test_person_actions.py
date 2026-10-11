"""Person actions (plugin API 0.3): one proposal for one review, choices that rerun it, files it builds, previews, and
applying exactly what the person reviewed as theirs."""

import base64
import sys

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.config import load_config
from tests.conftest import DEMO_B

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import Choice, Group, Item, NewFile, OpModel, Preview, Proposal, Record, RefTo, Settings

PNG = b"\\x89PNG\\r\\n\\x1a\\n" + b"\\x00" * 32

class Config(Settings):
    pass

class Work(Record):
    record_kind: ClassVar[str] = "p04/work"
    prefix: ClassVar[str] = "WRK"
    person_only: ClassVar[dict] = {"status": ("final",)}
    title: str
    status: Literal["draft", "final"] = "draft"

class Build(Record):
    record_kind: ClassVar[str] = "p04/build"
    prefix: ClassVar[str] = "BLD"
    work: Annotated[str, RefTo("p04/work")]
    file: Annotated[str, RefTo("file")]

class AddWork(OpModel):
    op: Literal["p04/add-work"] = "p04/add-work"
    writes: ClassVar[dict] = {"p04/work": ("*",)}
    title: str

    def describe(self):
        return "Start " + self.title

class SetStatus(OpModel):
    op: Literal["p04/set-status"] = "p04/set-status"
    writes: ClassVar[dict] = {"p04/work": ("status",)}
    work: str
    status: str
    read_version: int

class AddBuild(OpModel):
    op: Literal["p04/add-build"] = "p04/add-build"
    writes: ClassVar[dict] = {"p04/build": ("*",)}
    work: str
    file: str

def add_work(op, writer, cfg):
    writer.create("p04/work", {"title": op.title})

def set_status(op, writer, cfg):
    writer.update("p04/work", op.work, {"status": op.status}, read_version=op.read_version)

def add_build(op, writer, cfg):
    writer.create("p04/build", {"work": op.work, "file": op.file})

def new_work(target, context, choices):
    return Proposal("Start a work", ops=[{"op": "p04/add-work", "title": "Harbor Lights"}])

def finish(target, context, choices):
    status = choices.get("status", "final")
    return Proposal(
        "Mark " + target.data["title"] + " " + status,
        ops=[{"op": "p04/set-status", "work": target.id, "status": status, "read_version": target.version}],
        choices=[Choice("status", "Mark it", status, options=[("final", "Final"), ("draft", "Draft")])],
    )

def build(target, context, choices):
    if not context.tools.available("fakeprog"):
        return Proposal("Can't build without the converter", notes=["The converter isn't installed."])
    result = context.tools.run("fakeprog", ["in.txt"], {"in.txt": target.data["title"].encode()}, collect=["out.txt"])
    return Proposal(
        "Build " + target.data["title"],
        files=[NewFile("build.txt", "text/plain", result.files["out.txt"], project=None)],
        ops=[{"op": "p04/add-build", "work": target.id, "file": "$file:0"}],
        previews=[Preview("page-1.png", "image/png", PNG, "First page")],
    )

def import_lines(target, context, choices):
    lines = context.file_bytes(target.id).decode().splitlines()
    return Proposal("Import " + str(len(lines)) + " works", ops=[{"op": "p04/add-work", "title": t} for t in lines])

def broken(target, context, choices):
    raise RuntimeError("bug in the add-on")

def claims(target, context, choices):
    return Proposal("Say something", ops=[{"op": "fact", "text": "x", "evidence": {"quote": "x"}}])

def batch(target, context, choices):
    prefix = choices.get("prefix", "")
    titles = {"alpha": "Alpha", "beta": "Beta", "gamma": prefix + "Gamma"}
    return Proposal(
        "Start three works",
        choices=[Choice("prefix", "Prefix", prefix, options=[("", "None"), ("New ", "New")], group="style")],
        groups=[Group("style", "Style"), Group("works", "Works to start", "One per line in the list.")],
        items=[
            Item(key, "Start " + title, [{"op": "p04/add-work", "title": title}], group="works", kept=key != "beta")
            for key, title in titles.items()
        ],
    )

def bad_items(target, context, choices):
    return Proposal("Broken", items=[Item("x", "X", [{"op": "p04/add-work", "title": "X"}], group="missing")])

def bad_preview(target, context, choices):
    return Proposal("Show a page", previews=[Preview("page.html", "text/html", b"<b>hi</b>")])

def register(registrar):
    registrar.record_type(Work)
    registrar.record_type(Build)
    registrar.op(AddWork, "data", add_work)
    registrar.op(SetStatus, "data", set_status)
    registrar.op(AddBuild, "data", add_build)
    registrar.file_kind("p04/list", label="List of works", accept=("text/plain",))
    registrar.action("p04/new-work", label="Start a work", run=new_work)
    registrar.action("p04/finish", label="Finish", run=finish, on="p04/work")
    registrar.action("p04/build", label="Build", run=build, on="p04/work")
    registrar.action("p04/import", label="Import works", run=import_lines, on="file", file_kinds=("p04/list",))
    registrar.action("p04/broken", label="Broken", run=broken, on="p04/work")
    registrar.action("p04/claims", label="Claims", run=claims)
    registrar.action("p04/bad-preview", label="Bad preview", run=bad_preview)
    registrar.action("p04/batch", label="Batch", run=batch)
    registrar.action("p04/bad-items", label="Bad items", run=bad_items)
"""

PROGRAM = """
import pathlib, sys
if sys.argv[1:] == ["--version"]:
    print("fakeprog 1.0"); sys.exit(0)
pathlib.Path("out.txt").write_text("BUILT " + pathlib.Path(sys.argv[1]).read_text())
"""


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p04"
    plugin.mkdir(parents=True)
    manifest = {
        "name": "p04",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Person actions fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "requires": {"tools": [{"name": "fakeprog", "min_version": "1.0", "probe": "fakeprog --version"}]},
        "provides": {
            "record_types": ["p04/work", "p04/build"],
            "ops": ["p04/add-work", "p04/set-status", "p04/add-build"],
            "file_kinds": ["p04/list"],
            "actions": [
                "p04/new-work",
                "p04/finish",
                "p04/build",
                "p04/import",
                "p04/broken",
                "p04/claims",
                "p04/bad-preview",
                "p04/batch",
                "p04/bad-items",
            ],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (plugin / "fixture.py").write_text(FIXTURE)
    script = tmp_path / "fakeprog.py"
    script.write_text(PROGRAM)
    (ws.root / ".cockpit").mkdir(exist_ok=True)
    (ws.root / ".cockpit" / "tools.yaml").write_text(
        yaml.safe_dump({"fakeprog": {"command": [sys.executable, str(script)]}})
    )
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p04"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p04"), store.plugins.status["p04"].reason
    yield ws, cfg, store
    store.close()


def run(env, name, target=None, choices=None, **more):
    from engine import actions

    _, cfg, store = env
    return actions.preview(store, cfg, name, target, choices, **more)


def apply(env, pending):
    from engine import actions

    _, cfg, store = env
    return actions.apply(store, cfg, pending.token)


def a_work(env):
    _, _, store = env
    apply(env, run(env, "p04/new-work"))
    work = store.read().list("p04/work")[-1]
    return {"kind": "p04/work", "id": work.id}


def test_actions_are_offered_where_they_apply(env):
    from engine import actions
    from engine.files import add_file

    _, cfg, store = env
    assert {a.name for a in actions.available(store)} >= {"p04/new-work", "p04/claims"}
    assert "p04/finish" in {a.name for a in actions.available(store, "p04/work")}
    listing = add_file(store, cfg, b"One\nTwo", name="works.txt", media_type="text/plain", file_kind="p04/list")
    other = add_file(store, cfg, b"x", name="notes.txt", media_type="text/plain")
    assert [a.name for a in actions.available(store, "file", listing.id)] == ["p04/import"]
    assert "p04/import" not in {a.name for a in actions.available(store, "file", other.id)}


def test_a_person_action_applies_as_the_person(env):
    _, _, store = env
    work = a_work(env)
    pending = run(env, "p04/finish", work)
    cs_id = apply(env, pending)
    assert store.read().get("p04/work", work["id"]).data["status"] == "final"
    cs = store.read().get("changeset", cs_id).data
    assert cs["ops"][0]["status"] == "applied" and cs["reviewed"]
    assert cs["action"] == {
        "name": "p04/finish",
        "target": pending.target,
        "choices": {"status": "final"},
        "kept": [],
        "dropped": [],
    }
    request = store.read().get("request", cs["request"]).data
    assert request["origin"] == "pm" and request["changeset"] == cs_id
    entries = [e for e in store.read().ledger() if e["record_id"] == work["id"] and e["field"] == "status"]
    assert entries[-1]["actor"] == "pm" and entries[-1]["after"] == "final"


def test_flipping_a_choice_runs_the_action_again(env):
    from engine.actions import ActionFailed

    _, _, store = env
    work = a_work(env)
    pending = run(env, "p04/finish", work, {"status": "draft"})
    assert pending.summary.endswith("draft") and pending.choices == {"status": "draft"}
    with pytest.raises(ActionFailed, match="set to a value it doesn't offer"):
        run(env, "p04/finish", work, {"status": "lost"})  # the action kept a value it doesn't offer


def test_a_choice_no_longer_offered_is_dropped(env):
    _, _, store = env
    work = a_work(env)
    pending = run(env, "p04/finish", work, {"status": "draft", "colour": "blue"})
    assert pending.choices == {"status": "draft"}


def test_a_build_adds_its_file_and_undo_takes_everything_back(env):
    from engine.applier import undo
    from engine.files import read_bytes

    _, _, store = env
    work = a_work(env)
    pending = run(env, "p04/build", work)
    assert pending.previews[0]["data"] == PNG and pending.files[0]["name"] == "build.txt"
    cs_id = apply(env, pending)
    build = store.read().list("p04/build")[-1].data
    record, data = read_bytes(store, build["file"])
    assert data == b"BUILT Harbor Lights" and record.data["origin"] == "tool"
    assert store.read().list("tool_run")[-1].data["tool"] == "fakeprog"
    undo(store, cs_id)
    assert store.read().list("p04/build") == [] and store.read().get("file", build["file"]) is None


def test_nothing_applies_if_the_target_changed_after_the_review(env):
    _, _, store = env
    work = a_work(env)
    pending = run(env, "p04/finish", work, {"status": "draft"})
    apply(env, run(env, "p04/finish", work))
    from engine.storage import StoreError

    with pytest.raises(StoreError, match="changed since you reviewed"):
        apply(env, pending)


def test_a_review_applies_once(env):
    from engine.storage import StoreError

    pending = run(env, "p04/new-work")
    apply(env, pending)
    with pytest.raises(StoreError, match="expired"):
        apply(env, pending)


def test_an_action_reads_the_file_it_was_started_on(env):
    from engine.files import add_file

    _, cfg, store = env
    listing = add_file(
        store, cfg, b"North Pier\nSalt Road", name="works.txt", media_type="text/plain", file_kind="p04/list"
    )
    apply(env, run(env, "p04/import", {"kind": "file", "id": listing.id}))
    assert [w.data["title"] for w in store.read().list("p04/work")] == ["North Pier", "Salt Road"]


def test_a_crashing_action_turns_its_plugin_off(env):
    from engine.actions import ActionFailed

    _, _, store = env
    work = a_work(env)
    with pytest.raises(ActionFailed, match="turned off"):
        run(env, "p04/broken", work)
    assert not store.plugins.active("p04")


def test_an_action_may_not_propose_claims_or_unsafe_previews(env):
    from engine.actions import ActionFailed

    with pytest.raises(ActionFailed, match="isn't an op an action may propose"):
        run(env, "p04/claims")
    with pytest.raises(ActionFailed, match="previews can't be text/html"):
        run(env, "p04/bad-preview")


def test_actions_through_the_api(env):
    from api.app import create_app

    ws, cfg, store = env
    work = a_work(env)
    store.close()
    token = "test-token"
    client = TestClient(create_app(ws, cfg, token, start_worker=False))
    client.headers["Authorization"] = f"Bearer {token}"
    api = cfg.server.base_path.rstrip("/") + "/api"
    offered = client.get(f"{api}/plugin-actions", params={"kind": "p04/work", "id": work["id"]}).json()
    assert {"name": "p04/build", "label": "Build", "on": "p04/work"} in offered
    shown = client.post(f"{api}/plugin-actions/p04/build/preview", json={"target": work})
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert [o["op"] for o in body["ops"]] == ["file.add", "p04/add-build"]
    assert body["ops"][0]["label"] == "Add the file build.txt"
    assert base64.b64decode(body["previews"][0]["data_base64"]) == PNG
    applied = client.post(f"{api}/plugin-actions/apply", json={"token": body["token"]}).json()
    assert applied["applied"] == 2 and applied["refused"] == 0
    refused = client.post(f"{api}/plugin-actions/p04/finish/preview", json={"target": None})
    assert refused.status_code == 409


def titles(store):
    return sorted(w.data["title"] for w in store.read().list("p04/work"))


def test_only_kept_items_apply_and_the_changeset_says_which(env):
    _, _, store = env
    pending = run(env, "p04/batch")
    assert [(i["id"], i["kept"]) for i in pending.items] == [("alpha", True), ("beta", False), ("gamma", True)]
    cs_id = apply(env, pending)
    assert titles(store) == ["Alpha", "Gamma"]
    action = store.read().get("changeset", cs_id).data["action"]
    assert action["kept"] == ["alpha", "gamma"] and action["dropped"] == ["beta"]


def test_the_final_ticks_come_with_apply(env):
    from engine import actions

    _, cfg, store = env
    pending = run(env, "p04/batch")
    actions.apply(store, cfg, pending.token, {"alpha": False, "beta": True})
    assert titles(store) == ["Beta", "Gamma"]


def test_ticks_carry_over_to_unchanged_items_when_a_choice_reruns(env):
    first = run(env, "p04/batch", kept={"alpha": False, "beta": True, "gamma": False})
    again = run(env, "p04/batch", choices={"prefix": "New "}, previous=first.token)
    ticks = {i["id"]: i["kept"] for i in again.items}
    # alpha and beta came back unchanged and keep the person's ticks; gamma changed and starts as the action says.
    assert ticks == {"alpha": False, "beta": True, "gamma": True}


def test_a_bad_tick_refuses_and_keeps_the_review(env):
    from engine import actions
    from engine.storage import StoreError

    _, cfg, store = env
    pending = run(env, "p04/batch")
    with pytest.raises(StoreError, match="no item nope"):
        actions.apply(store, cfg, pending.token, {"nope": True})
    actions.apply(store, cfg, pending.token)
    assert titles(store) == ["Alpha", "Gamma"]


def test_items_and_choices_must_name_listed_groups(env):
    from engine.actions import ActionFailed

    with pytest.raises(ActionFailed, match="group the proposal doesn't list"):
        run(env, "p04/bad-items")


def test_the_review_lists_items_and_what_applies_now(env):
    from api.app import create_app

    ws, cfg, store = env
    store.close()
    token = "test-token"
    client = TestClient(create_app(ws, cfg, token, start_worker=False))
    client.headers["Authorization"] = f"Bearer {token}"
    api = cfg.server.base_path.rstrip("/") + "/api"
    body = client.post(f"{api}/plugin-actions/p04/batch/preview", json={}).json()
    assert [o["label"] for o in body["ops"]] == ["Start Alpha", "Start Gamma"]
    assert [(i["id"], i["group"], i["kept"]) for i in body["items"]][1] == ("beta", "works", False)
    assert body["groups"][1] == {"id": "works", "heading": "Works to start", "explanation": "One per line in the list."}
    assert body["choices"][0]["group"] == "style"
    rerun = client.post(
        f"{api}/plugin-actions/p04/batch/preview",
        json={"choices": {"prefix": "New "}, "previous": body["token"], "kept": {"beta": True}},
    ).json()
    applied = client.post(f"{api}/plugin-actions/apply", json={"token": rerun["token"], "kept": {"alpha": False}})
    assert applied.json()["applied"] == 2
