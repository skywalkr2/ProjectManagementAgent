"""Notices that something needs the person (design 7.19): off until turned on, only for Today's Decide group, a count
and never what an item is about, quiet hours, one notice for what is new, and "Send me a test", against a fake
address (no real network)."""

from datetime import timedelta

import httpx
import pytest

import engine.net
from engine import notifications
from engine.config import load_config
from engine.today import zone
from tests.conftest import DEMO_B  # noqa: F401
from tests.test_setup import client, make
from tests.test_today_queue import api, hand_in  # noqa: F401  (the fixture and the helper the queue tests use)

HOST = "notes.example.com"
ADDRESS = f"https://{HOST}/hook/abc123"
SECRET_PATH = "an-address-nobody-else-has"
ENV = {
    "COCKPIT__UI__NOTIFICATIONS__ENABLED": "true",
    "COCKPIT__UI__NOTIFICATIONS__WEBHOOK": "env:NOTE_ADDRESS",
    "COCKPIT__UI__NOTIFICATIONS__WEBHOOK_FORMAT": "json",
    "NOTE_ADDRESS": ADDRESS,
}


class Fake:
    """The address that notes are sent to: it records what it was sent and answers as told."""

    def __init__(self, status=200):
        self.status = status
        self.sent: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        return httpx.Response(self.status)

    def bodies(self):
        return [r.content.decode() for r in self.sent]


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(f))
    return f


def setup_env(tmp_path, extra=None, drop=()):
    ws, cfg, store = make(tmp_path)
    env = {k: v for k, v in {**ENV, **(extra or {})}.items() if k not in drop}
    return ws, load_config(ws.config_dir, env=env), store, env


def at(cfg, hour, minute=0):
    from datetime import datetime

    return datetime(2026, 10, 20, hour, minute, tzinfo=zone(cfg))


def keys_are(monkeypatch, keys):
    monkeypatch.setattr(notifications, "decide_keys", lambda *a, **k: list(keys))


# ---- what is set, and what is sent ---------------------------------------------------------------


def test_notices_are_off_by_default_and_nothing_is_sent(tmp_path, fake, monkeypatch):
    ws, _, store = make(tmp_path)
    cfg = load_config(ws.config_dir, env={})
    assert cfg.ui.notifications.enabled is False and cfg.ui.notifications.webhook is None
    keys_are(monkeypatch, ["question:Q1"])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 12)) is None
    assert fake.sent == []


def test_on_with_no_address_sends_nothing(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path, drop=("COCKPIT__UI__NOTIFICATIONS__WEBHOOK",))
    keys_are(monkeypatch, ["question:Q1"])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 12), env=env) is None
    assert fake.sent == []


def test_a_new_decision_sends_one_note_with_a_count_and_nothing_about_the_item(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path)
    keys_are(monkeypatch, ["question:Q1", "question:Q2"])
    sent = notifications.deliver_if_due(ws, store, cfg, at(cfg, 12), env=env)
    assert sent is not None and sent.ok
    assert len(fake.sent) == 1
    request = fake.sent[0]
    assert str(request.url) == ADDRESS and request.method == "POST"
    assert '"text": "2 decisions waiting for you"' in fake.bodies()[0]
    assert "Q1" not in fake.bodies()[0] and "question" not in fake.bodies()[0]
    # The same items are not told again, a restart included (what was told is kept on disk).
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 13), env=env) is None
    assert len(fake.sent) == 1


def test_one_item_is_worded_as_one_and_the_wording_is_a_setting(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path, {"COCKPIT__UI__NOTIFICATIONS__MESSAGE_ONE": "One for you"})
    keys_are(monkeypatch, ["question:Q1"])
    notifications.deliver_if_due(ws, store, cfg, at(cfg, 12), env=env)
    assert "One for you" in fake.bodies()[0]


def test_only_a_new_item_sends_another_note_with_how_many_wait_now(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path)
    keys_are(monkeypatch, ["question:Q1"])
    notifications.deliver_if_due(ws, store, cfg, at(cfg, 12), env=env)
    keys_are(monkeypatch, ["question:Q1", "question:Q2", "question:Q3"])
    notifications.deliver_if_due(ws, store, cfg, at(cfg, 12, 5), env=env)
    assert len(fake.sent) == 2 and "3 decisions waiting for you" in fake.bodies()[1]
    # An item that is dealt with sends nothing; when it is gone and comes back, it is new again.
    keys_are(monkeypatch, ["question:Q1", "question:Q3"])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 12, 10), env=env) is None
    keys_are(monkeypatch, [])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 12, 15), env=env) is None
    keys_are(monkeypatch, ["question:Q1"])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 12, 20), env=env) is not None
    assert len(fake.sent) == 3


