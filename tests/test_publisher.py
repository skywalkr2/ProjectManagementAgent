"""The outward act and the publisher (design 6.12): an act is a record with states, the person's yes covers a
fingerprint, and only the publisher calls a channel. The eight named tests of the designer's F7 come first, one for
each, then the guards around them. Channels are the core's `FakeChannel`; time and attempt keys are passed in, so
nothing waits and nothing is random. Names, ids and addresses come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import acts, outward
from engine.applier import Context, Inputs, apply_as_person, apply_changeset, check, undo
from engine.channels import ChannelFailed, FakeChannel
from engine.names import People
from engine.ops import CHANGESET
from engine.publisher import Publisher
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import init_workspace
from tests.conftest import fixture_records

START = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.publisher")
TOKEN = "publisher-token"


class Clock:
    """Time passed in: the store's clock and the publisher's, moved by the test."""

    def __init__(self) -> None:
        self.at = START

    def __call__(self) -> datetime:
        return self.at

    def text(self) -> str:
        return self.at.isoformat(timespec="seconds")

    def later(self, minutes: int = 1) -> None:
        self.at += timedelta(minutes=minutes)


class Env:
    """A workspace with its store, the person, two other people with addresses, a fake channel and a publisher."""

    def __init__(self, tmp_path, demo):
        self.demo = demo
        self.ws = init_workspace(tmp_path / "ws", template=demo, git=False)
        self.cfg = self.ws.config(
            env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"},
            flags={"server.base_path": "/", "storage.backups.automatic": False},
        )
        self.clock = Clock()
        self.store = Store(self.ws.db_path, cfg=self.cfg, clock=self.clock.text)
        self.pm = self.cfg.workspace.user.person
        others = [p["id"] for p in fixture_records(demo, "person") if p["id"] != self.pm]
        self.ana, self.ben = others[0], others[1]
        self.address = {self.ana: "first.recipient@example.com", self.ben: "second.recipient@example.com"}
        for person, address in self.address.items():
            self.set_address(person, address)
        self.fake = FakeChannel()
        self.use(self.fake)
        self.keys = iter(f"attempt-{n}" for n in range(1, 100))
        self.publisher = self.new_publisher()

    def new_publisher(self) -> Publisher:
        return Publisher(self.store, self.cfg, now=self.clock, new_key=lambda: next(self.keys))

    def use(self, fake: FakeChannel) -> None:
        self.fake = fake
        self.store.plugins.core_channels["fake"] = fake.registration()

    def set_address(self, person: str, address: str) -> None:
        with self.store.transaction() as tx:
            found = tx.get("person", person)
            reach = {**(found.data.get("how_to_reach") or {}), "email": address}
            tx.update("person", person, {"how_to_reach": reach}, _TEST, read_version=found.version)
        self.address[person] = address

    def name(self, person: str) -> str:
        return People(self.store, self.cfg).name(person)

    def message(self, *, to: list[str] | None = None, parts: dict | None = None, **more: Any) -> dict:
        recipients = [{"person": p, "kind": "email"} for p in (to or [self.ana])]
        return {
            "op": "act.draft",
            "channel": more.pop("channel", "fake"),
            "target": {"kind": "message", "recipients": recipients},
            "parts": parts or {"subject": "The proofs", "body": "The proofs ship on Monday."},
            **more,
        }

    def draft(self, **kwargs: Any) -> str:
        cs = apply_as_person(self.store, self.cfg, [self.message(**kwargs)], "Drafted an act")
        return self.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]

    def act(self, act_id: str) -> dict:
        return self.store.read().get("act", act_id).data

    def fingerprint(self, act_id: str) -> str:
        return acts.current_fingerprint(self.store.read(), self.store.plugins, self.act(act_id))[0]

    def yes(self, act_id: str, *, acknowledged: list[str] | None = None) -> str:
        """The person's yes on the act as their screen shows it now, acknowledging every recipient called out."""
        called = acts.callouts(self.store.read(), self.pm, self.act(act_id), act_id=act_id)
        op = {
            "op": "act.approve",
            "id": act_id,
            "fingerprint": self.fingerprint(act_id),
            "acknowledged": [c.key for c in called] if acknowledged is None else acknowledged,
        }
        return apply_as_person(self.store, self.cfg, [op], "Said yes")

    def ready(self, **kwargs: Any) -> str:
        act_id = self.draft(**kwargs)
        self.yes(act_id)
        return act_id

    def person_op(self, name: str, act_id: str, **fields: Any) -> str:
        return apply_as_person(self.store, self.cfg, [{"op": name, "id": act_id, **fields}], "The person's choice")

    def ops_in_ledger(self, act_id: str) -> list[str]:
        return [
            e["op"].split("#")[0]
            for e in self.store.read().ledger(kind="act", record_id=act_id)
            if e["field"] == "status"
        ]

    def as_assistant(self, ops: list[dict], *, trust: str, note: str = "", origin: str = "input"):
        """What the assistant proposes: a changeset checked as it would be from an input (`untrusted`) or from the
        person's own note (`trusted`)."""
        with self.store.transaction() as tx:
            request = tx.create(
                "request",
                {"task": "notes", "origin": origin, "state": "running", "note": note, "created_at": self.clock.text()},
                _TEST,
            )
        ctx = Context(
            self.store,
            self.cfg,
            People(self.store, self.cfg),
            tuple(self.store.plugins.ops),
            Inputs(request.id, None, "", note, trust),
        )
        changeset = CHANGESET.validate_python(
            {"summary": "Drafted", "ops": ops}, context={"op_models": self.store.plugins.ops}
        )
        return changeset, ctx

    def close(self) -> None:
        self.store.close()


