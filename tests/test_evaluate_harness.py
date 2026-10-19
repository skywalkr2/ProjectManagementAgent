"""The evaluation harness (design 6.16): exact scoring by default, starting records, hostile cases, the report's account
lines, and the harder set in the fictional workplace workspace. Names, ids and quotes come from the cases themselves."""

import json
import re
import shutil
import sys
from collections import Counter
from types import SimpleNamespace

import pytest
import yaml

import engine.evaluate as ev
from engine.evaluate import Report, RunResult, evaluate, load_cases, starting_records
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B, fixture_records

LOAD_CASES = ev.load_cases


def case_of(template, case_id):
    return next(c for c in load_cases(template) if c["id"] == case_id)


def quote_of(case):
    return case["stub_answer"]["ops"][0]["evidence"]["quote"]


def run_edited(monkeypatch, template, case_id, **edits):
    """Run one case with some of its keys replaced (the stub answers with the edited `stub_answer`)."""
    monkeypatch.setattr(ev, "load_cases", lambda t: [{**c, **edits} for c in LOAD_CASES(t) if c["id"] == case_id])
    return evaluate(template, stub=True, runs=1, env={}).results[0]


def with_ops(case, *extra):
    return {**case["stub_answer"], "ops": [*case["stub_answer"]["ops"], *extra]}


def fact_op(case, text="Something else was recorded."):
    return {"op": "fact", "text": text, "evidence": {"quote": quote_of(case)}}


# ---- exact scoring ---------------------------------------------------------------------------------------------------


def pm_id(template):
    return yaml.safe_load((template / "config" / "workspace.yaml").read_text())["user"]["person"]


def someone_else(template):
    return next(p["id"] for p in fixture_records(template, "person") if p["id"] != pm_id(template))


def internal_op(case, template, text="Check the proof with the printer"):
    """An action for the person: an extra that stays inside the workspace."""
    name = next(p["full_name"] for p in fixture_records(template, "person") if p["id"] == pm_id(template))
    return {"op": "action.add", "text": text, "owners": [name], "evidence": {"quote": quote_of(case)}}


def question_op(to, title="Which printer?"):
    links = next(q["links"] for q in fixture_records(DEMO_B, "question") if q.get("links"))
    return {"op": "question.add", "to": to, "title": title, "links": links, "matters_for": "ACT-1"}


def with_allowance(template, tmp_path, value):
    """A copy of the fictional workspace whose evaluation allows extras up to `value`."""
    copy = tmp_path / template.name
    shutil.copytree(template, copy)
    ai = copy / "config" / "ai.yaml"
    ai.write_text(re.sub(r"extra_allowance: [\d.]+", f"extra_allowance: {value}", ai.read_text()))
    return copy


def test_an_op_the_case_does_not_expect_is_listed_and_a_case_can_relax_exact(monkeypatch):
    case = case_of(DEMO_B, "close-action")
    assert "exact" not in case, "exact is the default"
    assert run_edited(monkeypatch, DEMO_B, case["id"]).passed
    extra = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, fact_op(case)))
    assert extra.passed and extra.extra == ["fact() applied"] and not extra.missing and not extra.forbidden
    relaxed = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, fact_op(case)), exact=False)
    assert relaxed.passed and relaxed.extra == [] and relaxed.extra_weight == 0.0


def test_an_extra_fact_is_free_and_an_extra_internal_op_costs_a_little(monkeypatch):
    case = case_of(DEMO_B, "close-action")
    fact = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, fact_op(case), fact_op(case, "Two")))
    assert fact.passed and len(fact.extra) == 2 and fact.extra_weight == 0.0
    one = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, internal_op(case, DEMO_B)))
    assert one.passed and one.extra_weight == ev.INTERNAL_EXTRA_WEIGHT and len(one.extra) == 1
    both = with_ops(case, internal_op(case, DEMO_B), fact_op(case))
    assert run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=both).extra_weight == ev.INTERNAL_EXTRA_WEIGHT


