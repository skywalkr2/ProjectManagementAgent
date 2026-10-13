"""Text stays text (design 6.7): where an op, a record edit, a suggested setting or a plugin's record needs text and a
mapping or a list arrives, the change is refused with plain words that say to put text with ': ' in quotes, and nothing
is turned into a string. Names and ids come from the fixtures."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import apply_as_person, setting_problem
from engine.dispatcher import Unreadable, parse, process
from engine.intake import hand_in
from engine.storage import Store, StoreError, WriteContext
from engine.text_shape import PUT_IN_QUOTES
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_ask import code_of

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
MAPPING = {"Team wireless": "release on top"}
LISTED = ["Team wireless", "release on top"]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def an_action() -> dict:
    return fixture_records(DEMO_B, "action")[0]


def answer_with(*ops: dict) -> None:
    set_responder(lambda task: json.dumps({"summary": "Changes.", "ops": list(ops)}))


def test_the_message_says_what_arrived_and_what_to_do():
    from engine.text_shape import text_problem

    for value, shape in ((MAPPING, "mapping"), (LISTED, "list")):
        why = text_problem("action.text", value)
        assert why.startswith("action.text has to be text") and shape in why and PUT_IN_QUOTES in why
    assert text_problem("action.text", "Team wireless: release on top") is None
    assert text_problem("action.text", None) is None and text_problem("action.text", 3) is None


def test_an_answer_that_sets_an_actions_text_to_a_mapping_is_refused_and_the_text_is_left_alone(env):
    ws, cfg, store = env
    action = an_action()
    answer_with({"op": "record.set", "kind": "action", "id": action["id"], "field": "text", "value": MAPPING})
    handed = hand_in(ws, store, note="", pasted="The wording of one action changes.", now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    op = store.read().get("changeset", cs_id).data["ops"][0]
    assert op["status"] == "refused"
    why = op["reason"]
    assert why.startswith("action.text has to be text") and PUT_IN_QUOTES in why
    assert "Input should be" not in why
    assert store.read().get("action", action["id"]).data["text"] == action["text"]


def test_a_list_for_a_person_edit_of_a_records_text_field_is_refused(env):
    _, cfg, store = env
    action = store.read().get("action", an_action()["id"])
    for field, value in (("notes", LISTED), ("notes", MAPPING), ("text", LISTED)):
        ops = [
            {
                "op": "record.edit",
                "record": {"kind": "action", "id": action.id},
                "fields": {field: value},
                "read_version": action.version,
            }
        ]
        with pytest.raises(StoreError) as refused:
            apply_as_person(store, cfg, ops, "Test change")
        assert f"action.{field} has to be text" in str(refused.value) and PUT_IN_QUOTES in str(refused.value)
    assert store.read().get("action", action.id).data["text"] == action.data["text"]
    assert store.read().get("action", action.id).data["notes"] == action.data["notes"]


def test_text_with_a_colon_that_arrives_as_text_is_kept_as_one_string(env):
    _, cfg, store = env
    action = store.read().get("action", an_action()["id"])
    title = "Team wireless: release on top"
    apply_as_person(
        store,
        cfg,
        [
            {
                "op": "record.edit",
                "record": {"kind": "action", "id": action.id},
                "fields": {"notes": title},
                "read_version": action.version,
            }
        ],
        "Test change",
    )
    assert store.read().get("action", action.id).data["notes"] == title


def test_a_declared_text_field_given_a_mapping_sends_the_whole_answer_back_with_the_same_words():
    for op in (
        {"op": "action.add", "text": MAPPING, "evidence": "Team wireless: release on top"},
        {"op": "note", "text": LISTED},
        {"op": "question.add", "to": "someone", "title": MAPPING},
    ):
        with pytest.raises(Unreadable) as unreadable:
            parse(json.dumps({"summary": "x", "ops": [op]}))
        assert PUT_IN_QUOTES in str(unreadable.value) and "Input should be" not in str(unreadable.value)


def test_an_organization_that_is_not_text_is_never_turned_into_a_name(env):
    from engine.organizations import resolve

    _, _, store = env
    before = len(store.read().list("organization"))
    with store.transaction() as tx:
        for value in (MAPPING, LISTED):
            with pytest.raises(StoreError, match=PUT_IN_QUOTES):
                resolve(tx, value, WriteContext("pm", "trusted", "edit"))
    assert len(store.read().list("organization")) == before


def test_a_record_written_with_a_mapping_in_a_text_field_is_refused_for_any_writer(env):
    _, _, store = env
    action = store.read().get("action", an_action()["id"])
    with pytest.raises(StoreError, match=PUT_IN_QUOTES), store.transaction() as tx:
        tx.update(
            "action",
            action.id,
            {"text": MAPPING},
            WriteContext("pm", "trusted", "edit"),
            read_version=action.version,
        )
    with pytest.raises(StoreError, match=PUT_IN_QUOTES), store.transaction() as tx:
        tx.update(
            "action",
            action.id,
            {"notes": LISTED},
            WriteContext("pm", "trusted", "edit"),
            read_version=action.version,
        )


def test_a_suggested_setting_that_holds_text_is_refused_for_a_mapping_and_a_list_of_text_for_a_mapping_item(env):
    ws, cfg, store = env
    host = SimpleNamespace(path=ws.root / "cockpit.db")
    name = setting_problem(host, code_of(cfg, "workspace.name"), MAPPING)
    assert name and "has to be text" in name and PUT_IN_QUOTES in name
    several = setting_problem(host, code_of(cfg, "workspace.our_accounts"), ["Casey Example", MAPPING])
    assert several and PUT_IN_QUOTES in several
    assert setting_problem(host, code_of(cfg, "workspace.name"), "Team wireless: release on top") is None
