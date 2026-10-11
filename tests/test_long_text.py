"""Long text: versions stored once by hash, units from a text format, authorship by passage, drafts and proposals
that wait for review, accepting change by change (three-way when the text moved on), Undo, and the export round trip."""

import pytest
import yaml

from engine.config import load_config
from engine.texts import markdown_units, plain_units
from tests.conftest import DEMO_B

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import LongText, OpModel, Record, Settings, Unit

class Config(Settings):
    pass

def scenes(text):
    units, start = [], 0
    for index, line in enumerate(text.splitlines(keepends=True)):
        pass
    pos = 0
    for block in text.split("* * *\\n"):
        end = pos + len(block) + (6 if pos + len(block) < len(text) else 0)
        units.append(Unit(pos, min(end, len(text)), "scene"))
        pos = min(end, len(text))
    return [u for u in units if u.end > u.start]

class Chapter(Record):
    record_kind: ClassVar[str] = "p08/chapter"
    prefix: ClassVar[str] = "CHA"
    title: str
    body: Annotated[str | None, LongText("plain")] = None
    scenes: Annotated[str | None, LongText("p08/scenes")] = None

class AddChapter(OpModel):
    op: Literal["p08/add-chapter"] = "p08/add-chapter"
    writes: ClassVar[dict] = {"p08/chapter": ("*",)}
    title: str
    text: str

class Rewrite(OpModel):
    op: Literal["p08/rewrite"] = "p08/rewrite"
    writes: ClassVar[dict] = {"p08/chapter": ("body",)}
    chapter: str
    text: str

class Sneak(OpModel):
    op: Literal["p08/sneak"] = "p08/sneak"
    writes: ClassVar[dict] = {"p08/chapter": ("*",)}
    title: str

def add_chapter(op, writer, cfg):
    chapter = writer.create("p08/chapter", {"title": op.title})
    writer.set_text("p08/chapter", chapter.id, "body", op.text)

def rewrite(op, writer, cfg):
    writer.set_text("p08/chapter", op.chapter, "body", op.text)

def sneak(op, writer, cfg):
    writer.create("p08/chapter", {"title": op.title, "body": "not a hash"})

def register(registrar):
    registrar.record_type(Chapter)
    registrar.text_format("p08/scenes", scenes)
    registrar.op(AddChapter, "data", add_chapter)
    registrar.op(Rewrite, "data", rewrite)
    registrar.op(Sneak, "data", sneak)