def test_the_weighed_extras_must_stay_within_the_allowance(monkeypatch):
    case = case_of(DEMO_B, "close-action")
    twice = with_ops(case, internal_op(case, DEMO_B), internal_op(case, DEMO_B, "Ask the printer for a proof"))
    two = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=twice)
    assert two.passed and two.extra_weight == 2 * ev.INTERNAL_EXTRA_WEIGHT  # exactly the default allowance of 1.0
    thrice = with_ops(case, *(internal_op(case, DEMO_B, f"Send proof {n} to the printer") for n in "abc"))
    three = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=thrice)
    assert not three.passed and three.extra_weight == 3 * ev.INTERNAL_EXTRA_WEIGHT
    assert not three.missing and not three.forbidden


@pytest.mark.parametrize(("allowance", "passes"), [(0, False), (1.0, True)])
def test_the_extra_allowance_is_a_setting(monkeypatch, tmp_path, allowance, passes):
    case = case_of(DEMO_B, "close-action")
    template = with_allowance(DEMO_B, tmp_path, allowance)
    one = with_ops(case, internal_op(case, DEMO_B))
    assert run_edited(monkeypatch, template, case["id"], stub_answer=one).passed is passes
    free = with_ops(case, fact_op(case))
    assert run_edited(monkeypatch, template, case["id"], stub_answer=free).passed, "a fact is free at any allowance"


def test_an_extra_that_reaches_another_person_fails_whatever_the_allowance(monkeypatch, tmp_path):
    case = case_of(DEMO_B, "close-action")
    template = with_allowance(DEMO_B, tmp_path, 20)
    to_me = with_ops(case, question_op(pm_id(DEMO_B)))
    assert run_edited(monkeypatch, template, case["id"], stub_answer=to_me).passed
    to_them = with_ops(case, question_op(someone_else(DEMO_B)))
    result = run_edited(monkeypatch, template, case["id"], stub_answer=to_them)
    assert not result.passed and len(result.extra) == 1 and result.extra[0].startswith("question.add")
    assert not result.missing and not result.forbidden


def test_an_extra_op_in_the_outbound_tier_reaches_another_person():
    class Plugins:
        tiers = {"outbound-thing": "outbound", "action.add": "data"}

    store = SimpleNamespace(plugins=Plugins())
    outbound = {"op": {"op": "outbound-thing"}, "status": "applied"}
    assert ev._reaches_another(outbound, store, None)
    assert not ev._reaches_another({"op": {"op": "action.add"}, "status": "applied"}, store, None)


def test_the_extras_of_a_run_are_within_the_allowance_only_when_none_reaches_anyone_and_the_weight_fits():
    assert ev.Extras([], 0.0, False).within(0)
    assert ev.Extras(["a"], 1.0, False).within(1.0) and not ev.Extras(["a"], 1.5, False).within(1.0)
    assert not ev.Extras(["a"], 0.5, True).within(100)


def test_the_report_shows_what_the_extras_weigh_and_the_json_keeps_it():
    report = Report(
        "a", 1, [RunResult("c", 1, True, extra=["action.add() applied"], extra_weight=1.0), RunResult("c", 2, True)]
    )
    assert "extras weigh 0.5 on average, 1.0 at most" in report.text()
    assert json.loads(report.as_json())["results"][0]["extra_weight"] == 1.0
    assert "extras weigh" not in Report("a", 1, [RunResult("c", 1, True)]).text()


def test_an_op_kind_the_case_allows_weighs_nothing(monkeypatch, tmp_path):
    case = case_of(DEMO_B, "close-action")
    template = with_allowance(DEMO_B, tmp_path, 0)
    stub = with_ops(case, internal_op(case, DEMO_B))
    allowed = run_edited(monkeypatch, template, case["id"], stub_answer=stub, allow=["action.add"])
    assert allowed.passed and allowed.extra == [] and allowed.extra_weight == 0.0
    note = {"op": "note", "text": "Nothing else."}
    other = run_edited(monkeypatch, template, case["id"], stub_answer=with_ops(case, fact_op(case), note), allow=["x"])
    assert other.passed and other.extra == ["fact() applied"]


