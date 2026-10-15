"""Reading files as text (design 6.2): the core's readers, plugins' readers first, attachments in what the assistant
reads, files nothing reads flagged once, and the readers' own check at startup as a line on Today."""

import base64
from datetime import UTC, datetime
from email.message import EmailMessage

import pytest
import yaml

from engine.config import load_config
from engine.extract import DOCUMENT, PDF, PRESENTATION, SPREADSHEET, Unsupported, fixtures, health, read_file
from engine.extract.core import CUT_MARK, ExtractError
from engine.storage import Store
from tests.conftest import DEMO_B

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
BIG = {"max_chars": 5000, "max_bytes": 10**7}


def make(tmp_path, sources, **watch):
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": sources, **watch}))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def attached(name, media_type, data):
    return {"name": name, "media_type": media_type, "data": base64.b64encode(data).decode()}


def mail_source(files):
    item = {
        "key": "m1",
        "title": "Plan attached",
        "text": "Here is the plan.",
        "message": {"sender": "A Sender <sender@example.com>", "received": "2030-03-04T08:30:00+00:00"},
        "files": files,
    }
    return {"id": "mail", "connector": "fake", "label": "Inbox", "first_run": "all", "settings": {"items": [item]}}


def handed_text(ws, store, request_id):
    request = store.read().get("request", request_id)
    source = store.read().get("source", request.data["source"])
    return (ws.sources_dir / f"{source.data['content_hash']}.txt").read_text()


# ---- the readers -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(fixtures.CHECKS))
def test_each_reader_reads_its_tiny_file_in_full(kind):
    media_type, build, phrases = fixtures.CHECKS[kind]
    read = read_file(build(), "check", media_type, **BIG)
    assert read.kind == kind and not read.cut
    assert all(phrase in read.text for phrase in phrases)


def test_a_document_keeps_its_order_and_a_spreadsheet_its_cells():
    document = read_file(fixtures.document(), "a.docx", DOCUMENT, **BIG).text.splitlines()
    assert document[:2] == [fixtures.TITLE, fixtures.BODY]
    assert document[2] == f"{fixtures.CELL} | 12" and document[3].startswith("Comment by ")
    sheet = read_file(fixtures.spreadsheet(), "a.xlsx", SPREADSHEET, **BIG).text
    assert sheet.startswith("Sheet: Costs") and f"A2: {fixtures.CELL} | B2: 12" in sheet
    assert f"Comment on B2 by {fixtures.AUTHOR}: {fixtures.COMMENT}" in sheet
    slides = read_file(fixtures.presentation(), "a.pptx", PRESENTATION, **BIG).text
    assert slides.startswith("Slide 1:") and slides.endswith(f"Speaker notes:\n{fixtures.NOTE}")
    assert "\n1\n" not in slides  # the slide number is not text


CORRUPT = {
    "not a zip": ("document", DOCUMENT, b"this is not a zip file"),
    "a cut zip": ("document", DOCUMENT, fixtures.document()[:60]),
    "a part that isn't xml": ("document", DOCUMENT, fixtures.zipped({"word/document.xml": "<w:document"})),
    "a zip of something else": ("document", DOCUMENT, fixtures.zipped({"readme.txt": "not a document"})),
    "a document read as a spreadsheet": ("spreadsheet", SPREADSHEET, fixtures.document()),
    "a presentation that isn't one": ("presentation", PRESENTATION, b"PK\x03\x04 broken"),
    "a broken pdf": ("pdf", PDF, b"%PDF-1.4 broken"),
    "a pdf with no text": ("pdf", PDF, fixtures.pdf("")),
    "text in no known encoding": ("text", "text/plain", b"\xff\xfe\x00 not utf-8 \x80"),
    "a document with nothing in it": (
        "document",
        DOCUMENT,
        fixtures.empty_document(),
    ),
}


EMPTY_DOCUMENT = CORRUPT["a document with nothing in it"][2]


@pytest.mark.parametrize("case", list(CORRUPT))
def test_a_file_that_cant_be_read_gives_a_reason_and_its_kind_never_an_empty_text(case):
    kind, media_type, data = CORRUPT[case]
    with pytest.raises(ExtractError) as failed:
        read_file(data, "broken", media_type, **BIG)
    assert failed.value.reason.strip() and failed.value.kind == kind


def test_the_text_is_cut_at_the_size_with_a_mark():
    body = "A line of the plan that repeats. " * 40
    for media_type, data in ((DOCUMENT, fixtures.document(body=body)), ("text/plain", (body * 5).encode())):
        read = read_file(data, "long", media_type, max_chars=300, max_bytes=10**7)
        assert read.cut and read.text.endswith(CUT_MARK) and len(read.text) <= 300 + len(CUT_MARK) + 1
    short = read_file(fixtures.document(), "short", DOCUMENT, **BIG)
    assert not short.cut and CUT_MARK not in short.text


