"""The capability matrix, step 1 (design 6.16, "What a model can do, measured"): every case, pair and scenario names the
skills it proves, each evaluation run adds to what each model has shown it can do, a measurement goes stale, and the
accounts list can show it."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from engine import skills as skill_list
from engine.ai import matrix
from engine.ai.checked import Folder
from engine.cli import main
from engine.config import load_config
from engine.evaluate import Report, RunResult, load_cases
from engine.pairs import load_pairs, load_scenarios
from engine.selfcheck import FIXTURES
from engine.selfcheck.skills import check_skills_named
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TODAY = date(2026, 10, 15)


def folder(tmp_path) -> Folder:
    return Folder(tmp_path / ".cockpit")


def report(results, *, case_set=None, versions=None, kind="cases", template="demo-x") -> Report:
    return Report(
        "configured",
        1,
        results,
        versions or {},
        case_set=case_set if case_set is not None else {"one": ["dates", "owners"], "two": ["dates"]},
        kind=kind,
        template=template,
    )


def run(case, passed, ref="svc/model-a", cost=0.0, **more) -> RunResult:
    return RunResult(case, 1, passed, cost_usd=cost, models=[ref], **more)


def held(tmp_path, ref="svc/model-a", **more):
    cfg = load_config(None, env={})
    found = matrix.standing(
        folder(tmp_path), cfg, ref, program_version=more.pop("program_version", None), current_sets={}, **more
    )
    return {s.skill.id: s for s in found}


# ---- the skills list -----------------------------------------------------------------------------


def test_the_shipped_skills_cover_what_the_fixtures_prove():
    ids = [s.id for s in skill_list.core_skills()]
    assert len(ids) == len(set(ids)) and len(ids) >= 11
    assert all(s.label and s.description for s in skill_list.core_skills())
    named = {
        skill
        for ws in FIXTURES
        for case in [*load_cases(ws), *load_pairs(ws), *load_scenarios(ws)]
        for skill in case["skills"]
    }
    assert named <= set(ids)


def test_a_pack_can_add_skills_without_replacing_the_core_ones():
    extra = [skill_list.Skill("voice", "Drafting in a voice", "x"), skill_list.Skill("dates", "Other", "y")]
    merged = skill_list.skills(extra)
    assert "voice" in {s.id for s in merged}
    assert next(s for s in merged if s.id == "dates").label != "Other"


# ---- the self-check rule -------------------------------------------------------------------------


def _workspace_with(tmp_path, **cases) -> Path:
    evals = tmp_path / "ws" / "evals"
    evals.mkdir(parents=True)
    for name, case in cases.items():
        (evals / f"{name}.yaml").write_text(yaml.safe_dump({"id": name, "title": "t", **case}), encoding="utf-8")
    return tmp_path / "ws"


def test_the_self_check_fails_a_case_with_no_skills_or_an_unknown_one(tmp_path):
    ws = _workspace_with(tmp_path, bare={}, odd={"skills": ["no-such-skill"]}, fine={"skills": ["dates"]})
    findings = check_skills_named([ws], tmp_path / "none")
    assert sorted(Path(f.path).stem for f in findings) == ["bare", "odd"]
    assert any("no-such-skill" in f.message for f in findings)


def test_the_shipped_cases_pass_the_skills_check():
    assert check_skills_named() == []


def test_a_case_that_names_an_unknown_skill_does_not_load(tmp_path):
    ws = _workspace_with(tmp_path, odd={"received": "2026-10-14", "skills": ["no-such-skill"], "stub_answer": {}})
    with pytest.raises(ValueError, match="no-such-skill"):
        load_cases(ws)


# ---- the matrix ----------------------------------------------------------------------------------


def test_a_run_adds_one_run_to_each_skill_its_case_names(tmp_path):
    matrix.record_report(
        folder(tmp_path),
        report([run("one", True, cost=0.02), run("two", False, cost=0.5), run("one", True, cost=0.04)]),
        stale_days=60,
        today=TODAY,
    )
    got = held(tmp_path, today=TODAY)
    assert (got["dates"].runs, got["dates"].passes) == (3, 2)
    assert (got["owners"].runs, got["owners"].passes) == (2, 2)
    assert got["dates"].cost_per_pass_usd == pytest.approx(0.03)  # a failing run's cost is not a passing run's
    assert got["dates"].last == TODAY and got["dates"].stale is None
    assert not got["evidence"].measured and got["evidence"].pass_rate is None


def test_a_run_that_was_not_made_adds_nothing(tmp_path):
    matrix.record_report(folder(tmp_path), report([run("one", False, not_run=True)]), stale_days=60, today=TODAY)
    assert not any(s.measured for s in held(tmp_path, today=TODAY).values())


def test_results_of_every_kind_of_account_are_kept_apart(tmp_path):
    """A service's own API, a compatible server, an aggregator (its model id holds a slash) and a command-line agent
    (with a program version) each have their own row; one's results never reach another's."""
    refs = {
        "native-api/model-one": True,
        "local-server/model-two": False,
        "aggregator/lab/model-three": True,
        "agent-program/model-four": False,
    }
    results = [run("two", passed, ref) for ref, passed in refs.items()]
    matrix.record_report(
        folder(tmp_path), report(results, versions={"agent-program": "3.1.4"}), stale_days=60, today=TODAY
    )
    rates = {ref: held(tmp_path, ref, today=TODAY, program_version="3.1.4" if "agent" in ref else None) for ref in refs}
    assert {ref: got["dates"].pass_rate for ref, got in rates.items()} == {
        "native-api/model-one": 1.0,
        "local-server/model-two": 0.0,
        "aggregator/lab/model-three": 1.0,
        "agent-program/model-four": 0.0,
    }
    assert all(got["dates"].runs == 1 and got["dates"].stale is None for got in rates.values())
    # Nothing is shared with a model nobody ran, whatever its name resembles.
    assert not held(tmp_path, "native-api/model-two", today=TODAY)["dates"].measured


def test_a_run_on_two_accounts_counts_for_both_and_divides_its_cost(tmp_path):
    both = RunResult("two", 1, True, cost_usd=0.10, models=["svc/model-a", "svc/model-b"])
    matrix.record_report(folder(tmp_path), report([both]), stale_days=60, today=TODAY)
    for ref in ("svc/model-a", "svc/model-b"):
        assert held(tmp_path, ref, today=TODAY)["dates"].cost_per_pass_usd == pytest.approx(0.05)


def test_a_skill_under_the_minimum_score_is_marked(tmp_path):
    results = [run("one", True), run("one", False), run("two", True), run("two", True), run("two", True)]
    matrix.record_report(folder(tmp_path), report(results), stale_days=60, today=TODAY)
    got = held(tmp_path, today=TODAY)
    assert got["dates"].pass_rate == 0.8 and got["dates"].below_min is False  # at the minimum is enough
    assert got["owners"].pass_rate == 0.5 and got["owners"].below_min is True
    assert got["evidence"].below_min is False  # never measured is unknown, not low


def test_the_program_version_makes_a_measurement_stale_and_recording_starts_it_again(tmp_path):
    version = {"svc": "1.0"}
    matrix.record_report(folder(tmp_path), report([run("two", True)], versions=version), stale_days=60, today=TODAY)
    assert held(tmp_path, today=TODAY, program_version="1.0")["dates"].stale is None
    assert held(tmp_path, today=TODAY, program_version="2.0")["dates"].stale == "program"
    matrix.record_report(
        folder(tmp_path), report([run("two", False)], versions={"svc": "2.0"}), stale_days=60, today=TODAY
    )
    after = held(tmp_path, today=TODAY, program_version="2.0")["dates"]
    assert (after.runs, after.passes, after.stale) == (1, 0, None)  # the old version's runs are not mixed in


def test_age_makes_a_measurement_stale_after_the_configured_days(tmp_path):
    matrix.record_report(folder(tmp_path), report([run("two", True)]), stale_days=60, today=TODAY)
    assert held(tmp_path, today=TODAY + timedelta(days=60))["dates"].stale is None
    late = held(tmp_path, today=TODAY + timedelta(days=61))["dates"]
    assert late.stale == "age" and late.pass_rate == 1.0  # it still says what it found


def test_a_changed_case_set_makes_a_measurement_stale(tmp_path):
    matrix.record_report(folder(tmp_path), report([run("two", True)]), stale_days=60, today=TODAY)
    cfg = load_config(None, env={})
    same = matrix.set_hashes({"one": ["dates", "owners"], "two": ["dates"]})
    grown = matrix.set_hashes({"one": ["dates", "owners"], "two": ["dates"], "three": ["dates"]})

    def stale(sets):
        got = matrix.standing(
            folder(tmp_path),
            cfg,
            "svc/model-a",
            program_version=None,
            current_sets={matrix.case_set_key("cases", "demo-x"): sets},
            today=TODAY,
        )
        return {s.skill.id: s.stale for s in got}["dates"]

    assert stale(same) is None
    assert stale(grown) == "cases"
    # A set kept under another workspace's name, or of another kind, is not compared.
    assert (
        matrix.standing(
            folder(tmp_path),
            cfg,
            "svc/model-a",
            program_version=None,
            current_sets={matrix.case_set_key("pairs", "demo-x"): grown},
            today=TODAY,
        )[3].stale
        is None
    )


def test_pairs_and_golden_cases_keep_their_own_sets(tmp_path):
    matrix.record_report(folder(tmp_path), report([run("two", True)], kind="cases"), stale_days=60, today=TODAY)
    matrix.record_report(
        folder(tmp_path), report([run("p", True)], case_set={"p": ["dates"]}, kind="pairs"), stale_days=60, today=TODAY
    )
    got = held(tmp_path, today=TODAY)["dates"]
    assert (got.runs, got.stale) == (2, None)  # the pairs' run did not restart the golden cases' measurement


# ---- cockpit evaluate ----------------------------------------------------------------------------


def test_an_evaluate_run_with_the_stand_in_fills_the_matrix(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    main(["evaluate", "-w", str(ws.root), "--from", str(DEMO_B), "--stub", "--case", "answer-question", "--runs", "2"])
    main(
        ["evaluate", "-w", str(ws.root), "--from", str(DEMO_B), "--stub", "--pairs", "--case", "acronym", "--runs", "1"]
    )
    stored = json.loads((ws.private_dir / matrix.MATRIX_FILE).read_text())["models"]["stub/scripted"]
    case = next(c for c in load_cases(DEMO_B) if c["id"] == "answer-question")
    assert {s: stored[s]["runs"] for s in case["skills"]} == {
        s: 2 for s in case["skills"] if s not in ("use-term", "use-lesson")
    }
    assert stored["use-term"]["runs"] == 1 and stored["use-lesson"]["runs"] == 1
    assert set(stored["use-term"]["sets"]) == {"pairs:demo-b"}


def test_an_evaluate_run_without_a_workspace_keeps_nothing(tmp_path):
    main(["evaluate", "--from", str(DEMO_B), "--stub", "--case", "answer-question", "--runs", "1"])
    assert not list(Path(DEMO_B).glob(".cockpit/ai-skills.json"))


# ---- the route -----------------------------------------------------------------------------------


def _client(ws):
    from api.app import create_app
    from engine.storage import Store

    cfg = load_config(ws.config_dir, env={})
    Store(ws.db_path, cfg=cfg).close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    return c, cfg.server.base_path.rstrip("/") + "/api"


def test_the_route_lists_every_skill_for_every_model_and_says_what_is_unmeasured(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    c, api = _client(ws)
    got = c.get(f"{api}/ai/skills").json()
    account = next(a for a in got["accounts"] if a["name"] == "stub")
    row = account["models"][0]
    assert row["model"] == "default"  # the short name the person chose, never the model's id
    assert [s["id"] for s in row["skills"]] == [s.id for s in skill_list.core_skills()]
    assert all(not s["measured"] and s["pass_rate"] is None and s["stale"] is None for s in row["skills"])
    assert got["min_score"] == 0.8 and got["stale_days"] == 60
    assert "scripted" not in json.dumps(got)


def test_the_route_reports_pass_rate_runs_age_cost_and_the_flags(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    results = [run("one", True, "stub/scripted", 0.2), run("one", False, "stub/scripted", 0.1)]
    matrix.record_report(ws, report(results, template="demo-x"), stale_days=60, today=date.today() - timedelta(days=3))
    c, api = _client(ws)
    skills = {s["id"]: s for s in c.get(f"{api}/ai/skills").json()["accounts"][0]["models"][0]["skills"]}
    dates = skills["dates"]
    assert (dates["runs"], dates["passes"], dates["pass_rate"], dates["age_days"]) == (2, 1, 0.5, 3)
    assert dates["cost_per_pass_usd"] == pytest.approx(0.2) and dates["below_min"] is True and dates["stale"] is None
    assert dates["label"] == next(s.label for s in skill_list.core_skills() if s.id == "dates")


def test_the_route_calls_a_measurement_stale_when_the_cases_changed(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    # Measured against a smaller set of golden cases than the workspace has now.
    matrix.record_report(
        ws,
        report([run("one", True, "stub/scripted")], case_set={"one": ["dates"]}, template="demo-b"),
        stale_days=60,
        today=date.today(),
    )
    c, api = _client(ws)
    skills = {s["id"]: s for s in c.get(f"{api}/ai/skills").json()["accounts"][0]["models"][0]["skills"]}
    assert skills["dates"]["stale"] == "cases"
