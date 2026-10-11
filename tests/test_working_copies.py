"""Working copies: long text handed out as a file for the person's own tool, and taken back as a proposal made from the
handed-out version (three-way when the text moved on), with whatever couldn't be read kept beside it."""

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B

TEXT = "The ferry left at dawn.\n\nNobody on the pier waved.\n"

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import LongText, OpModel, Record, Settings, TakeBack

class Config(Settings):
    pass

class Chapter(Record):
    record_kind: ClassVar[str] = "p11/chapter"
    prefix: ClassVar[str] = "CHW"
    title: str
    body: Annotated[str | None, LongText("plain")] = None

class AddChapter(OpModel):
    op: Literal["p11/add-chapter"] = "p11/add-chapter"
    writes: ClassVar[dict] = {"p11/chapter": ("*",)}
    title: str
    text: str

def add_chapter(op, writer, cfg):
    chapter = writer.create("p11/chapter", {"title": op.title})
    writer.set_text("p11/chapter", chapter.id, "body", op.text)

def hand_out(text, context):
    paragraphs = [p for p in text.split("\\n\\n") if p.strip()]
    return "\\n".join("\\u00b6 " + p.strip() for p in paragraphs).encode() + b"\\n"

def take_back(data, base_text, context):
    paragraphs, unmapped = [], []
    for line in data.decode().splitlines():
        if line.startswith("\\u00b6 "):
            paragraphs.append(line[2:])
        elif line.startswith("# "):
            unmapped.append("Comment: " + line[2:])
    return TakeBack("\\n\\n".join(paragraphs) + "\\n", unmapped)

def register(registrar):
    registrar.record_type(Chapter)
    registrar.op(AddChapter, "data", add_chapter)
    registrar.working_copy(
        "p11/lines", label="Lines", extension=".txt", media_type="text/plain", hand_out=hand_out, take_back=take_back
    )
