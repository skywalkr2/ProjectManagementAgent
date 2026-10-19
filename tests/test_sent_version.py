"""Learning from the sent version (design 6.35): what the person copied is kept exactly, the message that reaches the
sent folder is matched to it by rules alone (same recipient, inside the window, alike enough), and the difference
between the two is a `draft_edited` signal the learning loop reads like an edit made in the app. A copy no sent message
matches becomes one Today line, "Did your message to <name> go out?", only when a sent folder is being read. Names,
addresses and numbers come from the fixtures and the settings."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine import sent_version, watch
from engine.followups import mark_sent, sections, unmark_sent
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.sent-version")
TOKEN = "sent-version-token"
MY_ADDRESS = "the.person@example.com"
OTHER_ADDRESS = "another.recipient@example.com"
DRAFT = "The interior proofs ship on November 3 (the printer's published schedule)."
SENT_FOLDER = "sent"


def person(role: str) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


EDITOR = person("Editor")  # the fixture gives this person an address and open questions
OTHER = person("Cover designer")


def me(cfg) -> str:
    return cfg.workspace.user.person


def address_of(record: dict) -> str:
    return (record.get("how_to_reach") or {}).get("email") or OTHER_ADDRESS  # the second recipient's is set below


def mail(to: dict | None, body: str, *, address: str | None = None, subject: str = "Re: Interior proofs") -> str:
    """A message as a mail source writes its text: the header lines, a blank line, then the body."""
    name, email = (to["full_name"], address_of(to)) if to is not None else ("Someone", address or OTHER_ADDRESS)
    return "\n".join([f"From: The person <{MY_ADDRESS}>", f"To: {name} <{email}>", f"Subject: {subject}", "", body])


def _build(tmp_path, with_sent_folder: bool):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    if with_sent_folder:
        folder = tmp_path / "sent-mail"
        folder.mkdir()
        (ws.config_dir / "watch.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "sources": [
                        {
                            "id": SENT_FOLDER,
                            "connector": "folder",
                            "label": "Sent",
                            "first_run": "intake",
                            "author": ws.config(env={}).workspace.user.person,
                            "settings": {"path": str(folder)},
                        }
                    ],
                }
            )
        )
    cfg = ws.config(
        env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"},
        flags={"server.base_path": "/", "storage.backups.automatic": False},
    )
    return ws, cfg


def _addresses(store, cfg):
    with store.transaction() as tx:  # the person's own address and a second recipient's, as their records hold them
        for pid, address in ((me(cfg), MY_ADDRESS), (OTHER["id"], OTHER_ADDRESS)):
            found = tx.get("person", pid)
            reach = {**found.data.get("how_to_reach", {}), "email": address}
            tx.update("person", pid, {"how_to_reach": reach}, _TEST, read_version=found.version)


@pytest.fixture
def env(tmp_path):
    ws, cfg = _build(tmp_path, with_sent_folder=False)
    store = Store(ws.db_path, cfg=cfg)
    _addresses(store, cfg)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def env_sent(tmp_path):
    ws, cfg = _build(tmp_path, with_sent_folder=True)
    store = Store(ws.db_path, cfg=cfg)
    _addresses(store, cfg)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def api(tmp_path):
    ws, cfg = _build(tmp_path, with_sent_folder=True)
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.ws, client.cfg, client.store = ws, cfg, app.state.store
        _addresses(client.store, cfg)
        app.state.worker.now = lambda: NOW
        yield client


def settings(cfg):
    return cfg.steward.sent_match


def sent(env, *, to, body: str, at: datetime, folder: str = SENT_FOLDER, key: str | None = None) -> str:
    """A message the person sent, as taken in from the sent folder: a source whose change is their own work."""
    ws, cfg, store = env
    text = mail(to, body)
    with store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": at.isoformat(),
                "sent_at": at.isoformat(),
                "kind": "watched:mailbox",
                "title": "Re: Interior proofs",
                "content_hash": watch._keep_text(ws, text),
                "trust": "untrusted",
                "watched": {
                    "source": folder,
                    "key": key or f"<sent-{at.isoformat()}-{len(text)}@example.com>",
                    "change": "new",
                    "by_you": True,
                    "by_us": False,
                    "credited_to": me(cfg),
                },
            },
            _TEST,
        ).id


def follow_up(env, at: datetime, text: str | None = None):
    """The editor's follow-up, marked as sent at `at` (with `text` when the person edited it before sending);
    returns the message that was composed and the counts."""
    _, cfg, store = env
    section = next(s for s in sections(store, cfg, at.date()) if s.person == EDITOR["id"])
    counts = mark_sent(store, cfg, EDITOR["id"], sent_text=section.message if text is None else text, now=at)
    return section.message, counts


def copies(store) -> list:
    return store.read().list("copy")


def edited_signals(store) -> list:
    return [s for s in store.read().list("signal") if s.data["kind"] == "draft_edited"]


def match(env, now: datetime = NOW) -> list[str]:
    ws, cfg, store = env
    return sent_version.match_sent(ws, store, cfg, now)


# ---- a copy is kept --------------------------------------------------------------------------------------------------


def test_marking_a_follow_up_sent_keeps_the_text_exactly_as_copied_with_who_when_and_what_it_covered(env):
    ws, cfg, store = env
    at = NOW - timedelta(hours=3)
    message, counts = follow_up(env, at)
    (found,) = copies(store)
    assert found.data["kind"] == "follow_up" and found.data["person"] == EDITOR["id"]
    assert found.data["text"] == message and datetime.fromisoformat(found.data["at"]) == at
    assert found.data["questions"] == counts["question_ids"] and found.data["actions"] == counts["action_ids"]
    assert found.data["sent_source"] is None and found.data["settled"] is None


def test_the_text_kept_is_the_persons_own_wording_when_they_changed_it_before_copying(env):
    _, cfg, store = env
    own = "Hi, a few quick questions before Friday."
    follow_up(env, NOW - timedelta(hours=3), text=own)
    (found,) = copies(store)
    assert found.data["text"] == own


def test_marking_sent_with_nothing_waiting_keeps_no_copy_and_taking_the_mark_back_takes_the_copy_with_it(env):
    _, cfg, store = env
    _, counts = follow_up(env, NOW - timedelta(hours=3))
    assert len(copies(store)) == 1
    unmark_sent(store, EDITOR["id"], counts["question_ids"], counts["action_ids"])
    assert copies(store) == []
    assert mark_sent(store, cfg, "PER-NOBODY", now=NOW)["questions"] == 0 and copies(store) == []


def test_copying_a_drafted_reply_keeps_it_and_copying_it_again_moves_the_same_copy_forward(api):
    from tests.test_reply_lines import make_reply

    env = (api.ws, api.cfg, api.store)
    action = make_reply(env, received=NOW - timedelta(hours=9), subject="Interior proofs", reply=DRAFT)
    first = api.post(f"/api/replies/{action}/copied")
    assert first.status_code == 200, first.text
    (found,) = copies(api.store)
    assert first.json() == {"id": found.id}
    assert (found.data["kind"], found.data["person"], found.data["actions"], found.data["text"]) == (
        "reply",
        found.data["person"],
        [action],
        DRAFT,
    )
    assert found.data["person"] is not None and found.data["questions"] == []
    assert api.post(f"/api/replies/{action}/copied").json() == {"id": found.id}
    assert len(copies(api.store)) == 1


def test_copying_a_reply_that_is_not_owed_or_has_no_draft_is_refused(api):
    from tests.test_reply_lines import make_reply

    env = (api.ws, api.cfg, api.store)
    plain = api.store.read().list("action")[0].id
    assert api.post(f"/api/replies/{plain}/copied").status_code == 409
    assert api.post("/api/replies/ACT-NOPE/copied").status_code == 404
    bare = make_reply(env, received=NOW - timedelta(hours=9), subject="Cover proof", reply=None)
    assert api.post(f"/api/replies/{bare}/copied").status_code == 409
    assert copies(api.store) == []


# ---- a sent message matches it ---------------------------------------------------------------------------------------


def test_a_sent_message_that_differs_matches_its_copy_and_records_the_difference_as_a_draft_edit(env):
    ws, cfg, store = env
    message, counts = follow_up(env, NOW - timedelta(hours=5))
    wording = f"{message}\n\nOne more thing: please send the printer's contact."
    source = sent(env, to=EDITOR, body=wording, at=NOW - timedelta(hours=4))
    (copy_id,) = match(env)
    (found,) = copies(store)
    assert found.id == copy_id and found.data["sent_source"] == source and found.data["matched_at"]
    (signal,) = edited_signals(store)
    assert signal.data["note"] == wording
    assert set(signal.data["refs"]) == {EDITOR["id"], copy_id, *counts["question_ids"], *counts["action_ids"]}
    assert datetime.fromisoformat(signal.data["at"]) == NOW
    assert match(env) == [] and len(edited_signals(store)) == 1  # a second look changes nothing


def test_the_signal_names_the_changeset_and_run_that_wrote_the_questions(env):
    ws, cfg, store = env
    message, counts = follow_up(env, NOW - timedelta(hours=5))
    sent(env, to=EDITOR, body=message + "\n\nThanks, talk soon.", at=NOW - timedelta(hours=4))
    match(env)
    (signal,) = edited_signals(store)
    from engine.followups import _written_by

    assert (signal.data["changeset"], signal.data["run"]) == _written_by(store, counts["question_ids"])


def test_a_sent_message_that_is_the_same_records_nothing_but_is_still_matched(env):
    ws, cfg, store = env
    message, _ = follow_up(env, NOW - timedelta(hours=5))
    source = sent(env, to=EDITOR, body=message.upper(), at=NOW - timedelta(hours=4))  # case and spacing don't count
    (copy_id,) = match(env)
    assert copies(store)[0].data["sent_source"] == source and copy_id
    assert edited_signals(store) == []


def test_a_message_to_another_recipient_before_the_copy_or_outside_the_window_or_unlike_it_does_not_match(env):
    ws, cfg, store = env
    at = NOW - timedelta(days=settings(cfg).window_days + 3)
    message, _ = follow_up(env, at)
    other = sent(env, to=OTHER, body=message, at=at + timedelta(hours=1))
    before = sent(env, to=EDITOR, body=message, at=at - timedelta(hours=1))
    late = sent(env, to=EDITOR, body=message, at=at + timedelta(days=settings(cfg).window_days, minutes=1))
    unlike = sent(env, to=EDITOR, body="Lunch on Friday? I am free after noon.", at=at + timedelta(hours=2))
    assert {other, before, late, unlike} and match(env) == []
    assert copies(store)[0].data["sent_source"] is None and edited_signals(store) == []
    inside = sent(
        env, to=EDITOR, body=message + "\n\nOne more thing.", at=at + timedelta(days=settings(cfg).window_days)
    )
    assert match(env) == [copies(store)[0].id] and copies(store)[0].data["sent_source"] == inside


def test_the_similarity_is_the_setting_so_a_rewritten_message_matches_when_it_is_lowered(tmp_path):
    ws, cfg = _build(tmp_path, with_sent_folder=False)
    store = Store(ws.db_path, cfg=cfg)
    try:
        _addresses(store, cfg)
        env = (ws, cfg, store)
        message, _ = follow_up(env, NOW - timedelta(hours=5))
        rewritten = "Quick note: " + " ".join(message.split()[: max(3, int(len(message.split()) * 0.55))])
        sent(env, to=EDITOR, body=rewritten, at=NOW - timedelta(hours=4))
        assert sent_version.alike(message, rewritten) < settings(cfg).similarity
        assert match(env) == []
        loose = ws.config(
            env={"COCKPIT__STEWARD__SENT_MATCH__SIMILARITY": "0.2", "COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"}
        )
        assert sent_version.match_sent(ws, store, loose, NOW) != []
    finally:
        store.close()


def test_two_copies_to_one_person_match_one_to_one_newest_first(env):
    ws, cfg, store = env
    older = sent_version.record_copy(
        store, "reply", EDITOR["id"], DRAFT, actions=["ACT-OLD"], now=NOW - timedelta(hours=8)
    )
    newer = sent_version.record_copy(
        store, "reply", EDITOR["id"], DRAFT + " ", actions=["ACT-NEW"], now=NOW - timedelta(hours=6)
    )
    first = sent(env, to=EDITOR, body=DRAFT + " Thanks.", at=NOW - timedelta(hours=5))
    second = sent(env, to=EDITOR, body=DRAFT + " Thanks!", at=NOW - timedelta(hours=4))
    third = sent(env, to=EDITOR, body=DRAFT + " Thanks again.", at=NOW - timedelta(hours=3))
    assert match(env) == [newer, older]
    by_id = {c.id: c.data["sent_source"] for c in copies(store)}
    assert by_id == {newer: first, older: second} and third not in by_id.values()
    assert len(edited_signals(store)) == 2


def test_a_copy_for_nobody_known_is_kept_but_never_matched(env):
    ws, cfg, store = env
    sent_version.record_copy(store, "reply", None, DRAFT, actions=["ACT-1"], now=NOW - timedelta(hours=8))
    sent(env, to=None, body=DRAFT, at=NOW - timedelta(hours=7))
    assert match(env) == []


def test_a_message_someone_else_wrote_is_not_the_persons_sent_mail(env):
    ws, cfg, store = env
    message, _ = follow_up(env, NOW - timedelta(hours=5))
    text = mail(EDITOR, message + "\n\nExtra.").replace(
        f"From: The person <{MY_ADDRESS}>", "From: Someone <a@example.com>"
    )
    with store.transaction() as tx:
        tx.create(
            "source",
            {
                "received_at": (NOW - timedelta(hours=4)).isoformat(),
                "kind": "watched:mailbox",
                "title": "x",
                "content_hash": watch._keep_text(ws, text),
                "trust": "untrusted",
                "watched": {"source": "inbox", "key": "<x@example.com>", "change": "new", "by_you": False},
            },
            _TEST,
        )
    assert match(env) == []


def test_reading_the_sent_folder_matches_in_the_same_pass_that_ends_a_reply_owed(tmp_path):
    ws, cfg = _build(tmp_path, with_sent_folder=True)
    store = Store(ws.db_path, cfg=cfg)
    try:
        _addresses(store, cfg)
        env = (ws, cfg, store)
        message, _ = follow_up(env, NOW - timedelta(hours=3))
        folder = next(iter(cfg.watch.sources)).settings["path"]
        watch.refresh(ws, store, cfg, SENT_FOLDER, NOW - timedelta(hours=4))  # the first read
        from pathlib import Path

        (Path(folder) / "one.txt").write_text(mail(EDITOR, message + "\n\nOne more thing."))
        watch.refresh(ws, store, cfg, SENT_FOLDER, NOW)
        (found,) = copies(store)
        assert found.data["sent_source"] is not None
        assert len(edited_signals(store)) == 1
    finally:
        store.close()


# ---- copied but not found sent ---------------------------------------------------------------------------------------


def unsent(env, now: datetime = NOW) -> list:
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, now) if x.kind == "sent_check"]


def a_sent_folder_being_read(env):
    """One message already taken in from the sent folder, which is what shows the folder is read."""
    sent(env, to=OTHER, body="Lunch on Friday? I am free after noon.", at=NOW - timedelta(days=30))


def test_the_line_comes_after_the_settings_days_and_names_the_person(env_sent):
    ws, cfg, store = env_sent
    a_sent_folder_being_read(env_sent)
    days = settings(cfg).ask_after_days
    follow_up(env_sent, NOW - timedelta(days=days) + timedelta(hours=1))
    assert unsent(env_sent) == []  # not yet
    (line,) = unsent(env_sent, NOW + timedelta(hours=2))
    (found,) = copies(store)
    assert (line.group, line.person, line.sent_copy) == ("send", EDITOR["id"], found.id)
    assert line.key == f"sent_check:{found.id}" and line.questions == found.data["questions"]


def test_there_is_no_line_when_no_sent_folder_is_being_read(env):
    ws, cfg, store = env
    follow_up(env, NOW - timedelta(days=settings(cfg).ask_after_days + 3))
    sent(env, to=OTHER, body="Lunch on Friday?", at=NOW - timedelta(days=30), folder="elsewhere")  # not a source here
    assert unsent(env) == []


def test_a_matched_or_settled_copy_has_no_line(env_sent):
    ws, cfg, store = env_sent
    a_sent_folder_being_read(env_sent)
    message, _ = follow_up(env_sent, NOW - timedelta(days=settings(cfg).ask_after_days + 1))
    assert len(unsent(env_sent)) == 1
    sent(env_sent, to=EDITOR, body=message, at=NOW - timedelta(days=settings(cfg).ask_after_days))
    match(env_sent)
    assert unsent(env_sent) == []


def test_a_reply_whose_action_is_no_longer_owed_has_no_line(api):
    from tests.test_reply_lines import make_reply

    env = (api.ws, api.cfg, api.store)
    a_sent_folder_being_read(env)
    action = make_reply(env, received=NOW - timedelta(days=6), subject="Interior proofs")
    sent_version.record_copy(
        api.store,
        "reply",
        EDITOR["id"],
        DRAFT,
        actions=[action],
        now=NOW - timedelta(days=settings(api.cfg).ask_after_days + 1),
    )
    assert len(unsent(env)) == 1
    assert api.post(f"/api/replies/{action}/answered", json={}).status_code == 200
    assert unsent(env) == []


def settle(api, copy_id: str, how: str):
    return api.post(f"/api/copies/{copy_id}/settle", json={"how": how})


def unsettle(api, copy_id: str, done):
    return api.post(f"/api/copies/{copy_id}/unsettle", json=done.json())


def api_line(api):
    return [x for x in api.get("/api/today/queue").json() if x["kind"] == "sent_check"]


def waiting(api):
    ws, cfg, store = api.ws, api.cfg, api.store
    a_sent_folder_being_read((ws, cfg, store))
    message, counts = follow_up((ws, cfg, store), NOW - timedelta(days=settings(cfg).ask_after_days + 1))
    (found,) = copies(store)
    (line,) = api_line(api)
    assert line["person_name"] == EDITOR["full_name"] and line["sent_copy"] == found.id
    return found.id, counts


def test_yes_another_way_settles_the_copy_and_undo_asks_again(api):
    copy_id, _ = waiting(api)
    done = settle(api, copy_id, "sent_another_way")
    assert done.status_code == 200, done.text
    assert copies(api.store)[0].data["settled"] == "sent_another_way" and api_line(api) == []
    assert unsettle(api, copy_id, done).status_code == 200
    assert copies(api.store)[0].data["settled"] is None and len(api_line(api)) == 1


def test_not_sent_puts_the_questions_back_and_undo_marks_them_sent_again(api):
    copy_id, counts = waiting(api)
    view = api.store.read()
    assert all(view.get("question", q).data["status"] == "sent" for q in counts["question_ids"])
    sent_at = {q: view.get("question", q).data["sent_at"] for q in counts["question_ids"]}
    told = {a: view.get("action", a).data["told"] for a in counts["action_ids"]}
    done = settle(api, copy_id, "not_sent")
    assert done.status_code == 200, done.text
    view = api.store.read()
    assert all(view.get("question", q).data["status"] == "open" for q in counts["question_ids"])
    assert all(EDITOR["id"] not in view.get("action", a).data.get("told", {}) for a in counts["action_ids"])
    assert copies(api.store)[0].data["settled"] == "not_sent" and api_line(api) == []
    assert unsettle(api, copy_id, done).status_code == 200
    view = api.store.read()
    assert {q: view.get("question", q).data["sent_at"] for q in counts["question_ids"]} == sent_at
    assert all(view.get("question", q).data["status"] == "sent" for q in counts["question_ids"])
    assert {a: view.get("action", a).data["told"] for a in counts["action_ids"]} == told
    assert copies(api.store)[0].data["settled"] is None and len(api_line(api)) == 1


def test_still_to_send_asks_again_after_the_same_number_of_days_and_undo_asks_now(api):
    copy_id, _ = waiting(api)
    done = settle(api, copy_id, "still_to_send")
    assert done.status_code == 200, done.text
    assert copies(api.store)[0].data["settled"] is None and api_line(api) == []
    days = settings(api.cfg).ask_after_days
    ws, cfg, store = api.ws, api.cfg, api.store
    assert unsent((ws, cfg, store), NOW + timedelta(days=days) - timedelta(minutes=1)) == []
    assert len(unsent((ws, cfg, store), NOW + timedelta(days=days))) == 1
    assert unsettle(api, copy_id, done).status_code == 200
    assert len(api_line(api)) == 1


def test_settling_something_that_is_not_there_or_with_a_word_that_is_not_a_choice_is_refused(api):
    copy_id, _ = waiting(api)
    assert settle(api, "COPY-NOPE", "not_sent").status_code == 404
    assert settle(api, copy_id, "maybe").status_code == 422


def test_the_settings_have_descriptions_and_defaults(env):
    from engine.config.schema import SentMatchSettings

    fields = SentMatchSettings.model_fields
    assert set(fields) == {"window_days", "similarity", "ask_after_days"}
    assert all(f.description and f.default is not None for f in fields.values())
    assert json.loads(SentMatchSettings().model_dump_json()) == {
        "window_days": 7,
        "similarity": 0.6,
        "ask_after_days": 2,
    }


def test_copies_go_through_export_and_import_whole(tmp_path, env):
    from tests.roundtrip import round_trip

    ws, cfg, store = env
    message, _ = follow_up(env, NOW - timedelta(hours=5))
    sent(env, to=EDITOR, body=message + "\n\nOne more thing.", at=NOW - timedelta(hours=4))
    match(env)
    sent_version.record_copy(store, "reply", OTHER["id"], DRAFT, actions=["ACT-1"], now=NOW - timedelta(hours=2))
    sent_version.settle(store, cfg, copies(store)[-1].id, "still_to_send", NOW)
    assert len(copies(store)) == 2
    report = round_trip(store, cfg, tmp_path / "round-trip")
    assert report["differences"] == []
