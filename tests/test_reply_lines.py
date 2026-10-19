"""Replies owed (design 6.32, 6.35): a message that asks the person something becomes one action marked as a reply owed,
automatic mail and mail the person sent never do, each open one is a Today line with a draft under it and its choices,
and each ends the way a person would end it: their own sent mail on the thread to the asker closes it at once, an
answer from someone else waits for Keep and names who gave it. Names, ids and texts come from the fixtures."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import held_ask, reply_lines, watch
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.dispatcher import process
from engine.intake import hand_in
from engine.names import People
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.reply-lines")
TOKEN = "reply-lines-token"
ASK = "Can you tell me when the interior proofs will ship?"
DRAFT = "The interior proofs ship on November 3 (the printer's published schedule)."


def person(role: str) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


def me(cfg) -> str:
    return cfg.workspace.user.person


def named(record: dict, address: str) -> tuple[str, str]:
    return record["full_name"], address


def address_of(record: dict) -> str:
    return record["how_to_reach"]["email"]


ASKER = person("Editor")  # the fixture gives this person an address
ANOTHER = person("Cover designer")
MY_ADDRESS = "the.person@example.com"
ANOTHER_ADDRESS = "another.recipient@example.com"


def mail(sender: tuple[str, str], to: list[tuple[str, str]], subject: str, body: str, cc=()) -> str:
    """A message as a mail source writes its text: the header lines, a blank line, then the body."""
    write = lambda pair: f"{pair[0]} <{pair[1]}>"  # noqa: E731
    lines = [f"From: {write(sender)}", f"To: {', '.join(write(p) for p in to)}"]
    if cc:
        lines.append(f"Cc: {', '.join(write(p) for p in cc)}")
    return "\n".join([*lines, f"Subject: {subject}", "", body])


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    with store.transaction() as tx:  # the person's own address and a second recipient's, as their records hold them
        for pid, address in ((me(cfg), MY_ADDRESS), (ANOTHER["id"], ANOTHER_ADDRESS)):
            found = tx.get("person", pid)
            reach = {**found.data.get("how_to_reach", {}), "email": address}
            tx.update("person", pid, {"how_to_reach": reach}, _TEST, read_version=found.version)
    yield ws, cfg, store
    store.close()
    set_responder(None)


SUBJECT = "Interior proofs"


def asked(env, *, sender=None, text=None, subject=SUBJECT, body=ASK):
    """Hand in a pasted message to the person and let the model add the reply owed; returns the changeset's outcome op
    and the input's source id."""
    ws, cfg, store = env
    sender = sender or named(ASKER, address_of(ASKER))
    text = text if text is not None else mail(sender, [("The person", MY_ADDRESS)], subject, body)
    quote = body.strip().splitlines()[0] if body.strip() else "x"
    op = {
        "op": "action.add",
        "text": "Tell the shop when the interior proofs ship",
        "reply": DRAFT,
        "reply_owed": True,
        "owners": [me(cfg)],
        "evidence": {"quote": quote},
    }
    set_responder(lambda task: json.dumps({"summary": "A reply is owed.", "ops": [op]}))
    handed = hand_in(ws, store, pasted=text, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    return outcome, handed.source


def owed(store) -> list:
    return [a for a in store.read().list("action") if a.data.get("reply_owed")]


def lines(env, now=NOW, **match):
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, now) if all(getattr(x, k) == v for k, v in match.items())]


def reply_lines_of(env, now=NOW):
    return lines(env, now, kind="reply")


# ---- which actions are replies owed ----------------------------------------------------------------------------------


def test_a_reply_owed_from_a_message_gets_its_fields(env):
    ws, cfg, store = env
    outcome, source = asked(env)
    assert outcome["status"] == "applied"
    (action,) = owed(store)
    assert action.data["replies_to"] == source and action.data["asker"] == ASKER["id"]
    assert action.data["reply"] == DRAFT and action.data["reply_reviewed"] is False
    assert [o["person"] for o in action.data["owners"]] == [me(cfg)]


def test_an_action_the_model_does_not_mark_has_none_of_those_fields(env):
    ws, cfg, store = env
    set_responder(
        lambda task: json.dumps(
            {
                "summary": "A to-do.",
                "ops": [
                    {
                        "op": "action.add",
                        "text": "Review the proofs",
                        "owners": [me(cfg)],
                        "evidence": {"quote": "Please review the proofs"},
                    }
                ],
            }
        )
    )
    handed = hand_in(ws, store, pasted="Please review the proofs", now=NOW)
    process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (action,) = [a for a in store.read().list("action") if a.data["text"] == "Review the proofs"]
    assert (action.data["reply_owed"], action.data["replies_to"], action.data["asker"]) == (False, None, None)


