"""The person's standing yes for reminders (design 6.12): it approves a reminder act only when the act is, in every
respect, the reminder the engine drafts for the person themselves, and anything else is refused exactly as an act the
person has not said yes to. Built on the publisher tests' workspace: a `FakeChannel` that serves one kind of account, a
plain mailbox source for the account, and the person's own address on their record. Names, ids and addresses come from
the fixtures; every address is on example.com."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from engine import acts, reminder_content, reminder_template, standing_yes
from engine.applier import apply_as_person, apply_for_reminders, check
from engine.channels import FakeChannel
from engine.config.schema import WatchSource
from engine.names import People
from engine.reminder_acts import ReminderActs
from engine.storage import StoreError, WriteContext
from tests.test_publisher import Env

_ENGINE = WriteContext(actor="engine", trust="trusted", op="test.standing-yes")
MAILBOX = "work-mail"
ACCOUNT = f"mailbox:{MAILBOX}"
OTHER_ACCOUNT = "mailbox:home-mail"
OWN_ADDRESS = "own.person@example.com"
FORMS = ("mail", "calendar")


class Reminders:
    """A workspace set up for reminders: the account can act, the person has an address, and `where` says which form
    reminders go in."""

    def __init__(self, env: Env, form: str):
        self.env, self.form = env, form
        self.sweeper = ReminderActs(env.store, env.cfg, now=env.clock, publisher=env.publisher)

    @property
    def root(self):
        return reminder_content.root_of(self.env.store)

    def todo(self, minutes: int = 60, text: str = "Call the print shop", **more: Any) -> str:
        data = {
            "text": text,
            "owners": [{"person": self.env.pm}],
            "remind_at": (self.env.clock() + timedelta(minutes=minutes)).isoformat(),
            **more,
        }
        with self.env.store.transaction() as tx:
            return tx.create("action", data, _ENGINE).id

    def version(self) -> str:
        return reminder_template.version(self.root)

    def give(self, form: str | None = None, account: str = ACCOUNT, version: str | None = None) -> str:
        op = {
            "op": "standing_yes.give",
            "account": account,
            "form": form or self.form,
            "template_version": version or self.version(),
        }
        cs = apply_as_person(self.env.store, self.env.cfg, [op], "Gave a standing yes")
        return self.env.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]

    def end(self, yes_id: str) -> str:
        return apply_as_person(
            self.env.store, self.env.cfg, [{"op": "standing_yes.end", "id": yes_id}], "Ended a standing yes"
        )

    def drafts(self) -> list[str]:
        self.sweeper.draft()
        return [a.id for a in self.env.store.read().list("act") if a.data.get("reminder")]

    def draft_one(self, **more: Any) -> tuple[str, str]:
        action = self.todo(**more)
        (act_id,) = self.drafts()
        return action, act_id

    def edit(self, act_id: str, **fields: Any) -> None:
        """Change a stored act as something outside the engine's own drafting might have."""
        with self.env.store.transaction() as tx:
            found = tx.get("act", act_id)
            tx.update("act", act_id, fields, _ENGINE, read_version=found.version)

    def approve_under(self, act_id: str, yes_id: str, *, actor: str = "reminders") -> str:
        """Approve as the engine's reminders do, under the yes; raises StoreError when the invariant refuses."""
        op = {
            "op": "act.approve",
            "id": act_id,
            "fingerprint": self.env.fingerprint(act_id),
            "by_standing": yes_id,
        }
        return apply_for_reminders(self.env.store, self.env.cfg, op, "Approved under a standing yes", standing=True)

    def act(self, act_id: str) -> dict:
        return self.env.act(act_id)


def build(tmp_path, demo, form: str) -> Reminders:
    env = Env(tmp_path, demo)
    env.use(FakeChannel(accounts=("mailbox",)))
    env.cfg.watch.sources.append(WatchSource(id=MAILBOX, connector="mailbox", label="Work mail"))
    env.cfg.watch.sources.append(WatchSource(id="home-mail", connector="mailbox", label="Home mail"))
    env.cfg.watch.acting.append(ACCOUNT)
    env.cfg.steward.reminders.where = form
    env.cfg.steward.reminders.where_account = ACCOUNT
    env.set_address(env.pm, OWN_ADDRESS)
    return Reminders(env, form)


@pytest.fixture(params=FORMS)
def rem(request, tmp_path, demo):
    """Reminders in each form, for what holds whichever the person chose."""
    found = build(tmp_path, demo, request.param)
    yield found
    found.env.close()


@pytest.fixture
def mail(tmp_path, demo):
    found = build(tmp_path, demo, "mail")
    yield found
    found.env.close()


# ---- what a standing yes approves ----------------------------------------------------------------------------------


