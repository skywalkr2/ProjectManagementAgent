"""A connector says what it reads (plugin API 0.3.56): the setup walkthrough offers an add-on as a mail or calendar
service from that declaration, in the code and in the manifest. A connector that says nothing is still told apart by
its name, and the log says it should declare it."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from engine import connectors
from engine.config import load_config
from engine.connectors import CORE, reads
from engine.packs import summary
from engine.plugin_manifest import Provides
from engine.storage import Store
from tests.test_sign_in import signing as signing  # noqa: F401 - the fixture
from tests.test_sign_in_sources import READING, _app


def test_a_declaration_of_what_a_connector_reads_comes_before_its_name():
    assert reads("p18/stream", {"p18/stream": "mail"}) == ["mail"]
    assert reads("p18/stream", {"p18/stream": "calendar"}) == ["calendar"]
    assert reads("p18/calendar", {"p18/calendar": "mail"}) == ["mail"]  # the declaration wins over the name
    assert reads("p18/stream", {"p18/other": "mail"}) == []  # a declaration belongs to its own connector
    assert [CORE[name].reads for name in ("mailbox", "calendar", "folder", "feed")] == ["mail", "calendar", None, None]
    provides = {
        "connectors": ["p18/stream", "p18/diary"],
        "connector_reads": {"p18/stream": "mail", "p18/diary": "calendar"},
    }
    assert summary(provides, {})["reads"] == ["mail", "calendar"]


def test_a_connector_that_declares_nothing_is_read_by_its_name_and_the_log_says_to_declare_it(caplog):
    connectors._guessed.clear()
    with caplog.at_level("WARNING", logger="engine.connectors"):
        assert reads("p18/inbox") == ["mail"]
        assert reads("p18/inbox") == ["mail"]
        assert reads("p18/stream") == []
        assert reads("p18/diary", {"p18/diary": "calendar"}) == ["calendar"]
    said = [r.getMessage() for r in caplog.records]
    assert len(said) == 1 and "p18/inbox" in said[0] and "declare" in said[0]


#: A connector whose name says nothing about mail.
STREAM = READING.replace("p18/inbox", "p18/stream").replace("poll=poll_inbox)", "poll=poll_inbox, reads='mail')")


def _streaming(ws, in_code=True, in_manifest=True):
    """The add-on with a source of mail whose name doesn't say so, declaring what it reads in the code, the manifest
    or both."""
    plugin = ws.root / "plugins" / "p18"
    (plugin / "fixture.py").write_text(STREAM if in_code else STREAM.replace(", reads='mail'", ""))
    manifest = yaml.safe_load((plugin / "plugin.yaml").read_text())
    manifest["provides"]["connectors"] = ["p18/stream"]
    if in_manifest:
        manifest["provides"]["connector_reads"] = {"p18/stream": "mail"}
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))


def _steps(c, api):
    return {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}


def test_an_add_on_that_declares_what_its_connector_reads_is_a_mail_service_whatever_the_connector_is_called(
    signing,  # noqa: F811
):
    ws, cfg, store, _ = signing
    store.close()
    _streaming(ws)
    c, api = _app(ws, cfg)
    found = next(s for s in _steps(c, api).values() if s["sign_in"] == "p18/service")
    assert found["group"] == "mail" and not found["counted"]
    # A source of that connector, read by the workspace, is mail being read.
    assert not _steps(c, api)["mail"]["done"]
    path = ws.config_dir / "watch.yaml"
    config = yaml.safe_load(path.read_text()) or {}
    config["sources"] = [
        {"id": "mine", "label": "My mail", "connector": "p18/stream", "settings": {"folders": ["INBOX"]}}
    ]
    path.write_text(yaml.safe_dump(config))
    c, api = _app(ws, cfg)
    assert _steps(c, api)["mail"]["done"]
    assert [s["reads"] for s in c.get(f"{api}/watch").json() if s["id"] == "mine"] == [["mail"]]


def test_without_a_declaration_a_connector_whose_name_says_nothing_is_not_a_mail_service(signing):  # noqa: F811
    ws, cfg, store, _ = signing
    store.close()
    _streaming(ws, in_code=False, in_manifest=False)
    c, api = _app(ws, cfg)
    found = next(s for s in _steps(c, api).values() if s["sign_in"] == "p18/service")
    assert found["group"] == "done"


def _plugin(ws):
    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    try:
        return store.plugins.status["p18"].reason, store.plugins.active("p18")
    finally:
        store.close()


def test_what_the_code_and_the_manifest_say_a_connector_reads_must_match(signing):  # noqa: F811
    ws, _, store, _ = signing
    store.close()
    _streaming(ws, in_code=True, in_manifest=False)
    reason, active = _plugin(ws)
    assert not active and "connector reads do not match" in reason
    _streaming(ws, in_code=False, in_manifest=True)
    reason, active = _plugin(ws)
    assert not active and "connector reads do not match" in reason
    _streaming(ws)
    assert _plugin(ws)[1]


def test_the_manifest_names_only_its_own_connectors_and_a_kind_of_reading():
    assert Provides(connectors=["p18/stream"], connector_reads={"p18/stream": "mail"}).connector_reads
    assert Provides(connectors=["p18/*"], connector_reads={"p18/stream": "calendar"}).connector_reads
    for bad in ({"p18/other": "mail"}, {"p18/stream": "files"}):
        with pytest.raises(ValidationError):
            Provides(connectors=["p18/stream"], connector_reads=bad)
