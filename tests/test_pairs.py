"""Learning pairs and the day-30 scenario (design 6.22 "Proving it", phase L4): every pair and the scenario pass with
their ideal answers through the stub, a later input answered wrong fails, a negative pair fails when its later output
changes, and `cockpit evaluate --pairs` reports in the same shape as the golden set. Names and ids come from the pairs
themselves.
"""

import json
import re
import shutil
from types import SimpleNamespace

import pytest
import yaml

import engine.pairs as pairs
from engine.cli import main
from engine.evaluate import RunResult
from engine.pairs import evaluate_pairs, load_pairs, load_scenarios
from tests.conftest import DEMO_A, DEMO_B

TEMPLATES = (DEMO_A, DEMO_B)
CASES = [(t, c["id"]) for t in TEMPLATES for c in (*load_pairs(t), *load_scenarios(t)) if not c.get("pending")]


def run(template, case_id):
    return evaluate_pairs(template, stub=True, runs=1, env={}, only=[case_id]).results[0]


def problems(result):
    return result.missing + result.forbidden + result.extra + [result.error or ""]


def edited(monkeypatch, template, case_id, change):
    """Run one pair with its loaded form changed by `change`."""
    original = pairs.load_pairs

    def loaded(folder):
        found = original(folder)
        for pair in found:
            if pair["id"] == case_id:
                change(pair)
        return found

    monkeypatch.setattr(pairs, "load_pairs", loaded)
    return run(template, case_id)


def pair_of(template, case_id):
    return next(p for p in load_pairs(template) if p["id"] == case_id)


# ---- every pair passes with its ideal answers --------------------------------------------------------------------


@pytest.mark.parametrize(("template", "case_id"), CASES, ids=lambda v: v if isinstance(v, str) else v.name)
def test_every_pair_and_the_scenario_pass_with_their_ideal_answers(template, case_id):
    result = run(template, case_id)
    assert result.passed, problems(result)


def test_there_are_fifteen_or_more_pairs_and_about_a_third_are_negative():
    pairs_found = [p for t in TEMPLATES for p in load_pairs(t) if not p.get("pending")]
    negative = [p for p in pairs_found if p.get("negative")]
    assert len(pairs_found) >= 15
    assert 0.25 <= len(negative) / len(pairs_found) <= 0.5
    assert len({p["id"] for t in TEMPLATES for p in load_pairs(t)}) == len(
        [p for t in TEMPLATES for p in load_pairs(t)]
    )


def test_every_pair_that_relaxes_the_scoring_says_why():
    for template in TEMPLATES:
        for path in sorted((template / "pairs").glob("*.yaml")):
            lines = path.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines):
                if re.match(r"\s*(allow:|exact:\s*false)", line):
                    beside = "#" in line.split(":", 1)[1]
                    above = n > 0 and lines[n - 1].lstrip().startswith("#")
                    assert beside or above, f"{path.name}: line {n + 1} needs a comment saying why"


def test_the_scenario_lists_its_expected_differences_and_a_month_of_noise():
    scenario = load_scenarios(DEMO_B)[0]
    assert len(scenario["differences"]) >= 2
    inputs = [s["input"] for s in scenario["history"] if "input" in s]
    assert any(s.get("watched") for s in inputs), "a re-saved file"
    assert any("moved" in str(s["pasted"]) for s in inputs), "a moved meeting"
    assert sum(not s["answer"]["ops"] for s in inputs) >= 2, "mail with nothing to record"
    assert any("correct" in s for s in scenario["history"]) and any("keep_all" in s for s in scenario["history"])


# ---- a wrong later answer fails ----------------------------------------------------------------------------------


def test_a_pair_whose_later_input_is_answered_wrong_fails(monkeypatch):
    def nothing(pair):
        pair["ideal"]["later"] = {"summary": "Nothing.", "ops": []}

    result = edited(monkeypatch, DEMO_B, "acronym", nothing)
    assert not result.passed and any("missing" in m and "action.add" in m for m in result.missing)