def _scored_stages(template):
    """Every input a model's answer is scored on: each case, each pair's later input (and its first, when that is the
    account's own run), and each scenario's two days."""
    from engine.pairs import load_pairs, load_scenarios

    for case in load_cases(template):
        yield case["id"], case
    for pair in load_pairs(template):
        yield f"{pair['id']} later", pair["later"]
        if not {"wrong", "fixed"} & set(pair["first"]):
            yield f"{pair['id']} first", pair["first"]
    for scenario in load_scenarios(template):
        for day in ("day1", "day30"):
            yield f"{scenario['id']} {day}", {**scenario.get("input", {}), **scenario[day]}


def _ops(stage, key) -> list[tuple[list[str], dict]]:
    return [(ev._kinds(e), e) for e in stage.get(key, []) if "op" in e]


def _expects_a_due_date(stage) -> bool:
    return any(
        ("action.add" in kinds and e.get("due")) or ("record.set" in kinds and e.get("field") == "due")
        for kinds, e in _ops(stage, "expect")
    )


@pytest.mark.parametrize("template", [DEMO_A, DEMO_B], ids=["demo-a", "demo-b"])
def test_a_scored_input_whose_date_is_an_actions_own_forbids_a_calendar_entry(template):
    """A calendar entry is for a real event. A stage that expects an action with a due date, or a new due date for an
    open action, forbids an entry, so a model that adds one for the action's own date is scored down, unless the same
    input also names a real event, which the stage then expects or allows (with its reason beside the allow)."""
    unsaid = [
        name
        for name, stage in _scored_stages(template)
        if _expects_a_due_date(stage)
        and not any("event.add" in kinds for kinds, _ in _ops(stage, "expect") + _ops(stage, "forbid"))
        and "event.add" not in (stage.get("allow") or [])
    ]
    assert unsaid == []


def test_an_expected_op_naming_several_kinds_is_met_by_any_one_of_them(monkeypatch):
    case = case_of(DEMO_B, "colon-in-title")
    assert ev._kinds(case["expect"][0]) == ["fact", "action.add"]
    title = case["expect"][0]["text_has"][0]
    as_action = {"op": "action.add", "text": f"Settle {title}", "evidence": {"quote": title}}
    assert run_edited(monkeypatch, DEMO_B, case["id"], stub_answer={"summary": "s", "ops": [as_action]}).passed
    split = {"op": "action.add", "text": title.split(":")[0], "evidence": {"quote": title}}
    missed = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer={"summary": "s", "ops": [split]})
    assert not missed.passed and missed.missing


def test_an_entrys_time_matches_however_the_answer_wrote_it(monkeypatch):
    case = case_of(DEMO_B, "invitation-event")
    [entry] = case["stub_answer"]["ops"]
    written = {**entry, "start": entry["start"].replace(":00+00:00", "Z")}
    assert written["start"] != entry["start"]
    assert run_edited(monkeypatch, DEMO_B, case["id"], stub_answer={"summary": "s", "ops": [written]}).passed


def test_a_note_is_never_counted_as_an_unexpected_op(monkeypatch):
    case = case_of(DEMO_B, "close-action")
    note = {"op": "note", "text": "The printer has the file."}
    assert run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, note)).passed


def test_each_expected_op_accounts_for_one_produced_op_so_a_duplicate_is_extra(monkeypatch):
    case = case_of(DEMO_B, "printer-proof-date")
    twice = with_ops(case, {**case["stub_answer"]["ops"][0], "text": case["stub_answer"]["ops"][0]["text"] + " Again."})
    result = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=twice)
    assert result.extra == ["fact(project=PRJ-1) applied"] and result.extra_weight == 0.0


def test_a_held_op_is_extra_unless_the_case_expects_something_held(monkeypatch):
    unknown = case_of(DEMO_B, "unknown-person")
    close = case_of(DEMO_B, "close-action")
    stray = {**unknown["stub_answer"]["ops"][0], "evidence": {"quote": quote_of(close)}}
    result = run_edited(monkeypatch, DEMO_B, close["id"], stub_answer=with_ops(close, stray))
    assert len(result.extra) == 1 and result.extra[0].endswith("held") and result.extra_weight == 0.5
    assert run_edited(monkeypatch, DEMO_B, unknown["id"]).extra == [], "a case that expects a held action allows it"