def test_a_file_over_the_limit_is_not_read():
    with pytest.raises(ExtractError, match="larger than"):
        read_file(fixtures.document(), "big.docx", DOCUMENT, max_chars=5000, max_bytes=100)


def test_markup_that_declares_entities_is_refused():
    packed = fixtures.zipped({"word/document.xml": '<!DOCTYPE d [<!ENTITY a "aaaa">]><d><body/></d>'})
    with pytest.raises(ExtractError, match="isn't safe"):
        read_file(packed, "x.docx", DOCUMENT, **BIG)


def test_the_name_decides_when_the_type_is_missing_or_generic():
    for declared in ("", "application/octet-stream", None):
        assert read_file(fixtures.document(), "plan.DOCX", declared, **BIG).kind == "document"
    assert read_file(fixtures.pdf(), "plan.pdf", "Application/PDF; name=plan.pdf", **BIG).kind == "pdf"
    with pytest.raises(Unsupported) as unsupported:
        read_file(b"\x00\x01", "archive.bin", "application/zip", **BIG)
    assert unsupported.value.media_type == "application/zip"


# ---- plugins' readers come first -------------------------------------------------------------------------------------

PLUGIN = """
from engine.plugin_api import ExtractError, Settings

class Config(Settings):
    pass

def read(data, name):
    if name.startswith("skip"):
        return None
    if data.startswith(b"LOCKED"):
        raise ExtractError("the file is locked")
    if data.startswith(b"CRASH"):
        raise RuntimeError("broken")
    return "plugin read " + name

def register(registrar):
    registrar.extractor("p21/documents", label="Special documents", media_types=["%s"], extract=read)
"""


@pytest.fixture
def plugin(tmp_path):
    folder = tmp_path / "p21"
    folder.mkdir()
    (folder / "fixture.py").write_text(PLUGIN % DOCUMENT)
    manifest = {
        "name": "p21",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Extractor fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"extractors": ["p21/documents"]},
    }
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    return folder


def test_a_plugin_reader_is_used_before_the_cores_and_declining_falls_back_to_it(plugin, tmp_path):
    from engine.files import add_file
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path) as ws:
        assert "p21/documents" in ws.registered()["extractors"]

        def stored(name):
            return add_file(ws.store, ws.cfg, fixtures.document(), name=name, media_type=DOCUMENT).id

        assert ws.view().file_text(stored("a.docx")) == "plugin read a.docx"  # the core could have read it too
        declined = ws.view().file_text(stored("skip.docx"))
        assert fixtures.BODY in declined and "plugin read" not in declined
        host = ws.store.plugins
        assert host.read_with_plugins(DOCUMENT, b"x", "skip.docx") is None
        assert host.read_with_plugins(PDF, b"x", "x.pdf") is None  # not a type it registered
        read = read_file(fixtures.document(), "b.docx", DOCUMENT, **BIG, plugin=host.read_with_plugins)
        assert (read.kind, read.text) == ("Special documents", "plugin read b.docx")


def test_a_plugin_reader_that_cant_read_a_file_says_why_and_one_that_crashes_is_contained(plugin, tmp_path):
    from engine.files import add_file
    from engine.plugin_api import StoreError
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path) as ws:
        locked = add_file(ws.store, ws.cfg, b"LOCKED", name="l.docx", media_type=DOCUMENT).id
        with pytest.raises(StoreError, match="l.docx can't be read: the file is locked"):
            ws.view().file_text(locked)
        with pytest.raises(ExtractError) as failed:
            ws.store.plugins.read_with_plugins(DOCUMENT, b"LOCKED", "l.docx")
        assert failed.value.kind == "Special documents"
        crashed = add_file(ws.store, ws.cfg, b"CRASH" + fixtures.document(), name="c.docx", media_type=DOCUMENT).id
        assert fixtures.BODY in ws.view().file_text(crashed)  # the crash is contained and the core reads the file
        assert "extractor p21/documents failed: broken" in ws.store.plugins.status["p21"].notes[-1]
        assert ws.store.plugins.active("p21")


def test_a_file_the_core_reads_is_read_for_a_plugin_packet(tmp_path):
    from engine.files import add_file

    ws, cfg, store = make(tmp_path, [])
    try:
        record = add_file(store, cfg, fixtures.spreadsheet(), name="costs.xlsx", media_type=SPREADSHEET)
        from engine.plugin_api import ReadView

        view = store.plugins._with_files(ReadView(store.read(), "p21"))
        assert fixtures.CELL in view.file_text(record.id)
        with pytest.raises(Exception, match="there is no file"):
            view.file_text("F-404")
    finally:
        store.close()


# ---- what arrives with an item ---------------------------------------------------------------------------------------