@pytest.fixture
def env(tmp_path, demo):
    e = Env(tmp_path, demo)
    yield e
    e.close()


@pytest.fixture
def api(tmp_path, demo):
    ws = init_workspace(tmp_path / "ws", template=demo, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.cfg, client.store = cfg, app.state.store
        client.fake = FakeChannel()
        client.store.plugins.core_channels["fake"] = client.fake.registration()
        pm = cfg.workspace.user.person
        client.person = next(p["id"] for p in fixture_records(demo, "person") if p["id"] != pm)
        with client.store.transaction() as tx:
            found = tx.get("person", client.person)
            tx.update(
                "person",
                client.person,
                {"how_to_reach": {"email": "api.recipient@example.com"}},
                _TEST,
                read_version=found.version,
            )
        yield client


# ---- the designer's eight named tests (F7) ----------------------------------------------


def test_the_exact_approved_content_and_recipients_go_out(env):
    parts = {"subject": "The proofs", "body": "The proofs ship on Monday.\n\nThanks."}
    op = env.message(parts=parts)
    op["target"]["recipients"].append({"person": env.ben, "kind": "email", "role": "cc"})
    cs = apply_as_person(env.store, env.cfg, [op], "Drafted an act")
    act_id = env.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]
    env.yes(act_id)
    env.clock.later()

    result = env.publisher.send(act_id)

    assert result.status == "sent"
    ((sent_act, key),) = env.fake.delivered
    assert sent_act.parts == parts and key == "attempt-1"
    assert [(r.address, r.role, r.person) for r in sent_act.recipients] == [
        (env.address[env.ana], "to", env.ana),
        (env.address[env.ben], "cc", env.ben),
    ]
    made = env.act(act_id)
    assert made["status"] == "sent" and made["service_id"] == "fake-attempt-1" and made["sent_by"] == "publisher"
    assert made["approved"]["by"] == env.pm and made["attempt_key"] == "attempt-1"
    # each change of state is an op in the ledger, in order
    assert env.ops_in_ledger(act_id) == ["act.draft", "act.approve", "act.sending", "act.sent"]