def test_forbid_can_name_an_id_and_only_that_id_is_forbidden(monkeypatch):
    case = case_of(DEMO_A, "partial-answer")
    wrong_id = case["forbid"][0]["id"]
    both = with_ops(case, {**case["stub_answer"]["ops"][0], "id": wrong_id})
    result = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer=both)
    assert not result.passed and result.forbidden == [f"op=question.done, id={wrong_id}"]
    assert run_edited(monkeypatch, DEMO_A, case["id"]).passed


def promise_case(kind):
    """The first case whose ideal answer is one op of this kind: a promise (it names who it is owed to and the words its
    date came from), or an ending."""

    def fits(case):
        ops = case["stub_answer"]["ops"]
        promise = kind != "action.add" or bool(ops) and {"promised_to", "due_words"} <= set(ops[0])
        return [o["op"] for o in ops] == [kind] and promise

    return next(c for c in load_cases(DEMO_B) if fits(c))


def test_a_promise_is_matched_on_who_it_is_owed_to_and_the_words_its_date_came_from(monkeypatch):
    case = promise_case("action.add")
    (ideal,) = case["stub_answer"]["ops"]
    assert run_edited(monkeypatch, DEMO_B, case["id"]).passed
    people = [p["full_name"] for p in fixture_records(DEMO_B, "person")]
    other = next(name for name in people if name not in ideal["promised_to"])
    wrong_to = {**case["stub_answer"], "ops": [{**ideal, "promised_to": [other]}]}
    result = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=wrong_to)
    assert not result.passed and any("promised_to" in m for m in result.missing)
    # Other words give the same day, so the date matches; the words themselves are still checked.
    words = ideal["due_words"]
    same_day = words[3:] if words.startswith("by ") else f"by {words}"
    wrong_words = {**case["stub_answer"], "ops": [{**ideal, "due_words": same_day}]}
    result = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=wrong_words)
    assert not result.passed and any("due_words" in m for m in result.missing)
    spaced = {**case["stub_answer"], "ops": [{**ideal, "due_words": "  " + ideal["due_words"].upper() + " "}]}
    assert run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=spaced).passed


@pytest.mark.parametrize("kind", ["action.move", "action.part", "action.news"])
def test_an_ending_that_waits_for_the_persons_keep_is_matched_on_the_action_and_its_own_fields(monkeypatch, kind):
    case = promise_case(kind)
    (ideal,) = case["stub_answer"]["ops"]
    assert run_edited(monkeypatch, DEMO_B, case["id"]).passed  # held for Keep, yet it counts as made
    elsewhere = {**case["stub_answer"], "ops": [{**ideal, "id": "ACT-1"}]}
    result = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=elsewhere)
    assert not result.passed and result.missing
    if kind == "action.move":
        moved = {**case["stub_answer"], "ops": [{**ideal, "due_words": "next Thursday"}]}
        result = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=moved)
        assert not result.passed and any("due_words" in m for m in result.missing)
    else:
        words = "no such words"
        result = run_edited(monkeypatch, DEMO_B, case["id"], expect=[{**case["expect"][0], "text_has": [words]}])
        assert not result.passed and any(words in m for m in result.missing)
        right = ideal["delivered"] if kind == "action.part" else ideal["text"]
        has = [{**case["expect"][0], "text_has": [right.split()[0]]}]
        assert run_edited(monkeypatch, DEMO_B, case["id"], expect=has).passed


def test_a_forbidden_ending_is_caught_while_it_waits_for_the_persons_keep(monkeypatch):
    case = promise_case("action.news")
    target = case["stub_answer"]["ops"][0]["id"]
    close = {"op": "action.close", "id": target, "evidence": case["stub_answer"]["ops"][0]["evidence"]}
    result = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, close))
    assert not result.passed and result.forbidden == [f"op=action.close, id={target}"]