def test_nothing_is_sent_in_quiet_hours_and_what_came_up_goes_out_once_when_they_end(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path)
    assert (cfg.ui.notifications.quiet_hours.start, cfg.ui.notifications.quiet_hours.end) == ("21:00", "07:00")
    keys_are(monkeypatch, ["question:Q1"])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 23), env=env) is None
    keys_are(monkeypatch, ["question:Q1", "question:Q2"])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 3), env=env) is None
    assert fake.sent == []
    assert notifications.quiet_now(cfg, at(cfg, 23)) and not notifications.quiet_now(cfg, at(cfg, 7))
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 7), env=env) is not None
    assert len(fake.sent) == 1 and "2 decisions waiting for you" in fake.bodies()[0]


def test_quiet_hours_are_a_setting(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(
        tmp_path,
        {
            "COCKPIT__UI__NOTIFICATIONS__QUIET_HOURS__START": "12:00",
            "COCKPIT__UI__NOTIFICATIONS__QUIET_HOURS__END": "13:00",
        },
    )
    keys_are(monkeypatch, ["question:Q1"])
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 12, 30), env=env) is None
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 13), env=env) is not None


def test_a_note_that_could_not_be_delivered_is_tried_again_later_and_the_screen_says_why(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path)
    keys_are(monkeypatch, ["question:Q1"])
    fake.status = 500
    first = notifications.deliver_if_due(ws, store, cfg, at(cfg, 12), env=env)
    assert first is not None and not first.ok
    assert notifications.last_problem(ws)
    # Not again until the wait has passed, and not marked as told.
    assert notifications.deliver_if_due(ws, store, cfg, at(cfg, 12, 5), env=env) is None
    assert len(fake.sent) == 1
    fake.status = 200
    later = at(cfg, 12) + timedelta(minutes=cfg.ui.notifications.retry_minutes)
    assert notifications.deliver_if_due(ws, store, cfg, later, env=env).ok
    assert notifications.last_problem(ws) is None and len(fake.sent) == 2


def test_the_plain_form_sends_the_words_alone(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path, {"COCKPIT__UI__NOTIFICATIONS__WEBHOOK_FORMAT": "plain"})
    keys_are(monkeypatch, ["question:Q1"])
    notifications.deliver_if_due(ws, store, cfg, at(cfg, 12), env=env)
    assert fake.bodies() == ["1 decision waiting for you"]
    assert fake.sent[0].headers["content-type"].startswith("text/plain")


def test_a_note_goes_only_to_the_persons_own_address_over_https(tmp_path, fake, monkeypatch):
    ws, cfg, store, env = setup_env(tmp_path, {"NOTE_ADDRESS": f"http://{HOST}/hook"})
    keys_are(monkeypatch, ["question:Q1"])
    sent = notifications.deliver_if_due(ws, store, cfg, at(cfg, 12), env=env)
    assert sent is not None and not sent.ok and fake.sent == []


# ---- what counts ---------------------------------------------------------------------------------


def test_only_the_decide_group_counts_core_lines_and_add_on_lines_alike(tmp_path, monkeypatch):
    from types import SimpleNamespace as N

    ws, cfg, store, _ = setup_env(tmp_path)
    lines = [N(key="question:Q1", group="decide"), N(key="review:R1", group="review"), N(key="risk:1", group="risk")]
    monkeypatch.setattr("engine.today_queue.queue", lambda *a, **k: lines)
    plugin = [("p", N(id="L1", group="decide")), ("p", N(id="L2", group="review"))]
    monkeypatch.setattr(type(store.plugins), "today", lambda self: plugin)
    assert notifications.decide_keys(ws, store, cfg, at(cfg, 12)) == ["question:Q1", "plugin:p:L1"]


def test_a_real_decision_on_today_is_what_the_open_screen_is_told_about(api, tmp_path):  # noqa: F811
    c, base, worker = api
    hand_in(c, base, worker, "decision-for-pm")
    decision = next(line for line in c.get(f"{base}/today/queue").json() if line["kind"] == "decision")
    ws = worker.ws
    cfg = load_config(ws.config_dir, env=ENV)
    found = notifications.waiting(ws, worker.store, cfg, worker.now())
    assert decision["key"] in found.keys
    assert found.message == notifications.message_for(cfg, found.count)
    assert decision["text"] not in found.message


# ---- the screens' side ---------------------------------------------------------------------------


def fingerprint(c, base):
    return c.get(f"{base}/settings").json()["fingerprint"]


