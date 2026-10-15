"""`cockpit evaluate --out`: the report is written to the file the person names, after every case, so a long run that
stops, or whose printed report is lost, still leaves what it did."""

from __future__ import annotations

import json

import pytest

from engine.cli import main
from engine.evaluate import RunResult
from tests.conftest import DEMO_B


def test_the_report_is_in_the_named_file_at_the_end(tmp_path, capsys):
    out = tmp_path / "report.json"
    main(
        ["evaluate", "--pairs", "--from", str(DEMO_B), "--stub", "--case", "acronym", "--runs", "1", "--out", str(out)]
    )
    report = json.loads(out.read_text())
    assert [r["case"] for r in report["results"]] == ["acronym"]
    assert f"The report is in {out}." in capsys.readouterr().err


def test_a_run_that_stops_partway_keeps_the_cases_it_finished(tmp_path, monkeypatch):
    import engine.pairs

    def stops(template, *, progress, **_):
        progress(RunResult(case="first", run=1, passed=True), 1, 2)
        raise KeyboardInterrupt

    monkeypatch.setattr(engine.pairs, "evaluate_pairs", stops)
    out = tmp_path / "report.json"
    with pytest.raises(KeyboardInterrupt):
        main(["evaluate", "--pairs", "--from", str(DEMO_B), "--stub", "--out", str(out)])
    assert [r["case"] for r in json.loads(out.read_text())["results"]] == ["first"]


def _report_of(*results):
    from engine.evaluate import Report

    return Report("configured", 1, list(results))


def _two_results():
    return [
        RunResult(case="good", run=1, passed=True),
        RunResult(case="bad", run=2, passed=False, missing=["one", "two"], error="x" * 400),
    ]


def _run(monkeypatch, capsys, args, results):
    import engine.pairs

    seen = {}

    def fake(template, *, only=None, **_):
        seen["only"] = only
        return _report_of(*results)

    monkeypatch.setattr(engine.pairs, "evaluate_pairs", fake)
    code = main(["evaluate", "--pairs", "--from", str(DEMO_B), "--stub", *args])
    return code, seen, capsys.readouterr().err


def test_a_failing_run_gets_one_line_and_a_failures_file(tmp_path, monkeypatch, capsys):
    out = tmp_path / "report.json"
    _, _, err = _run(monkeypatch, capsys, ["--out", str(out)], _two_results())
    lines = [line for line in err.splitlines() if line.startswith("FAILED")]
    assert len(lines) == 1
    assert lines[0].startswith("FAILED bad run 2: missing: one; two | error: ")
    assert lines[0].endswith("…")
    assert "good" not in lines[0]
    failures = tmp_path / "report.json.failures.txt"
    assert failures.read_text() == lines[0] + "\n"
    assert f"The failures are in {failures}." in err


def test_no_failure_prints_a_plain_line_and_writes_no_file(tmp_path, monkeypatch, capsys):
    out = tmp_path / "report.json"
    _, _, err = _run(monkeypatch, capsys, ["--out", str(out)], [RunResult(case="good", run=1, passed=True)])
    assert "No run failed." in err
    assert "FAILED" not in err
    assert not (tmp_path / "report.json.failures.txt").exists()


def test_case_failed_runs_only_the_cases_that_failed(tmp_path, monkeypatch, capsys):
    saved = tmp_path / "before.json"
    saved.write_text(
        _report_of(*_two_results(), RunResult(case="skipped", run=1, passed=False, not_run=True)).as_json()
    )
    code, seen, _ = _run(monkeypatch, capsys, ["--case-failed", str(saved)], _two_results())
    assert seen["only"] == ["bad"]
    assert code == 1


def test_case_failed_merges_with_case(tmp_path, monkeypatch, capsys):
    saved = tmp_path / "before.json"
    saved.write_text(_report_of(*_two_results()).as_json())
    _, seen, _ = _run(monkeypatch, capsys, ["--case-failed", str(saved), "--case", "good"], _two_results())
    assert seen["only"] == ["good", "bad"]


def test_case_failed_with_a_missing_report_says_why_and_runs_nothing(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "nope.json"
    code, seen, err = _run(monkeypatch, capsys, ["--case-failed", str(missing)], _two_results())
    assert code == 1
    assert seen == {}
    assert f"{missing} is missing or is not a report" in err


def test_case_failed_with_no_failing_case_says_so_and_runs_nothing(tmp_path, monkeypatch, capsys):
    saved = tmp_path / "before.json"
    saved.write_text(_report_of(RunResult(case="good", run=1, passed=True)).as_json())
    code, seen, err = _run(monkeypatch, capsys, ["--case-failed", str(saved)], _two_results())
    assert code == 1
    assert seen == {}
    assert "no case failed" in err