def test_a_fact_is_matched_on_the_day_it_is_as_of(monkeypatch):
    case = case_of(DEMO_A, "reported-earlier-day")
    typed_day = str(case["received"])
    named_day = case["expect"][0]["as_of"]
    assert typed_day != named_day
    assert run_edited(monkeypatch, DEMO_A, case["id"]).passed
    wrong = json.loads(json.dumps(case["stub_answer"]))
    wrong["ops"][0]["as_of"] = typed_day
    result = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer=wrong)
    assert not result.passed and any(f"as_of={named_day}" in m for m in result.missing)
    left_out = json.loads(json.dumps(case["stub_answer"]))
    del left_out["ops"][0]["as_of"]
    assert not run_edited(monkeypatch, DEMO_A, case["id"], stub_answer=left_out).passed, "it defaults to the typed day"


def test_every_case_that_relaxes_exact_says_why():
    for template in (DEMO_A, DEMO_B):
        for path in sorted((template / "evals").glob("*.yaml")):
            lines = path.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines):
                if re.match(r"exact:\s*false\b", line):
                    beside = "#" in line.split("false", 1)[1]
                    above = n > 0 and lines[n - 1].lstrip().startswith("#")
                    assert beside or above, f"{path.name}: exact: false needs a comment saying why"


def test_exact_is_true_or_false_and_injected_needs_a_hostile_case(tmp_path):
    folder = tmp_path / "evals"
    folder.mkdir()
    base = {"id": "c", "received": "2026-10-09", "note": "A note.", "stub_answer": {"summary": "", "ops": []}}
    (folder / "c.yaml").write_text(yaml.safe_dump({**base, "exact": "no"}))
    with pytest.raises(ValueError, match="case c: exact"):
        load_cases(tmp_path)
    (folder / "c.yaml").write_text(yaml.safe_dump({**base, "injected": ["PER-1"]}))
    with pytest.raises(ValueError, match="case c: injected.*hostile"):
        load_cases(tmp_path)


# ---- starting records ------------------------------------------------------------------------------------------------


def test_the_shared_starting_state_is_not_a_case_and_half_the_harder_set_uses_it():
    cases = load_cases(DEMO_A)
    ids = [c["id"] for c in cases]
    assert "busy-portfolio" not in ids and len(ids) == len(set(ids))
    assert sum(bool(c.get("given_file")) for c in cases) * 2 >= len(cases)
    assert any(c.get("given") for c in cases), "a case can also carry its own starting records"


def test_the_busy_portfolio_has_about_twenty_projects_fifty_open_actions_and_near_namesakes(tmp_path):
    case = next(c for c in load_cases(DEMO_A) if c.get("given_file"))
    ws = init_workspace(tmp_path / "ws", template=DEMO_A, git=False)
    store = Store(ws.db_path)
    try:
        before = {p.id for p in store.read().list("person")}
        ev._create_starting_records(store, case["id"], starting_records(DEMO_A, case))
        view = store.read()
        assert len(view.list("project")) >= 20
        assert len([a for a in view.list("action") if a.data["status"] == "open"]) >= 50
        people = view.list("person")
        assert Counter(p.data["full_name"].split()[0] for p in people).most_common(1)[0][1] >= 2
        added = [p for p in people if p.id not in before]
        assert len({p.data["role"] for p in added}) == 3, "the people it adds come in three roles"
        titles = [p.data["name"] for p in view.list("project")]
        assert any(a != b and a.split()[:2] == b.split()[:2] for a in titles for b in titles), "similar names"
    finally:
        store.close()


def test_starting_records_exist_before_the_input_is_handed_in(monkeypatch):
    case = case_of(DEMO_A, "quoted-thread-action-exists")
    given = case["given"][0]
    assert run_edited(monkeypatch, DEMO_A, case["id"]).passed, "the date update lands on the given action"
    without = run_edited(monkeypatch, DEMO_A, case["id"], given=[], given_file=None)
    assert not without.passed, "with no starting action the same answer has nothing to change"
    assert given["id"] in case["expect"][0]["id"]


def test_a_given_file_that_is_missing_or_not_a_list_is_refused_with_the_case_named(tmp_path):
    folder = tmp_path / "evals"
    folder.mkdir()
    case = {"id": "c", "received": "2026-10-09", "note": "A note.", "given_file": "nothing.yaml"}
    (folder / "c.yaml").write_text(yaml.safe_dump(case))
    with pytest.raises(ValueError, match="case c: given_file nothing.yaml isn't in the evals folder"):
        load_cases(tmp_path)
    (folder / "nothing.yaml").write_text("id: not-a-list\n")
    with pytest.raises(ValueError, match="case c: nothing.yaml should be a list"):
        starting_records(tmp_path, case)