"""


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p11"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(FIXTURE)
    manifest = {
        "name": "p11",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Working copies fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p11/chapter"],
            "ops": ["p11/add-chapter"],
            "working_copies": ["p11/lines"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p11"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p11"), store.plugins.status["p11"].reason
    yield ws, cfg, store
    store.close()


def chapter(env):
    from engine.applier import apply_as_person

    _, cfg, store = env
    apply_as_person(store, cfg, [{"op": "p11/add-chapter", "title": "The Crossing", "text": TEXT}], "Add a chapter")
    return store.read().list("p11/chapter")[-1]


def file_bytes(env, file_id):
    from engine.files import read_bytes

    return read_bytes(env[2], file_id)[1]


def test_handing_out_records_the_copy_and_its_file(env):
    from engine import working

    _, cfg, store = env
    record = chapter(env)
    assert [w.name for w in working.formats_for(store, record.kind, "body")] == ["p11/lines"]
    assert working.formats_for(store, record.kind, "title") == []
    copy = working.hand_out(store, cfg, "p11/lines", record.kind, record.id, "body")
    assert copy.data["status"] == "out" and copy.data["base"] == 1
    made = store.read().get("file", copy.data["file"])
    assert made.data["name"].endswith("-body-v1.txt")
    assert file_bytes(env, copy.data["file"]).decode().startswith("¶ The ferry left at dawn.")
    assert not working.stale(store, copy)


def test_an_unchanged_file_proposes_nothing(env):
    from engine import working

    _, cfg, store = env
    record = chapter(env)
    copy = working.hand_out(store, cfg, "p11/lines", record.kind, record.id, "body")
    result = working.take_back(store, cfg, copy.id, file_bytes(env, copy.data["file"]))
    assert result == {"unchanged": True, "version": None, "unmapped": []}
    assert [v.data["status"] for v in store.read().list("text_version")] == ["accepted"]


def test_an_edited_file_becomes_a_proposal_with_what_was_unmapped(env):
    from engine import working
    from engine.texts import read_text

    _, cfg, store = env
    record = chapter(env)
    copy = working.hand_out(store, cfg, "p11/lines", record.kind, record.id, "body")
    edited = "¶ The ferry left before dawn.\n# check the tide\n¶ Nobody on the pier waved.\n".encode()
    result = working.take_back(store, cfg, copy.id, edited, "chapter.txt")
    assert not result["unchanged"] and result["unmapped"] == ["Comment: check the tide"]
    version = store.read().get("text_version", result["version"])
    assert version.data["status"] == "pending" and version.data["source"] == "proposal"
    assert version.data["base"] == 1 and version.data["unmapped"] == ["Comment: check the tide"]
    assert "working copy (Lines)" in version.data["note"]
    assert read_text(store, version.data["sha256"]) == "The ferry left before dawn.\n\nNobody on the pier waved.\n"
    back = store.read().get("working_copy", copy.id)
    assert back.data["status"] == "returned" and back.data["proposal"] == version.id
    assert store.read().get("file", back.data["returned_file"]).data["name"] == "chapter.txt"


def test_a_copy_taken_back_after_the_text_moved_on_reviews_three_ways(env):
    from engine import working
    from engine.applier import apply_as_person
    from engine.texts import review

    _, cfg, store = env
    record = chapter(env)
    copy = working.hand_out(store, cfg, "p11/lines", record.kind, record.id, "body")
    moved = "The ferry left at dawn.\n\nNobody on the pier waved goodbye.\n"
    ref = {"kind": record.kind, "id": record.id}
    apply_as_person(store, cfg, [{"op": "text.edit", "record": ref, "field": "body", "text": moved}], "Edit")
    assert working.stale(store, store.read().get("working_copy", copy.id))
    edited = "¶ The ferry left before dawn.\n¶ Nobody on the pier waved.\n".encode()
    result = working.take_back(store, cfg, copy.id, edited)
    found = review(store, store.read(), result["version"])
    assert found["base"].data["number"] == 1 and found["current"].data["number"] == 2


def test_a_dropped_copy_cant_come_back(env):
    from engine import working
    from engine.storage import StoreError

    _, cfg, store = env
    record = chapter(env)
    copy = working.hand_out(store, cfg, "p11/lines", record.kind, record.id, "body")
    working.drop(store, copy.id)
    assert store.read().get("working_copy", copy.id).data["status"] == "dropped"
    with pytest.raises(StoreError, match="isn't a working copy that's out"):
        working.take_back(store, cfg, copy.id, "\u00b6 Anything.\n".encode())


def test_a_format_that_fails_is_turned_off(env):
    from dataclasses import replace

    from engine import working
    from engine.storage import StoreError

    _, cfg, store = env
    record = chapter(env)
    formats = store.plugins.registrars["p11"].working_copies

    def broken(text, context):
        raise RuntimeError("no")

    formats["p11/lines"] = replace(formats["p11/lines"], hand_out=broken)
    with pytest.raises(StoreError, match="failed, and was turned off"):
        working.hand_out(store, cfg, "p11/lines", record.kind, record.id, "body")
    assert not store.plugins.active("p11")


def test_the_working_copy_routes(env):
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws, cfg, store = env
    record = chapter(env)
    store.close()
    token = "test-token"
    client = TestClient(create_app(ws, cfg, token, start_worker=False))
    client.headers["Authorization"] = f"Bearer {token}"
    api = cfg.server.base_path.rstrip("/") + "/api"
    formats = client.get(f"{api}/working-copies/formats", params={"kind": record.kind, "field": "body"}).json()
    assert formats == [{"name": "p11/lines", "label": "Lines", "extension": ".txt"}]
    out = client.post(
        f"{api}/working-copies", json={"format": "p11/lines", "kind": record.kind, "id": record.id, "field": "body"}
    )
    assert out.status_code == 200, out.text
    copy = out.json()
    assert copy["status"] == "out" and copy["base"] == 1 and not copy["stale"] and copy["label"] == "Lines"
    content = client.get(f"{api}/files/{copy['file']}/content")
    assert content.status_code == 200
    edited = content.content.replace(b"at dawn", b"before dawn") + b"# a note\n"
    back = client.post(f"{api}/working-copies/{copy['id']}/return", content=edited, params={"name": "ch.txt"})
    assert back.status_code == 200, back.text
    taken = back.json()
    assert not taken["unchanged"] and taken["unmapped"] == ["Comment: a note"]
    review = client.get(f"{api}/text-versions/{taken['version']}/review").json()
    assert review["regions"][0]["pending"] == "The ferry left before dawn."
    listed = client.get(f"{api}/working-copies", params={"kind": record.kind, "id": record.id}).json()
    assert [c["status"] for c in listed] == ["returned"] and listed[0]["proposal"] == taken["version"]
    assert client.post(f"{api}/working-copies/{copy['id']}/drop").status_code == 200
    missing = client.post(f"{api}/working-copies/{copy['id']}/return", content=b"x")
    assert missing.status_code in (400, 404, 409)


def test_a_format_that_wouldnt_round_trip_hands_nothing_out(env):
    from dataclasses import replace

    from engine import working
    from engine.storage import StoreError

    _, cfg, store = env
    record = chapter(env)
    formats = store.plugins.registrars["p11"].working_copies

    def lossy(text, context):
        return text.split("\n\n")[0].encode()

    formats["p11/lines"] = replace(formats["p11/lines"], hand_out=lossy)
    with pytest.raises(StoreError, match="wouldn't bring this text back unchanged"):
        working.hand_out(store, cfg, "p11/lines", record.kind, record.id, "body")
    assert store.read().list("working_copy") == [] and store.plugins.active("p11")
