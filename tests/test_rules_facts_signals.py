"""Phase L1: standing rules as records, facts with key, as_of and supersedes, signals that name what they correct.

Names come from the imprint fixture, never written out here.
"""

import json
from datetime import UTC, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import apply_as_person, release
from engine.config.schema import RulesFile
from engine.dispatcher import process, send_back, signal, undo_changeset
from engine.facts import superseded_by
from engine.intake import hand_in
from engine.names import People
from engine.rules import active_rules, rule_names, seed_rules
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.roundtrip import round_trip

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def answers(*bodies: dict) -> None:
    queue = [json.dumps(b) for b in bodies]
    set_responder(lambda task: queue.pop(0) if len(queue) > 1 else queue[0])


def run(env, pasted: str, now: datetime = NOW):
    ws, cfg, store = env
    handed = hand_in(ws, store, note="", pasted=pasted, now=now)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=now)
    return handed, cs_id


def outcome(store, cs_id, index=0):
    return store.read().get("changeset", cs_id).data["ops"][index]


def starting_set(store, *rules):
    store.plugins.cfg.files["rules"] = RulesFile(rules=list(rules))


def by_name(store, name):
    return next(r for r in store.read().list("rule") if r.data["name"] == name)


# ---- rules -----------------------------------------------------------------------------------------------------------


def test_seeding_makes_each_starting_rule_an_active_seed_record_once(env):
    _, _, store = env
    starting_set(
        store,
        {
            "id": "R-1",
            "text": "Say who raised each risk.",
            "applies_to": {"task_kinds": ["notes"]},
            "added": "2026-10-01",
        },
        {"id": "R-2", "text": "An old rule.", "status": "retired"},
    )
    assert seed_rules(store) == ["R-1", "R-2"]
    first = by_name(store, "R-1").data
    assert first["origin"] == "seed" and first["status"] == "active" and first["kept_by"] is None
    assert first["text"] == "Say who raised each risk." and first["applies_to"]["task_kinds"] == ["notes"]
    assert first["learned_at"].startswith("2026-10-01")
    assert by_name(store, "R-2").data["status"] == "retired"
    before = {r.id: r.version for r in store.read().list("rule")}
    assert seed_rules(store) == []
    assert {r.id: r.version for r in store.read().list("rule")} == before
    assert [r.id for r in active_rules(store)] == ["R-1"] and rule_names(store) == {"R-1", "R-2"}


def test_a_retired_seed_rule_is_not_made_again(env):
    _, cfg, store = env
    starting_set(store, {"id": "R-1", "text": "Say who raised each risk."})
    seed_rules(store)
    record = by_name(store, "R-1")
    apply_as_person(store, cfg, [{"op": "rule.retire", "id": record.id}], "Retire a rule")
    assert by_name(store, "R-1").data["status"] == "retired"
    assert seed_rules(store) == []
    assert active_rules(store) == [] and len(store.read().list("rule")) == 1


def test_starting_the_app_seeds_the_rules_before_anything_reads_them(tmp_path):
    from api.app import create_app

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    (ws.config_dir / "rules.yaml").write_text("rules:\n  - id: R-1\n    text: Be ready\n")
    cfg = ws.config(env={})
    app = create_app(ws, cfg, "t", start_worker=False)
    store = app.state.worker.store
    assert [r.data["name"] for r in store.read().list("rule")] == ["R-1"]


def test_rule_add_without_a_name_gets_one_and_a_rule_cannot_reuse_a_name_or_name_a_missing_check(env):
    _, cfg, store = env
    starting_set(store, {"id": "R-1", "text": "Seeded."})
    seed_rules(store)
    cs_id = apply_as_person(store, cfg, [{"op": "rule.add", "text": "Prose only"}], "Add a rule")
    (added,) = outcome(store, cs_id)["records"]
    name = store.read().get("rule", added["id"]).data["name"]
    assert name == "rule-" + added["id"].split("-")[1]
    with pytest.raises(Exception, match="already a rule named"):
        apply_as_person(store, cfg, [{"op": "rule.add", "text": "Again", "name": "R-1"}], "Add a rule")
    with pytest.raises(Exception, match="no check called"):
        apply_as_person(store, cfg, [{"op": "rule.add", "text": "Checked", "check": "missing/check"}], "Add a rule")