def test_the_view_says_what_is_set_and_that_mail_to_yourself_comes_with_mail_sending(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    view = c.get(f"{base}/notifications").json()
    assert view["enabled"] is False and view["webhook"] == {"where": "none", "name": None}
    assert view["mail_ready"] is False and view["problem"] is None
    assert c.get(f"{base}/notifications/waiting").json() == {"browser": False, "keys": [], "message": ""}


def test_an_address_typed_on_the_screen_is_kept_as_a_reference_and_never_sent_back(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    done = c.post(
        f"{base}/notifications/webhook",
        json={"value": f"https://{HOST}/{SECRET_PATH}", "fingerprint": fingerprint(c, base)},
    )
    assert done.status_code == 200, done.text
    assert SECRET_PATH not in done.text
    kept = ws.private_dir / "keys" / "notify-webhook"
    assert SECRET_PATH in kept.read_text()
    held = load_config(ws.config_dir, env={}).ui.notifications.webhook
    assert held == f"file:{kept.resolve()}"
    assert SECRET_PATH not in c.get(f"{base}/notifications").text + c.get(f"{base}/settings").text
    assert c.get(f"{base}/notifications").json()["webhook"] == {"where": "kept", "name": None}
    # Nothing but the keys folder holds it.
    assert not [
        p
        for p in ws.root.rglob("*")
        if p.is_file()
        and (ws.private_dir / "keys").resolve() not in p.resolve().parents
        and SECRET_PATH.encode() in p.read_bytes()
    ]


def test_a_reference_the_person_names_is_kept_as_it_is(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    done = c.post(
        f"{base}/notifications/webhook", json={"reference": "env:NOTE_ADDRESS", "fingerprint": fingerprint(c, base)}
    )
    assert done.status_code == 200, done.text
    assert load_config(ws.config_dir, env={}).ui.notifications.webhook == "env:NOTE_ADDRESS"
    assert c.get(f"{base}/notifications").json()["webhook"] == {"where": "env", "name": "NOTE_ADDRESS"}


def test_send_me_a_test_sends_the_test_note_to_the_address_and_reports_how_it_went(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("NOTE_ADDRESS", ADDRESS)
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    assert (
        c.post(
            f"{base}/notifications/webhook", json={"reference": "env:NOTE_ADDRESS", "fingerprint": fingerprint(c, base)}
        ).status_code
        == 200
    )
    ok = c.post(f"{base}/notifications/test", json={"target": "webhook"}).json()
    assert ok["ok"] is True and ok["problem"] is None
    assert len(fake.sent) == 1 and str(fake.sent[0].url) == ADDRESS
    assert "This is a test" in fake.bodies()[0]
    fake.status = 500
    bad = c.post(f"{base}/notifications/test", json={"target": "webhook"}).json()
    assert bad["ok"] is False and bad["problem"]
    assert c.get(f"{base}/notifications").json()["problem"] == bad["problem"]


def test_a_test_with_no_address_says_so(tmp_path, fake):
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    answer = c.post(f"{base}/notifications/test", json={"target": "webhook"}).json()
    assert answer["ok"] is False and "no address" in answer["problem"].lower() and fake.sent == []


def test_the_browsers_test_answers_with_the_words_and_sends_nothing(tmp_path, fake):
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    answer = c.post(f"{base}/notifications/test", json={"target": "browser"}).json()
    assert answer["ok"] is True and "This is a test" in answer["message"] and fake.sent == []


def test_the_open_screen_is_told_about_decisions_only_while_notices_and_the_browser_are_on(tmp_path, monkeypatch):
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    keys_are(monkeypatch, ["question:Q1"])
    assert c.get(f"{base}/notifications/waiting").json()["browser"] is False
    assert (
        c.post(
            f"{base}/settings",
            json={"changes": {"ui.notifications.enabled": True}, "fingerprint": fingerprint(c, base)},
        ).status_code
        == 200
    )
    now = c.get(f"{base}/notifications/waiting").json()
    assert now["keys"] == ["question:Q1"] and now["message"] == "1 decision waiting for you"


def test_the_worker_sends_the_notice_from_the_settings_as_the_files_hold_them(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("NOTE_ADDRESS", ADDRESS)
    ws, cfg, store = make(tmp_path)
    c, base = client(ws, cfg, store)
    keys_are(monkeypatch, ["question:Q1"])
    fp = fingerprint(c, base)
    assert (
        c.post(f"{base}/notifications/webhook", json={"reference": "env:NOTE_ADDRESS", "fingerprint": fp}).status_code
        == 200
    )
    assert (
        c.post(
            f"{base}/settings",
            json={
                "changes": {
                    "ui.notifications.enabled": True,
                    "ui.notifications.quiet_hours.start": "01:00",
                    "ui.notifications.quiet_hours.end": "02:00",
                },
                "fingerprint": fingerprint(c, base),
            },
        ).status_code
        == 200
    )
    worker = c.app.state.worker
    worker.now = lambda: at(cfg, 12)
    assert worker.notify_if_due() is True
    assert len(fake.sent) == 1
    assert worker.notify_if_due() is False and len(fake.sent) == 1
