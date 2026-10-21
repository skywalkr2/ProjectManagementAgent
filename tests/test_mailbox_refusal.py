"""A mail server's sign-in refusal reaches the screen in plain words: classified by rules, the advice named by a
wording key, the server's own words kept only as quoted text with addresses shortened to their domain."""

import imaplib
import json
from pathlib import Path

import pytest
import yaml

from engine.connectors import ConnectorContext, ConnectorError
from engine.connectors.imap_refusal import RULES, imap_problem
from engine.connectors.mailbox import MailboxSettings, read_mailbox
from tests.test_calendar_mail import N

WORDS = json.loads((Path(__file__).parents[1] / "web" / "src" / "wording" / "en.json").read_text(encoding="utf-8"))
ADVICE = yaml.safe_load((Path(__file__).parents[1] / "engine" / "defaults" / "source_advice.yaml").read_text("utf-8"))


def refusing(reply):
    class Refusing:
        def __init__(self, host, port, ssl_context=None, timeout=None):
            pass

        def login(self, user, password):
            raise imaplib.IMAP4.error(reply)

        def logout(self):
            pass

    return Refusing


def refused(monkeypatch, tmp_path, reply) -> ConnectorError:
    monkeypatch.setattr(imaplib, "IMAP4_SSL", refusing(reply))
    monkeypatch.setenv("MAIL_PASSWORD", "wrong")
    settings = MailboxSettings(host=N["mail_host"], user=N["mail_user"], password="env:MAIL_PASSWORD")
    with pytest.raises(ConnectorError) as raised:
        read_mailbox(settings, {}, ConnectorContext(tmp_path))
    return raised.value


def test_a_service_that_wants_an_app_password_says_so_without_the_raw_reply(monkeypatch, tmp_path):
    reply = b"[ALERT] Application-specific password required: support.example.com/accounts/answer/185833"
    error = refused(monkeypatch, tmp_path, reply)
    assert error.kind == "auth" and error.advice_key == "sources.advice.create_app_password"
    assert "b'" not in error.detail and "support.example.com/accounts" not in error.detail
    assert "support.example.com" in error.detail and "Application-specific password required" in error.detail
    assert error.detail.startswith("the mail server refused the sign-in") and "“" in error.detail


def test_the_server_busy_is_an_outage_with_its_own_advice(monkeypatch, tmp_path):
    error = refused(monkeypatch, tmp_path, "[UNAVAILABLE] Mailbox under maintenance")
    assert (error.kind, error.advice_key) == ("outage", "sources.advice.retry_later")


def test_a_refusal_no_rule_names_shows_the_servers_words_and_asks_for_a_look(monkeypatch, tmp_path):
    error = refused(monkeypatch, tmp_path, "something nobody expected")
    assert (error.kind, error.advice_key) == ("auth", "sources.advice.review_server_message")
    assert "something nobody expected" in error.detail


def test_a_long_reply_is_cut_inside_its_quotes(monkeypatch, tmp_path):
    error = refused(monkeypatch, tmp_path, "[AUTHENTICATIONFAILED] " + "word " * 400)
    assert error.detail.endswith("”.") and len(error.detail) < 500


def test_every_advice_the_classifier_can_give_has_words_on_the_screen_and_for_the_server():
    from api.screen_text import problems

    keys = {imap_problem(f"NO {r['phrase']}", "mail.example.com").advice_key for r in RULES}
    keys |= {imap_problem(r, "mail.example.com").advice_key for r in ("NO [UNAVAILABLE] x", "NO [PRIVACYREQUIRED] x")}
    keys |= {imap_problem("NO [AUTHENTICATIONFAILED] x", "m").advice_key, imap_problem("", "m").advice_key}
    assert keys >= {"create_app_password", "review_server_message", "check_credentials", "retry_later"}
    for key in keys:
        sentence = WORDS[f"sources.advice.{key}"]
        assert sentence == ADVICE[f"sources.advice.{key}"], key  # one sentence, in both sheets
        assert not problems(sentence), key
    assert "password box" in WORDS["sources.advice.create_app_password"]
    assert "Connections" in WORDS["sources.advice.create_app_password"]


def _mailbox_workspace(tmp_path, monkeypatch, reply):
    from engine.config import load_config
    from engine.storage import Store
    from engine.workspace import init_workspace
    from tests.conftest import DEMO_B

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    mailbox = {"host": N["mail_host"], "user": N["mail_user"], "password": "env:MAIL_PASSWORD"}
    source = {"id": "m", "connector": "mailbox", "label": "Work mail", "settings": mailbox}
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": [source]}))
    cfg = load_config(ws.config_dir, env={})
    monkeypatch.setattr(imaplib, "IMAP4_SSL", refusing(reply))
    monkeypatch.setenv("MAIL_PASSWORD", "wrong")
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def test_a_failed_read_keeps_the_advice_and_the_problem_leaves_out_the_generic_step(tmp_path, monkeypatch):
    from engine import watch

    ws, cfg, store = _mailbox_workspace(tmp_path, monkeypatch, b"[ALERT] Application-specific password required")
    try:
        result = watch.refresh(ws, store, cfg, "m")
        assert result.outcome == "failed"
        last = watch.last_run(store, "m")
        assert last.data["error_advice"] == "sources.advice.create_app_password"
        text = watch.problem_text(store, "m")
        assert "Sign in to it again" not in text and "password box" in text and "Application-specific" in text
        assert "Sign in to it again" not in (result.problem or "")
    finally:
        store.close()


def test_the_sources_list_carries_the_advice_key_for_the_screen(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine import watch

    ws, cfg, store = _mailbox_workspace(tmp_path, monkeypatch, b"[ALERT] Application-specific password required")
    watch.refresh(ws, store, cfg, "m")
    store.close()
    client = TestClient(create_app(ws, cfg, "t", start_worker=False))
    client.headers["Authorization"] = "Bearer t"
    (listed,) = client.get(cfg.server.base_path.rstrip("/") + "/api/watch").json()
    assert listed["last"]["error_advice"] == "sources.advice.create_app_password"
    assert listed["last"]["error_kind"] == "auth" and "\u201c" in listed["last"]["error"]
