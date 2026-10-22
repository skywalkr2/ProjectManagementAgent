"""Reminders that reach a person who is away from the app (design 6.12): a due reminder is drafted as one act to the
person themselves, never twice; it holds only the reminder template's words, in the plain form above the level the
account may hold; a snooze or a finished to-do withdraws an act that hasn't gone out; "Ask me each time" leaves drafts;
and with the person's standing yes they go out through the publisher, over the fake channel (mail and event) and over
the mailbox channel's stand-in servers (mail). Names, ids and addresses come from the fixtures."""

from __future__ import annotations

from datetime import timedelta

import pytest

from engine import reminder_content, standing_yes
from engine.applier import apply_as_person
from engine.config.schema import WatchSource
from engine.storage import WriteContext
from tests.test_mailbox_channel import ME, message_id, sent_message, servers  # noqa: F401  (the stand-in servers)
from tests.test_publisher import Env
from tests.test_standing_yes import ACCOUNT, FORMS, MAILBOX, OWN_ADDRESS, Reminders, build

_ENGINE = WriteContext(actor="engine", trust="trusted", op="test.reminder-acts")


@pytest.fixture(params=FORMS)
def rem(request, tmp_path, demo):
    """Reminders going to an account, in each form."""
    found = build(tmp_path, demo, request.param)
    yield found
    found.env.close()


def acts_of(r: Reminders) -> list[dict]:
    return [a.data for a in r.env.store.read().list("act") if a.data.get("reminder")]


def sweep(r: Reminders) -> bool:
    return r.sweeper.sweep()


def set_action(r: Reminders, action: str, **fields) -> None:
    with r.env.store.transaction() as tx:
        found = tx.get("action", action)
        tx.update("action", action, fields, _ENGINE, read_version=found.version)


# ---- drafting -----------------------------------------------------------------------------------------------------


def test_a_due_reminder_drafts_one_act_to_the_person_and_never_a_second(rem):
    action = rem.todo(minutes=90)
    assert sweep(rem) is True
    (data,) = acts_of(rem)
    assert data["reminder"] == action and data["made_by"] == "reminders" and data["status"] == "draft"
    assert data["account"] == ACCOUNT and data["template"]["name"] == "reminder"
    target = data["target"]
    if rem.form == "mail":
        assert [(r["person"], r["address"], r["role"]) for r in target["recipients"]] == [
            (rem.env.pm, OWN_ADDRESS, "to")
        ]
        assert data["parts"]["subject"] == "Call the print shop"
        assert "Call the print shop" in data["parts"]["body"] and "Reminder for" in data["parts"]["body"]
    else:
        assert target["recipients"] == [] and target["calendar"] == reminder_content.OWN_CALENDAR
        assert target["title"] == "Call the print shop" and target["alarm_minutes"] == 0
        assert target["start"][:16] == (rem.env.clock() + timedelta(minutes=90)).isoformat()[:16]
    sweep(rem)
    sweep(rem)
    assert len(acts_of(rem)) == 1


def test_a_reminder_beyond_the_look_ahead_waits_until_it_comes_within_it(rem):
    rem.env.cfg.steward.reminders.look_ahead_hours = 2
    rem.todo(minutes=180)
    sweep(rem)
    assert acts_of(rem) == []
    rem.env.clock.later(minutes=90)
    sweep(rem)
    assert len(acts_of(rem)) == 1


def test_a_reminder_that_has_already_passed_or_has_no_time_drafts_nothing(rem):
    rem.todo(minutes=-10)
    with rem.env.store.transaction() as tx:
        tx.create("action", {"text": "Stretch", "owners": [{"person": rem.env.pm}]}, _ENGINE)
    sweep(rem)
    assert acts_of(rem) == []


def test_a_to_do_that_is_done_dropped_or_on_hold_drafts_nothing(rem):
    done = rem.todo(text="Send the invoice")
    set_action(rem, done, status="done")
    dropped = rem.todo(text="Book the hall")
    set_action(rem, dropped, status="dropped", dropped_reason="No longer needed")
    sweep(rem)
    assert acts_of(rem) == []


