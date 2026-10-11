"""The example plugin's person action: a note from a plain text file."""

import pytest
import yaml

from engine import actions
from engine.config import load_config
from engine.files import add_file
from engine.storage import Store, StoreError
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NAME = "example/note-from-file"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    # Enabled here, so the test holds in the core-only run too, where the copied fixtures enable no plugins.
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    enabled = settings.setdefault("plugins", {}).setdefault("enabled", [])
    if "example" not in enabled:
        enabled.append("example")
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    yield cfg, store
    store.close()


def target(store, record):
    return {"kind": "file", "id": record.id}


def test_it_is_offered_on_attachments(env):
    cfg, store = env
    record = add_file(store, cfg, b"x", name="a.txt", media_type="text/plain")
    offered = actions.available(store, "file", record.id)
    assert [a.name for a in offered] == [NAME]
    assert offered[0].label == "Make a note from this file"


def test_preview_and_apply_make_one_note_with_the_word_count(env):
    cfg, store = env
    record = add_file(store, cfg, b"\n\n  First line here  \nSecond line", name="notes.txt", media_type="text/plain")
    pending = actions.preview(store, cfg, NAME, target(store, record))
    assert "notes.txt" in pending.summary
    assert pending.choices == {"count": True}
    assert pending.ops == [{"op": "note", "text": "First line here (5 words)"}]
    assert pending.previews == [] and pending.files == []
    before = len(store.read().list("note"))
    actions.apply(store, cfg, pending.token)
    notes = store.read().list("note")
    assert len(notes) == before + 1
    assert notes[-1].data["text"] == "First line here (5 words)"


def test_turning_the_count_off_leaves_the_line_alone(env):
    cfg, store = env
    record = add_file(store, cfg, b"Only line\nmore words", name="n.txt", media_type="text/plain")
    pending = actions.preview(store, cfg, NAME, target(store, record), {"count": False})
    assert pending.ops == [{"op": "note", "text": "Only line"}]
    assert pending.choices == {"count": False}


def test_a_long_first_line_is_trimmed(env):
    cfg, store = env
    record = add_file(store, cfg, b"word " * 100, name="long.txt", media_type="text/plain")
    pending = actions.preview(store, cfg, NAME, target(store, record), {"count": False})
    assert len(pending.ops[0]["text"]) <= 200


def test_a_file_that_is_not_text_is_refused_in_plain_words(env):
    cfg, store = env
    record = add_file(store, cfg, b"%PDF-1.4", name="doc.pdf", media_type="application/pdf")
    with pytest.raises(StoreError, match="Only plain text"):
        actions.preview(store, cfg, NAME, target(store, record))


def test_a_file_with_no_text_is_refused(env):
    cfg, store = env
    record = add_file(store, cfg, b"\n \n", name="blank.txt", media_type="text/plain")
    with pytest.raises(StoreError, match="no text"):
        actions.preview(store, cfg, NAME, target(store, record))