def test_a_negative_pair_fails_when_the_later_output_changes(monkeypatch):
    def changed(pair):
        (op,) = pair["ideal"]["later"]["ops"]
        pair["ideal"]["later"]["ops"] = [{**op, "to": "PER-5"}]

    assert run(DEMO_B, "routing-only-proposed").passed
    result = edited(monkeypatch, DEMO_B, "routing-only-proposed", changed)
    assert not result.passed and result.forbidden


def test_a_pair_that_keeps_nothing_fails_because_the_packet_lacks_what_was_learned(monkeypatch):
    def not_kept(pair):
        pair["first"]["keep"] = False

    result = edited(monkeypatch, DEMO_B, "routing", not_kept)
    assert not result.passed and any("the packet doesn't hold" in m for m in result.missing)


def test_a_proposal_that_is_not_the_expected_one_fails_the_first_half(monkeypatch):
    def other(pair):
        pair["first"]["expect_proposal"][0]["text_has"] = ["never said"]

    result = edited(monkeypatch, DEMO_B, "acronym", other)
    assert not result.passed and any(m.startswith("first: no proposal like") for m in result.missing)


def test_an_extra_entry_or_op_in_a_pair_is_weighed_instead_of_failing_it(monkeypatch):
    result = edited(monkeypatch, DEMO_B, "acronym", lambda pair: pair["first"].update(expect_proposal=[]))
    assert result.passed and result.extra_weight == 0.5
    assert len(result.extra) == 1 and result.extra[0].startswith("first: unexpected glossary")
    later = edited(monkeypatch, DEMO_B, "acronym", lambda pair: pair["later"].pop("allow"))
    assert (
        later.passed and later.extra and later.extra_weight == 0.5 * sum(not e.startswith("fact") for e in later.extra)
    )


def test_a_pair_fails_when_its_extras_outweigh_the_allowance(monkeypatch, tmp_path):
    copy = tmp_path / "ws"
    shutil.copytree(DEMO_B, copy)
    ai = copy / "config" / "ai.yaml"
    ai.write_text(re.sub(r"extra_allowance: [\d.]+", "extra_allowance: 0", ai.read_text()))
    result = edited(monkeypatch, copy, "acronym", lambda pair: pair["first"].update(expect_proposal=[]))
    assert not result.passed and result.extra_weight == 0.5 and not result.missing and not result.forbidden


def test_an_unexpected_entry_goes_to_the_extras_when_they_are_asked_for_and_to_the_problems_otherwise():
    entry = SimpleNamespace(
        id="X-1", kind="lesson", data={"text": "Something", "status": "proposed", "origin": "own", "trust": "trusted"}
    )
    extra: list[str] = []
    assert pairs._proposal_findings("later", [], [entry], extra) == [] and len(extra) == 1
    assert len(pairs._proposal_findings("later", [], [entry])) == 1
    assert len(pairs._proposal_findings("later", "none", [entry], extra)) == 1, "none stays a problem"
    joined = pairs._joined(pairs.Extras(["a"], 0.5, False), pairs.Extras(["b"], 0.0, True), extra[:1])
    assert joined.lines == ["a", "b", extra[0]] and joined.weight == 1.0 and joined.reaches


def test_something_active_that_the_person_did_not_keep_fails_unless_their_own_act_made_it(monkeypatch):
    assert run(DEMO_A, "not-a-project").passed
    result = edited(monkeypatch, DEMO_A, "not-a-project", lambda pair: pair["first"].pop("allow_active"))
    assert not result.passed and any("became active without the person's Keep" in m for m in result.missing)


def test_a_stage_that_cannot_go_on_says_why(monkeypatch):
    def drops(pair):
        pair["first"]["correction"] = {"kind": "moved", "id": "ACT-99", "person": "PER-2"}

    result = edited(monkeypatch, DEMO_A, "over-application", drops)
    assert not result.passed and result.error


# ---- pending pairs -----------------------------------------------------------------------------------------------