def test_a_yes_goes_stale_when_the_draft_a_recipients_address_or_the_template_changes(env):
    # the draft changes: an edit clears the yes, and the act is a draft again that can't be sent
    edited = env.ready()
    version = env.store.read().get("act", edited).version
    env.person_op("act.edit", edited, read_version=version, parts={"subject": "The proofs", "body": "Now Tuesday."})
    assert env.act(edited)["status"] == "draft" and env.act(edited)["approved"] is None
    with pytest.raises(StoreError, match="not approved"):
        env.publisher.send(edited)

    # a recipient's address changes: the yes no longer covers it, and nothing is sent
    moved = env.ready()
    env.set_address(env.ana, "moved.recipient@example.com")
    assert env.publisher.send(moved).status == "stale"
    assert env.act(moved)["status"] == "stale" and env.act(moved)["why"] == ["target"]
    assert env.fake.calls == []

    # the template is updated since the content was rendered from it
    env.use(FakeChannel(templates={"letter": "1"}))
    templated = env.ready(template={"name": "letter", "version": "1"})
    env.fake.templates["letter"] = "2"
    assert env.publisher.send(templated).status == "stale"
    assert env.act(templated)["why"] == ["template"] and env.fake.calls == []

    # a new yes on what it is now makes it go out
    env.yes(moved)
    assert env.act(moved)["status"] == "approved"
    assert env.publisher.send(moved).status == "sent"
    ((sent_act, _),) = env.fake.delivered
    assert sent_act.recipients[0].address == "moved.recipient@example.com"


def test_a_timeout_retry_or_restart_never_sends_twice(env):
    env.use(FakeChannel(mode="timeout_after_send"))
    act_id = env.ready()

    assert env.publisher.send(act_id).status == "sending"  # it went out, and the answer was lost
    assert env.act(act_id)["status"] == "sending" and len(env.fake.delivered) == 1

    # a retry from the person, and a restart: each asks the service about the key first and finds it
    with pytest.raises(StoreError, match="sent, not approved"):
        env.publisher.send(act_id)
    restarted = env.new_publisher()
    restarted.resume()
    assert env.act(act_id)["status"] == "sent" and env.act(act_id)["service_id"] == "fake-attempt-1"
    assert len(env.fake.calls) == 1 and len(env.fake.delivered) == 1
    with pytest.raises(StoreError):
        restarted.send(act_id)
    assert len(env.fake.calls) == 1

    # when the service has nothing for the key it is approved again, and never sent by itself
    env.use(FakeChannel(mode="timeout"))
    other = env.ready()
    assert env.publisher.send(other).status == "sending"
    env.new_publisher().resume()
    assert env.act(other)["status"] == "approved" and len(env.fake.calls) == 1
    assert env.fake.delivered == []
    env.fake.mode = "succeed"
    assert env.publisher.send(other).status == "sent"
    assert len(env.fake.delivered) == 1


def test_an_uncertain_answer_shows_as_uncertain_never_as_sent(env):
    env.use(FakeChannel(mode="timeout_after_send", answer="unknown"))
    act_id = env.ready()
    env.publisher.send(act_id)
    env.new_publisher().resume()

    assert env.act(act_id)["status"] == "uncertain" and env.act(act_id)["why"] == ["lost_answer"]
    assert env.act(act_id)["sent_at"] is None and env.act(act_id)["service_id"] is None
    with pytest.raises(StoreError):
        env.publisher.send(act_id)  # an uncertain act is not sent again by itself

    # a channel with no way to ask is uncertain too, and says why
    env.use(FakeChannel(mode="timeout", answer="no_status"))
    blind = env.ready()
    env.publisher.send(blind)
    env.new_publisher().resume()
    assert env.act(blind)["status"] == "uncertain" and env.act(blind)["why"] == ["no_status"]

    # "It was sent" is the person's word, with Undo; "Send it again" asks for a new attempt
    cs = env.person_op("act.confirm_sent", act_id)
    assert env.act(act_id)["status"] == "sent" and env.act(act_id)["sent_by"] == "person"
    undo(env.store, cs)
    assert env.act(act_id)["status"] == "uncertain"
    env.use(FakeChannel())
    env.person_op("act.resend", act_id)
    assert env.act(act_id)["status"] == "approved"
    assert env.publisher.send(act_id).status == "sent"
    assert env.act(act_id)["attempt_key"] == "attempt-3" and len(env.fake.delivered) == 1