"""

TEXT = "The ferry left at dawn.\n\nNobody on the pier waved.\n\nThe gulls followed it out.\n"


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p08"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(FIXTURE)
    manifest = {
        "name": "p08",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Long text fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p08/chapter"],
            "ops": ["p08/add-chapter", "p08/rewrite", "p08/sneak"],
            "text_formats": ["p08/scenes"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p08"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p08"), store.plugins.status["p08"].reason
    yield ws, cfg, store
    store.close()


def apply(env, ops, *, person=True):
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET

    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, "", "", "trusted"),
        confirmed_by_pm=person,
        actor="pm" if person else "assistant",
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def view(env):
    from engine.plugin_api import ReadView

    _, _, store = env
    return store.plugins._with_files(ReadView(store.read(), "p08"))


def chapter(env, text=TEXT):
    _, _, store = env
    apply(env, [{"op": "p08/add-chapter", "title": "The Crossing", "text": text}])
    return store.read().list("p08/chapter")[-1]


def versions(env, record):
    return view(env).text_versions(record, "body")


def test_the_persons_text_is_the_first_version_and_written_by_them(env):
    _, _, store = env
    record = chapter(env)
    [first] = versions(env, record)
    assert first.data["status"] == "accepted" and first.data["source"] == "import" and first.data["number"] == 1
    assert record.data["body"] == first.data["sha256"]
    assert view(env).text(record, "body") == TEXT
    assert {s["kind"] for s in view(env).authorship(record, "body")} == {"person"}
    assert first.data["words"] == len(TEXT.split())


def test_the_assistants_text_is_a_draft_that_changes_nothing_until_reviewed(env):
    _, _, store = env
    record = chapter(env)
    draft = TEXT.replace("Nobody on the pier waved.", "No one on the pier lifted a hand.")
    _, statuses = apply(env, [{"op": "p08/rewrite", "chapter": record.id, "text": draft}], person=False)
    assert statuses == ["applied"]
    second = versions(env, record)[-1]
    assert second.data["status"] == "pending" and second.data["source"] == "draft"
    assert view(env).text(store.read().get("p08/chapter", record.id), "body") == TEXT
    kinds = [s["kind"] for s in second.data["authorship"]]
    assert kinds == ["person", "assistant_edit", "person"]


def accept(env, version, choices=None):
    _, _, store = env
    current = store.read().get("text_version", version.id)
    op = {"op": "text.accept", "version": version.id, "read_version": current.version, "choices": choices or {}}
    return apply(env, [op])


def test_accepting_everything_makes_the_draft_current_and_says_so(env):
    _, _, store = env
    record = chapter(env)
    seen = []
    original = store.plugins.publish
    store.plugins.publish = lambda event, data: (seen.append((event, data)), original(event, data))
    draft = TEXT + "\nThe island came up out of the haze.\n"
    apply(env, [{"op": "p08/rewrite", "chapter": record.id, "text": draft}], person=False)
    pending = versions(env, record)[-1]
    assert accept(env, pending)[1] == ["applied"]
    fresh = store.read().get("p08/chapter", record.id)
    assert view(env).text(fresh, "body") == draft
    assert store.read().get("text_version", pending.id).data["status"] == "accepted"
    payload = next(data for event, data in seen if event == "text.accepted" and data["version"] == 2)
    assert payload["previous"] == 1 and payload["source"] == "draft"
    assert payload["authorship"]["assistant"] == len(["The", "island", "came", "up", "out", "of", "the", "haze."])


def test_accepting_some_changes_writes_a_merged_version(env):
    _, _, store = env
    record = chapter(env)
    draft = "The ferry left before dawn.\n\nNobody on the pier waved.\n\nThe gulls wheeled behind it.\n"
    apply(env, [{"op": "p08/rewrite", "chapter": record.id, "text": draft}], person=False)
    pending = versions(env, record)[-1]
    accept(env, pending, {"c2": "reject"})
    fresh = store.read().get("p08/chapter", record.id)
    merged = view(env).text(fresh, "body")
    assert merged.startswith("The ferry left before dawn.") and "The gulls followed it out." in merged
    assert store.read().get("text_version", pending.id).data["status"] == "merged"
    latest = versions(env, fresh)[-1]
    assert latest.data["source"] == "merge" and latest.data["status"] == "accepted"
    assert [s["kind"] for s in latest.data["authorship"]] == ["assistant_edit", "person"]


def test_rejecting_everything_discards_the_draft(env):
    _, _, store = env
    record = chapter(env)
    apply(env, [{"op": "p08/rewrite", "chapter": record.id, "text": "Something else entirely.\n"}], person=False)
    pending = versions(env, record)[-1]
    accept(env, pending, {"c1": "reject"})
    assert store.read().get("text_version", pending.id).data["status"] == "discarded"
    assert view(env).text(store.read().get("p08/chapter", record.id), "body") == TEXT


def test_a_proposal_made_from_an_older_version_merges_three_ways(env):
    _, _, store = env
    record = chapter(env)
    newer = TEXT.replace("The gulls followed it out.", "The gulls followed it out past the breakwater.")
    apply(env, [{"op": "text.edit", "record": {"kind": record.kind, "id": record.id}, "field": "body", "text": newer}])
    handed_back = TEXT.replace("The ferry left at dawn.", "The ferry slipped out at dawn.")
    op = {
        "op": "text.propose",
        "record": {"kind": record.kind, "id": record.id},
        "field": "body",
        "text": handed_back,
        "base": 1,
        "note": "handed back from a working copy",
    }
    apply(env, [op])
    proposal = versions(env, record)[-1]
    assert proposal.data["status"] == "pending" and proposal.data["base"] == 1
    accept(env, proposal)
    text = view(env).text(store.read().get("p08/chapter", record.id), "body")
    assert "slipped out at dawn" in text and "past the breakwater" in text


def test_only_the_person_edits_accepts_or_discards(env):
    _, _, store = env
    record = chapter(env)
    edit = {"op": "text.edit", "record": {"kind": record.kind, "id": record.id}, "field": "body", "text": "Mine.\n"}
    assert apply(env, [edit], person=False)[1] == ["refused"]


def test_undo_brings_the_earlier_text_back(env):
    from engine.applier import undo

    _, _, store = env
    record = chapter(env)
    edit = {"op": "text.edit", "record": {"kind": record.kind, "id": record.id}, "field": "body", "text": "New.\n"}
    cs_id, _ = apply(env, [edit])
    assert view(env).text(store.read().get("p08/chapter", record.id), "body") == "New.\n"
    undo(store, cs_id)
    assert view(env).text(store.read().get("p08/chapter", record.id), "body") == TEXT
    assert len(versions(env, record)) == 1


def test_a_plugin_never_writes_long_text_directly(env):
    _, _, store = env
    assert apply(env, [{"op": "p08/sneak", "title": "Sneaky"}])[1] == ["refused"]
    assert not store.plugins.active("p08")


def test_long_text_survives_the_export_round_trip(env, tmp_path):
    from engine.storage import Store
    from engine.storage.export import export_data, import_data

    ws, cfg, store = env
    record = chapter(env, text="Line one.\r\n\r\nLine two.\n")
    export_data(store, tmp_path / "data")
    assert (tmp_path / "data" / "texts" / f"{record.data['body']}.txt").read_bytes() == b"Line one.\r\n\r\nLine two.\n"
    import shutil

    shutil.copytree(ws.root / "plugins", tmp_path / "other" / "plugins")
    other = Store(tmp_path / "other" / "cockpit.db", cfg=cfg)
    import_data(other, tmp_path / "data")
    from engine.plugin_api import ReadView

    again = other.plugins._with_files(ReadView(other.read(), "p08"))
    assert again.text(other.read().get("p08/chapter", record.id), "body") == "Line one.\r\n\r\nLine two.\n"
    export_data(other, tmp_path / "data2")
    files = sorted(p.relative_to(tmp_path / "data").as_posix() for p in (tmp_path / "data").rglob("*") if p.is_file())
    files2 = sorted(
        p.relative_to(tmp_path / "data2").as_posix() for p in (tmp_path / "data2").rglob("*") if p.is_file()
    )
    assert files == files2
    for name in files:
        assert (tmp_path / "data" / name).read_bytes() == (tmp_path / "data2" / name).read_bytes(), name
    other.close()


def test_markdown_units_keep_code_lists_and_footnotes_whole():
    text = (
        "# Heading\n\nA paragraph.\n\n```\ncode\n\nmore\n```\n\n- one\n- two\n\n  still two\n\n"
        "[^1]: A note.\n\n    More.\n\nEnd."
    )
    units = markdown_units(text)
    pieces = [(text[u.start : u.end].strip(), u.kind, u.atomic) for u in units]
    assert pieces[0] == ("# Heading", "heading", False)
    assert pieces[2] == ("```\ncode\n\nmore\n```", "code", True)
    assert pieces[3][1] == "list" and "still two" in pieces[3][0]
    assert pieces[4][1] == "footnote" and "More." in pieces[4][0]
    assert "".join(text[u.start : u.end] for u in units) == text


def test_plain_units_cover_the_text_exactly():
    text = "\n\nOne.\n\n\nTwo\nlines.\n"
    units = plain_units(text)
    assert "".join(text[u.start : u.end] for u in units) == text and len(units) == 2


def test_a_plugins_text_format_is_checked(env):
    from engine.texts import units_of

    _, _, store = env
    text = "Scene one.\n* * *\nScene two.\n"
    units = units_of(store, "p08/scenes", text)
    assert "".join(text[u.start : u.end] for u in units) == text


def test_the_review_routes_compare_accept_and_edit(env):
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws, cfg, store = env
    record = chapter(env)
    draft = "The ferry left before dawn.\n\nNobody on the pier waved.\n\nThe gulls wheeled behind it.\n"
    apply(env, [{"op": "p08/rewrite", "chapter": record.id, "text": draft}], person=False)
    store.close()
    token = "test-token"
    client = TestClient(create_app(ws, cfg, token, start_worker=False))
    client.headers["Authorization"] = f"Bearer {token}"
    api = cfg.server.base_path.rstrip("/") + "/api"
    where = {"kind": record.kind, "id": record.id, "field": "body"}
    field = client.get(f"{api}/texts", params=where).json()
    assert (
        field["current"] == 1
        and field["text"] == TEXT
        and [v["status"] for v in field["versions"]]
        == [
            "accepted",
            "pending",
        ]
    )
    pending = field["versions"][1]
    review = client.get(f"{api}/text-versions/{pending['id']}/review").json()
    assert not review["three_way"] and [r["id"] for r in review["regions"]] == ["c1", "c2"]
    assert review["regions"][0]["pending"] == "The ferry left before dawn."
    stale = client.post(f"{api}/text-versions/{pending['id']}/accept", json={"read_version": 99})
    assert stale.status_code == 409
    done = client.post(
        f"{api}/text-versions/{pending['id']}/accept",
        json={"read_version": pending["version"], "choices": {"c2": "reject"}},
    )
    assert done.status_code == 200, done.text
    after = client.get(f"{api}/texts", params=where).json()
    assert after["current"] == 3 and after["text"].startswith("The ferry left before dawn.")
    assert {s["kind"] for s in after["authorship"]} == {"assistant_edit", "person"}
    edited = client.post(f"{api}/texts/edit", json={**where, "text": "All mine now.\n"})
    assert edited.status_code == 200
    assert client.get(f"{api}/texts", params=where).json()["text"] == "All mine now.\n"