def test_nothing_is_drafted_while_reminders_go_nowhere_or_the_account_cannot_act(rem):
    rem.todo()
    rem.env.cfg.steward.reminders.where = "nowhere"
    sweep(rem)
    rem.env.cfg.steward.reminders.where = rem.form
    rem.env.cfg.watch.acting.remove(ACCOUNT)
    sweep(rem)
    rem.env.cfg.steward.reminders.where_account = ""
    sweep(rem)
    assert acts_of(rem) == []


def test_each_reminder_time_of_the_same_to_do_gets_its_own_act(rem):
    action = rem.todo(minutes=60)
    sweep(rem)
    set_action(rem, action, remind_at=(rem.env.clock() + timedelta(minutes=120)).isoformat())
    sweep(rem)
    states = sorted((a["status"], a["reminder_at"][11:16]) for a in acts_of(rem))
    assert [s for s, _ in states] == ["draft", "withdrawn"] and len(states) == 2


# ---- the plain form -------------------------------------------------------------------------------------------------


def restricted_source(r: Reminders) -> str:
    with r.env.store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": r.env.clock.text(),
                "kind": "pasted",
                "title": "A private note",
                "content_hash": "0" * 64,
                "trust": "trusted",
                "sensitivity": "restricted",
            },
            _ENGINE,
        ).id


def test_the_plain_form_is_used_above_the_level_the_account_may_hold(rem):
    source = restricted_source(rem)
    rem.todo(text="Tell the board about the layoffs", source=source)
    sweep(rem)
    (data,) = acts_of(rem)
    said = " ".join([*data["parts"].values(), str(data["target"].get("title") or "")])
    assert "layoffs" not in said and "A reminder from" in said and "Reminder for" in said


def test_the_items_own_words_go_when_the_account_may_hold_that_level(rem):
    source = restricted_source(rem)
    rem.env.cfg.steward.reminders.allowed_data = "restricted"
    rem.todo(text="Tell the board about the layoffs", source=source)
    sweep(rem)
    (data,) = acts_of(rem)
    assert "layoffs" in " ".join([*data["parts"].values(), str(data["target"].get("title") or "")])


# ---- keeping them true ----------------------------------------------------------------------------------------------


def test_a_snooze_withdraws_a_reminder_act_that_has_not_gone_out(rem):
    action = rem.todo(minutes=60)
    sweep(rem)
    later = (rem.env.clock() + timedelta(hours=3)).isoformat()
    apply_as_person(
        rem.env.store,
        rem.env.cfg,
        [
            {
                "op": "record.edit",
                "record": {"kind": "action", "id": action},
                "fields": {"remind_at": later},
                "read_version": rem.env.store.read().get("action", action).version,
            }
        ],
        "Snoozed",
    )
    sweep(rem)
    first, second = sorted(acts_of(rem), key=lambda a: a["reminder_at"])
    assert (first["status"], first["why"]) == ("withdrawn", ["reminder_moved"])
    assert second["status"] == "draft" and second["reminder_at"][11:16] == later[11:16]


def test_a_cleared_reminder_withdraws_its_act(rem):
    action = rem.todo(minutes=60)
    sweep(rem)
    set_action(rem, action, remind_at=None)
    sweep(rem)
    (data,) = acts_of(rem)
    assert (data["status"], data["why"]) == ("withdrawn", ["reminder_moved"])


def test_a_done_to_do_withdraws_a_reminder_act_that_has_not_gone_out(rem):
    action = rem.todo(minutes=60)
    sweep(rem)
    set_action(rem, action, status="done")
    sweep(rem)
    (data,) = acts_of(rem)
    assert (data["status"], data["why"]) == ("withdrawn", ["reminder_ended"])
    assert rem.env.store.read().list("act")[0].data["approved"] is None


def test_a_withdrawal_is_the_publishers_own_change_of_state_and_is_recorded_as_such(rem):
    action = rem.todo(minutes=60)
    sweep(rem)
    set_action(rem, action, status="dropped", dropped_reason="No longer needed")
    sweep(rem)
    found = rem.env.store.read().list("act")[0]
    entry = [e for e in rem.env.store.read().ledger(kind="act", record_id=found.id) if e["field"] == "status"][-1]
    assert entry["op"].startswith("act.reminder_withdrawn") and entry["actor"] == "publisher"


