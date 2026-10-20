"""An ending needs delivery words to be done (design 6.33, endings): "mark this closed" isn't "done".

The engine reads the words an ending quotes, not the model: delivery words close the action and credit its owners,
words about learning it elsewhere or it no longer mattering call it off with nobody credited, and a bare "closed"
asks "Done by <owner>, or no longer needed?", even from the person's own note. Each answer applies with Undo and
records its signal; calling off what an owner was told about drafts one line for the person to send. Names, ids and
words come from the fixtures and the settings.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from engine import endings, held_ask
from engine.applier import Context, Inputs, apply_as_person, apply_changeset, release, undo
from engine.config.schema import LanguageFile
from engine.dispatcher import signal as record_signal  # noqa: F401  (the one place signals are written)
from engine.names import People
from engine.ops import CHANGESET
from engine.record_page import _completed
from engine.storage import Store, StoreError, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B, fixture_records
from tests.test_corrections import pm_of, signals
from tests.test_knowledge_records import apply, request, source

_TEST = WriteContext(actor="pm", trust="trusted", op="test.endings")
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
ACTIONS = fixture_records(DEMO_B, "action")
OPEN = [a for a in ACTIONS if a.get("status", "open") == "open" and a.get("owners")]

DELIVERED = "She sent it yesterday"
CALLED_OFF = "The planning sessions will cover it"
CLOSED = "Mark it closed"
BOTH = "She sent it, and the planning sessions will cover the rest"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def someone_elses(cfg) -> dict:
    return next(a for a in OPEN if a["owners"][0]["person"] != pm_of(cfg))


def owners_of(action) -> list[str]:
    return [o["person"] for o in action["owners"]]


def data(store, record_id, kind="action") -> dict:
    return store.read().get(kind, record_id).data


def close_op(action_id, quote):
    return {"op": "action.close", "id": action_id, "evidence": {"quote": quote}}


def drop_op(action_id, quote, reason="Not needed"):
    return {"op": "action.drop", "id": action_id, "reason": reason, "evidence": {"quote": quote}}


def own_note(store, cfg, op):
    """The op the assistant proposes from the person's own note, which holds the quote."""
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request(store, "pm"), None, "", op["evidence"]["quote"], "trusted"),
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def from_input(store, cfg, op):
    return apply(
        store, cfg, [op], origin="input", trust="untrusted", source_id=source(store), raw=op["evidence"]["quote"]
    )


def linked(store, cs_id):
    """Tie the request the changeset was made for to it, as a run does, so Today shows its held items."""
    changeset = store.read().get("changeset", cs_id)
    with store.transaction() as tx:
        found = tx.get("request", changeset.data["request"])
        tx.update("request", found.id, {"changeset": cs_id}, _TEST, read_version=found.version)


def op_of(store, cs_id, index=0) -> dict:
    return store.read().get("changeset", cs_id).data["ops"][index]


# ---- reading the words ----------------------------------------------------------------------------------------------


def test_the_words_are_read_whole_and_each_kind_wins_only_alone(env):
    _, cfg, _ = env
    words = cfg.language
    assert endings.reading(DELIVERED, words) == "done"
    assert endings.reading(CALLED_OFF, words) == "called_off"
    assert endings.reading(CLOSED, words) == "choice"
    assert endings.reading(BOTH, words) == "choice"  # delivery and a call-off together are not one answer
    assert endings.reading("Mark it closed, it's moot", words) == "called_off"  # a call-off settles "closed"
    assert endings.reading("Mark it closed, she sent it", words) == "done"
    assert endings.reading("Thanks for checking in", words) is None  # no ending words at all: left as proposed
    assert endings.reading("It's undone", words) is None  # whole words only


# ---- the rule through the applier ----------------------------------------------------------------------------------


