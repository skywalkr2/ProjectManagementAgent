"""Asking the assistant (design 6.25): answers come only from the user guide, the settings, what the install can do
and the records, with the words they rest on; a setting is suggested and the person applies it; something the app
can't do becomes a report the person sends."""

import json

import pytest
from fastapi.testclient import TestClient

from engine.ai.adapters.stub import set_responder
from engine.config import load_config
from engine.help import chosen_sections, guide_sections, settings_lines
from tests.conftest import DEMO_B

BACKUP_WORDS = "it must exist, be outside the workspace and be writable"


@pytest.fixture
def app(tmp_path):
    from api.app import create_app
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    application = create_app(ws, cfg, "t", start_worker=False)
    c = TestClient(application)
    c.headers["Authorization"] = "Bearer t"
    yield ws, c, cfg.server.base_path.rstrip("/") + "/api", application.state.worker
    set_responder(None)


def answer_with(*ops):
    seen = []

    def respond(task):
        seen.append(task)
        return json.dumps({"summary": "Answered the question.", "ops": list(ops)})

    set_responder(respond)
    return seen


def test_the_guide_sections_for_a_question_are_chosen_by_its_words():
    titles = [s.title for s in guide_sections()]
    assert "Backups" in titles and "Settings" in titles
    assert chosen_sections("How do I set up backups to a drive?")[0].title == "Backups"
    assert chosen_sections("zzz qqq") == guide_sections()[:1]


def test_settings_in_the_material_never_say_where_keys_come_from(tmp_path):
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    lines = "\n".join(settings_lines(load_config(ws.config_dir, env={})))
    assert "storage.backups.keep" in lines and "LOWCOST_AI_KEY" not in lines and "auth" not in lines


def test_an_answer_rests_on_quoted_words_and_suggests_a_setting(app):
    ws, c, api, worker = app
    seen = answer_with(
        {"op": "answer", "text": "Choose a backup folder in Settings.", "cites": [{"quote": BACKUP_WORDS}]},
        {"op": "setting.propose", "key": "storage.backups.keep", "value": 30, "why": "Keep a month of backups."},
    )
    asked = c.post(f"{api}/ask", json={"question": "How do I keep a month of backups?"}).json()["id"]
    worker.run_pending()
    packet = seen[-1]
    assert "Backups" in packet.request and "<question>" in packet.request and "LOWCOST_AI_KEY" not in packet.stable
    found = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)
    assert found["answer"]["text"] == "Choose a backup folder in Settings."
    assert found["answer"]["cites"] == [{"quote": BACKUP_WORDS, "source": "help"}]
    proposal = found["proposals"][0]
    assert proposal["key"] == "storage.backups.keep" and proposal["status"] == "open"
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    applied = c.post(
        f"{api}/setting-proposals/{proposal['id']}/apply",
        json={"fingerprint": fingerprint, "read_version": proposal["version"]},
    )
    assert applied.status_code == 200, applied.text
    assert load_config(ws.config_dir, env={}).storage.backups.keep == 30
    after = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)
    assert after["proposals"][0]["status"] == "applied"


def test_words_that_arent_in_the_material_are_refused(app):
    _, c, api, worker = app
    answer_with({"op": "answer", "text": "Press the magic button.", "cites": [{"quote": "press the magic button"}]})
    asked = c.post(f"{api}/ask", json={"question": "How do I make it faster?"}).json()["id"]
    worker.run_pending()
    found = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)
    assert found["answer"] is None


def test_a_setting_the_screens_dont_change_is_never_suggested(app):
    _, c, api, worker = app
    answer_with(
        {"op": "answer", "text": "The port is set in its file.", "cites": [{"quote": BACKUP_WORDS}]},
        {"op": "setting.propose", "key": "server.port", "value": 9000, "why": "Another port."},
    )
    asked = c.post(f"{api}/ask", json={"question": "Can I change the port backups use?"}).json()["id"]
    worker.run_pending()
    found = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)
    assert found["answer"] is not None and found["proposals"] == []


def test_something_the_app_cant_do_becomes_a_report_to_send(app):
    _, c, api, worker = app
    answer_with(
        {"op": "answer", "text": "The app can't do that yet; here is a report.", "cites": [{"quote": BACKUP_WORDS}]},
        {"op": "report.draft", "title": "Back up to two folders at once", "text": "People want two copies."},
    )
    asked = c.post(f"{api}/ask", json={"question": "Can backups go to a printer?"}).json()["id"]
    worker.run_pending()
    report = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)["reports"][0]
    assert report["status"] == "draft" and report["title"] == "Back up to two folders at once"
    sent = c.post(f"{api}/reports/{report['id']}/sent", json={"read_version": report["version"]})
    assert sent.status_code == 200
    assert next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)["reports"][0]["status"] == "sent"