def test_a_rule_from_an_input_is_a_proposal_the_person_makes_theirs_by_keeping_it(env):
    _, cfg, store = env
    pasted = "From now on every risk names who raised it."
    answers({"ops": [{"op": "rule.add", "text": "Every risk names who raised it.", "evidence": {"quote": pasted}}]})
    _, cs_id = run(env, pasted)
    assert outcome(store, cs_id)["status"] == "applied"
    (rule,) = store.read().list("rule")
    pm = People(store, cfg).pm
    assert pm is not None
    assert (rule.data["origin"], rule.data["status"], rule.data["trust"]) == ("input", "proposed", "untrusted")
    assert rule.data["kept_by"] is None and rule.data["evidence"]["quote"] == pasted
    assert active_rules(store) == []  # a proposal changes nothing until it is kept
    apply_as_person(
        store,
        cfg,
        [
            {
                "op": "record.edit",
                "record": {"kind": "rule", "id": rule.id},
                "fields": {"status": "active", "kept_by": pm, "kept_at": store.clock(), "trust": "trusted"},
                "read_version": rule.version,
            }
        ],
        "Kept what was learned",
    )
    kept = store.read().get("rule", rule.id).data
    assert (kept["status"], kept["kept_by"], kept["trust"], kept["origin"]) == ("active", pm, "trusted", "input")


def test_rules_and_their_history_survive_export_and_import(env, tmp_path):
    _, cfg, store = env
    starting_set(store, {"id": "R-1", "text": "Seeded."})
    seed_rules(store)
    apply_as_person(store, cfg, [{"op": "rule.add", "text": "Added by the person."}], "Add a rule")
    apply_as_person(store, cfg, [{"op": "rule.retire", "id": by_name(store, "R-1").id}], "Retire a rule")
    assert round_trip(store, cfg, tmp_path / "trip")["differences"] == []


# ---- facts -----------------------------------------------------------------------------------------------------------


def fact_ops(text, quote, **more):
    return {"ops": [{"op": "fact", "text": text, "evidence": {"quote": quote}, **more}]}


def only_fact(store, cs_id):
    (touched,) = outcome(store, cs_id)["records"]
    return store.read().get("fact", touched["id"])


def test_a_fact_takes_the_day_its_input_arrived_unless_it_says_another_day(env):
    _, _, store = env
    one = "The venue holds two hundred guests."
    answers(fact_ops("The venue holds two hundred guests.", one, key=True))
    handed, cs_id = run(env, one)
    fact = only_fact(store, cs_id)
    arrived = store.read().get("source", handed.source).data["received_at"]
    assert fact.data["key"] is True and fact.data["as_of"] == arrived[:10]
    two = "As of the first of September the hall held one hundred."
    answers(fact_ops("The hall held one hundred guests.", two, as_of="2026-09-01"))
    _, cs_id = run(env, two, LATER)
    again = only_fact(store, cs_id)
    assert again.data["as_of"] == "2026-09-01" and again.data["key"] is False and again.data["supersedes"] is None