def test_a_mails_attachments_are_files_for_the_core_to_read():
    from engine.connectors.mailbox import message_item

    mail = EmailMessage()
    mail["Message-ID"] = "<one@example.com>"
    mail["From"] = "A Sender <sender@example.com>"
    mail["Subject"] = "Plan attached"
    mail.set_content("Here is the plan.")
    mail.add_attachment(
        fixtures.document(), maintype="application", subtype=DOCUMENT.split("/")[1], filename="plan.docx"
    )
    mail.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename="plan.pdf")
    item = message_item(mail.as_bytes())
    assert [(f.name, f.media_type) for f in item.files] == [("plan.docx", DOCUMENT), ("plan.pdf", PDF)]
    assert item.files[0].data == fixtures.document() and "Attached" not in item.text


def test_a_mail_attachments_text_is_in_the_packet_as_outside_content(tmp_path):
    from engine import packet
    from engine.watch import refresh

    ws, cfg, store = make(tmp_path, [mail_source([attached("plan.docx", DOCUMENT, fixtures.document())])])
    try:
        result = refresh(ws, store, cfg, "mail", NOW)
        text = handed_text(ws, store, result.new[0])
        assert f"Attached file: plan.docx\n{fixtures.TITLE}" in text and "End of attached file: plan.docx" in text
        built = packet.build(ws, store, cfg, result.new[0], NOW.date())
        outside = built.task.request.split("<untrusted", 1)[1].split("</untrusted>", 1)[0]
        assert fixtures.BODY in outside and fixtures.COMMENT in outside
        assert fixtures.BODY not in built.task.stable
        assert health.problems(ws) == []
    finally:
        store.close()


def set_files(ws, **values):
    """Change the files limits in the workspace's settings and read them again."""
    path = ws.config_dir / "storage.yaml"
    storage = yaml.safe_load(path.read_text())
    storage["files"].update(values)
    path.write_text(yaml.safe_dump(storage))
    cfg = load_config(ws.config_dir, env={})
    return cfg, Store(ws.db_path, cfg=cfg)


def test_the_text_of_an_attachment_is_cut_to_the_configured_size_with_a_mark(tmp_path):
    from engine.watch import refresh

    body = "The long plan goes on. " * 400
    ws, cfg, store = make(tmp_path, [mail_source([attached("long.docx", DOCUMENT, fixtures.document(body=body))])])
    store.close()
    cfg, store = set_files(ws, read_max_chars=1000)
    try:
        result = refresh(ws, store, cfg, "mail", NOW)
        text = handed_text(ws, store, result.new[0])
        assert text.count(CUT_MARK) == 1 and len(text) < 1000 + 300  # the item's own words and the mark come on top
        assert "End of attached file: long.docx" in text
    finally:
        store.close()


