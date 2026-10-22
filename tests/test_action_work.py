"""Handing an action to the assistant (design 6.7, 7.5; roadmap B-6b): the person asks for the work an action stands for
(a message, a list, a page) to be drafted. It is one request, estimated and held for the person's go like any other, and
what comes back is a pending draft on the action's `work` text for the person to review. The action stays the person's:
its words, owners, day and status never change. Every way the person changes or rejects the draft is a signal.
Names and ids come from the fixtures; the AI is the stub."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from engine import action_work
from engine import packet as packets
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import apply_as_person
from engine.config.schema import Price
from engine.dispatcher import process
from engine.storage import Store, StoreError, WriteContext
from engine.tasks import task_kind
from engine.texts import read_text, versions
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records, without_first_go
from tests.test_knowledge_section import lesson

NOW = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
TODAY = date(2026, 10, 14)
_PM = WriteContext("pm", "trusted", "test")
PROJECT = fixture_records(DEMO_B, "project")[0]
PERSONS = [p["id"] for p in fixture_records(DEMO_B, "person")]
OWNER = PERSONS[1]
WORDS = "Send the marked proof pages to the printer"
DRAFT = "Hello,\n\nThe marked proof pages are attached.\n\nThank you.\n"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def make_action(store, **fields) -> str:
    data = {"text": WORDS, "owners": [{"person": OWNER}], "project": PROJECT["id"], "due": "2026-10-20", **fields}
    with store.transaction() as tx:
        return tx.create("action", data, _PM).id


def answer(text: str = DRAFT) -> list:
    asked: list = []

    def responder(task):
        asked.append(task)
        return text

    set_responder(responder)
    return asked


def run(env, request_id: str):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def requests_of(store) -> list:
    return [r for r in store.read().list("request") if r.data["task"] == action_work.TASK]


def drafts(store, action_id: str) -> list:
    return versions(store.read(), "action", action_id, "work")


def person_does(env, op: dict) -> str:
    _, cfg, store = env
    return apply_as_person(store, cfg, [op], "Reviewed the draft")


def signals(store) -> list:
    return store.read().list("signal")


# ---- handing it over ----------------------------------------------------------------------------------------------


def test_handing_an_action_over_queues_one_request_for_it_and_changes_nothing_else(env):
    _, _, store = env
    action = make_action(store)
    before = store.read().get("action", action)
    request = action_work.hand_over(store, action)
    (queued,) = requests_of(store)
    assert queued.id == request
    assert queued.data["about"] == {"kind": "action", "id": action}
    assert (queued.data["origin"], queued.data["state"]) == ("pm", "queued")
    after = store.read().get("action", action)
    assert after.version == before.version and after.data == before.data


def test_only_an_open_action_can_be_handed_over(env):
    _, _, store = env
    done = make_action(store, status="done", done_by=[OWNER])
    with pytest.raises(StoreError, match="open"):
        action_work.hand_over(store, done)
    with pytest.raises(StoreError, match="no action"):
        action_work.hand_over(store, "ACT-9999")
    assert requests_of(store) == []


def test_an_action_already_with_the_assistant_is_not_handed_over_twice(env):
    _, _, store = env
    action = make_action(store)
    action_work.hand_over(store, action)
    with pytest.raises(StoreError, match="already"):
        action_work.hand_over(store, action)
    assert len(requests_of(store)) == 1


def test_the_persons_note_goes_with_the_request(env):
    _, _, store = env
    action = make_action(store)
    action_work.hand_over(store, action, note="  Keep it to three lines.  ")
    assert requests_of(store)[0].data["note"] == "Keep it to three lines."


# ---- the packet ---------------------------------------------------------------------------------------------------


def test_the_packet_has_the_instructions_what_was_learned_and_the_action_marked_as_data(env):
    ws, cfg, store = env
    action = make_action(store, notes="The printer wants PDF files only.")
    learned = lesson(store, "Messages to a printer are short and say what is attached.", guard="Keep it short.")
    request = action_work.hand_over(store, action, note="Keep it to three lines.")
    built = packets.build(ws, store, cfg, request, TODAY)
    assert built.task.kind == action_work.TASK and built.task.output == "text"
    assert built.task.instructions.startswith("You are")
    assert learned in built.task.stable or learned in built.task.request
    assert built.knowledge is not None and learned in built.knowledge.given
    assert built.about == ("action", action) and built.draft_base is None
    request_text = built.task.request
    assert WORDS in request_text and "The printer wants PDF files only." in request_text
    assert "2026-10-20" in request_text and PROJECT["name"] in request_text
    assert "Keep it to three lines." in request_text
    assert request_text.count("<untrusted") >= 1 and built.untrusted_material
    assert "<untrusted" not in built.task.stable  # stable parts first, and none of them is data


def test_a_second_draft_starts_from_the_text_the_person_kept(env):
    ws, cfg, store = env
    action = make_action(store)
    person_does(env, {"op": "text.edit", "record": {"kind": "action", "id": action}, "field": "work", "text": DRAFT})
    request = action_work.hand_over(store, action)
    built = packets.build(ws, store, cfg, request, TODAY)
    assert "The marked proof pages are attached." in built.task.request
    assert built.draft_base == 1


# ---- the run ------------------------------------------------------------------------------------------------------


def test_a_run_files_a_pending_draft_on_the_action_and_leaves_the_action_alone(env):
    _, _, store = env
    action = make_action(store)
    before = store.read().get("action", action)
    asked = answer()
    request = action_work.hand_over(store, action)
    run(env, request)
    (draft,) = drafts(store, action)
    assert (draft.data["status"], draft.data["source"]) == ("pending", "draft")
    assert read_text(store, draft.data["sha256"]).strip() == DRAFT.strip()
    after = store.read().get("action", action)
    assert {k: v for k, v in after.data.items() if k != "work"} == {k: v for k, v in before.data.items() if k != "work"}
    assert after.data.get("work") is None  # nothing is the action's text until the person accepts it
    assert store.read().get("request", request).data["state"] == "review"
    assert asked and asked[0].kind == action_work.TASK


def test_a_run_writes_its_knowledge_log(env):
    _, _, store = env
    action = make_action(store)
    answer()
    run(env, action_work.hand_over(store, action))
    log = store.read().list("run")[-1].data["knowledge"]
    assert set(log) >= {"given", "stable_chars", "rules_present"}


def test_the_kind_is_a_draft_on_the_actions_work_text_and_the_person_starts_it(env):
    kind = task_kind(action_work.TASK)
    assert (kind.output, kind.on, kind.field, kind.ops) == ("draft", "action", "work", ("text.draft",))
    assert kind.where == {"status": ("open",)}


def test_the_run_is_estimated_and_waits_for_the_go_above_the_amount_to_confirm(env):
    ws, cfg, store = env
    use = cfg.ai.tiers["routine"].use
    cfg.ai.prices[use] = Price(input_per_million=500_000.0, output_per_million=500_000.0)
    cfg.ai.budgets.per_run_usd = 1000.0
    cfg.ai.budgets.confirm_above_usd = 0.0
    action = make_action(store)
    asked = answer()
    request = action_work.hand_over(store, action)
    run(env, request)
    held = store.read().get("request", request).data
    assert (held["state"], held["approval"]) == ("needs_you", "required")
    assert held["estimate_usd"] and held["estimate_usd"] > 0
    assert asked == [] and drafts(store, action) == []


# ---- every way the person changes or rejects the draft is a signal -------------------------------------------------


def drafted(env, action: str, text: str = DRAFT):
    _, _, store = env
    answer(text)
    run(env, action_work.hand_over(store, action))
    return drafts(store, action)[-1]


def review(env, version, **op):
    _, _, store = env
    current = store.read().get("text_version", version.id)
    return person_does(env, {"version": version.id, "read_version": current.version, **op})


def test_discarding_the_draft_is_a_signal_naming_the_action_and_the_run(env):
    _, _, store = env
    action = make_action(store)
    draft = drafted(env, action)
    review(env, draft, op="text.discard")
    (signal,) = signals(store)
    assert signal.data["kind"] == "dropped" and signal.data["refs"] == [action]
    assert signal.data["run"] == draft.data["run"] and signal.data["changeset"]
    assert store.read().get("text_version", draft.id).data["status"] == "discarded"
    assert not signal.data.get("note"), "setting a draft aside gives no reason, so there is nothing to learn from"
    assert [r for r in store.read().list("request") if r.data["task"] == "learn-correction"] == []


def test_accepting_the_draft_as_it_is_corrects_nothing(env):
    _, _, store = env
    action = make_action(store)
    draft = drafted(env, action)
    review(env, draft, op="text.accept", choices={})
    assert signals(store) == []
    assert read_text(store, store.read().get("text_version", draft.id).data["sha256"]).strip() == DRAFT.strip()


def test_accepting_only_some_of_it_is_a_signal_with_the_text_as_the_person_kept_it(env):
    _, _, store = env
    action = make_action(store)
    first = "One.\n\nTwo.\n\nThree.\n"
    person_does(env, {"op": "text.edit", "record": {"kind": "action", "id": action}, "field": "work", "text": first})
    draft = drafted(env, action, "Uno.\n\nTwo.\n\nTres.\n")
    review(env, draft, op="text.accept", choices={"c2": "reject"})
    (signal,) = signals(store)
    assert signal.data["kind"] == "draft_edited" and signal.data["refs"] == [action]
    assert "Uno." in signal.data["note"] and "Three." in signal.data["note"] and "Tres." not in signal.data["note"]


def test_rejecting_every_change_when_accepting_is_a_dropped_draft(env):
    _, _, store = env
    action = make_action(store)
    draft = drafted(env, action)
    review(env, draft, op="text.accept", choices={"c1": "reject"})
    assert [s.data["kind"] for s in signals(store)] == ["dropped"]


def test_the_persons_own_text_edit_is_not_a_correction(env):
    _, _, store = env
    action = make_action(store)
    person_does(env, {"op": "text.edit", "record": {"kind": "action", "id": action}, "field": "work", "text": DRAFT})
    assert signals(store) == []


def test_after_a_discard_the_action_can_be_handed_over_again(env):
    _, _, store = env
    action = make_action(store)
    draft = drafted(env, action)
    review(env, draft, op="text.discard")
    action_work.hand_over(store, action)
    assert len(requests_of(store)) == 2


def test_an_action_with_a_draft_waiting_is_not_handed_over_again(env):
    _, _, store = env
    action = make_action(store)
    drafted(env, action)
    with pytest.raises(StoreError, match="already"):
        action_work.hand_over(store, action)