@pytest.mark.parametrize(
    ("what", "subject", "body", "from_asker", "why"),
    [
        ("automatic mail", "Automatic reply: " + SUBJECT, ASK, True, "automatic mail"),
        ("mail the person sent", SUBJECT, ASK, False, "you sent this message"),
        (
            "a message that says no reply is needed",
            SUBJECT,
            "Thanks, that settles it. No need to reply.",
            True,
            "not needed",
        ),
    ],
)
def test_automatic_mail_mail_the_person_sent_and_no_reply_needed_are_not_replies_owed(
    env, what, subject, body, from_asker, why
):
    ws, cfg, store = env
    sender = named(ASKER, address_of(ASKER)) if from_asker else ("The person", MY_ADDRESS)
    quote = body.splitlines()[0]
    outcome, _ = asked(env, sender=sender, subject=subject, body=body)
    assert outcome["status"] == "refused", what
    assert [p["check"] for p in outcome["problems"] if p["severity"] == "refuse"] == ["reply-not-owed"]
    assert outcome["reason"].startswith("no reply is owed") and why in outcome["reason"] and owed(store) == []
    assert quote  # the quote was in the input: the refusal is the rules', not an evidence problem


def test_a_message_whose_headers_cannot_be_read_is_not_refused(env):
    ws, cfg, store = env
    outcome, _ = asked(env, text=f"Someone wrote to ask: {ASK}")
    assert outcome["status"] == "applied"
    (action,) = owed(store)
    assert action.data["asker"] is None


def test_a_reply_owed_is_the_persons_own_so_an_owner_who_is_someone_else_is_refused(env):
    ws, cfg, store = env
    op = {
        "op": "action.add",
        "text": "Tell the shop when the interior proofs ship",
        "reply_owed": True,
        "owners": [ANOTHER["id"]],
        "evidence": {"quote": ASK},
    }
    set_responder(lambda task: json.dumps({"summary": "x", "ops": [op]}))
    text = mail(named(ASKER, address_of(ASKER)), [("The person", MY_ADDRESS)], SUBJECT, ASK)
    handed = hand_in(ws, store, pasted=text, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "refused" and owed(store) == []


# ---- the line on Today -----------------------------------------------------------------------------------------------


def make_reply(env, *, received: datetime, subject: str, asker=ASKER, reply=DRAFT, **more) -> str:
    """A reply owed whose message was received at `received`: the action and the source it came from."""
    ws, cfg, store = env
    text = mail(named(asker, address_of(asker)), [("The person", MY_ADDRESS)], subject, ASK)
    with store.transaction() as tx:
        digest = watch._keep_text(ws, text)
        source = tx.create(
            "source",
            {
                "received_at": received.isoformat(),
                "kind": "watched:mailbox",
                "title": subject,
                "content_hash": digest,
                "trust": "untrusted",
                "watched": {
                    "source": "inbox",
                    "key": f"<{subject}@example.com>",
                    "change": "new",
                    "by_you": False,
                    "by_us": False,
                },
            },
            _TEST,
        ).id
        data = {
            "text": f"Reply to {asker['full_name']} about {subject}",
            "owners": [{"person": me(cfg)}],
            "reply_owed": True,
            "replies_to": source,
            "asker": asker["id"],
            "reply": reply,
            "source": source,
            **more,
        }
        return tx.create("action", data, _TEST).id


def test_each_open_reply_owed_is_one_line_oldest_message_first_with_its_draft(env):
    ws, cfg, store = env
    newer = make_reply(env, received=NOW - timedelta(hours=2), subject="Cover proof")
    older = make_reply(
        env,
        received=NOW - timedelta(days=2),
        subject=SUBJECT,
        asker=ANOTHER | {"how_to_reach": {"email": ANOTHER_ADDRESS}},
    )
    found = reply_lines_of(env)
    assert [x.actions for x in found] == [[older], [newer]]
    first = found[0]
    assert (first.group, first.person, first.subject, first.reply, first.reply_reviewed) == (
        "send",
        ANOTHER["id"],
        SUBJECT,
        DRAFT,
        False,
    )
    assert first.key == f"reply:{older}" and first.count == 1


def test_a_reply_with_no_draft_is_still_a_line_and_a_closed_or_held_one_is_not(env):
    ws, cfg, store = env
    bare = make_reply(env, received=NOW - timedelta(hours=1), subject="No answer on file", reply=None)
    done = make_reply(env, received=NOW - timedelta(hours=1), subject="Finished", status="done")
    hold = make_reply(
        env,
        received=NOW - timedelta(hours=1),
        subject="Waiting",
        on_hold={"waiting_for": "the printer", "since": "2026-10-18"},
    )
    (line,) = reply_lines_of(env)
    assert line.actions == [bare] and line.reply is None
    assert done not in {a for x in reply_lines_of(env) for a in x.actions}
    assert hold not in {a for x in reply_lines_of(env) for a in x.actions}


def test_the_line_reads_the_subject_from_the_message_and_never_the_internal_text(env):
    make_reply(env, received=NOW - timedelta(hours=1), subject="Re: " + SUBJECT)
    (line,) = reply_lines_of(env)
    assert line.subject == SUBJECT  # a reply prefix is not part of the subject the line shows


def test_the_words_of_the_reply_line_come_from_the_wording_sheet():
    words = json.loads((Path(__file__).parent.parent / "web/src/wording/en.json").read_text(encoding="utf-8"))
    assert words["queue.reply.title"] == "Reply to {name}: {subject}"
    for key in (
        "queue.pill.reply",
        "queue.reply.copy",
        "queue.reply.write",
        "queue.reply.draft",
        "queue.reply.no_reply_needed",
        "queue.reply.answered_another_way",
        "queue.reply.edit",
        "queue.reply.answered_label",
        "queue.reply.answered_go",
        "queue.reply.edit_label",
        "queue.reply.edit_save",
        "queue.reply.no_reply_reason",
        "queue.reply.answered_toast",
        "queue.reply.dropped_toast",
        "queue.reply.copied_toast",
    ):
        assert words[key].strip(), key
    assert re.search(r"\{name\}", words["queue.reply.title"]) and "{subject}" in words["queue.reply.title"]


# ---- the person's choices --------------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(
        env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"},
        flags={"server.base_path": "/", "storage.backups.automatic": False},
    )
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.ws, client.cfg, client.store = ws, cfg, app.state.store
        app.state.worker.now = lambda: NOW
        yield client
    set_responder(None)