def test_a_withdrawn_sign_in_stops_the_act_plainly(env):
    account = env.cfg.workspace.user.accounts[0]
    env.use(FakeChannel(mode="fail", failure=ChannelFailed("auth", f"Sign in to {account} again")))
    act_id = env.ready()

    result = env.publisher.send(act_id)

    assert (result.status, result.reason) == ("failed", f"Sign in to {account} again")
    made = env.act(act_id)
    assert made["status"] == "failed" and made["failure"]["kind"] == "auth"
    assert made["failure"]["reason"] == f"Sign in to {account} again"
    # nothing retries: not another send, not a restart
    with pytest.raises(StoreError):
        env.publisher.send(act_id)
    env.new_publisher().resume()
    assert len(env.fake.calls) == 1 and env.fake.delivered == []
    assert env.act(act_id)["status"] == "failed"


def test_outside_content_that_tries_to_change_a_recipient_or_add_an_act_is_refused(env):
    stranger = "stranger.address@example.net"
    adds = {"op": "act.draft", "channel": "fake", "target": {"kind": "message", "recipients": [{"address": stranger}]}}
    adds["parts"] = {"body": "Please send this."}
    changeset, ctx = env.as_assistant([adds], trust="untrusted")
    refused = [p for p in check(changeset, ctx) if p.severity == "refuse"]
    assert [p.check for p in refused] == ["act-from-outside"]

    act_id = env.draft()
    edits = {"op": "act.edit", "id": act_id, "read_version": 1, "recipients": [{"address": stranger}]}
    changeset, ctx = env.as_assistant([edits], trust="untrusted")
    assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"act-from-outside"}
    apply_changeset(changeset, [], ctx, run=None)
    assert [r["address"] for r in env.act(act_id)["target"]["recipients"]] == [env.address[env.ana]]

    # even from the person's own note, the assistant may only draft: it never edits a draft or addresses a stranger
    changeset, ctx = env.as_assistant([edits], trust="trusted", origin="pm")
    assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"person-only"}
    changeset, ctx = env.as_assistant([adds], trust="trusted", origin="pm")
    assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"act-recipient"}
    assert len(env.store.read().list("act")) == 1


def test_a_closed_lid_or_lost_network_mid_send_is_checked_with_the_service_before_any_retry(env):
    class Died(BaseException):
        """The process stopped mid-send: not an error the publisher can catch and settle."""

    act_id = env.ready()
    sent_then_died = env.fake.send

    def send(act, key):
        sent_then_died(act, key)
        raise Died

    env.fake.send = send
    env.store.plugins.core_channels["fake"] = env.fake.registration()
    with pytest.raises(Died):
        env.publisher.send(act_id)
    assert env.act(act_id)["status"] == "sending" and len(env.fake.delivered) == 1

    # on the next start the service is asked about that key before anything else; it was sent, so nothing goes again
    env.fake.send = sent_then_died
    env.store.plugins.core_channels["fake"] = env.fake.registration()
    restarted = env.new_publisher()
    restarted.resume()
    assert env.fake.status_calls == ["attempt-1"]
    assert env.act(act_id)["status"] == "sent" and len(env.fake.delivered) == 1 and len(env.fake.calls) == 1

    # a retry from the person on another act asks first too, and only then calls the channel
    env.use(FakeChannel(mode="timeout"))
    lost = env.ready()
    env.publisher.send(lost)
    env.fake.mode = "succeed"
    assert env.publisher.send(lost).status == "sent"
    assert env.fake.status_calls == ["attempt-2"]
    assert [key for _, key in env.fake.calls] == ["attempt-2", "attempt-3"]
    assert [key for _, key in env.fake.delivered] == ["attempt-3"]


