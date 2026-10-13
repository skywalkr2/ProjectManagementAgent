"""Asking the assistant (design 6.25): answers come only from the user guide, the settings, what the install can do
and the records, with the words they rest on; a setting is suggested and the person applies it; something the app
can't do becomes a report the person sends."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from api.screen_text import problems
from engine import settings as config_screens
from engine.ai.adapters.stub import set_responder
from engine.config import load_config
from engine.help import askable_settings, chosen_sections, guide_sections, settings_lines
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


def code_of(cfg, key):
    """The setting code Ask's material gives a setting, read from its line as the assistant reads it."""
    item = next(i for i in askable_settings(cfg) if i.key == key)
    line = next(x for x in settings_lines(cfg) if x.startswith(config_screens.screen_name(item) + ":"))
    return line.rsplit("Setting code: ", 1)[1]


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
    cfg = load_config(ws.config_dir, env={})
    lines = "\n".join(settings_lines(cfg))
    assert "LOWCOST_AI_KEY" not in lines and "auth" not in lines


def test_a_setting_handle_is_short_and_stays_the_same():
    key = "storage.backups.keep"
    assert config_screens.handle_of(key) == config_screens.handle_of(key)
    assert re.fullmatch(r"s-[0-9a-f]{6}", config_screens.handle_of(key))
    assert config_screens.handle_of(key) != config_screens.handle_of("storage.backups.every_hours")


def test_the_material_names_settings_by_a_code_and_never_by_a_key(tmp_path):
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    shown = askable_settings(cfg)
    lines = settings_lines(cfg)
    assert len(lines) == len(shown) > 20
    assert all(re.search(r"Setting code: s-[0-9a-f]{6,}$", line) for line in lines)
    text = "\n".join(lines)
    leaked = [i.key for i in shown if re.search(r"(?<![\w.])" + re.escape(i.key) + r"(?![\w])", text)]
    assert leaked == []
    assert "Key for a setting proposal" not in text


def test_a_handle_resolves_among_the_current_settings_and_an_unknown_one_is_refused(tmp_path):
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    shown = askable_settings(load_config(ws.config_dir, env={}))
    key = "storage.backups.keep"
    assert config_screens.resolve_handle(config_screens.handle_of(key), shown).key == key
    with pytest.raises(config_screens.SettingsError, match="isn't one of the settings"):
        config_screens.resolve_handle("s-000000", shown)
    with pytest.raises(config_screens.SettingsError):
        config_screens.resolve_handle(key, shown)  # a key is not a handle


def test_handles_that_collide_get_longer_so_each_names_one_setting(monkeypatch):
    first, second, third = "storage.backups.keep", "storage.backups.every_hours", "ui.toast_seconds"
    real = config_screens._digest

    def colliding(key):
        return "abcdef" + real(key)[6:] if key in (first, second) else real(key)

    monkeypatch.setattr(config_screens, "_digest", colliding)
    found = config_screens.handles([first, second, third])
    assert found[first] != found[second]
    assert len(found[first]) > len("s-") + 6 and len(found[second]) > len("s-") + 6
    assert found[third] == config_screens.handle_of(third)
    assert config_screens.handles([first, second, third]) == found  # the same on every call
    items = [i for i in askable_settings(load_config(DEMO_B / "config", env={})) if i.key in (first, second, third)]
    assert {config_screens.resolve_handle(h, items).key for h in found.values()} == {first, second, third}


def test_an_answer_rests_on_quoted_words_and_suggests_a_setting(app):
    ws, c, api, worker = app
    seen = answer_with(
        {"op": "answer", "text": "Choose a backup folder in Settings.", "cites": [{"quote": BACKUP_WORDS}]},
        {
            "op": "setting.propose",
            "setting": code_of(load_config(ws.config_dir, env={}), "storage.backups.keep"),
            "value": 30,
            "why": "Keep a month of backups.",
        },
    )
    asked = c.post(f"{api}/ask", json={"question": "How do I keep a month of backups?"}).json()["id"]
    worker.run_pending()
    packet = seen[-1]
    assert "Backups" in packet.request and "<question>" in packet.request and "LOWCOST_AI_KEY" not in packet.stable
    found = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)
    assert found["answer"]["text"] == "Choose a backup folder in Settings."
    assert found["answer"]["cites"] == [{"quote": BACKUP_WORDS, "source": "help"}]
    proposal = found["proposals"][0]
    assert proposal["key"] == "storage.backups.keep" and proposal["status"] == "open"  # kept as the resolved key
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
    ws, c, api, worker = app
    answer_with(
        {"op": "answer", "text": "The port is set in its file.", "cites": [{"quote": BACKUP_WORDS}]},
        {
            "op": "setting.propose",
            "setting": code_of(load_config(ws.config_dir, env={}), "server.port"),
            "value": 9000,
            "why": "Another port.",
        },
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


def test_a_suggestion_naming_an_unknown_setting_code_is_refused(app):
    ws, c, api, worker = app
    answer_with(
        {"op": "answer", "text": "Keep more backups.", "cites": [{"quote": BACKUP_WORDS}]},
        {"op": "setting.propose", "setting": "s-000000", "value": 30, "why": "Keep a month of backups."},
    )
    before = load_config(ws.config_dir, env={}).storage.backups.keep
    asked = c.post(f"{api}/ask", json={"question": "How do I keep a month of backups?"}).json()["id"]
    worker.run_pending()
    found = next(a for a in c.get(f"{api}/asks").json() if a["id"] == asked)
    assert found["proposals"] == []
    from types import SimpleNamespace

    from engine.applier import setting_problem

    why = setting_problem(SimpleNamespace(path=ws.root / "cockpit.db"), "s-000000", 30)
    assert why and "setting code" in why and not problems(why)
    assert load_config(ws.config_dir, env={}).storage.backups.keep == before


def test_an_answer_that_cites_a_settings_line_shows_no_settings_key(app):
    ws, c, api, worker = app
    cfg = load_config(ws.config_dir, env={})
    item = next(i for i in askable_settings(cfg) if i.key == "storage.backups.keep")
    line = next(x for x in settings_lines(cfg) if x.startswith(config_screens.screen_name(item) + ":"))
    name = config_screens.screen_name(item)
    quoted = line  # the whole line, as an answer may cite it
    seen = answer_with(
        {"op": "answer", "text": f"Change {name} in Settings.", "cites": [{"quote": quoted}]},
        {"op": "setting.propose", "setting": code_of(cfg, item.key), "value": 30, "why": f"{name} says how many."},
    )
    asked = c.post(f"{api}/ask", json={"question": "How do I keep a month of backups?"}).json()["id"]
    worker.run_pending()
    assert item.key not in seen[-1].stable and item.key not in seen[-1].request
    response = c.get(f"{api}/asks")  # typed as screen text, so the wording check refuses a key in it
    assert response.status_code == 200, response.text
    found = next(a for a in response.json() if a["id"] == asked)
    assert found["answer"]["cites"][0]["quote"] == quoted
    shown = json.dumps([found["answer"], [p["why"] for p in found["proposals"]]])
    assert item.key not in shown
