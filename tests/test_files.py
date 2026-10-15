"""Files people add (design 5.3): limits, kinds, storage by content, reading back, and safe downloads."""

import pytest
from fastapi.testclient import TestClient

from engine.files import FileKind, add_file, blob_path, read_bytes
from engine.storage import StoreError
from tests.conftest import fixture_records

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def env(workspace):
    from engine.storage import Store

    cfg = workspace.config(env={})
    store = Store(workspace.db_path, cfg=cfg)
    yield workspace, cfg, store
    store.close()


def test_a_file_is_stored_once_by_content_and_read_back(env, demo):
    _, cfg, store = env
    project = fixture_records(demo, "project")[0]["id"]
    first = add_file(store, cfg, PNG, name="cover.png", media_type="image/png", project=project)
    second = add_file(store, cfg, PNG, name="cover copy.png", media_type="image/png")
    assert first.data["sha256"] == second.data["sha256"] and first.id != second.id
    assert blob_path(store, first.data["sha256"]).read_bytes() == PNG
    record, data = read_bytes(store, first.id)
    assert data == PNG and record.data["project"] == project and record.data["origin"] == "upload"


def test_limits_types_and_kinds_are_checked(env):
    _, cfg, store = env
    with pytest.raises(StoreError, match="can't be added"):
        add_file(store, cfg, b"<html>", name="page.html", media_type="text/html")
    cfg.storage.files.max_file_mb = 0.00001
    with pytest.raises(StoreError, match="larger than"):
        add_file(store, cfg, PNG, name="big.png", media_type="image/png")
    cfg.storage.files.max_file_mb = 50
    with pytest.raises(StoreError, match="no file kind"):
        add_file(store, cfg, PNG, name="x.png", media_type="image/png", file_kind="nobody/thing")
    with pytest.raises(StoreError, match="no project"):
        add_file(store, cfg, PNG, name="x.png", media_type="image/png", project="PRJ-999")
    with pytest.raises(StoreError, match="surprise"):
        add_file(store, cfg, PNG, name="x.png", media_type="image/png", meta={"surprise": 1})


def test_a_file_sent_with_no_type_or_a_generic_one_takes_the_type_its_name_gives(env):
    _, cfg, store = env
    for sent in ("", "application/octet-stream"):
        record = add_file(store, cfg, b"# Notes\n\nPlain words.", name="notes.md", media_type=sent)
        assert record.data["media_type"] == "text/markdown"
    # A name that says text but bytes that aren't text keep the generic type, which the workspace doesn't accept.
    with pytest.raises(StoreError, match="can't be added"):
        add_file(store, cfg, b"\xff\xfe\x00\x01binary", name="notes.md", media_type="application/octet-stream")
    # A type the browser did send is kept as sent.
    record = add_file(store, cfg, PNG, name="picture.md", media_type="image/png")
    assert record.data["media_type"] == "image/png"


def test_changed_bytes_on_disk_are_caught(env):
    _, cfg, store = env
    record = add_file(store, cfg, PNG, name="cover.png", media_type="image/png")
    blob_path(store, record.data["sha256"]).write_bytes(b"tampered")
    with pytest.raises(StoreError, match="don't match"):
        read_bytes(store, record.id)


def test_adding_a_file_publishes_file_added(env):
    _, cfg, store = env
    seen = []
    original = store.plugins.publish
    store.plugins.publish = lambda event, data, **kw: (seen.append((event, data)), original(event, data, **kw))
    record = add_file(store, cfg, PNG, name="cover.png", media_type="image/png")
    assert ("file.added", {"id": record.id, "kind": "attachment"}) in seen


def test_upload_and_download_through_the_api(env):
    from api.app import create_app

    ws, cfg, store = env
    store.close()
    token = "test-token"
    client = TestClient(create_app(ws, cfg, token, start_worker=False))
    client.headers["Authorization"] = f"Bearer {token}"
    api = cfg.server.base_path.rstrip("/") + "/api"
    added = client.post(
        f"{api}/files?name=cover.png&meta=" + '{"description": "Front cover"}',
        content=PNG,
        headers={"Content-Type": "image/png"},
    )
    assert added.status_code == 200, added.text
    file_id = added.json()["id"]
    assert added.json()["meta"] == {"description": "Front cover"}
    shown = client.get(f"{api}/files/{file_id}/content")
    assert shown.content == PNG and shown.headers["content-disposition"].startswith("inline")
    assert shown.headers["x-content-type-options"] == "nosniff"
    text = client.post(f"{api}/files?name=notes.txt", content=b"plain words", headers={"Content-Type": "text/plain"})
    download = client.get(f"{api}/files/{text.json()['id']}/content")
    assert download.headers["content-disposition"].startswith("attachment")
    assert download.headers["content-type"] == "application/octet-stream"
    refused = client.post(f"{api}/files?name=page.html", content=b"<html>", headers={"Content-Type": "text/html"})
    assert refused.status_code == 409
    assert [f["name"] for f in client.get(f"{api}/files").json()] == ["notes.txt", "cover.png"]
    assert any(k["name"] == "attachment" for k in client.get(f"{api}/file-kinds").json())


def test_a_kind_never_widens_the_accepted_types(env):
    _, cfg, store = env
    store.plugins.file_kinds = lambda: {"narrow": FileKind("narrow", accept=("image/svg+xml", "image/png"))}
    with pytest.raises(StoreError, match="can't be added"):
        add_file(store, cfg, b"<svg/>", name="x.svg", media_type="image/svg+xml", file_kind="narrow")
    assert add_file(store, cfg, PNG, name="x.png", media_type="image/png", file_kind="narrow").data["size"] == len(PNG)