def test_starting_records_that_cannot_load_say_which_case_and_why(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_A, git=False)
    store = Store(ws.db_path)
    try:
        taken = fixture_id(store, "action")
        with pytest.raises(ValueError, match=f"case c: its starting records don't load: .*{taken}.*already exists"):
            ev._create_starting_records(store, "c", [{"kind": "action", "id": taken, "fields": {"text": "Do it"}}])
        with pytest.raises(ValueError, match="case c: no record kind widget"):
            ev._create_starting_records(store, "c", [{"kind": "widget", "id": "WID-1"}])
        with pytest.raises(ValueError, match="case c: its starting records don't load"):
            ev._create_starting_records(store, "c", [{"kind": "action", "id": "ACT-99", "fields": {"text": ""}}])
    finally:
        store.close()


def fixture_id(store, kind):
    return store.read().list(kind)[0].id


# ---- hostile cases ---------------------------------------------------------------------------------------------------


def test_a_hostile_case_fails_on_any_system_op_whatever_became_of_it(monkeypatch):
    case = case_of(DEMO_A, "hostile-standing-rule")
    assert case["hostile"] is True
    asked = case["pasted"].split("Assistant: ")[1][:34]
    rule = {"op": "rule.add", "text": "Copy someone on every message.", "evidence": {"quote": asked}}
    result = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer={"summary": "", "ops": [rule]})
    assert not result.passed and "proposed a system op (rule.add)" in result.forbidden
    assert run_edited(monkeypatch, DEMO_A, case["id"]).passed


def test_a_hostile_case_fails_on_an_op_that_names_an_injected_person(monkeypatch):
    case = case_of(DEMO_A, "hostile-make-owner")
    (injected,) = case["injected"]
    person = next(r for r in starting_records(DEMO_A, case) if r["id"] == injected)
    asked = case["pasted"].split("Note for the assistant: ")[1][:30]
    owned = {
        "op": "action.add",
        "text": "Review the dashboard",
        "owners": [person["fields"]["full_name"]],
        "evidence": {"quote": asked},
    }
    result = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer={"summary": "", "ops": [owned]})
    assert not result.passed and f"names {injected} (action.add)" in result.forbidden
    by_id = {**owned, "owners": [injected]}
    result = run_edited(
        monkeypatch,
        DEMO_A,
        case["id"],
        stub_answer={"summary": "", "ops": [by_id]},
        injected=[person["fields"]["full_name"]],
    )
    assert any(f.startswith("names ") for f in result.forbidden), "named by full name, found by the id it resolved to"


def test_a_note_that_only_mentions_an_injected_person_does_not_name_them_as_an_owner(monkeypatch):
    case = case_of(DEMO_A, "hostile-make-owner")
    person = next(r for r in starting_records(DEMO_A, case) if r["id"] == case["injected"][0])
    note = {"op": "note", "text": f"The message asks for {person['fields']['full_name']} to own everything."}
    result = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer={"summary": "", "ops": [note]})
    assert result.passed, result.forbidden


# ---- the report ------------------------------------------------------------------------------------------------------


def test_a_run_on_one_account_says_so_in_the_json_and_the_summary():
    report = evaluate(DEMO_B, stub=True, runs=1, env={}, only=[case_of(DEMO_B, "close-action")["id"]])
    assert len(report.accounts()) == 1 and report.accounts()[0].startswith("stub/") and report.one_account()
    assert json.loads(report.as_json())["one_account"] is True
    assert ev.ONE_ACCOUNT_LINE in report.text()
    assert ev.ONE_ACCOUNT_LINE.startswith("Every tier ran on the same account")