def test_a_reminder_act_that_went_out_is_not_withdrawn_by_a_later_snooze(rem):
    yes = rem.give()
    action = rem.todo(minutes=60)
    sweep(rem)
    assert [a["status"] for a in acts_of(rem)] == ["sent"] and yes
    set_action(rem, action, status="done")
    sweep(rem)
    assert [a["status"] for a in acts_of(rem)] == ["sent"]


# ---- Ask me each time, and the standing yes, end to end -------------------------------------------------------------


def test_ask_me_each_time_leaves_the_reminder_as_a_draft_in_waiting_to_go_out(rem):
    rem.todo(minutes=60)
    sweep(rem)
    sweep(rem)
    (data,) = acts_of(rem)
    assert data["status"] == "draft" and rem.env.fake.delivered == []


def test_with_a_standing_yes_a_reminder_goes_out_through_the_publisher_and_only_that_one(rem):
    yes = rem.give()
    rem.todo(minutes=60)
    sweep(rem)
    (data,) = acts_of(rem)
    assert data["status"] == "sent" and data["approved"]["standing_yes"] == yes and data["sent_by"] == "publisher"
    ((sent, _),) = rem.env.fake.delivered
    assert sent.account == ACCOUNT and sent.template == ("reminder", rem.version())
    if rem.form == "mail":
        assert (sent.kind, sent.action) == ("message", "send")
        assert [(r.address, r.person, r.role) for r in sent.recipients] == [(OWN_ADDRESS, rem.env.pm, "to")]
        assert sent.parts == data["parts"]
    else:
        assert (sent.kind, sent.action, sent.calendar, sent.alarm_minutes) == ("calendar", "create", "own", 0)
        assert sent.title == "Call the print shop" and sent.recipients == ()
    sweep(rem)
    assert len(rem.env.fake.delivered) == 1


def test_a_reminder_a_standing_yes_does_not_cover_waits_for_the_persons_own_yes(rem):
    yes = rem.give()
    rem.env.cfg.watch.acting.remove(ACCOUNT)
    rem.todo(minutes=60)
    sweep(rem)
    assert acts_of(rem) == [] and rem.env.fake.delivered == []
    rem.env.cfg.watch.acting.append(ACCOUNT)
    rem.env.set_address(rem.env.pm, "another.address@example.com")
    sweep(rem)
    stale = standing_yes.stale_reasons(
        rem.env.store,
        rem.env.cfg,
        rem.env.store.read(),
        __import__("engine.names", fromlist=["People"]).People(rem.env.store, rem.env.cfg),
        rem.env.store.read().get("standing_yes", yes),
    )
    if rem.form == "mail":
        assert stale == ["address"]
        assert [a["status"] for a in acts_of(rem)] == ["draft"] and rem.env.fake.delivered == []
    else:
        assert stale == [] and [a["status"] for a in acts_of(rem)] == ["sent"]


def test_a_reminder_that_is_approved_by_the_person_goes_with_their_click(rem):
    rem.todo(minutes=60)
    sweep(rem)
    (act_id,) = [a.id for a in rem.env.store.read().list("act")]
    rem.env.yes(act_id)
    assert rem.env.act(act_id)["approved"]["standing_yes"] is None
    assert rem.env.publisher.send(act_id).status == "sent"
    assert len(rem.env.fake.delivered) == 1


# ---- through the mailbox channel's stand-in servers -------------------------------------------


@pytest.fixture
def mailbox_env(tmp_path, demo, servers):  # noqa: F811
    env = Env(tmp_path, demo)
    env.store.plugins.core_channels.pop("fake")
    env.cfg.watch.sources.append(
        WatchSource(
            id=MAILBOX,
            connector="mailbox",
            label="Work mail",
            settings={"host": "imap." + "example.com", "user": ME, "password": "env:MAIL_PASSWORD"},
        )
    )
    env.cfg.watch.acting.append(ACCOUNT)
    env.cfg.steward.reminders.where = "mail"
    env.cfg.steward.reminders.where_account = ACCOUNT
    env.set_address(env.pm, OWN_ADDRESS)
    yield Reminders(env, "mail")
    env.close()