def api_lines(client):
    return [x for x in client.get("/api/today/queue").json() if x["kind"] == "reply"]


def test_no_reply_needed_drops_it_with_the_reason_a_signal_the_assistant_learns_from_and_undo(api):
    env = (api.ws, api.cfg, api.store)
    action = make_reply(env, received=NOW - timedelta(hours=3), subject=SUBJECT)
    (line,) = api_lines(api)
    assert line["person_name"] == ASKER["full_name"] and line["subject"] == SUBJECT and line["reply"] == DRAFT
    why = "No reply needed"
    done = api.post(f"/api/actions/{action}/drop", json={"reason": why})
    assert done.status_code == 200, done.text
    found = api.store.read().get("action", action).data
    assert (found["status"], found["dropped_reason"]) == ("dropped", why)
    assert api_lines(api) == []
    (signal,) = api.store.read().list("signal")
    assert (signal.data["kind"], signal.data["refs"], signal.data["note"]) == ("no_reply_needed", [action], why)
    from engine.learn import SILENT, TEACHES

    assert "no_reply_needed" in SILENT and "no_reply_needed" in TEACHES
    assert api.post(f"/api/changesets/{done.json()['changeset']}/undo", json={"ops": None}).status_code == 200
    assert api.store.read().get("action", action).data["status"] == "open" and len(api_lines(api)) == 1


def test_answered_another_way_closes_it_for_the_person_with_the_words_as_evidence_and_undo(api):
    env = (api.ws, api.cfg, api.store)
    action = make_reply(env, received=NOW - timedelta(hours=3), subject=SUBJECT)
    words = "We settled it on the phone"
    done = api.post(f"/api/replies/{action}/answered", json={"note": words})
    assert done.status_code == 200, done.text
    found = api.store.read().get("action", action).data
    assert (found["status"], found["done_by"], found["reported_by"]) == ("done", [me(api.cfg)], me(api.cfg))
    (op,) = api.store.read().get("changeset", done.json()["changeset"]).data["ops"]
    assert op["status"] == "applied" and op["op"]["evidence"] == {"quote": words}
    assert api_lines(api) == []
    assert api.post(f"/api/changesets/{done.json()['changeset']}/undo", json={"ops": None}).status_code == 200
    assert api.store.read().get("action", action).data["status"] == "open"