def test_a_fact_from_a_typed_note_takes_the_day_the_request_was_made(env):
    ws, cfg, store = env
    note = "The hall is booked."
    answers(fact_ops("The hall is booked.", note))
    handed = hand_in(ws, store, note=note, pasted="", now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    request = store.read().get("request", handed.request)
    assert only_fact(store, cs_id).data["as_of"] == request.data["created_at"][:10]


def test_a_fact_from_a_typed_note_that_names_an_earlier_day_takes_that_day(env):
    """A note often reports something said earlier: the day the text names wins over the day the note was typed."""
    ws, cfg, store = env
    note = "The hall was confirmed as booked last Friday."
    answers(fact_ops("The hall is booked.", note, as_of="2026-10-02"))
    handed = hand_in(ws, store, note=note, pasted="", now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    typed = store.read().get("request", handed.request).data["created_at"][:10]
    assert typed != "2026-10-02" and only_fact(store, cs_id).data["as_of"] == "2026-10-02"


def test_a_newer_fact_marks_the_older_one_as_replaced_and_undo_takes_the_mark_away(env):
    _, _, store = env
    old = "The book ships in the spring."
    answers(fact_ops("The book ships in the spring.", old))
    _, first_cs = run(env, old)
    older = only_fact(store, first_cs)
    assert superseded_by(store.read(), older.id) is None
    new = "The book now ships in the autumn."
    answers(fact_ops("The book ships in the autumn.", new, supersedes=older.id))
    _, second_cs = run(env, new, LATER)
    newer = only_fact(store, second_cs)
    assert newer.data["supersedes"] == older.id
    assert superseded_by(store.read(), older.id) == newer.id
    assert store.read().get("fact", older.id).data["text"] == "The book ships in the spring."  # kept, findable
    assert {f.id for f in store.read().list("fact")} == {older.id, newer.id}
    undo_changeset(store, second_cs)
    assert superseded_by(store.read(), older.id) is None


def test_a_fact_cannot_replace_nothing_or_something_already_replaced(env):
    _, _, store = env
    text = "The book ships in the spring."
    answers(fact_ops(text, text))
    _, first_cs = run(env, text)
    older = only_fact(store, first_cs)
    later = "The book now ships in the autumn."
    answers(fact_ops(later, later, supersedes=older.id))
    run(env, later, LATER)
    again = "The book now ships in the winter."
    answers(fact_ops(again, again, supersedes=older.id))
    _, cs_id = run(env, again, LATER)
    refused = outcome(store, cs_id)
    assert refused["status"] == "refused" and "already replaced" in refused["reason"]
    answers(fact_ops(again, again, supersedes="FACT-999"))
    _, cs_id = run(env, again, LATER)
    assert outcome(store, cs_id)["status"] == "refused" and "no fact FACT-999" in outcome(store, cs_id)["reason"]


def test_fact_fields_survive_export_and_import(env, tmp_path):
    _, cfg, store = env
    text = "The book ships in the spring."
    answers(fact_ops(text, text, key=True, as_of="2026-09-01"))
    run(env, text)
    assert round_trip(store, cfg, tmp_path / "trip")["differences"] == []


# ---- signals ---------------------------------------------------------------------------------------------------------


def one_note(env, pasted="Anything at all."):
    answers({"ops": [{"op": "note", "text": "Something."}]})
    _, cs_id = run(env, pasted)
    return cs_id, store_of(env).read().get("changeset", cs_id).data["run"]


def store_of(env):
    return env[2]


def signals(store, kind):
    return [s.data for s in store.read().list("signal") if s.data["kind"] == kind]


def test_sending_back_and_undoing_name_the_changeset_and_its_run(env):
    _, _, store = env
    cs_id, run_id = one_note(env)
    assert run_id is not None
    send_back(store, cs_id, "This should have been an action.")
    (sent,) = signals(store, "sent_back")
    assert sent["changeset"] == cs_id and sent["run"] == run_id
    cs_id, run_id = one_note(env, "Another input entirely.")
    undo_changeset(store, cs_id)
    (undone,) = signals(store, "undone")
    assert undone["changeset"] == cs_id and undone["run"] == run_id


def test_saying_who_a_name_is_names_the_changeset_and_its_run(env):
    _, cfg, store = env
    stranger = "Jordan " + "Pike"
    pasted = f"{stranger} will book the venue."
    answers(
        {
            "ops": [
                {"op": "action.add", "text": "Book the venue", "owners": [stranger], "evidence": {"quote": pasted[:-1]}}
            ]
        }
    )
    _, cs_id = run(env, pasted)
    run_id = store.read().get("changeset", cs_id).data["run"]
    publicist = next(p.id for p in store.read().list("person") if p.data.get("role") == "Publicist")
    release(store, cfg, cs_id, 0, person=publicist)
    (routed,) = signals(store, "routed")
    assert routed["changeset"] == cs_id and routed["run"] == run_id


def test_a_correction_of_something_no_run_made_leaves_run_and_changeset_empty(env):
    _, _, store = env
    action = store.read().list("action")[0].id
    from engine.followups import put_on_hold, take_off_hold

    put_on_hold(store, action, "the printer", now=NOW)
    take_off_hold(store, action, now=NOW)
    held = signals(store, "put_on_hold") + signals(store, "taken_off_hold")
    assert len(held) == 2 and all(s["run"] is None and s["changeset"] is None for s in held)
    signal(store, "pulled_back", [action], "Closed by a rule")
    (pulled,) = signals(store, "pulled_back")
    assert pulled["run"] is None and pulled["changeset"] is None


def test_a_signal_given_a_changeset_takes_its_run_and_one_given_both_keeps_them(env):
    _, _, store = env
    cs_id, run_id = one_note(env)
    signal(store, "dropped", [cs_id], changeset=cs_id)
    signal(store, "reworded", [cs_id], changeset=cs_id, run="RUN-99")
    dropped, reworded = signals(store, "dropped")[0], signals(store, "reworded")[0]
    assert dropped["run"] == run_id and reworded["run"] == "RUN-99"
    with store.transaction() as tx:
        tx.create(
            "signal", {"kind": "set_aside", "refs": [], "at": NOW.isoformat()}, WriteContext("pm", "trusted", "t")
        )
    assert signals(store, "set_aside")[0]["changeset"] is None