def test_done_with_delivery_words_credits_the_owner_from_the_persons_own_note_and_from_an_input(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    cs_id, result = own_note(store, cfg, close_op(target["id"], DELIVERED))
    assert result == ["applied"]
    done = data(store, target["id"])
    assert done["status"] == "done" and done["done_by"] == owners_of(target)
    # From an input the same words wait for the person's Keep as an ending always did, and then credit the owner.
    other = next(a for a in OPEN if a["id"] != target["id"] and a["owners"][0]["person"] != pm_of(cfg))
    cs_id, result = from_input(store, cfg, close_op(other["id"], DELIVERED))
    assert result == ["held"]
    release(store, cfg, cs_id, 0)
    assert data(store, other["id"])["done_by"] == owners_of(other)


def test_call_off_words_drop_with_the_words_as_the_reason_and_credit_nobody(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    cs_id, result = own_note(store, cfg, close_op(target["id"], CALLED_OFF))
    assert result == ["applied"]
    assert op_of(store, cs_id)["op"]["op"] == "action.drop"  # the engine decided, not the model
    gone = data(store, target["id"])
    assert (gone["status"], gone["dropped_reason"]) == ("dropped", CALLED_OFF)
    assert gone["done_by"] == [] and gone["reported_by"] is None
    view = store.read()
    owner = target["owners"][0]["person"]
    assert _completed(view, "person", owner, lambda kind, ident: ident) == []  # nothing on the history others read
    assert undo(store, cs_id).restored == [0]
    assert data(store, target["id"])["status"] == "open"


def test_a_drop_proposed_for_delivery_words_is_not_turned_into_done_and_a_bare_closed_drop_asks(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    _, result = own_note(store, cfg, drop_op(target["id"], "Cancel it"))
    assert result == ["applied"]  # no ending words at all: as the model proposed
    other = next(a for a in OPEN if a["id"] != target["id"] and a["owners"][0]["person"] != pm_of(cfg))
    cs_id, result = own_note(store, cfg, drop_op(other["id"], CLOSED, reason="Marked closed"))
    assert result == ["held"]
    assert data(store, other["id"])["status"] == "open"
    assert endings.CHOICE_WAITS in op_of(store, cs_id)["reason"]


@pytest.mark.parametrize("own", [True, False])
def test_closed_alone_holds_one_choice_even_from_the_persons_own_note(env, own):
    ws, cfg, store = env
    target = someone_elses(cfg)
    cs_id, result = (own_note if own else from_input)(store, cfg, close_op(target["id"], CLOSED))
    assert result == ["held"]
    assert data(store, target["id"])["status"] == "open" and data(store, target["id"])["done_by"] == []
    held = op_of(store, cs_id)
    assert endings.CHOICE_WAITS in held["reason"]
    linked(store, cs_id)
    line = next(
        line for line in queue(ws, store, cfg, NOW) if line.kind == "held" and line.changeset == cs_id and line.op == 0
    )
    assert line.held["ask"] == "ending"
    assert line.held["quote"] == CLOSED
    people = People(store, cfg)
    assert line.held["owners"] == [people.owner(o) for o in target["owners"]]
    assert line.held["item"] == target["text"]


def test_a_done_that_would_credit_someone_else_with_no_word_of_delivery_asks_and_the_persons_own_does_not(env):
    _, cfg, store = env
    other = someone_elses(cfg)
    _, result = from_input(store, cfg, close_op(other["id"], "All good on that one"))
    assert result == ["held"] and data(store, other["id"])["done_by"] == []
    mine = next((a for a in OPEN if all(o["person"] == pm_of(cfg) for o in a["owners"])), None)
    if mine is not None:
        _, result = own_note(store, cfg, close_op(mine["id"], "All good on that one"))
        assert result != ["held"]


def test_the_describe_of_a_plain_close_is_still_a_close(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    shown = held_ask.describe(store.read(), People(store, cfg), close_op(target["id"], DELIVERED))
    assert shown is not None and shown["ask"] == "close"


def test_each_answer_applies_with_undo_and_records_its_signal(env):
    _, cfg, store = env
    first, second = [a for a in OPEN if a["owners"][0]["person"] != pm_of(cfg)][:2]
    done_cs, _ = own_note(store, cfg, close_op(first["id"], CLOSED))
    off_cs, _ = own_note(store, cfg, close_op(second["id"], CLOSED))

    endings.answer(store, cfg, done_cs, 0, "done", now=NOW)
    done = data(store, first["id"])
    assert done["status"] == "done" and done["done_by"] == owners_of(first)
    assert op_of(store, done_cs)["status"] == "applied"
    assert undo(store, done_cs).restored == [0]
    assert data(store, first["id"])["status"] == "open"

    endings.answer(store, cfg, off_cs, 0, "called_off", now=NOW)
    gone = data(store, second["id"])
    assert (gone["status"], gone["dropped_reason"]) == ("dropped", CLOSED)
    assert gone["done_by"] == [] and gone["reported_by"] is None
    assert op_of(store, off_cs)["op"]["op"] == "action.drop"
    assert undo(store, off_cs).restored == [0]
    assert data(store, second["id"])["status"] == "open"

    kept = signals(store, "answered_assistant")
    assert len(kept) == 2
    assert {s["refs"][0] for s in kept} == {first["id"], second["id"]}
    assert {s["note"] for s in kept} == {
        endings.ANSWER_DONE,
        endings.ANSWER_CALLED_OFF,
    }


def test_an_answer_needs_a_choice_that_still_waits(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    plain, _ = from_input(store, cfg, close_op(target["id"], DELIVERED))
    with pytest.raises(StoreError):
        endings.answer(store, cfg, plain, 0, "called_off", now=NOW)  # an ordinary held ending isn't this choice
    asked, _ = own_note(store, cfg, close_op(target["id"], CLOSED))
    endings.answer(store, cfg, asked, 0, "done", now=NOW)
    with pytest.raises(StoreError):
        endings.answer(store, cfg, asked, 0, "done", now=NOW)  # answered once


def test_the_persons_own_close_on_a_screen_is_not_read_for_words(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    apply_as_person(store, cfg, [{"op": "action.close", "id": target["id"]}], "Mark done")
    assert data(store, target["id"])["status"] == "done"


# ---- an owner who was told ------------------------------------------------------------------------------------------


def test_calling_off_what_an_owner_was_told_drafts_one_line_and_sends_nothing(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    owner = target["owners"][0]["person"]
    with store.transaction() as tx:
        current = tx.get("action", target["id"])
        tx.update(
            "action", target["id"], {"told": {owner: NOW.date().isoformat()}}, _TEST, read_version=current.version
        )
    before = {q.id for q in store.read().list("question")}
    cs_id, result = own_note(store, cfg, close_op(target["id"], CALLED_OFF))
    assert result == ["held"]  # the owner was already told: look at it first, as any drop of a told action
    release(store, cfg, cs_id, 0)
    made = [q for q in store.read().list("question") if q.id not in before]
    assert len(made) == 1
    line = made[0].data
    assert (line["to"], line["status"], line["kind"]) == (owner, "open", "action-notice")
    assert line["title"] == cfg.language.messages.called_off_notice.format(item=target["text"])
    assert line["sent_at"] is None  # nothing is sent by itself
    assert undo(store, cs_id).restored == [0]
    assert store.read().get("question", made[0].id) is None  # Undo takes the draft away with it


def test_an_owner_who_was_never_told_gets_no_line_and_neither_does_the_person(env):
    _, cfg, store = env
    target = someone_elses(cfg)
    before = {q.id for q in store.read().list("question")}
    own_note(store, cfg, close_op(target["id"], CALLED_OFF))
    mine = next(a for a in OPEN if a["owners"][0]["person"] == pm_of(cfg))
    with store.transaction() as tx:
        current = tx.get("action", mine["id"])
        told = {pm_of(cfg): NOW.date().isoformat()}  # the person is never drafted a line about their own action
        tx.update("action", mine["id"], {"told": told}, _TEST, read_version=current.version)
    apply_as_person(store, cfg, [{"op": "action.drop", "id": mine["id"], "reason": "Not needed"}], "Drop")
    assert {q.id for q in store.read().list("question")} == before


# ---- the settings ----------------------------------------------------------------------------------------------------


def test_the_settings_have_descriptions_defaults_and_demo_values_in_both_workspaces():
    for key in ("delivery_words", "called_off_words", "closed_words"):
        assert LanguageFile.model_fields[key].description
        assert getattr(LanguageFile(), key)
    assert LanguageFile.model_fields["messages"].annotation.model_fields["called_off_notice"].description
    for template in (DEMO_A, DEMO_B):
        language = yaml.safe_load((template / "config" / "language.yaml").read_text())
        for key, default in (
            ("delivery_words", endings.DEFAULT_DELIVERY_WORDS),
            ("called_off_words", endings.DEFAULT_CALLED_OFF_WORDS),
            ("closed_words", endings.DEFAULT_CLOSED_WORDS),
        ):
            assert language[key] == list(default)
        assert "{item}" in language["messages"]["called_off_notice"]
    for word in endings.DEFAULT_CLOSED_WORDS:
        assert endings.reading(word, LanguageFile()) == "choice"  # each alone is neither done nor called off