def test_answered_another_way_needs_no_words_and_refuses_two_letters_or_something_not_a_reply_owed(api):
    env = (api.ws, api.cfg, api.store)
    action = make_reply(env, received=NOW - timedelta(hours=3), subject=SUBJECT)
    assert api.post(f"/api/replies/{action}/answered", json={"note": "ok"}).status_code == 422
    assert api.post(f"/api/replies/{action}/answered", json={}).status_code == 200
    assert api.store.read().get("action", action).data["status"] == "done"
    plain = api.store.read().list("action")[0].id
    assert api.post(f"/api/replies/{plain}/answered", json={}).status_code == 409
    assert api.post("/api/replies/ACT-NOPE/answered", json={}).status_code == 404


def test_copying_the_draft_approves_it_and_editing_it_is_the_persons_own_words(api):
    env = (api.ws, api.cfg, api.store)
    action = make_reply(env, received=NOW - timedelta(hours=3), subject=SUBJECT)
    assert api.post(f"/api/actions/{action}/reply", json={}).status_code == 200
    (line,) = api_lines(api)
    assert line["reply"] == DRAFT and line["reply_reviewed"] is True
    own = "Hi, the proofs ship on the third."
    assert api.post(f"/api/actions/{action}/reply", json={"text": own}).status_code == 200
    (line,) = api_lines(api)
    assert line["reply"] == own and line["reply_reviewed"] is True


# ---- how a reply owed ends -------------------------------------------------------------------------------------------


def sent(env, *, to, subject: str, received: datetime, body="The interior proofs ship on November 3.", key=None) -> str:
    """A message the person sent, as taken in from the sent folder: a source whose change is their own work."""
    ws, cfg, store = env
    text = mail(("The person", MY_ADDRESS), to, subject, body)
    with store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": received.isoformat(),
                "sent_at": received.isoformat(),
                "kind": "watched:mailbox",
                "title": subject,
                "content_hash": watch._keep_text(ws, text),
                "trust": "untrusted",
                "watched": {
                    "source": "sent",
                    "key": key or f"<sent-{subject}-{received.isoformat()}@example.com>",
                    "change": "new",
                    "by_you": True,
                    "by_us": False,
                    "credited_to": me(cfg),
                },
            },
            _TEST,
        ).id


def end(env):
    ws, cfg, store = env
    return reply_lines.close_answered(ws, store, cfg, NOW)


def status(store, action) -> str:
    return store.read().get("action", action).data["status"]


def test_a_sent_message_on_the_thread_to_the_asker_after_the_ask_ends_it_at_once_as_the_persons_own_act(env):
    ws, cfg, store = env
    action = make_reply(env, received=NOW - timedelta(hours=5), subject=SUBJECT)
    source = sent(
        env, to=[named(ASKER, address_of(ASKER))], subject="Re: " + SUBJECT, received=NOW - timedelta(hours=1)
    )
    (cs_id,) = end(env)
    found = store.read().get("action", action).data
    assert (found["status"], found["done_by"], found["reported_by"]) == ("done", [me(cfg)], me(cfg))
    (op,) = store.read().get("changeset", cs_id).data["ops"]
    assert op["status"] == "applied" and op["op"]["op"] == "action.close"
    quote = op["op"]["evidence"]["quote"]
    assert quote in (ws.sources_dir / f"{store.read().get('source', source).data['content_hash']}.txt").read_text()
    assert reply_lines_of(env) == [] and end(env) == []  # the line is gone and a second look changes nothing


def test_a_sent_message_to_someone_else_or_before_the_ask_or_on_another_thread_does_not_end_it(env):
    ws, cfg, store = env
    action = make_reply(env, received=NOW - timedelta(hours=5), subject=SUBJECT)
    to_other = sent(
        env, to=[named(ANOTHER, ANOTHER_ADDRESS)], subject="Re: " + SUBJECT, received=NOW - timedelta(hours=1)
    )
    before = sent(
        env, to=[named(ASKER, address_of(ASKER))], subject="Re: " + SUBJECT, received=NOW - timedelta(hours=6)
    )
    elsewhere = sent(
        env, to=[named(ASKER, address_of(ASKER))], subject="Lunch on Friday", received=NOW - timedelta(hours=1)
    )
    assert {to_other, before, elsewhere} and end(env) == []
    assert status(store, action) == "open" and len(reply_lines_of(env)) == 1


