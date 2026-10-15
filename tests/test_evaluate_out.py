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
