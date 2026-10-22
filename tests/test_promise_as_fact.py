"""promise-as-fact: someone's promise with a date, recorded as a fact, goes back once to be recorded as their action."""

from __future__ import annotations

import pytest

from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from engine.yaml_load import load_yaml
from tests.conftest import DEMO_A, DEMO_B, fixture_records

LINT = "promise-as-fact"
_PM = WriteContext(actor="pm", trust="trusted", op="test")
PEOPLE = fixture_records(DEMO_B, "person")
ME = next(p for p in PEOPLE if p["id"] == "PER-1")
TEAMMATE = next(
    p
    for p in PEOPLE
    if p["id"] != ME["id"]
    and p.get("team") == ME["team"]
    and sum(q["full_name"].split()[0] == p["full_name"].split()[0] for q in PEOPLE) == 1
)
OUTSIDER = next(p for p in PEOPLE if p.get("team") not in (None, ME["team"]))
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
CASE = load_yaml((DEMO_A / "evals" / "new-person-with-organization.yaml").read_text(encoding="utf-8"))
NEW = next(op for op in CASE["stub_answer"]["ops"] if op["op"] == "person.add")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def first(person: dict) -> str:
    return person["full_name"].split()[0]


def fact(quote: str, **more) -> dict:
    return {"op": "fact", "text": quote, "evidence": {"quote": quote}, **more}


def found(env, ops: list[dict], *, actor: str = "assistant") -> list:
    _, cfg, store = env
    raw = "\n".join(op["evidence"]["quote"] for op in ops if "evidence" in op)
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", "SRC-1", raw, "", "untrusted"),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if p.check == LINT]


def test_a_new_persons_dated_promise_recorded_as_a_fact_is_sent_back_to_be_their_action(env):
    quote = f"{NEW['full_name']} from {NEW['org']} will drive the pallet audit by the 20th"
    person = {"op": "person.add", "full_name": NEW["full_name"], "org": NEW["org"]}
    (problem,) = found(env, [person, fact(quote)])
    assert (problem.severity, problem.op) == ("return", 1)
    assert NEW["full_name"] in problem.message and "action.add" in problem.message


def test_a_teammates_promise_by_first_name_is_sent_back_too(env):
    (problem,) = found(env, [fact(f"{first(TEAMMATE)} will draft the pilot plan by the 30th.")])
    assert problem.op == 0


def test_a_state_no_date_nobody_named_or_words_another_op_quotes_are_left_alone(env):
    assert found(env, [fact(f"{first(TEAMMATE)} will be away on the 20th.")]) == []
    assert found(env, [fact(f"{first(TEAMMATE)} will draft the pilot plan.")]) == []
    assert found(env, [fact("The depot will close by the 20th.")]) == []
    quote = f"{first(TEAMMATE)} will draft the pilot plan by the 30th."
    action = {
        "op": "action.add",
        "text": "Draft the pilot plan",
        "owners": [TEAMMATE["id"]],
        "evidence": {"quote": quote},
    }
    assert found(env, [action, fact(quote)]) == []


def test_another_teams_promise_a_watched_project_and_the_persons_own_note_are_left_alone(env):
    assert found(env, [fact(f"{OUTSIDER['full_name']} will send the figures by the 30th.")]) == []
    quote = f"{first(TEAMMATE)} will draft the pilot plan by the 30th."
    assert found(env, [fact(quote)], actor="pm") == []
    _, _, store = env
    with store.transaction() as tx:
        project = tx.get("project", PROJECT)
        roles = [{"person": ME["id"], "role": "watch"}]
        tx.update("project", PROJECT, {"roles": roles}, _PM, read_version=project.version)
    assert found(env, [fact(quote, project=PROJECT)]) == []


def test_severity_off_turns_it_off(env):
    _, cfg, _ = env
    cfg.checks.lints[LINT] = "off"
    assert found(env, [fact(f"{first(TEAMMATE)} will draft the pilot plan by the 30th.")]) == []