def test_a_message_from_someone_else_is_not_the_persons_sent_mail(env):
    ws, cfg, store = env
    action = make_reply(env, received=NOW - timedelta(hours=5), subject=SUBJECT)
    other_text = mail(named(ANOTHER, ANOTHER_ADDRESS), [named(ASKER, address_of(ASKER))], "Re: " + SUBJECT, "Nov 3.")
    with store.transaction() as tx:
        tx.create(
            "source",
            {
                "received_at": (NOW - timedelta(hours=1)).isoformat(),
                "kind": "watched:mailbox",
                "title": SUBJECT,
                "content_hash": watch._keep_text(ws, other_text),
                "trust": "untrusted",
                "watched": {"source": "inbox", "key": "<x@example.com>", "change": "new", "by_you": False},
            },
            _TEST,
        )
    assert end(env) == [] and status(store, action) == "open"


def test_reading_the_sent_folder_takes_the_ending_in_when_the_mail_is_taken_in(tmp_path):
    folder = tmp_path / "sent-mail"
    folder.mkdir()
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    import yaml

    person_id = ws.config(env={}).workspace.user.person
    (ws.config_dir / "watch.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "sources": [
                    {
                        "id": "sent",
                        "connector": "folder",
                        "label": "Sent",
                        "first_run": "intake",
                        "author": person_id,
                        "settings": {"path": str(folder)},
                    }
                ],
            }
        )
    )
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    try:
        with store.transaction() as tx:
            found = tx.get("person", me(cfg))
            tx.update("person", me(cfg), {"how_to_reach": {"email": MY_ADDRESS}}, _TEST, read_version=found.version)
        env = (ws, cfg, store)
        action = make_reply(env, received=NOW - timedelta(days=1), subject=SUBJECT)
        watch.refresh(ws, store, cfg, "sent", NOW - timedelta(hours=3))  # the first read
        (folder / "reply.txt").write_text(
            mail(
                ("The person", MY_ADDRESS), [named(ASKER, address_of(ASKER))], "Re: " + SUBJECT, "Ships on November 3."
            )
        )
        watch.refresh(ws, store, cfg, "sent", NOW)
        assert status(store, action) == "done"
    finally:
        store.close()


def test_an_answer_from_another_recipient_is_held_for_keep_and_the_line_names_who_gave_it(env):
    ws, cfg, store = env
    action = make_reply(env, received=NOW - timedelta(hours=5), subject=SUBJECT)
    said = "The proofs ship on November 3, I have the schedule."
    text = mail(
        named(ANOTHER, ANOTHER_ADDRESS),
        [named(ASKER, address_of(ASKER)), ("The person", MY_ADDRESS)],
        "Re: " + SUBJECT,
        said,
    )
    body = json.dumps(
        {"summary": "Answered.", "ops": [{"op": "action.close", "id": action, "evidence": {"quote": said}}]}
    )
    set_responder(lambda task: body)
    handed = hand_in(ws, store, pasted=text, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "held" and status(store, action) == "open"
    (held,) = lines(env, kind="held")
    assert held.held["ask"] == "close" and held.held["record"] == action and held.held["quote"] == said
    assert held.held["reporter"] == ANOTHER["full_name"]
    shown = held_ask.describe(store.read(), People(store, cfg), outcome["op"], reporter=ANOTHER["id"])
    assert shown is not None and shown["reporter"] == ANOTHER["full_name"]
    assert [x.actions for x in reply_lines_of(env)] == [[action]]  # still a line for the person until they keep it


def test_the_notes_prompt_tells_the_model_to_close_a_reply_someone_else_answered():
    prompt = (Path(__file__).parent.parent / "engine/prompts/notes.md").read_text(encoding="utf-8")
    assert "reply_owed" in prompt and "answers what a reply owed asks" in prompt


def test_the_open_list_a_run_reads_marks_a_reply_owed_and_who_asked(env):
    from engine.packet import _open_actions

    ws, cfg, store = env
    action = make_reply(env, received=NOW - timedelta(hours=5), subject=SUBJECT)
    listed = next(
        line for line in _open_actions(store, People(store, cfg)).splitlines() if line.startswith(f"- {action}")
    )
    assert f"reply owed to {ASKER['full_name']}" in listed