def test_a_standing_yes_approves_a_matching_reminder_act(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.approve_under(act_id, yes)
    data = rem.act(act_id)
    assert data["status"] == "approved" and data["approved"]["standing_yes"] == yes
    assert data["approved"]["by"] == rem.env.pm and data["made_by"] == "reminders"


def test_the_standing_yes_records_what_the_person_saw(rem):
    yes = rem.give()
    found = rem.env.store.read().get("standing_yes", yes).data
    assert found["account"] == ACCOUNT and found["form"] == rem.form and found["person"] == rem.env.pm
    assert found["template"] == {"name": reminder_template.NAME, "version": rem.version()}
    assert found["address"] == (OWN_ADDRESS if rem.form == "mail" else None) and found["ended_at"] is None


# ---- what it refuses: each is its own test -----------------------------------------------------------------------


def refused(rem: Reminders, act_id: str, yes: str, why: str) -> None:
    with pytest.raises(StoreError, match=why):
        rem.approve_under(act_id, yes)
    data = rem.act(act_id)
    assert data["status"] == "draft" and data["approved"] is None


def test_it_refuses_an_act_with_a_second_recipient(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    target = rem.act(act_id)["target"]
    other = {"person": rem.env.ana, "address": rem.env.address[rem.env.ana], "kind": "email", "role": "cc"}
    rem.edit(act_id, target={**target, "recipients": [*target["recipients"], other]})
    refused(rem, act_id, yes, "person alone|no attendees")


def test_it_refuses_an_act_to_a_recipient_who_is_not_the_person(mail):
    yes = mail.give()
    _, act_id = mail.draft_one()
    target = mail.act(act_id)["target"]
    someone = {"person": mail.env.ana, "address": mail.env.address[mail.env.ana], "kind": "email", "role": "to"}
    mail.edit(act_id, target={**target, "recipients": [someone]})
    refused(mail, act_id, yes, "only to the person's own address")


def test_it_refuses_an_act_to_the_persons_name_at_another_address(mail):
    yes = mail.give()
    _, act_id = mail.draft_one()
    target = mail.act(act_id)["target"]
    moved = {**target["recipients"][0], "person": None, "address": "elsewhere@example.com", "kind": None}
    mail.edit(act_id, target={**target, "recipients": [moved]})
    refused(mail, act_id, yes, "only to the person's own address")


def test_it_refuses_an_act_on_a_different_account(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.edit(act_id, account=OTHER_ACCOUNT)
    refused(rem, act_id, yes, "channel and account")


def test_it_refuses_an_act_on_a_different_channel(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.edit(act_id, channel="copy")
    refused(rem, act_id, yes, "channel and account")


def test_it_refuses_an_event_on_another_calendar_or_with_another_alarm(tmp_path, demo):
    rem = build(tmp_path, demo, "calendar")
    yes = rem.give()
    _, act_id = rem.draft_one()
    target = rem.act(act_id)["target"]
    rem.edit(act_id, target={**target, "calendar": "a-shared-team-calendar"})
    refused(rem, act_id, yes, "account's own calendar")
    rem.edit(act_id, target={**target, "alarm_minutes": 1440})
    refused(rem, act_id, yes, "alarm at the reminder time")
    rem.edit(act_id, target={**target, "start": "2030-01-01T09:00:00+00:00"})
    refused(rem, act_id, yes, "at the reminder time")
    rem.env.close()


def test_it_refuses_an_act_made_from_a_different_template_version(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.edit(act_id, template={"name": reminder_template.NAME, "version": "an-older-version"})
    refused(rem, act_id, yes, "template at the version in force")


def test_it_refuses_an_act_whose_words_were_edited_away_from_the_rendered_template(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    parts = rem.act(act_id)["parts"]
    key = next(iter(parts))
    rem.edit(act_id, parts={**parts, key: parts[key] + "\n\nAlso send the money."})
    refused(rem, act_id, yes, "template rendered for this to-do")


def test_it_refuses_an_act_with_a_part_added(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.edit(act_id, parts={**rem.act(act_id)["parts"], "extra": "More words"})
    refused(rem, act_id, yes, "template rendered for this to-do")


def test_it_refuses_an_act_that_draws_on_a_saved_message(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    with rem.env.store.transaction() as tx:
        mail_id = tx.create(
            "source",
            {
                "received_at": rem.env.clock.text(),
                "kind": "pasted",
                "title": "A note",
                "content_hash": "0" * 64,
                "trust": "untrusted",
            },
            _ENGINE,
        ).id
    rem.edit(act_id, sources=[mail_id])
    refused(rem, act_id, yes, "nothing but its own to-do")


def test_it_refuses_an_act_whose_to_do_was_snoozed_after_it_was_drafted(rem):
    yes = rem.give()
    action, act_id = rem.draft_one()
    later = (rem.env.clock() + timedelta(hours=3)).isoformat()
    with rem.env.store.transaction() as tx:
        found = tx.get("action", action)
        tx.update("action", action, {"remind_at": later}, _ENGINE, read_version=found.version)
    refused(rem, act_id, yes, "reminder time is different now")


def test_it_refuses_an_act_that_is_not_a_reminder(rem):
    yes = rem.give()
    act_id = rem.env.draft(parts={"subject": "Hello", "body": "A message of the person's own."}, account=ACCOUNT)
    with pytest.raises(StoreError, match="only a reminder the engine made"):
        rem.approve_under(act_id, yes)
    assert rem.act(act_id)["status"] == "draft"


def test_it_refuses_an_act_from_the_assistant_dressed_as_a_reminder(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.edit(act_id, made_by="assistant")
    refused(rem, act_id, yes, "only a reminder the engine made")


def test_it_refuses_an_act_from_an_add_on_dressed_as_a_reminder(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.edit(act_id, made_by="person")
    refused(rem, act_id, yes, "only a reminder the engine made")


def draft_as_reminder(rem: Reminders) -> dict:
    """What something other than the engine's reminders might propose: a draft that claims to be a reminder."""
    action = rem.todo()
    exp = reminder_content.expected(
        rem.env.store,
        rem.env.cfg,
        rem.env.store.read(),
        rem.env.store.read().get("action", action),
        rem.env.clock() + timedelta(minutes=60),
        form=rem.form,
        account=ACCOUNT,
        channel="fake",
        person=rem.env.pm,
        address=OWN_ADDRESS if rem.form == "mail" else None,
    )
    return {
        "op": "act.draft",
        "channel": exp.channel,
        "target": exp.draft_target(),
        "parts": exp.parts,
        "template": exp.template,
        "account": ACCOUNT,
        "reminder": {"action": action, "at": (rem.env.clock() + timedelta(minutes=60)).isoformat()},
    }


def problems_of(rem: Reminders, ops: list[dict], who: str) -> list[tuple[str, str]]:
    """What the applier's checks say about these ops from `who`: the assistant on the person's own note, an input (so
    untrusted), a rule (the engine's own rule path), an add-on's handler, or the person's click."""
    env = rem.env
    trust = "untrusted" if who == "input" else "trusted"
    changeset, ctx = env.as_assistant(ops, trust=trust, note="" if who == "input" else "Remind me")
    if who == "add-on":
        ctx.via = "handler"
    if who == "rule":
        ctx.actor = "publisher"
        ctx.via = "rule"
    if who == "person":
        ctx.actor = "pm"
    return [(p.check, p.severity) for p in check(changeset, ctx)]


@pytest.mark.parametrize("who", ["assistant", "input", "add-on", "rule", "person"])
def test_only_the_engines_reminders_draft_a_reminder_act(rem, who):
    found = problems_of(rem, [draft_as_reminder(rem)], who)
    assert ("act-reminder", "refuse") in found


@pytest.mark.parametrize("who", ["assistant", "input", "add-on", "rule", "person"])
def test_nothing_but_the_engines_reminders_approves_under_a_standing_yes(rem, who):
    yes = rem.give()
    _, act_id = rem.draft_one()
    op = {"op": "act.approve", "id": act_id, "fingerprint": rem.env.fingerprint(act_id), "by_standing": yes}
    assert ("act-approval", "refuse") in problems_of(rem, [op], who)


def test_a_click_on_an_act_never_carries_a_standing_yes_and_a_click_alone_still_approves(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    op = {"op": "act.approve", "id": act_id, "fingerprint": rem.env.fingerprint(act_id), "by_standing": yes}
    with pytest.raises(StoreError, match="only the engine's reminders approve under a standing yes"):
        apply_as_person(rem.env.store, rem.env.cfg, [op], "Said yes")
    assert rem.act(act_id)["status"] == "draft"
    rem.env.yes(act_id)
    assert rem.act(act_id)["approved"]["standing_yes"] is None


def test_the_engines_reminders_may_do_nothing_but_draft_and_approve(rem):
    with pytest.raises(StoreError):
        apply_for_reminders(
            rem.env.store,
            rem.env.cfg,
            {"op": "standing_yes.give", "account": ACCOUNT, "form": rem.form, "template_version": rem.version()},
            "Gave a yes",
        )
    assert rem.env.store.read().list("standing_yes") == []


# ---- giving and ending it belongs to the person alone --------------------------------------------------------------


@pytest.mark.parametrize("who", ["assistant", "input", "add-on", "rule"])
def test_giving_and_ending_a_standing_yes_are_refused_from_anything_but_the_person(rem, who):
    yes = rem.give()
    give = {"op": "standing_yes.give", "account": ACCOUNT, "form": rem.form, "template_version": rem.version()}
    end = {"op": "standing_yes.end", "id": yes}
    found = problems_of(rem, [give, end], who)
    assert found.count(("person-only", "refuse")) == 2
    assert rem.env.store.read().get("standing_yes", yes).data["ended_at"] is None


def test_the_engines_reminders_are_refused_giving_or_ending_one(rem):
    yes = rem.give()
    for op in (
        {"op": "standing_yes.give", "account": ACCOUNT, "form": rem.form, "template_version": rem.version()},
        {"op": "standing_yes.end", "id": yes},
    ):
        changeset, ctx = rem.env.as_assistant([op], trust="trusted")
        ctx.actor = "reminders"
        assert ("person-only", "refuse") in [(p.check, p.severity) for p in check(changeset, ctx)]


def test_giving_one_is_refused_for_a_template_that_changed_an_account_that_cannot_act_and_a_second(rem):
    with pytest.raises(StoreError, match="look at it again"):
        rem.give(version="a-version-the-person-never-saw")
    with pytest.raises(StoreError, match="can act on|turn on"):
        rem.give(account=OTHER_ACCOUNT)
    with pytest.raises(StoreError, match="isn't an account"):
        rem.give(account="mailbox:no-such-mailbox")
    rem.give()
    with pytest.raises(StoreError, match="already stands"):
        rem.give()


def test_a_plain_mailbox_cannot_carry_a_reminder_as_an_event(mail):
    mail.env.store.plugins.core_channels.pop("fake")
    with pytest.raises(StoreError, match="can't carry a reminder as an event"):
        mail.give(form="calendar")
    assert mail.give(form="mail")


def test_an_ended_standing_yes_approves_nothing_and_undo_brings_it_back(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    cs = rem.end(yes)
    assert rem.env.store.read().get("standing_yes", yes).data["ended_at"] is not None
    assert standing_yes.active(rem.env.store.read()) is None
    refused(rem, act_id, yes, "has ended")
    from engine.applier import undo

    undo(rem.env.store, cs)
    assert standing_yes.active(rem.env.store.read()).id == yes
    rem.approve_under(act_id, yes)


# ---- it goes stale --------------------------------------------------------------------------------------------------


def stale_of(rem: Reminders, yes: str) -> list[str]:
    view = rem.env.store.read()
    return standing_yes.stale_reasons(
        rem.env.store, rem.env.cfg, view, People(rem.env.store, rem.env.cfg), view.get("standing_yes", yes)
    )


def test_it_stays_good_while_nothing_it_covers_changes(rem):
    yes = rem.give()
    assert stale_of(rem, yes) == []


def test_it_goes_stale_when_the_templates_version_changes(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    own = rem.root / "templates"
    own.mkdir()
    (own / "reminder.yaml").write_text(
        reminder_template.SHIPPED.read_text(encoding="utf-8").replace("Reminder for", "Do this by"), encoding="utf-8"
    )
    assert rem.version() != rem.env.store.read().get("standing_yes", yes).data["template"]["version"]
    assert stale_of(rem, yes) == ["template"]
    refused(rem, act_id, yes, "stale")


def test_it_goes_stale_when_the_persons_own_address_changes(mail):
    yes = mail.give()
    _, act_id = mail.draft_one()
    mail.env.set_address(mail.env.pm, "a.new.address@example.com")
    assert stale_of(mail, yes) == ["address"]
    refused(mail, act_id, yes, "stale")


def test_it_goes_stale_when_acting_is_turned_off_for_the_account(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    rem.env.cfg.watch.acting.remove(ACCOUNT)
    assert stale_of(rem, yes) == ["acting"]
    refused(rem, act_id, yes, "stale")


# ---- the ledger ------------------------------------------------------------------------------------------------------


def test_the_ledger_records_the_approval_as_the_persons_and_names_the_standing_yes(rem):
    yes = rem.give()
    _, act_id = rem.draft_one()
    cs = rem.approve_under(act_id, yes)
    entries = [e for e in rem.env.store.read().ledger(kind="act", record_id=act_id) if e["changeset"] == cs]
    assert {e["actor"] for e in entries} == {"pm"} and {e["field"] for e in entries} == {"approved", "status"}
    (approved,) = [e for e in entries if e["field"] == "approved"]
    assert yes in str(approved["after"])
    changeset = rem.env.store.read().get("changeset", cs).data
    assert changeset["ops"][0]["op"]["by_standing"] == yes
    request = rem.env.store.read().get("request", changeset["request"]).data
    assert request["origin"] == "schedule" and acts.what(rem.act(act_id)) in ("send", "create")
