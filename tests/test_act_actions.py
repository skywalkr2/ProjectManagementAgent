"""What an act does, which account carries it, and taking a sent act back (design 6.12, S1b-2). Built on the publisher
tests' workspace: a `FakeChannel` that declares every action and serves one kind of account, a plain mailbox source the
saved messages came in on, and acting switched on or off in the `watch.acting` setting. Names, ids and addresses come
from the fixtures; every address is on example.com."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from engine import act_accounts, acts
from engine.applier import apply_as_person, check, undo
from engine.channels import ChannelFailed, ChannelRegistration, FakeChannel
from engine.config.schema import WatchSource
from engine.ops import ACT_UNDOABLE, CHANGESET, ActDraftOp
from engine.storage import StoreError, WriteContext
from tests.test_publisher import Env, api  # noqa: F401  (the API fixture)

_ENGINE = WriteContext(actor="engine", trust="trusted", op="test.act-actions")
AUTH = "https://" + "auth.example.com"
CALLBACK = "https://" + "app.example.com/callback"
MAILBOX = "work-mail"
ACCOUNT = f"mailbox:{MAILBOX}"
OTHER_ACCOUNT = "mailbox:home-mail"
ORGANIZER = "organizer@example.com"
START = "2026-11-02T09:00:00+00:00"
END = "2026-11-02T10:00:00+00:00"


@pytest.fixture
def env(tmp_path, demo):
    e = Env(tmp_path, demo)
    e.use(FakeChannel(accounts=("mailbox",)))
    e.cfg.watch.sources.append(WatchSource(id=MAILBOX, connector="mailbox", label="Work mail"))
    e.cfg.watch.sources.append(WatchSource(id="home-mail", connector="mailbox", label="Home mail"))
    e.cfg.watch.acting.append(ACCOUNT)
    yield e
    e.close()


def saved_message(env: Env, key: str, *, source: str = MAILBOX) -> str:
    with env.store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": env.clock.text(),
                "kind": "watched:mailbox",
                "title": f"Subject of {key}",
                "content_hash": "0" * 64,
                "trust": "untrusted",
                "watched": {"source": source, "key": f"<{key}@example.com>", "change": "new", "author": ORGANIZER},
            },
            _ENGINE,
        ).id


def calendar_entry(env: Env, key: str, *, source: str, **more: Any) -> str:
    with env.store.transaction() as tx:
        return tx.create(
            "event",
            {
                "title": "Planning session",
                "start": START,
                "end": END,
                "key": key,
                "source": source,
                "invitation": True,
                "organizer": {"address": ORGANIZER, "name": "The Organizer"},
                "trust": "untrusted",
                **more,
            },
            _ENGINE,
        ).id


def update_record(env: Env, kind: str, record_id: str, **fields: Any) -> None:
    with env.store.transaction() as tx:
        found = tx.get(kind, record_id)
        tx.update(kind, record_id, fields, _ENGINE, read_version=found.version)


def draft_target(env: Env, target: dict, *, parts: dict | None = None, **more: Any) -> str:
    op = {"op": "act.draft", "channel": "fake", "target": target, "parts": parts or {}, **more}
    cs = apply_as_person(env.store, env.cfg, [op], "Drafted an act")
    return env.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]


def to_ana(env: Env, **more: Any) -> dict:
    return {"kind": "message", "recipients": [{"person": env.ana, "kind": "email"}], **more}


BODY = {"subject": "Re: the proofs", "body": "The proofs ship on Monday."}


# ---- each action drafts and validates -----------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["reply", "reply_all", "forward"])
def test_a_message_action_that_answers_a_saved_message_names_it(env, action):
    mail = saved_message(env, "thread")
    act_id = draft_target(env, to_ana(env, action=action), parts=BODY, in_reply_to=mail)
    data = env.act(act_id)
    assert acts.what(data) == action and data["in_reply_to"] == mail
    assert data["account"] == ACCOUNT  # the account the message came in on
    assert data["channel"] == "fake" and data["intended_channel"] is None

    with pytest.raises(ValidationError, match="names the saved message it answers"):
        ActDraftOp.model_validate(
            {"op": "act.draft", "channel": "fake", "target": to_ana(env, action=action), "parts": BODY}
        )


def test_a_new_message_with_no_action_is_a_send(env):
    act_id = draft_target(env, to_ana(env), parts=BODY, account=ACCOUNT)
    assert acts.what(env.act(act_id)) == "send"


@pytest.mark.parametrize(
    ("target", "problem"),
    [
        ({"action": "archive"}, "names the saved messages"),
        ({"action": "move", "about": ["X"]}, "names the folder"),
        ({"action": "label", "about": ["X"]}, "names the label"),
        ({"action": "delete", "about": ["X"]}, "can't delete"),
    ],
)
def test_a_mailbox_act_needs_its_messages_and_what_its_action_needs(target, problem):
    with pytest.raises(ValidationError, match=problem):
        ActDraftOp.model_validate({"op": "act.draft", "channel": "fake", "target": {"kind": "mailbox", **target}})


def test_a_mailbox_act_has_no_content_and_no_recipients(env):
    one, two = saved_message(env, "one"), saved_message(env, "two")
    for action, extra in (
        ("archive", {}),
        ("mark_read", {}),
        ("move", {"folder": "Done"}),
        ("label", {"label": "Waiting"}),
    ):
        act_id = draft_target(env, {"kind": "mailbox", "action": action, "about": [one, two], **extra})
        data = env.act(act_id)
        assert data["parts"] == {} and data["target"]["about"] == [one, two] and data["account"] == ACCOUNT
        assert set(data["sources"]) == {one, two}  # the act carries the level of the messages it changes
    with pytest.raises(ValidationError, match="no recipients"):
        ActDraftOp.model_validate(
            {
                "op": "act.draft",
                "channel": "fake",
                "target": {"kind": "mailbox", "action": "archive", "about": [one], "recipients": [{"person": env.ana}]},
            }
        )
    with pytest.raises(StoreError, match="isn't a saved message"):
        draft_target(env, {"kind": "mailbox", "action": "archive", "about": ["no-such-record"]})


def test_a_calendar_act_names_what_its_action_needs(env):
    mail = saved_message(env, "invite")
    entry = calendar_entry(env, "uid-1", source=mail)
    created = draft_target(
        env,
        {
            "kind": "calendar",
            "action": "create",
            "calendar": "Work",
            "start": START,
            "end": END,
            "title": "A hold",
            "alarm_minutes": 15,
        },
        account=ACCOUNT,
    )
    assert env.act(created)["target"]["alarm_minutes"] == 15
    moved = draft_target(env, {"kind": "calendar", "action": "move", "about": [entry], "start": START, "end": END})
    cancelled = draft_target(env, {"kind": "calendar", "action": "cancel", "about": [entry]})
    answered = draft_target(env, {"kind": "calendar", "action": "answer", "about": [entry], "answer": "accepted"})
    proposed = draft_target(
        env,
        {
            "kind": "calendar",
            "action": "answer",
            "about": [entry],
            "answer": "propose",
            "proposed_start": START,
            "proposed_end": END,
        },
    )
    assert [acts.what(env.act(a)) for a in (moved, cancelled, answered, proposed)] == [
        "move",
        "cancel",
        "answer",
        "answer",
    ]
    for bad, problem in (
        ({"action": "cancel", "about": [entry, mail]}, "names one calendar entry"),
        ({"action": "move", "about": [entry]}, "names its new start"),
        ({"action": "answer", "about": [entry]}, "accepted, tentative, declined or propose"),
        ({"action": "answer", "about": [entry], "answer": "propose"}, "proposed start and end"),
        ({"action": "create", "calendar": "Work"}, "names the calendar and the time"),
    ):
        with pytest.raises(ValidationError, match=problem):
            ActDraftOp.model_validate({"op": "act.draft", "channel": "fake", "target": {"kind": "calendar", **bad}})


def test_an_act_made_before_actions_were_named_still_works_and_keeps_its_yes(env):
    env.use(FakeChannel())  # a channel that serves no account, as every channel did before accounts
    act_id = env.ready()  # a message with no action, no account: the first of its kind's actions, as before
    data = env.act(act_id)
    assert acts.what(data) == "send" and data["account"] is None
    parts = acts.current_fingerprint(env.store.read(), env.store.plugins, data)[1]
    assert set(parts) == {"channel", "target", "content", "template"}  # nothing new is covered when nothing new is used
    assert env.publisher.send(act_id).status == "sent"


def test_a_draft_whose_action_its_channel_does_not_declare_is_refused_with_a_reason(env):
    narrow = FakeChannel(accounts=("mailbox",))
    registration = narrow.registration()
    env.store.plugins.core_channels["narrow"] = ChannelRegistration(
        **{**registration.__dict__, "name": "narrow", "actions": {"message": ("send",), "mailbox": ("archive",)}}
    )
    mail = saved_message(env, "thread")
    with pytest.raises(StoreError, match="can't reply for a message act: it can send"):
        draft_target(env, to_ana(env, action="reply"), parts=BODY, in_reply_to=mail, channel="narrow")
    with pytest.raises(StoreError, match="can't label for a mailbox act: it can archive"):
        draft_target(env, {"kind": "mailbox", "action": "label", "about": [mail], "label": "x"}, channel="narrow")
    draft_target(env, {"kind": "mailbox", "action": "archive", "about": [mail]}, channel="narrow")


def test_a_plugin_declares_actions_and_accounts_when_it_registers_a_channel():
    from engine.plugin_api import Registrar, Settings

    registrar = Registrar("example", Settings())
    registrar.channel(
        "example/mail",
        "Example mail",
        ["message", "mailbox"],
        send=lambda act, key: None,
        actions={"message": ["send", "reply"], "mailbox": ["archive"]},
        accounts=["example/account"],
    )
    channel = registrar.channels["example/mail"]
    assert channel.takes("message", "reply") and not channel.takes("message", "forward")
    assert channel.takes("mailbox", "archive") and not channel.takes("calendar", "create")
    assert channel.accounts == ("example/account",)
    for bad in (
        {"calendar": ["create"]},  # a kind the channel doesn't take
        {"message": ["send", "archive"]},  # an action of another kind
        {"message": []},
        {"mailbox": ["delete"]},  # there is no delete
    ):
        with pytest.raises(ValueError):
            registrar.channel("example/other", "Other", ["message", "mailbox"], send=lambda a, k: None, actions=bad)


def test_a_sign_in_declares_the_scopes_acting_adds():
    from engine.plugin_api import Registrar, Settings
    from engine.sign_in import allowed_scopes, missing_acting, start

    registrar = Registrar("example", Settings())
    registrar.sign_in(
        "example/account",
        label="Example",
        authorize_url=f"{AUTH}/authorize",
        token_url=f"{AUTH}/token",
        scopes=["read"],
        acting_scopes=["send", "read"],
    )
    sign_in = registrar.sign_ins["example/account"]
    assert sign_in.acting_scopes == ("send",)
    assert "send" not in start(sign_in, "client", CALLBACK)
    assert "scope=read+send" in start(sign_in, "client", CALLBACK, acting=True)
    assert allowed_scopes(sign_in, {}) == {"read"} and allowed_scopes(sign_in, {"acting": True}) == {"read", "send"}
    assert missing_acting(sign_in, {"read"}) == ["send"] and missing_acting(sign_in, {"read", "send"}) == []


# ---- the account ----------------------------------------------------------------------------------------------------


def test_the_account_defaults_to_where_the_message_came_in_and_a_new_message_to_the_one_picked_last(env):
    with pytest.raises(StoreError, match="say which account"):
        draft_target(env, to_ana(env), parts=BODY)  # nothing came in and nothing was picked yet
    home = saved_message(env, "home", source="home-mail")
    env.cfg.watch.acting.append(OTHER_ACCOUNT)
    archived = draft_target(env, {"kind": "mailbox", "action": "archive", "about": [home]})
    assert env.act(archived)["account"] == OTHER_ACCOUNT  # where the message came in
    assert env.act(draft_target(env, to_ana(env), parts=BODY))["account"] == OTHER_ACCOUNT  # the one picked last
    assert env.act(draft_target(env, to_ana(env), parts=BODY, account=ACCOUNT))["account"] == ACCOUNT
    assert env.act(draft_target(env, to_ana(env), parts=BODY))["account"] == ACCOUNT


def test_messages_from_two_accounts_are_never_one_act_and_the_account_must_be_one_the_channel_serves(env):
    one, two = saved_message(env, "one"), saved_message(env, "two", source="home-mail")
    with pytest.raises(StoreError, match="different accounts"):
        draft_target(env, {"kind": "mailbox", "action": "archive", "about": [one, two]})
    with pytest.raises(StoreError, match="doesn't serve that account"):
        draft_target(env, to_ana(env), parts=BODY, account="other-kind:someone@example.com")


def test_editing_the_account_clears_the_yes_and_can_bring_the_channel_back(env):
    mail = saved_message(env, "thread")
    act_id = draft_target(env, to_ana(env, action="reply"), parts=BODY, in_reply_to=mail)
    env.yes(act_id)
    assert env.act(act_id)["status"] == "approved"
    version = env.store.read().get("act", act_id).version
    env.person_op("act.edit", act_id, read_version=version, account=OTHER_ACCOUNT)
    data = env.act(act_id)
    assert data["status"] == "draft" and data["approved"] is None
    assert data["account"] == OTHER_ACCOUNT and data["channel"] == "copy" and data["intended_channel"] == "fake"
    env.cfg.watch.acting.append(OTHER_ACCOUNT)
    env.person_op("act.edit", act_id, read_version=env.store.read().get("act", act_id).version, account=OTHER_ACCOUNT)
    assert env.act(act_id)["channel"] == "fake" and env.act(act_id)["intended_channel"] is None


# ---- the fingerprint ------------------------------------------------------------------------------------------------


def test_the_yes_goes_stale_when_an_items_service_id_or_the_account_changes(env):
    mail = saved_message(env, "thread")
    ref = acts.service_ref(env.store.read(), mail)
    assert ref["service_id"] == "<thread@example.com>" and ref["source"] == MAILBOX
    entry = calendar_entry(env, "uid-1", source=mail)
    answer = draft_target(env, {"kind": "calendar", "action": "answer", "about": [entry], "answer": "accepted"})
    env.yes(answer)
    before = env.fingerprint(answer)
    update_record(env, "event", entry, key="uid-2")  # the service now calls the entry something else
    assert env.fingerprint(answer) != before
    assert env.publisher.send(answer).status == "stale" and env.fake.calls == []

    archive = draft_target(env, {"kind": "mailbox", "action": "archive", "about": [mail]})
    env.yes(archive)
    assert env.act(archive)["approved"]["covers"].keys() >= {"about", "account"}
    first = env.fingerprint(archive)
    env.cfg.watch.acting.append(OTHER_ACCOUNT)
    env.person_op("act.edit", archive, read_version=env.store.read().get("act", archive).version, account=OTHER_ACCOUNT)
    assert env.act(archive)["status"] == "draft"  # editing clears the yes
    assert env.fingerprint(archive) != first
    assert acts.what_changed({"account": "a", "about": "b"}, {"account": "c", "about": "b"}) == ["account"]


def test_a_changed_calendar_entry_or_event_field_makes_the_yes_stale_at_send(env):
    invite = saved_message(env, "invite")
    entry = calendar_entry(env, "uid-1", source=invite)
    act_id = draft_target(env, {"kind": "calendar", "action": "answer", "about": [entry], "answer": "accepted"})
    env.yes(act_id)
    before = env.fingerprint(act_id)
    ref = acts.service_ref(env.store.read(), entry)
    assert ref["uid"] == "uid-1" and ref["service_id"] == "uid-1" and ref["start"] == START

    update_record(env, "event", entry, start="2026-11-02T08:00:00+00:00")  # the organizer moved it
    assert env.fingerprint(act_id) != before
    result = env.publisher.send(act_id)
    assert result.status == "stale" and env.fake.calls == []
    assert env.act(act_id)["why"] == ["about"]

    # an event field of the act itself
    created = draft_target(
        env, {"kind": "calendar", "action": "create", "calendar": "Work", "start": START, "end": END, "title": "Hold"}
    )
    env.yes(created)
    first = env.fingerprint(created)
    with env.store.transaction() as tx:
        found = tx.get("act", created)
        tx.update(
            "act",
            created,
            {"target": {**found.data["target"], "alarm_minutes": 5}},
            _ENGINE,
            read_version=found.version,
        )
    assert env.fingerprint(created) != first


def test_the_channel_is_handed_what_the_act_is_about_with_the_service_ids_as_they_resolve_now(env):
    mail = saved_message(env, "thread")
    entry = calendar_entry(env, "uid-9", source=mail)
    archive = draft_target(env, {"kind": "mailbox", "action": "move", "about": [mail], "folder": "Done"})
    answer = draft_target(
        env, {"kind": "calendar", "action": "answer", "about": [entry], "answer": "tentative"}, account=ACCOUNT
    )
    for act_id in (archive, answer):
        env.yes(act_id)
        assert env.publisher.send(act_id).status == "sent"
    moved, answered = (call[0] for call in env.fake.delivered)
    assert (moved.kind, moved.action, moved.folder, moved.account) == ("mailbox", "move", "Done", ACCOUNT)
    assert moved.about[0].id == mail and moved.about[0].service_id == "<thread@example.com>"
    assert (answered.action, answered.answer) == ("answer", "tentative")
    assert answered.about[0].uid == "uid-9" and answered.about[0].sequence is None


# ---- an answer goes to the organizer --------------------------------------------------------------------------------


def test_an_answers_recipient_is_the_organizer_and_is_called_out(env):
    entry = calendar_entry(env, "uid-1", source=saved_message(env, "invite"))
    act_id = draft_target(env, {"kind": "calendar", "action": "answer", "about": [entry], "answer": "accepted"})
    (recipient,) = env.act(act_id)["target"]["recipients"]
    assert recipient["address"] == ORGANIZER and recipient["person"] is None and recipient["from_text"] is True
    (called,) = acts.callouts(env.store.read(), env.pm, env.act(act_id), act_id=act_id)
    assert called.key == ORGANIZER and set(called.reasons) == {"new", "outside", "untrusted"}
    with pytest.raises(StoreError, match="acknowledge each recipient"):
        env.yes(act_id, acknowledged=[])
    env.yes(act_id)
    env.publisher.send(act_id)
    (sent, _key) = env.fake.delivered[0]
    assert [r.address for r in sent.recipients] == [ORGANIZER]

    bare = calendar_entry(env, "uid-2", source=saved_message(env, "second"), organizer=None)
    with pytest.raises(StoreError, match="names no organizer"):
        draft_target(env, {"kind": "calendar", "action": "answer", "about": [bare], "answer": "declined"})


# ---- acting is the person's switch ----------------------------------------------------------------------------------


def test_a_draft_for_an_account_that_is_not_switched_on_is_carried_out_by_copy(env):
    env.cfg.watch.acting.clear()
    mail = saved_message(env, "thread")
    act_id = draft_target(env, to_ana(env, action="reply"), parts=BODY, in_reply_to=mail)
    data = env.act(act_id)
    assert data["channel"] == "copy" and data["intended_channel"] == "fake" and data["account"] == ACCOUNT
    env.yes(act_id)
    with pytest.raises(StoreError, match="carried out by you"):
        env.publisher.send(act_id)
    env.person_op("act.confirm_sent", act_id)
    assert env.act(act_id)["status"] == "sent" and env.fake.calls == []


def test_switching_acting_off_after_the_yes_stops_the_channel_being_called(env):
    act_id = env.ready(account=ACCOUNT)
    env.cfg.watch.acting.clear()
    with pytest.raises(StoreError, match="acting is off"):
        env.publisher.send(act_id)
    assert env.fake.calls == [] and env.act(act_id)["status"] == "approved"


def test_acting_is_the_persons_switch_a_setting_proposal_from_the_assistant_or_an_input_is_refused(env):
    from engine.applier import setting_problem
    from engine.help import askable_settings

    assert "watch.acting" not in {s.key for s in askable_settings(env.cfg)}
    assert setting_problem(env.store, "watch.acting", [ACCOUNT])  # not a setting an ask can name
    for trust in ("untrusted", "trusted"):  # an input's, and the person's own note read by the assistant
        changeset, ctx = env.as_assistant([], trust=trust, note="turn on acting")
        ctx.allowed_ops = ("setting.propose",)  # the ask's op, so the refusal is about the setting itself
        changeset = CHANGESET.validate_python(
            {
                "summary": "Suggest",
                "ops": [
                    {"op": "setting.propose", "setting": "watch.acting", "value": [ACCOUNT], "why": "to save time"}
                ],
            }
        )
        problems = check(changeset, ctx)
        assert [(p.check, p.severity) for p in problems] == [("targets", "refuse")], trust
    assert act_accounts.acting_on(env.cfg, ACCOUNT) and not act_accounts.acting_on(env.cfg, OTHER_ACCOUNT)
    assert act_accounts.same("Mailbox:Work-Mail", ACCOUNT) is False  # the kind is exact, the name ignores case only
    assert act_accounts.same("mailbox:WORK-MAIL", ACCOUNT)


# ---- undo ----------------------------------------------------------------------------------------------------------


def test_undo_of_a_sent_mailbox_act_calls_the_channel_once_and_records_undone(env):
    mail = saved_message(env, "thread")
    act_id = draft_target(env, {"kind": "mailbox", "action": "archive", "about": [mail]})
    env.yes(act_id)
    env.publisher.send(act_id)
    assert env.act(act_id)["status"] == "sent"

    env.person_op("act.undo", act_id)
    assert env.act(act_id)["undo_requested_at"] is not None
    result = env.publisher.undo(act_id)
    assert result.status == "undone" and len(env.fake.undone) == 1
    (handed, service_id) = env.fake.undone[0]
    assert service_id == env.act(act_id)["service_id"] and handed.action == "archive" and handed.about[0].id == mail
    data = env.act(act_id)
    assert data["status"] == "undone" and data["undone_at"] is not None and data["undo_requested_at"] is None
    assert env.ops_in_ledger(act_id)[-2:] == ["act.sent", "act.undone"]
    with pytest.raises(StoreError):  # nothing left to take back
        env.publisher.undo(act_id)
    assert len(env.fake.undone) == 1


def test_a_created_event_can_be_taken_back_but_a_move_a_cancel_and_an_answer_cannot(env):
    assert {(k, a) for k, a in ACT_UNDOABLE} == ACT_UNDOABLE and ("calendar", "create") in ACT_UNDOABLE
    invite = saved_message(env, "invite")
    entry = calendar_entry(env, "uid-1", source=invite)
    created = draft_target(
        env,
        {"kind": "calendar", "action": "create", "calendar": "Work", "start": START, "end": END, "title": "Hold"},
        account=ACCOUNT,
    )
    env.yes(created)
    env.publisher.send(created)
    env.person_op("act.undo", created)
    assert env.publisher.undo(created).status == "undone"

    for target in (
        {"kind": "calendar", "action": "move", "about": [entry], "start": START},
        {"kind": "calendar", "action": "cancel", "about": [entry]},
        {"kind": "calendar", "action": "answer", "about": [entry], "answer": "declined"},
    ):
        act_id = draft_target(env, target)
        env.yes(act_id)
        env.publisher.send(act_id)
        assert env.act(act_id)["status"] == "sent"
        with pytest.raises(StoreError, match="can't be taken back"):
            env.person_op("act.undo", act_id)


def test_a_sent_message_cannot_be_taken_back(env):
    mail = saved_message(env, "thread")
    for target, extra in ((to_ana(env), {}), (to_ana(env, action="reply"), {"in_reply_to": mail})):
        act_id = draft_target(env, target, parts=BODY, account=ACCOUNT, **extra)
        env.yes(act_id)
        env.publisher.send(act_id)
        with pytest.raises(StoreError, match="can't be taken back"):
            env.person_op("act.undo", act_id)
        with pytest.raises(StoreError):
            env.publisher.undo(act_id)
    assert env.fake.undone == []


def test_a_refused_or_unanswered_undo_leaves_the_act_sent_with_the_reason(env):
    mail = saved_message(env, "thread")
    for mode in ("fail", "timeout"):
        env.use(
            FakeChannel(accounts=("mailbox",), undo_mode=mode, failure=ChannelFailed("refused", "The service said no."))
        )
        act_id = draft_target(env, {"kind": "mailbox", "action": "mark_read", "about": [mail]})
        env.yes(act_id)
        env.publisher.send(act_id)
        env.person_op("act.undo", act_id)
        result = env.publisher.undo(act_id)
        data = env.act(act_id)
        assert result.status == "failed" and data["status"] == "sent" and data["undo_requested_at"] is None
        expected = "The service said no." if mode == "fail" else env.cfg.language.messages.undo_no_answer
        assert data["undo_failure"]["reason"] == expected and len(env.fake.undone) == 1
        env.person_op("act.undo", act_id)  # the person may ask again


def test_only_the_person_asks_to_take_an_act_back_and_a_channel_without_undo_cannot(env):
    mail = saved_message(env, "thread")
    act_id = draft_target(env, {"kind": "mailbox", "action": "archive", "about": [mail]})
    env.yes(act_id)
    env.publisher.send(act_id)
    changeset, ctx = env.as_assistant([{"op": "act.undo", "id": act_id}], trust="trusted", note="take it back")
    assert any(p.severity == "refuse" for p in check(changeset, ctx))
    env.use(FakeChannel(accounts=("mailbox",), undoes=False))
    with pytest.raises(StoreError, match="can't take it back"):
        env.person_op("act.undo", act_id)
    assert env.act(act_id)["undo_requested_at"] is None
    # what the person asked is not taken back by Undo: the channel may already have been called
    env.use(FakeChannel(accounts=("mailbox",)))
    asked = env.person_op("act.undo", act_id)
    report = undo(env.store, asked)
    assert report.restored == [] and report.skipped
    assert env.act(act_id)["undo_requested_at"] is not None
    assert env.publisher.undo(act_id).status == "undone"


# ---- the API -----------------------------------------------------------------------------------------------------


def test_the_api_shows_what_an_act_does_and_takes_back_a_sent_mailbox_act(api):  # noqa: F811
    from tests.conftest import fixture_records  # noqa: F401

    api.cfg.watch.sources.append(WatchSource(id=MAILBOX, connector="mailbox", label="Work mail"))
    api.cfg.watch.acting.append(ACCOUNT)
    api.fake = FakeChannel(accounts=("mailbox",))
    api.store.plugins.core_channels["fake"] = api.fake.registration()
    with api.store.transaction() as tx:
        mail = tx.create(
            "source",
            {
                "received_at": "2026-10-22T09:00:00+00:00",
                "kind": "watched:mailbox",
                "title": "The proofs",
                "content_hash": "0" * 64,
                "trust": "untrusted",
                "watched": {"source": MAILBOX, "key": "<api@example.com>", "change": "new", "author": ORGANIZER},
            },
            _ENGINE,
        ).id
    op = {
        "op": "act.draft",
        "channel": "fake",
        "target": {"kind": "mailbox", "action": "label", "about": [mail], "label": "Waiting"},
        "parts": {},
    }
    cs = apply_as_person(api.store, api.cfg, [op], "Drafted an act")
    act_id = api.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]

    shown = api.get(f"/api/acts/{act_id}").json()
    assert shown["kind"] == "mailbox" and shown["action"] == "label" and shown["label"] == "Waiting"
    assert shown["account"] == ACCOUNT and shown["account_label"] == "Work mail" and shown["acting"] is True
    (about,) = shown["about"]
    assert about == {
        "id": mail,
        "kind": "message",
        "title": "The proofs",
        "sender": ORGANIZER,
        "when": "2026-10-22",
        "end": None,
    }
    assert shown["undoable"] is False and shown["copied_because"] is None

    sent = api.post(f"/api/acts/{act_id}/send", json={"fingerprint": shown["fingerprint"], "acknowledged": []}).json()
    assert sent["status"] == "sent"
    assert api.get(f"/api/acts/{act_id}").json()["undoable"] is True

    undone = api.post(f"/api/acts/{act_id}/undo").json()
    assert undone["status"] == "undone" and len(api.fake.undone) == 1
    assert api.post(f"/api/acts/{act_id}/undo").status_code == 409

    # several states, and a limit
    other = apply_as_person(api.store, api.cfg, [op], "Drafted an act")
    assert other
    both = api.get("/api/acts", params=[("status", "undone"), ("status", "draft")]).json()["acts"]
    assert {a["status"] for a in both} == {"undone", "draft"}
    assert len(api.get("/api/acts", params={"limit": 1}).json()["acts"]) == 1
    assert [a["status"] for a in api.get("/api/acts", params={"status": "draft"}).json()["acts"]] == ["draft"]


def test_an_account_not_switched_on_says_why_copy_carries_it_and_the_settings_offer_the_switch(api):  # noqa: F811
    api.cfg.watch.sources.append(WatchSource(id=MAILBOX, connector="mailbox", label="Work mail"))
    api.fake = FakeChannel(accounts=("mailbox",))
    api.store.plugins.core_channels["fake"] = api.fake.registration()
    op = {
        "op": "act.draft",
        "channel": "fake",
        "target": {"kind": "message", "recipients": [{"person": api.person, "kind": "email"}]},
        "parts": {"subject": "Proofs", "body": "They ship Monday."},
        "account": ACCOUNT,
    }
    cs = apply_as_person(api.store, api.cfg, [op], "Drafted an act")
    act_id = api.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]
    shown = api.get(f"/api/acts/{act_id}").json()
    assert (
        shown["channel"] == "copy" and shown["copied_because"] == "acting_off" and shown["intended_channel"] == "fake"
    )
    assert shown["acting"] is False and shown["channel_label"] == "Copy"
    assert ACCOUNT in [a.id for a in act_accounts.known(api.store, api.cfg)]
    settings = {s["key"]: s for s in api.get("/api/settings").json()["items"]}
    offered = settings["watch.acting"]
    assert offered["choices"] == "acting_accounts" and offered["options"]  # the mailboxes the workspace reads
    assert all(option.startswith("mailbox:") for option in offered["options"])
