"""The evaluation harness (design 6.16): exact scoring by default, starting records, hostile cases, the report's account
lines, and the harder set in the fictional workplace workspace. Names, ids and quotes come from the cases themselves."""

import json
import re
import sys
from collections import Counter
from types import SimpleNamespace

import pytest
import yaml

import engine.evaluate as ev
from engine.evaluate import Report, RunResult, evaluate, load_cases, starting_records
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B

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


def test_an_op_the_case_does_not_expect_fails_the_run_unless_the_case_says_exact_false(monkeypatch):
    case = case_of(DEMO_B, "close-action")
    assert "exact" not in case, "exact is the default"
    assert run_edited(monkeypatch, DEMO_B, case["id"]).passed
    extra = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, fact_op(case)))
    assert not extra.passed and extra.extra == ["fact() applied"] and not extra.missing and not extra.forbidden
    relaxed = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, fact_op(case)), exact=False)
    assert relaxed.passed and relaxed.extra == []


def test_an_op_kind_the_case_allows_is_never_counted_as_extra(monkeypatch):
    case = case_of(DEMO_B, "close-action")
    allowed = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, fact_op(case)), allow=["fact"])
    assert allowed.passed and allowed.extra == []
    note = {"op": "note", "text": "Nothing else."}
    other = run_edited(
        monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, fact_op(case), note), allow=["event.add"]
    )
    assert not other.passed and other.extra == ["fact() applied"]


def test_the_harder_set_allows_the_calendar_entry_the_notes_prompt_asks_for_beside_a_dated_action():
    for case_id in ("forwarded-under-note", "quoted-thread-action-exists", "quoted-thread-action-missing"):
        assert "event.add" in case_of(DEMO_A, case_id).get("allow", []), case_id


def test_a_note_is_never_counted_as_an_unexpected_op(monkeypatch):
    case = case_of(DEMO_B, "close-action")
    note = {"op": "note", "text": "The printer has the file."}
    assert run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=with_ops(case, note)).passed


def test_each_expected_op_accounts_for_one_produced_op_so_a_duplicate_is_extra(monkeypatch):
    case = case_of(DEMO_B, "printer-proof-date")
    twice = with_ops(case, {**case["stub_answer"]["ops"][0], "text": case["stub_answer"]["ops"][0]["text"] + " Again."})
    result = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer=twice)
    assert not result.passed and result.extra == ["fact() applied"]


def test_a_held_op_is_extra_unless_the_case_expects_something_held(monkeypatch):
    unknown = case_of(DEMO_B, "unknown-person")
    close = case_of(DEMO_B, "close-action")
    stray = {**unknown["stub_answer"]["ops"][0], "evidence": {"quote": quote_of(close)}}
    result = run_edited(monkeypatch, DEMO_B, close["id"], stub_answer=with_ops(close, stray))
    assert not result.passed and len(result.extra) == 1 and result.extra[0].endswith("held")
    assert run_edited(monkeypatch, DEMO_B, unknown["id"]).passed, "a case that expects a held question allows it"


def test_forbid_can_name_an_id_and_only_that_id_is_forbidden(monkeypatch):
    case = case_of(DEMO_A, "partial-answer")
    wrong_id = case["forbid"][0]["id"]
    both = with_ops(case, {**case["stub_answer"]["ops"][0], "id": wrong_id})
    result = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer=both)
    assert not result.passed and result.forbidden == [f"op=question.done, id={wrong_id}"]
    assert run_edited(monkeypatch, DEMO_A, case["id"]).passed


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