def test_a_yes_does_not_survive_a_restart_that_changed_the_acts_inputs(env):
    act_id = env.ready()
    env.set_address(env.ana, "changed.while.closed@example.com")  # while the app was closed

    env.new_publisher().resume()  # the start: nothing is sent, and the yes is gone

    assert env.act(act_id)["status"] == "stale" and env.act(act_id)["approved"] is None
    assert env.act(act_id)["why"] == ["target"]
    with pytest.raises(StoreError, match="stale"):
        env.publisher.send(act_id)
    assert env.fake.calls == []
    # the worker's own start does the same
    other = env.ready()
    env.set_address(env.ana, "changed.again@example.com")
    from engine.worker import Events, Worker

    worker = Worker(env.ws, env.store, env.cfg, Events(), now=env.clock)
    worker.settle_acts()
    assert env.act(other)["status"] == "stale" and env.fake.calls == []


# ---- the guards around them ----------------------------------------------


def test_only_the_person_approves_and_an_outbound_op_is_never_applied_automatically(env):
    act_id = env.draft()
    ask = {"op": "act.approve", "id": act_id, "fingerprint": env.fingerprint(act_id), "acknowledged": [env.ana]}

    # the assistant, from the person's own note or from an input, and an add-on's staged change
    for trust, origin, via in (
        ("trusted", "pm", None),
        ("untrusted", "input", None),
        ("untrusted", "schedule", "handler"),
    ):
        changeset, ctx = env.as_assistant([ask], trust=trust, origin=origin)
        ctx.via = via
        assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"act-approval"}
        apply_changeset(changeset, [], ctx, run=None)
        assert env.act(act_id)["status"] == "draft"
    # the publisher's own context is no yes either
    changeset, ctx = env.as_assistant([ask], trust="trusted")
    ctx.actor, ctx.via = "publisher", "publisher"
    assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"act-approval"}

    # what only the publisher records is refused from anyone else
    for name, extra in (
        ("act.sent", {"attempt_key": "k", "service_id": "x", "at": START.isoformat()}),
        ("act.stale", {"why": ["content"]}),
    ):
        changeset, ctx = env.as_assistant([{"op": name, "id": act_id, **extra}], trust="trusted")
        assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"act-publisher-only"}
    with pytest.raises(StoreError):
        apply_as_person(env.store, env.cfg, [{"op": "act.stale", "id": act_id, "why": ["content"]}], "Pretended")

    # a draft the assistant makes from the person's note waits for them, and does nothing until they release it
    before = len(env.store.read().list("act"))
    changeset, ctx = env.as_assistant([env.message()], trust="trusted", origin="pm")
    cs_id = apply_changeset(changeset, [], ctx, run=None)
    (outcome,) = env.store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "held" and len(env.store.read().list("act")) == before
    from engine.applier import release

    release(env.store, env.cfg, cs_id, 0)
    made = env.store.read().list("act")[-1]
    assert len(env.store.read().list("act")) == before + 1
    assert made.data["status"] == "draft" and made.data["made_by"] == "assistant"
    # and nothing the person did not say yes to ever reaches a channel
    with pytest.raises(StoreError):
        env.publisher.send(made.id)
    assert env.fake.calls == []