def test_a_pending_pair_is_left_out_unless_it_is_named(monkeypatch):
    template = DEMO_A
    first = load_pairs(template)[0]
    marked = {**first, "pending": "a gap in the code that stops it passing"}
    monkeypatch.setattr(pairs, "load_pairs", lambda t: [marked] if t == template else [])
    monkeypatch.setattr(pairs, "load_scenarios", lambda t: [])
    ran = []

    def fake_pair(template, item, n, **how):
        ran.append(item["id"])
        return RunResult("x", n, True)

    monkeypatch.setattr(pairs, "_run_pair", fake_pair)
    evaluate_pairs(template, stub=True, runs=1, env={})
    assert ran == [], "a pending pair is not run unless it is named"
    evaluate_pairs(template, stub=True, runs=1, env={}, only=[first["id"]])
    assert ran == [first["id"]]


def test_a_pending_flag_must_say_what_is_missing(tmp_path):
    folder = tmp_path / "pairs"
    folder.mkdir()
    pair = yaml.safe_load((DEMO_B / "pairs" / "routing.yaml").read_text())
    (folder / "routing.yaml").write_text(yaml.safe_dump({**pair, "pending": " "}))
    with pytest.raises(ValueError, match="pending says what is missing"):
        load_pairs(tmp_path)


# ---- the format is checked when it is loaded ---------------------------------------------------------------------


def test_a_pair_without_a_stand_in_for_each_stage_is_refused_when_loaded(tmp_path):
    folder = tmp_path / "pairs"
    folder.mkdir()
    pair = yaml.safe_load((DEMO_B / "pairs" / "acronym.yaml").read_text())
    for key, message in (("learn", "learn"), ("later", "ideal.later")):
        broken = json.loads(json.dumps(pair))
        del broken["ideal"][key]
        (folder / "acronym.yaml").write_text(yaml.safe_dump(broken))
        with pytest.raises(ValueError, match=message):
            load_pairs(tmp_path)
    broken = json.loads(json.dumps(pair))
    broken["later"]["then"] = [{"received": "2026-10-21", "note": "More."}]
    (folder / "acronym.yaml").write_text(yaml.safe_dump(broken))
    with pytest.raises(ValueError, match="one answer for each of the 2 later inputs"):
        load_pairs(tmp_path)


def test_a_file_is_named_after_its_id_and_a_correction_is_one_of_the_known_kinds(tmp_path):
    folder = tmp_path / "pairs"
    folder.mkdir()
    pair = yaml.safe_load((DEMO_B / "pairs" / "acronym.yaml").read_text())
    (folder / "other-name.yaml").write_text(yaml.safe_dump(pair))
    with pytest.raises(ValueError, match="name the file after the id"):
        load_pairs(tmp_path)
    (folder / "other-name.yaml").unlink()
    pair["first"]["correction"]["kind"] = "edited"
    (folder / "acronym.yaml").write_text(yaml.safe_dump(pair))
    with pytest.raises(ValueError, match="a correction is one of"):
        load_pairs(tmp_path)


# ---- the command and its report ----------------------------------------------------------------------------------


def test_the_pairs_command_reports_each_pair_in_the_shape_of_the_golden_set(capsys):
    assert (
        main(["evaluate", "--from", str(DEMO_B), "--pairs", "--stub", "--runs", "2", "--json", "--case", "routing"])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {"account", "runs", "pass_rate", "accounts", "one_account", "program_versions", "results"}
    assert report["runs"] == 2 and report["pass_rate"] == 1.0 and len(report["accounts"]) == 1
    assert [r["run"] for r in report["results"]] == [1, 2] and {r["case"] for r in report["results"]} == {"routing"}
    first = report["results"][0]
    assert first["passed"] and first["negative"] is False
    assert any("ROUTE-" in line for line in first["given"]), "what the later run was given from what was learned"


def test_the_text_report_gives_a_rate_per_pair_and_what_the_later_run_was_given():
    report = evaluate_pairs(DEMO_B, stub=True, runs=1, env={}, only=["look-it-up", "same-batch"])
    text = report.text()
    assert "100%  look-it-up" in text and "100%  same-batch" in text
    assert "later run was given: LES-1" in text
    assert "Every tier ran on the same account" in text


def test_the_pairs_command_needs_a_pairs_folder(tmp_path, capsys):
    (tmp_path / "evals").mkdir()
    assert main(["evaluate", "--from", str(tmp_path), "--pairs", "--stub"]) == 1
    assert "no pairs/ folder" in capsys.readouterr().err