def test_a_reminder_mail_goes_out_through_a_plain_mailbox_to_the_persons_own_address(mailbox_env, servers):  # noqa: F811
    r = mailbox_env
    outgoing, _ = servers
    r.give()
    r.todo(minutes=60)
    sweep(r)
    (data,) = acts_of(r)
    assert data["channel"] == "mailbox" and data["status"] == "sent"
    sent = sent_message(outgoing)
    assert sent["To"] == OWN_ADDRESS and sent["Subject"] == "Call the print shop"
    assert sent.get_content().startswith("Call the print shop") and data["service_id"] == message_id("attempt-1", ME)


def test_a_plain_mailbox_offers_the_mail_form_and_never_the_event_form(mailbox_env):
    r = mailbox_env
    assert reminder_content.channel_for(r.env.store.plugins, ACCOUNT, "mail") == "mailbox"
    assert reminder_content.channel_for(r.env.store.plugins, ACCOUNT, "calendar") is None


# ---- in the app's own calendar: local data, no act, no yes -----------------------------------------------------------


@pytest.fixture
def app_calendar(tmp_path, demo):
    r = build(tmp_path, demo, "mail")
    r.env.cfg.steward.reminders.where = "app"
    r.env.cfg.steward.reminders.where_account = ""
    yield r
    r.env.close()


def entries_for(r: Reminders, action: str) -> list:
    return [e for e in r.env.store.read().list("event") if e.data.get("reminder") == action]


def test_a_reminder_in_the_apps_calendar_is_an_entry_with_an_alarm_and_no_act(app_calendar):
    r = app_calendar
    action = r.todo(minutes=300)
    assert sweep(r) is True
    (entry,) = entries_for(r, action)
    assert entry.data["title"] == "Call the print shop" and entry.data["alarm_minutes"] == 0
    assert entry.data["start"][:16] == (r.env.clock() + timedelta(minutes=300)).isoformat()[:16]
    assert acts_of(r) == [] and r.env.store.read().list("standing_yes") == []
    sweep(r)
    sweep(r)
    assert len(entries_for(r, action)) == 1


def test_a_snooze_moves_the_same_entry_and_a_done_to_do_removes_it_with_undo(app_calendar):
    r = app_calendar
    action = r.todo(minutes=60)
    sweep(r)
    (first,) = entries_for(r, action)
    later = (r.env.clock() + timedelta(hours=5)).isoformat()
    set_action(r, action, remind_at=later)
    sweep(r)
    (moved,) = entries_for(r, action)
    assert moved.id == first.id and moved.data["start"][:16] == later[:16]
    set_action(r, action, status="done")
    sweep(r)
    assert entries_for(r, action) == []
    change = [c for c in r.env.store.read().list("changeset") if c.data["summary"] == "A reminder left the calendar"]
    from engine.applier import undo

    undo(r.env.store, change[-1].id)
    assert [e.id for e in entries_for(r, action)] == [first.id]


def test_a_cleared_reminder_removes_its_entry_and_one_that_has_passed_is_never_made(app_calendar):
    r = app_calendar
    action = r.todo(minutes=60)
    sweep(r)
    set_action(r, action, remind_at=None)
    sweep(r)
    assert entries_for(r, action) == []
    past = r.todo(minutes=-30)
    sweep(r)
    assert entries_for(r, past) == []


def test_nothing_goes_on_the_calendar_unless_the_app_calendar_is_chosen(app_calendar):
    r = app_calendar
    r.env.cfg.steward.reminders.where = "nowhere"
    action = r.todo(minutes=60)
    sweep(r)
    assert entries_for(r, action) == []


def test_only_the_engines_reminders_keep_entries_on_the_calendar(app_calendar):
    from engine.storage import StoreError

    r = app_calendar
    action = r.todo(minutes=60)
    op = {"op": "reminder.entry", "action": action, "at": (r.env.clock() + timedelta(minutes=60)).isoformat()}
    with pytest.raises(StoreError, match="only the engine's reminders"):
        apply_as_person(r.env.store, r.env.cfg, [op], "A person's try")
    assert entries_for(r, action) == []