def test_an_assistants_draft_may_address_the_people_in_the_message_it_answers(env):
    import hashlib

    thread_address = "someone.in.the.thread@example.net"
    header = f"From: Someone <{thread_address}>\nTo: The person <{env.address[env.ana]}>\nSubject: The proofs"
    text = f"{header}\n\nAre they ready?"
    digest = hashlib.sha256(text.encode()).hexdigest()
    (env.ws.sources_dir / f"{digest}.txt").write_text(text, encoding="utf-8")
    with env.store.transaction() as tx:
        source = tx.create(
            "source",
            {
                "received_at": env.clock.text(),
                "kind": "pasted",
                "title": "The proofs",
                "content_hash": digest,
                "trust": "untrusted",
            },
            _TEST,
        )
    op = {
        "op": "act.draft",
        "channel": "fake",
        "target": {"kind": "message", "recipients": [{"address": thread_address}]},
        "parts": {"body": "Yes, Monday."},
        "in_reply_to": source.id,
    }
    changeset, ctx = env.as_assistant([op], trust="trusted", origin="pm")
    assert [p for p in check(changeset, ctx) if p.severity == "refuse"] == []

    elsewhere = {**op, "target": {"kind": "message", "recipients": [{"address": "not.in.the.thread@example.net"}]}}
    changeset, ctx = env.as_assistant([elsewhere], trust="trusted", origin="pm")
    assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"act-recipient"}
    flagged = {
        **elsewhere,
        "target": {"kind": "message", "recipients": [{"address": "not.in.the.thread@example.net", "called_out": True}]},
    }
    changeset, ctx = env.as_assistant([flagged], trust="trusted", origin="pm")
    assert [
        p for p in check(changeset, ctx) if p.severity == "refuse"
    ] == []  # it waits for the person, who sees the callout


def test_a_recipient_called_out_must_be_acknowledged_by_name(env):
    stranger = "stranger.address@example.net"
    op = env.message()
    op["target"]["recipients"].append({"address": stranger, "from_text": True})
    cs = apply_as_person(env.store, env.cfg, [op], "Drafted an act")
    act_id = env.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]

    called = {c.key: c.reasons for c in acts.callouts(env.store.read(), env.pm, env.act(act_id), act_id=act_id)}
    assert called == {env.ana: ("new",), stranger: ("new", "outside", "untrusted")}
    with pytest.raises(StoreError, match="acknowledge"):
        env.yes(act_id, acknowledged=[env.ana])  # one acknowledged is not both
    assert env.act(act_id)["status"] == "draft"
    env.yes(act_id, acknowledged=[env.ana, stranger, "someone.not.called.out"])
    assert env.act(act_id)["approved"]["acknowledged"] == sorted([env.ana, stranger])
    assert env.publisher.send(act_id).status == "sent"
    # once written to, a person is no longer new
    assert env.ana not in {c.key for c in acts.callouts(env.store.read(), env.pm, env.act(env.draft()))}
    # a yes on a fingerprint the screen did not show is refused
    again = env.draft()
    with pytest.raises(StoreError, match="different from the one you were shown"):
        apply_as_person(
            env.store,
            env.cfg,
            [{"op": "act.approve", "id": again, "fingerprint": "0" * 64, "acknowledged": [env.ana]}],
            "Yes",
        )


def test_the_copy_channel_goes_sent_only_by_the_persons_mark_sent(env):
    act_id = env.ready(channel="copy")
    with pytest.raises(StoreError, match="carried out by you"):
        env.publisher.send(act_id)
    assert env.act(act_id)["status"] == "approved"
    changeset, ctx = env.as_assistant([{"op": "act.confirm_sent", "id": act_id}], trust="trusted", origin="pm")
    assert {p.check for p in check(changeset, ctx) if p.severity == "refuse"} == {"person-only"}

    cs = env.person_op("act.confirm_sent", act_id)

    made = env.act(act_id)
    assert made["status"] == "sent" and made["sent_by"] == "person" and made["service_id"] is None
    assert env.fake.calls == []
    undo(env.store, cs)
    assert env.act(act_id)["status"] == "approved"
    # a draft that was never approved can't be marked sent
    unapproved = env.draft(channel="copy")
    with pytest.raises(StoreError):
        env.person_op("act.confirm_sent", unapproved)


