"""A phone number in a known sender's signature is offered for their record by rule (design 6.7): the changeset gets a
`person.contact` op with the signature line as evidence, which waits for the person like any contact detail. A rule on
the text and the From line, with no AI: a number already on the record, an unknown sender, the person's own mail, a
number only in the body and a contact op the answer already holds all add nothing.

Names, ids and addresses come from the fixtures; the AI is the stub.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, restatements
from engine.dispatcher import process
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET
from engine.signature_contact import phones_in
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
_PM = WriteContext("pm", "trusted", "test")
PEOPLE = fixture_records(DEMO_B, "person")
ME = next(p for p in PEOPLE if p["id"] == "PER-1")
SENDER = next(p for p in PEOPLE if p.get("how_to_reach", {}).get("email"))
SENDER_EMAIL = SENDER["how_to_reach"]["email"]
MY_ADDRESS = f"{ME['full_name'].lower().replace(' ', '.')}@example.com"
PHONE = "555 0142"
SIGNED = f"--\n{SENDER['full_name']}\n{SENDER['role']}\n{PHONE}"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    cfg.workspace.user.accounts = [f"{ME['full_name']} <{MY_ADDRESS}>"]
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def mail(body: str, sender: str | None = None) -> str:
    sender = sender or f"{SENDER['full_name']} <{SENDER_EMAIL}>"
    return f"From: {sender}\nTo: {MY_ADDRESS}\nSubject: Jacket proofs\n\n{body}\n"


def contacts(env, raw: str, ops: list | None = None, *, actor: str = "assistant") -> list:
    """The person.contact ops of the answer once the applier has read it, for an answer with these ops to this input."""
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops or []}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", "SRC-1", raw, "", "untrusted"),
        actor=actor,
    )
    return [op for op in restatements(cs, ctx).ops if op.op == "person.contact"]


def test_a_known_senders_signature_phone_is_proposed(env):
    (op,) = contacts(env, mail(f"The jacket proofs look right to me.\n\n{SIGNED}"))
    assert (op.person, op.kind, op.value, op.evidence.quote) == (SENDER["id"], "phone", PHONE, PHONE)


def test_the_line_holding_the_number_is_the_evidence_and_the_number_stays_as_written(env):
    raw = mail(f"Looks right.\n\nBest,\n{SENDER['full_name']}\nTel: +1 (555) 014-2000 ext 3")
    (op,) = contacts(env, raw)
    assert op.value == "+1 (555) 014-2000" and op.evidence.quote == "Tel: +1 (555) 014-2000 ext 3"


def test_a_proposed_contact_waits_for_the_person_through_a_real_run(env):
    ws, cfg, store = env
    set_responder(lambda task: json.dumps({"summary": "Nothing to do.", "ops": []}))
    handed = hand_in(ws, store, pasted=mail(f"Looks right.\n\n{SIGNED}"), now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    held = [o for o in store.read().get("changeset", cs_id).data["ops"] if o["op"]["op"] == "person.contact"]
    assert len(held) == 1 and held[0]["status"] == "held"
    assert PHONE in held[0]["label"] and SENDER["full_name"] in held[0]["label"]
    assert not store.read().get("person", SENDER["id"]).data.get("how_to_reach", {}).get("phone")


def test_a_phone_already_on_the_record_is_not_proposed(env):
    _, _, store = env
    record = store.read().get("person", SENDER["id"])
    with store.transaction() as tx:
        reach = {**record.data["how_to_reach"], "phone": "555-0142"}
        tx.update("person", SENDER["id"], {"how_to_reach": reach}, _PM, read_version=record.version)
    assert contacts(env, mail(f"Looks right.\n\n{SIGNED}")) == []


def test_an_unknown_sender_is_not_proposed(env):
    raw = mail(f"Looks right.\n\n{SIGNED}", sender="Someone Unlisted <unlisted@example.com>")
    assert contacts(env, raw) == []


def test_the_persons_own_sent_mail_is_not_proposed(env):
    assert contacts(env, mail(f"Looks right.\n\n{SIGNED}", sender=f"{ME['full_name']} <{MY_ADDRESS}>")) == []
    assert contacts(env, f"{ME['full_name']}\n{PHONE}") == []


def test_the_persons_own_changes_are_not_read(env):
    assert contacts(env, mail(f"Looks right.\n\n{SIGNED}"), actor="pm") == []


def test_a_phone_only_in_the_body_is_not_proposed(env):
    assert contacts(env, mail(f"Call the printer on {PHONE} before Friday.\n\nBest,\n{SENDER['full_name']}")) == []


def test_the_models_own_contact_for_it_is_kept_and_no_second_one_is_added(env):
    own = {
        "op": "person.contact",
        "person": SENDER["id"],
        "kind": "phone",
        "value": PHONE,
        "evidence": {"quote": PHONE},
    }
    (op,) = contacts(env, mail(f"Looks right.\n\n{SIGNED}"), [own])
    assert op.evidence.quote == PHONE and op.person == SENDER["id"]


def test_an_address_a_link_a_day_and_a_short_run_are_not_phone_numbers(env):
    lines = [
        SENDER_EMAIL.replace("@", "2026101@"),
        "www.example.com/1234567",
        "Sent 2026-10-09",
        "Suite 200",
        "Room 12-34",
    ]
    assert phones_in(lines, 7) == []
    assert phones_in(["Room 12-34"], 4) == [("12-34", "Room 12-34")]


def test_the_minimum_digit_count_is_config(env):
    _, cfg, _ = env
    cfg.workspace.phone_min_digits = 9
    assert contacts(env, mail(f"Looks right.\n\n{SIGNED}")) == []