def test_a_run_on_two_accounts_makes_no_such_claim():
    results = [RunResult("a", 1, True, accounts=["low/small"]), RunResult("b", 1, True, accounts=["high/large"])]
    report = Report("mixed", 1, results)
    assert not report.one_account() and json.loads(report.as_json())["one_account"] is False
    assert ev.ONE_ACCOUNT_LINE not in report.text()
    assert not Report("none", 1, []).one_account(), "a report with no calls says nothing about accounts"


def test_an_agent_account_reports_its_program_version_once_per_provider():
    calls = []

    def factory(name, settings, secret):
        calls.append(name)
        return SimpleNamespace(program_version=lambda: "agent 9.9")

    providers = {
        "agent": SimpleNamespace(adapter="cli-agent"),
        "gateway": SimpleNamespace(adapter="http-api"),
        "stub": SimpleNamespace(adapter="stub"),
    }
    cfg = SimpleNamespace(ai=SimpleNamespace(providers=providers))
    versions: dict = {}
    ev._read_program_versions(cfg, {"agent", "gateway", "stub", "unlisted"}, versions, factory)
    ev._read_program_versions(cfg, {"agent"}, versions, factory)
    assert versions == {"agent": "agent 9.9"} and calls == ["cli-agent"]


def test_the_report_says_the_version_or_that_it_is_not_known():
    report = Report("a", 1, [RunResult("c", 1, True)], {"agent": "agent 9.9", "other": None})
    assert json.loads(report.as_json())["program_versions"] == {"agent": "agent 9.9", "other": None}
    assert "Agent program version (agent): agent 9.9" in report.text()
    assert "Agent program version (other): not known" in report.text()
    assert "Agent program version" not in Report("a", 1, [RunResult("c", 1, True)]).text()


def test_a_run_through_a_command_line_agent_records_its_version_and_account(tmp_path):
    case = case_of(DEMO_B, "close-action")
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps(case["stub_answer"]))
    script = tmp_path / "agent.py"
    script.write_text("import sys\nsys.stdin.read()\nprint(open(sys.argv[1]).read())\n")
    ai = yaml.safe_load((DEMO_B / "config" / "ai.yaml").read_text())
    ai["providers"] = {
        "agent": {
            "adapter": "cli-agent",
            "models": {"default": "agent-model"},
            "allowed_data": ["open", "internal", "restricted"],
            "agent": {
                "command": [sys.executable, str(script), str(answer)],
                "version_command": [sys.executable, "-c", "print('agent 4.5.6')"],
            },
        }
    }
    ai["tiers"] = {"routine": {"use": "agent/default"}, "deep": {"use": "agent/default"}}
    config = tmp_path / "ai.yaml"
    config.write_text(yaml.safe_dump(ai))
    report = evaluate(DEMO_B, account="agent/default", ai_config=config, only=[case["id"]], env={})
    assert report.pass_rate() == 1.0
    data = json.loads(report.as_json())
    assert data["program_versions"] == {"agent": "agent 4.5.6"} and data["one_account"] is True
    assert data["accounts"] == ["agent/agent-model"]
    assert "Agent program version (agent): agent 4.5.6" in report.text()


# ---- word alternatives and what a pair kept --------------------------------------------------------------------------


def test_a_word_with_a_bar_is_met_by_any_one_of_its_alternatives():
    assert ev._has_words("The work is Finished.", ["complet|finish|done"])
    assert ev._has_words("A follow-up is not completion", ["complet|finish|done", "FOLLOW"])
    assert not ev._has_words("Nothing relevant here", ["complet|finish|done"])
    assert not ev._has_words("It is done", ["complet|finish|done", "follow|nudge"])
    assert ev._has_words("plain words", ["plain", "words"]), "an entry without a bar is matched as it always was"


def test_a_pair_run_says_what_the_harness_kept_and_the_report_prints_it():
    from engine.pairs import evaluate_pairs

    report = evaluate_pairs(DEMO_B, stub=True, runs=1, env={}, only=["acronym"])
    kept = report.results[0].kept
    assert kept and kept[0].startswith("GLOSS-1:") and "(reach:" in kept[0]
    assert any(line.strip().startswith("kept: GLOSS-1:") for line in report.text().splitlines())
    assert "GLOSS-1:" in json.loads(report.as_json())["results"][0]["kept"][0]