def test_an_acts_records_survive_export_and_import(env, tmp_path):
    from tests.roundtrip import round_trip

    sent = env.ready()
    env.publisher.send(sent)
    stale = env.ready()
    env.set_address(env.ana, "after.the.yes@example.com")
    env.publisher.send(stale)
    env.use(FakeChannel(mode="fail", failure=ChannelFailed("refused", "The service said no.")))
    failed = env.ready()
    env.publisher.send(failed)
    env.use(FakeChannel(mode="timeout_after_send", answer="unknown"))
    unsure = env.ready()
    env.publisher.send(unsure)
    env.new_publisher().resume()
    withdrawn = env.draft()
    env.person_op("act.withdraw", withdrawn)
    statuses = sorted(env.act(i)["status"] for i in (sent, stale, failed, unsure, withdrawn))
    assert statuses == ["failed", "sent", "stale", "uncertain", "withdrawn"]

    report = round_trip(env.store, env.cfg, tmp_path / "round-trip")

    assert report["differences"] == []


def test_the_name_check_refuses_a_part_that_names_the_assistant(env):
    name = env.cfg.workspace.assistant_name
    where = env.cfg.language.messages.withheld_where.format(name=env.name(env.ana))
    named = env.draft(parts={"body": f"Hello, it is {name} here."})

    with pytest.raises(StoreError) as refused:
        env.yes(named)
    assert str(refused.value) == env.cfg.language.messages.withheld_name.format(where=where, name=name)
    assert env.act(named)["status"] == "draft"
    assert outward.outgoing_problem(
        env.store.read(), env.cfg, acts.part_labels(env.store.read(), env.cfg, env.act(named))
    )

    # a name the assistant went by since the yes is caught at send, and nothing is sent
    clean = env.ready(parts={"body": "Meet at the dock."})
    with env.store.transaction() as tx:
        tx.create(
            "setting_change",
            {
                "key": outward.NAME_KEY,
                "before": "the dock",
                "after": name,
                "was_default": False,
                "is_default": False,
                "at": env.clock.text(),
            },
            _TEST,
        )
    with pytest.raises(StoreError, match="Held back"):
        env.publisher.send(clean)
    assert env.fake.calls == [] and env.act(clean)["status"] == "approved"


def test_an_act_may_not_address_someone_outside_the_limit_of_what_it_draws_on(env):
    with env.store.transaction() as tx:
        source = tx.create(
            "source",
            {
                "received_at": env.clock.text(),
                "kind": "pasted",
                "title": "A limited message",
                "content_hash": "0" * 64,
                "trust": "trusted",
                "audience": {"people": [env.pm, env.ana]},
            },
            _TEST,
        )
    with pytest.raises(StoreError, match="limited to"):
        apply_as_person(env.store, env.cfg, [env.message(to=[env.ben], sources=[source.id])], "Drafted an act")
    made = env.draft(sources=[source.id])
    assert env.act(made)["sources"] == [source.id]


def test_a_plugins_channel_is_registered_by_name_and_the_core_ships_copy(env):
    from engine.plugin_api import Registrar, Settings

    registrar = Registrar("example", Settings())
    registrar.channel("example/mail", "Example mail", ["message"], send=lambda act, key: None)
    assert (
        registrar.channels["example/mail"].kinds == ("message",) and registrar.channels["example/mail"].status is None
    )
    for bad in (
        dict(name="other/mail", kinds=["message"]),  # not the plugin's own name
        dict(name="example/mail", kinds=["message"]),  # twice
        dict(name="example/post", kinds=["letter"]),  # not a kind of target
        dict(name="example/none", kinds=[]),
    ):
        with pytest.raises(ValueError):
            registrar.channel(bad["name"], "x", bad["kinds"], send=lambda act, key: None)
    assert "copy" in env.store.plugins.channels() and env.store.plugins.channels()["copy"].manual