def test_a_change_in_an_attachment_is_a_change_in_the_item(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(tmp_path, [mail_source([attached("plan.docx", DOCUMENT, fixtures.document())])])
    try:
        refresh(ws, store, cfg, "mail", NOW)
        store.close()
        source = mail_source([attached("plan.docx", DOCUMENT, fixtures.document(body="The new plan is in."))])
        (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": [source]}))
        cfg = load_config(ws.config_dir, env={})
        store = Store(ws.db_path, cfg=cfg)
        again = refresh(ws, store, cfg, "mail", NOW.replace(hour=10))
        assert len(again.changed) == 1 and "+The new plan is in." in handed_text(ws, store, again.changed[0])
    finally:
        store.close()


def test_a_watched_document_in_a_folder_is_read_by_the_core(tmp_path):
    from engine.watch import refresh

    folder = tmp_path / "shared"
    folder.mkdir()
    ws, cfg, store = make(
        tmp_path,
        [
            {
                "id": "shared",
                "connector": "folder",
                "label": "Shared",
                "first_run": "all",
                "settings": {"path": str(folder), "patterns": ["*.docx", "*.pdf", "*.md"]},
            }
        ],
    )
    try:
        (folder / "plan.docx").write_bytes(fixtures.document())
        (folder / "plan.pdf").write_bytes(fixtures.pdf())
        (folder / "note.md").write_text("A plain note")
        result = refresh(ws, store, cfg, "shared", NOW)
        texts = [handed_text(ws, store, r) for r in result.new]
        assert len(texts) == 3
        assert any(fixtures.BODY in t for t in texts) and any(f"Page 1:\n{fixtures.TITLE}" in t for t in texts)
        assert any("A plain note" in t and "Attached file" not in t for t in texts)
    finally:
        store.close()


# ---- what nothing reads, and what fails -----------------------------------------------------------------------------


def questions(store):
    return [
        q for q in store.read().list("question") if (q.data.get("resolves") or {}).get("kind") == "unread_file_kind"
    ]


def test_a_type_nothing_reads_is_flagged_to_the_person_once(tmp_path):
    from engine.watch import refresh

    first = [attached("a.zip", "application/zip", b"PK"), attached("b.zip", "application/zip", b"PK")]
    ws, cfg, store = make(tmp_path, [mail_source(first)])
    try:
        assert cfg.workspace.user.person, "the demo workspace names the person"
        result = refresh(ws, store, cfg, "mail", NOW)
        assert "Attached file: a.zip (not read: files of this kind can't be read yet)" in handed_text(
            ws, store, result.new[0]
        )
        assert len(questions(store)) == 1 and questions(store)[0].data["to"] == cfg.workspace.user.person
        assert "a.zip" in questions(store)[0].data["title"]
        store.close()
        more = {
            "key": "m2",
            "title": "Another",
            "text": "More.",
            "files": [attached("c.zip", "application/zip", b"PK")],
        }
        source = mail_source(first)
        source["settings"]["items"].append(more)
        (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": [source]}))
        cfg = load_config(ws.config_dir, env={})
        store = Store(ws.db_path, cfg=cfg)
        refresh(ws, store, cfg, "mail", NOW.replace(hour=10))
        assert len(questions(store)) == 1
        assert health.problems(ws) == []  # an unsupported type isn't a reader that stopped working
    finally:
        store.close()


def test_a_watched_file_with_no_text_is_an_issue_about_its_reader_never_a_question(tmp_path):
    from engine.today_queue import queue
    from engine.watch import refresh

    ws, cfg, store = make(tmp_path, [mail_source([attached("empty.docx", DOCUMENT, EMPTY_DOCUMENT)])])
    try:
        before = len(store.read().list("question"))
        result = refresh(ws, store, cfg, "mail", NOW)
        assert "Attached file: empty.docx (not read: the document has no text in it)" in handed_text(
            ws, store, result.new[0]
        )
        assert len(store.read().list("question")) == before
        (problem,) = health.problems(ws)
        assert problem.kind == "document" and "no text" in problem.reason
        (line,) = [line for line in queue(ws, store, cfg, NOW) if line.kind == "extractor"]
        assert (line.file_kind, line.group, line.text) == ("document", "risk", problem.reason)
        store.close()
        source = mail_source([attached("plan.docx", DOCUMENT, fixtures.document())])
        source["settings"]["items"][0]["key"] = "m3"
        (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": [source]}))
        cfg = load_config(ws.config_dir, env={})
        store = Store(ws.db_path, cfg=cfg)
        refresh(ws, store, cfg, "mail", NOW.replace(hour=10))
        assert health.problems(ws) == []  # a later file of that kind that reads well ends it
    finally:
        store.close()


def test_a_file_over_the_size_limit_is_named_as_not_read_without_blaming_a_reader(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(tmp_path, [mail_source([attached("big.docx", DOCUMENT, fixtures.document())])])
    store.close()
    cfg, store = set_files(ws, read_max_mb=0.00001)
    try:
        result = refresh(ws, store, cfg, "mail", NOW)
        assert "Attached file: big.docx (not read: it is larger than" in handed_text(ws, store, result.new[0])
        assert health.problems(ws) == []
    finally:
        store.close()


# ---- the readers check themselves at startup ------------------------------------------------------------------------


def test_a_failing_reader_is_a_line_on_today_and_the_line_goes_when_it_works(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws, cfg, store = make(tmp_path, [])
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"

    def reading_lines():
        return [line for line in c.get(f"{api}/today/queue").json() if line["kind"] == "extractor"]

    app.state.worker.check_readers()
    assert reading_lines() == []  # every reader reads its own tiny file
    media_type, _build, phrases = fixtures.CHECKS["pdf"]
    monkeypatch.setitem(fixtures.CHECKS, "pdf", (media_type, lambda: b"%PDF-1.4 not a file", phrases))
    app.state.worker.check_readers()
    (line,) = reading_lines()
    assert line["file_kind"] == "pdf" and line["group"] == "risk"
    assert line["text"].startswith("its own check file didn't read:")
    monkeypatch.setitem(fixtures.CHECKS, "pdf", (media_type, fixtures.pdf, phrases))
    app.state.worker.check_readers()
    assert reading_lines() == []


def test_the_worker_checks_the_readers_when_it_starts(tmp_path, monkeypatch):
    from api.app import create_app

    ws, cfg, store = make(tmp_path, [])
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    called = []
    monkeypatch.setattr(app.state.worker, "_loop", lambda: None)
    monkeypatch.setattr(app.state.worker, "_backup_loop", lambda: None)
    monkeypatch.setattr(app.state.worker, "_sync_loop", lambda: None)
    monkeypatch.setattr(app.state.worker, "_jobs_loop", lambda: None)
    monkeypatch.setattr(app.state.worker, "check_readers", lambda: called.append(True))
    app.state.worker.start()
    app.state.worker.stop()
    assert called == [True]
