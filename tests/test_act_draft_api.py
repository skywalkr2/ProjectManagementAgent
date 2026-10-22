"""The person drafts an act from a saved message or an invitation (design 6.12, S1b-2d): `POST /api/acts` for each kind,
Copy when acting is off for the account, a draft its channel can't carry refused with its reason; what can be done about
a record (`GET /api/acts/options`) and the free times to propose (`GET /api/acts/free-slots`). Built on the act tests'
workspace: a `FakeChannel` that serves plain mailboxes, one source the saved messages came in on. Names, ids and
addresses come from the fixtures; every address is on example.com."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from engine import propose_times
from engine.channels import ChannelRegistration, FakeChannel
from engine.channels_mailbox import NO_PROPOSE
from engine.config.schema import WatchSource
from engine.reminder_lines import rules
from engine.storage import WriteContext
from tests.test_publisher import api  # noqa: F401  (the API fixture)

_ENGINE = WriteContext(actor="engine", trust="trusted", op="test.act-draft-api")
MAILBOX = "work-mail"
ACCOUNT = f"mailbox:{MAILBOX}"
SIGNED_IN = "demo-service:pat@example.com"
ORGANIZER = "organizer@example.com"
START = "2026-11-02T09:00:00+00:00"
END = "2026-11-02T10:00:00+00:00"
BODY = {"subject": "Re: the proofs", "body": "The proofs ship on Monday."}


@pytest.fixture
def client(api):  # noqa: F811
    api.cfg.watch.sources.append(WatchSource(id=MAILBOX, connector="mailbox", label="Work mail"))
    api.cfg.watch.acting.append(ACCOUNT)
    api.fake = FakeChannel(accounts=("mailbox",))
    api.store.plugins.core_channels["fake"] = api.fake.registration()
    # The fake channel stands in for the core's mailbox channel, so what carries an act is the one the test chose.
    api.mailbox_channel = api.store.plugins.core_channels.pop("mailbox")
    return api


def message(client, key: str = "thread", source: str = MAILBOX, text: str | None = None) -> str:
    digest = hashlib.sha256(f"{key}{text}".encode()).hexdigest()
    if text is not None:
        folder = Path(client.store.path).parent / "sources"
        folder.mkdir(exist_ok=True)
        (folder / f"{digest}.txt").write_text(text, encoding="utf-8")
    with client.store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": "2026-10-22T09:00:00+00:00",
                "kind": "watched:mailbox",
                "title": f"Subject of {key}",
                "content_hash": digest,
                "trust": "untrusted",
                "watched": {"source": source, "key": f"<{key}@example.com>", "change": "new", "author": ORGANIZER},
            },
            _ENGINE,
        ).id


def entry(client, source: str, **more: Any) -> str:
    with client.store.transaction() as tx:
        return tx.create(
            "event",
            {
                "title": "Planning session",
                "start": START,
                "end": END,
                "key": "<entry-1>",
                "source": source,
                "invitation": True,
                "organizer": {"address": ORGANIZER, "name": "The Organizer"},
                "trust": "untrusted",
                **more,
            },
            _ENGINE,
        ).id


def draft(client, target: dict, **more: Any):
    return client.post("/api/acts", json={**target, **more})


def to_person(client, **more: Any) -> dict:
    return {"kind": "message", "recipients": [{"person": client.person, "kind": "email"}], **more}


@pytest.mark.parametrize("action", ["reply", "reply_all", "forward"])
def test_a_reply_reply_all_or_forward_drafts_on_the_account_the_message_came_in_on(client, action):
    mail = message(client)
    made = draft(client, to_person(client, action=action), parts=BODY, in_reply_to=mail)
    assert made.status_code == 200, made.text
    shown = made.json()
    assert shown["status"] == "draft" and shown["kind"] == "message" and shown["action"] == action
    assert shown["account"] == ACCOUNT and shown["account_label"] == "Work mail" and shown["acting"] is True
    assert shown["channel"] == "fake" and shown["copied_because"] is None
    assert shown["parts"] == BODY and [r["address"] for r in shown["recipients"]] == ["api.recipient@example.com"]
    assert client.get(f"/api/acts/{shown['id']}").json()["fingerprint"] == shown["fingerprint"]
    assert client.fake.delivered == []  # drafting sends nothing


def test_a_reply_needs_the_message_it_answers_and_some_words(client):
    assert draft(client, to_person(client, action="reply"), parts=BODY).status_code == 409
    assert draft(client, to_person(client, action="reply"), parts={}, in_reply_to=message(client)).status_code == 409
    none = draft(client, {"kind": "message", "action": "send"}, parts=BODY)
    assert none.status_code == 409 and "at least one person" in none.json()["detail"]


def test_a_reply_goes_to_the_sender_and_a_reply_to_everyone_to_the_others_but_the_person(client):
    mine = "my.own@example.com"
    client.cfg.workspace.user.accounts.append(mine)
    text = (
        "From: Sender One <sender.one@example.com>\n"
        f"To: {mine}, second.person@example.com\n"
        "Cc: third.person@example.com, Sender One <sender.one@example.com>\n"
        "Subject: The proofs\n\nCan you send them?"
    )
    mail = message(client, "headers", text=text)
    reply = draft(client, {"kind": "message", "action": "reply"}, parts=BODY, in_reply_to=mail).json()
    assert [(r["address"], r["role"]) for r in reply["recipients"]] == [("sender.one@example.com", "to")]
    everyone = draft(client, {"kind": "message", "action": "reply_all"}, parts=BODY, in_reply_to=mail).json()
    assert [(r["address"], r["role"]) for r in everyone["recipients"]] == [
        ("sender.one@example.com", "to"),
        ("second.person@example.com", "to"),
        ("third.person@example.com", "cc"),
    ]
    # a message whose text has no readable header lines names no one: the person is asked who it goes to
    bare = draft(client, {"kind": "message", "action": "reply"}, parts=BODY, in_reply_to=message(client, "bare"))
    assert bare.status_code == 409 and "at least one person" in bare.json()["detail"]


def test_acting_off_makes_it_a_copy_and_says_why(client):
    client.cfg.watch.acting.remove(ACCOUNT)
    shown = draft(client, to_person(client, action="reply"), parts=BODY, in_reply_to=message(client)).json()
    assert shown["channel"] == "copy" and shown["channel_label"] == "Copy"
    assert shown["copied_because"] == "acting_off" and shown["intended_channel"] == "fake"
    assert shown["acting"] is False and shown["account"] == ACCOUNT


def test_a_message_that_came_in_no_account_way_is_a_copy_with_no_account(client):
    with client.store.transaction() as tx:
        pasted = tx.create(
            "source",
            {
                "received_at": "2026-10-22T09:00:00+00:00",
                "kind": "note",
                "title": "Pasted note",
                "content_hash": "1" * 64,
                "trust": "untrusted",
            },
            _ENGINE,
        ).id
    shown = draft(client, to_person(client, action="forward"), parts=BODY, in_reply_to=pasted).json()
    assert shown["channel"] == "copy" and shown["account"] is None and shown["copied_because"] is None


@pytest.mark.parametrize(
    ("target", "label", "folder"),
    [
        ({"action": "archive"}, None, None),
        ({"action": "mark_read"}, None, None),
        ({"action": "label", "label": "Waiting"}, "Waiting", None),
        ({"action": "move", "folder": "Projects"}, None, "Projects"),
    ],
)
def test_a_mailbox_act_on_several_messages_is_one_act(client, target, label, folder):
    one, two = message(client, "one"), message(client, "two")
    shown = draft(client, {"kind": "mailbox", "about": [one, two], **target}).json()
    assert shown["kind"] == "mailbox" and shown["action"] == target["action"] and shown["parts"] == {}
    assert [a["id"] for a in shown["about"]] == [one, two]
    assert [a["title"] for a in shown["about"]] == ["Subject of one", "Subject of two"]
    assert shown["label"] == label and shown["folder"] == folder
    assert shown["account"] == ACCOUNT and shown["channel"] == "fake"


def test_a_mailbox_act_missing_what_it_needs_or_across_accounts_is_refused_with_the_reason(client):
    client.cfg.watch.sources.append(WatchSource(id="home-mail", connector="mailbox", label="Home mail"))
    one, other = message(client, "one"), message(client, "two", source="home-mail")
    moved = draft(client, {"kind": "mailbox", "action": "move", "about": [one]})
    assert moved.status_code == 409 and "names the folder" in moved.json()["detail"]
    split = draft(client, {"kind": "mailbox", "action": "archive", "about": [one, other]})
    assert split.status_code == 409 and "different accounts" in split.json()["detail"]
    gone = draft(client, {"kind": "mailbox", "action": "archive", "about": ["no-such-message"]})
    assert gone.status_code == 409


@pytest.mark.parametrize("answer", ["accepted", "tentative", "declined"])
def test_an_answer_to_an_invitation_drafts_to_its_organizer(client, answer):
    invite = entry(client, message(client, "invite"))
    shown = draft(client, {"kind": "calendar", "action": "answer", "about": [invite], "answer": answer}).json()
    assert shown["kind"] == "calendar" and shown["action"] == "answer" and shown["answer"] == answer
    assert shown["account"] == ACCOUNT and shown["channel"] == "fake"
    assert [r["address"] for r in shown["recipients"]] == [ORGANIZER]
    assert [a["kind"] for a in shown["about"]] == ["event"]


def test_a_plain_mailbox_cannot_propose_a_time_and_says_why(client):
    invite = entry(client, message(client, "invite"))
    target = {
        "kind": "calendar",
        "action": "answer",
        "about": [invite],
        "answer": "propose",
        "proposed_start": "2026-11-03T14:00:00+00:00",
        "proposed_end": "2026-11-03T15:00:00+00:00",
    }
    refused = draft(client, target)
    assert refused.status_code == 409 and refused.json()["detail"] == NO_PROPOSE
    assert client.get("/api/acts", params={"status": "draft"}).json()["acts"] == []

    # an account of a service whose channel can propose gets the draft, with the proposed time shown
    registration = client.fake.registration("demo/calendar")
    client.store.plugins.core_channels["demo/calendar"] = ChannelRegistration(
        **{**registration.__dict__, "accounts": ("demo-service",)}
    )
    client.cfg.watch.acting.append(SIGNED_IN)
    made = draft(client, target, account=SIGNED_IN)
    assert made.status_code == 200, made.text
    shown = made.json()
    assert shown["channel"] == "demo/calendar" and shown["answer"] == "propose" and shown["acting"] is True
    assert (shown["proposed_start"], shown["proposed_end"]) == (target["proposed_start"], target["proposed_end"])


def test_a_draft_its_channel_cannot_carry_is_refused_with_its_reason(client):
    narrow = client.fake.registration("narrow")
    client.store.plugins.core_channels["narrow"] = ChannelRegistration(
        **{**narrow.__dict__, "actions": {"message": ("send",), "mailbox": ("archive",)}}
    )
    del client.store.plugins.core_channels["fake"]
    one = message(client)
    labeled = draft(client, {"kind": "mailbox", "action": "label", "about": [one], "label": "x"})
    assert labeled.status_code == 409 and "can't label" in labeled.json()["detail"]
    assert draft(client, {"kind": "mailbox", "action": "archive", "about": [one]}).status_code == 200


def test_the_options_for_a_message_say_what_its_account_can_do(client):
    mail = message(client)
    options = client.get("/api/acts/options", params={"record": mail}).json()
    assert options["kind"] == "message" and options["account"] == ACCOUNT and options["account_label"] == "Work mail"
    assert options["acting"] is True and options["can_act"] is True and options["channel_label"] == "Fake"
    assert options["actions"] == ["reply", "reply_all", "forward", "archive", "move", "label", "mark_read"]
    assert options["folder_source"] == MAILBOX and options["answers"] == []

    client.cfg.watch.acting.remove(ACCOUNT)
    off = client.get("/api/acts/options", params={"record": mail}).json()
    assert off["acting"] is False and off["can_act"] is False and "reply" in off["actions"]

    missing = client.get("/api/acts/options", params={"record": "no-such-record"}).json()
    assert missing["kind"] == "missing" and missing["actions"] == [] and missing["can_act"] is False


def test_the_options_for_a_reply_owed_are_those_of_the_message_that_asked(client):
    mail = message(client)
    with client.store.transaction() as tx:
        owed = tx.create(
            "action",
            {
                "text": "Answer the question",
                "owners": [{"person": client.person}],
                "reply_owed": True,
                "replies_to": mail,
            },
            _ENGINE,
        ).id
    options = client.get("/api/acts/options", params={"record": owed}).json()
    assert options["kind"] == "message" and options["record"] == mail  # the message that asked
    assert options["account"] == ACCOUNT and options["can_act"] is True


def test_the_options_for_an_invitation_say_which_answers_the_account_gives(client):
    invite = entry(client, message(client, "invite"))
    mailbox = client.get("/api/acts/options", params={"record": invite}).json()
    assert mailbox["kind"] == "event" and mailbox["can_act"] is True and mailbox["actions"] == []
    assert mailbox["answers"] == ["accepted", "tentative", "declined"] and mailbox["propose_refusal"] == NO_PROPOSE

    registration = client.fake.registration("demo/calendar")
    client.store.plugins.core_channels["demo/calendar"] = ChannelRegistration(
        **{**registration.__dict__, "accounts": ("demo-service",)}
    )
    del client.store.plugins.core_channels["fake"]
    # with nothing serving a plain mailbox, Copy carries what is drafted
    plain = client.get("/api/acts/options", params={"record": invite}).json()
    assert plain["can_act"] is False and plain["answers"] == []  # Copy carries what is drafted


def test_the_core_mailbox_channel_serves_a_plain_mailbox_account_and_cannot_propose(client):
    client.store.plugins.core_channels["mailbox"] = client.mailbox_channel
    del client.store.plugins.core_channels["fake"]
    invite = entry(client, message(client, "invite"))
    options = client.get("/api/acts/options", params={"record": invite}).json()
    assert options["channel_label"] == "Mailbox" and options["can_act"] is True
    assert options["answers"] == ["accepted", "tentative", "declined"] and options["propose_refusal"] == NO_PROPOSE
    shown = draft(client, {"kind": "calendar", "action": "answer", "about": [invite], "answer": "accepted"}).json()
    assert shown["channel"] == "mailbox" and shown["account"] == ACCOUNT


def test_the_accounts_an_act_can_go_through_carry_the_switch(client):
    def mine() -> dict:
        return next(a for a in client.get("/api/acts/accounts").json()["accounts"] if a["id"] == ACCOUNT)

    assert mine() == {"id": ACCOUNT, "label": "Work mail", "acting": True, "sign_in": None, "can_act": True}
    client.cfg.watch.acting.remove(ACCOUNT)
    assert mine()["acting"] is False


def test_the_free_times_to_propose_are_gaps_in_the_working_week_as_long_as_the_invitation(client):
    invite = entry(client, message(client, "invite"))
    shown = client.get("/api/acts/free-slots", params={"about": invite}).json()["slots"]
    assert 0 < len(shown) <= client.cfg.watch.propose_slots
    for slot in shown:
        assert datetime.fromisoformat(slot["end"]) - datetime.fromisoformat(slot["start"]) == timedelta(hours=1)
    assert client.get("/api/acts/free-slots", params={"about": "no-such-entry"}).json()["slots"] == []


def test_a_free_time_avoids_what_the_calendar_holds(client):
    # The window opens on a Sunday evening, so the first working day is the Monday after it.
    invite = entry(
        client, message(client, "invite"), start="2026-11-02T09:00:00+00:00", end="2026-11-02T10:00:00+00:00"
    )
    entry(
        client, message(client, "held"), start="2026-11-02T00:00:00+00:00", end="2026-11-02T12:00:00+00:00", key="<e2>"
    )
    entry(
        client,
        message(client, "declined"),
        start="2026-11-03T09:00:00+00:00",
        end="2026-11-03T17:00:00+00:00",
        key="<e3>",
        response="declined",
    )
    entry(client, message(client, "all-day"), start="2026-11-04", end="2026-11-04", key="<e4>")
    now = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
    client.cfg.workspace.user.timezone = "UTC"
    found = propose_times.slots(client.store.read(), client.cfg, now, invite)
    starts = [s.start.astimezone(UTC).isoformat() for s in found]
    assert starts[0] == "2026-11-02T12:00:00+00:00"  # the held morning is skipped, the invitation itself isn't a block
    opens = rules(client.cfg).working.start.isoformat()  # the working day starts when the workspace says
    assert starts[1] == f"2026-11-03T{opens}+00:00"  # a declined entry blocks nothing
    assert starts[2] == f"2026-11-05T{opens}+00:00"  # the all-day entry takes the whole of the 4th
    assert all(s.end - s.start == timedelta(hours=1) for s in found)


def test_the_first_free_time_starts_at_the_next_round_time_after_now(client):
    invite = entry(client, message(client, "invite"))
    client.cfg.workspace.user.timezone = "UTC"
    now = datetime(2026, 11, 2, 10, 37, 20, 123456, tzinfo=UTC)  # a Monday, inside the working day
    step = client.cfg.watch.propose_round_minutes
    found = propose_times.slots(client.store.read(), client.cfg, now, invite)
    first = found[0].start.astimezone(UTC)
    assert first.second == 0 and first.microsecond == 0 and first.minute % step == 0
    assert now < first <= now + timedelta(minutes=step)