# ---- the API ----------------------------------------------


def test_the_api_lists_reads_approves_and_sends_an_act_after_the_yes(api):
    op = {
        "op": "act.draft",
        "channel": "fake",
        "target": {"kind": "message", "recipients": [{"person": api.person, "kind": "email"}]},
        "parts": {"subject": "Proofs", "body": "They ship Monday."},
    }
    cs = apply_as_person(api.store, api.cfg, [op], "Drafted an act")
    act_id = api.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]

    listed = api.get("/api/acts", params={"status": "draft"}).json()["acts"]
    assert [a["id"] for a in listed] == [act_id]
    shown = api.get(f"/api/acts/{act_id}").json()
    assert shown["status"] == "draft" and shown["parts"] == op["parts"] and shown["channel_label"] == "Fake"
    (recipient,) = shown["recipients"]
    assert recipient["address"] == "api.recipient@example.com" and recipient["reasons"] == ["new"]
    assert recipient["key"] == api.person and shown["withheld"] is None

    # a fingerprint the screen did not show, and a recipient not acknowledged, are refused
    wrong = api.post(f"/api/acts/{act_id}/approve", json={"fingerprint": "0" * 64, "acknowledged": [api.person]})
    assert wrong.status_code == 409
    silent = api.post(f"/api/acts/{act_id}/approve", json={"fingerprint": shown["fingerprint"]})
    assert silent.status_code == 409 and "acknowledge" in silent.json()["detail"]

    sent = api.post(
        f"/api/acts/{act_id}/send", json={"fingerprint": shown["fingerprint"], "acknowledged": [api.person]}
    )
    assert sent.status_code == 200 and sent.json()["status"] == "sent"
    assert api.get(f"/api/acts/{act_id}").json()["status"] == "sent"
    assert [a["id"] for a in api.get("/api/acts", params={"status": "sent"}).json()["acts"]] == [act_id]
    assert api.fake.delivered[0][0].recipients[0].address == "api.recipient@example.com"
    assert api.get("/api/acts/OUT-99").status_code == 404


def test_the_api_withdraws_an_act_and_takes_the_persons_answers_for_one_it_cannot_confirm(api):
    def draft() -> str:
        op = {
            "op": "act.draft",
            "channel": "fake",
            "target": {"kind": "message", "recipients": [{"person": api.person, "kind": "email"}]},
            "parts": {"body": "Hello."},
        }
        cs = apply_as_person(api.store, api.cfg, [op], "Drafted an act")
        return api.store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]

    def body(act_id: str) -> dict:
        return {"fingerprint": api.get(f"/api/acts/{act_id}").json()["fingerprint"], "acknowledged": [api.person]}

    withdrawn = draft()
    assert api.post(f"/api/acts/{withdrawn}/withdraw").json()["status"] == "withdrawn"
    assert api.post(f"/api/acts/{withdrawn}/withdraw").status_code == 409

    api.fake.mode = "timeout_after_send"
    api.fake.answer = "unknown"
    api.store.plugins.core_channels["fake"] = api.fake.registration()
    unsure = draft()
    assert api.post(f"/api/acts/{unsure}/send", json=body(unsure)).json()["status"] == "sending"
    Publisher(api.store, api.cfg).resume()
    assert api.get(f"/api/acts/{unsure}").json()["status"] == "uncertain"
    assert api.post(f"/api/acts/{unsure}/settle", json={"answer": "sent"}).json()["status"] == "sent"

    api.fake.mode = "succeed"
    again = draft()
    api.fake.mode = "timeout_after_send"
    api.post(f"/api/acts/{again}/send", json=body(again))
    Publisher(api.store, api.cfg).resume()
    api.fake.mode = "succeed"
    answered = api.post(f"/api/acts/{again}/settle", json={"answer": "again"}).json()
    assert answered["status"] == "sent" and len(api.fake.delivered) == 3
