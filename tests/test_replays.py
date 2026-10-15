"""Replay cases (design 6.16, phase L7): each real miss starts from the person's own action through the screen's entry
point and is scored on the records as they end up. Every replay passes with the stand-in, and each fails when the miss
it replays comes back. Names and ids come from the replays themselves."""

import json

import pytest

import engine.pairs as pairs
import engine.replays as replays
from engine.ai import matrix
from engine.cli import main
from engine.replays import evaluate_replays, load_replays
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B

TEMPLATES = (DEMO_A, DEMO_B)
CASES = [(t, c["id"]) for t in TEMPLATES for c in load_replays(t)]
REAL_MISSES = (
    "not-a-project-is-one-piece",
    "part-of-is-one-piece",
    "moved-decision-stays-a-decision",
    "already-asked-files-the-question-as-sent",
    "a-moved-date-sent-back-leaves-no-calendar-entry",
    "moving-an-entry-asks-about-the-actions-tied-to-it",
)


def run(template, case_id):
    return evaluate_replays(template, stub=True, runs=1, env={}, only=[case_id]).results[0]


def problems(result):
    return result.missing + result.forbidden + [result.error or ""]


def edited(monkeypatch, template, case_id, change):
    """Run one replay with its loaded form changed by `change`."""
    original = replays.load_replays

    def loaded(folder):
        found = original(folder)
        for replay in found:
            if replay["id"] == case_id:
                change(replay)
        return found

    monkeypatch.setattr(replays, "load_replays", loaded)
    return run(template, case_id)


# ---- every replay passes with its ideal answers ------------------------------------------------------------------


@pytest.mark.parametrize(("template", "case_id"), CASES, ids=lambda v: v if isinstance(v, str) else v.name)
def test_every_replay_passes_with_the_stand_in(template, case_id):
    result = run(template, case_id)
    assert result.passed, problems(result)


def test_both_workspaces_replay_each_real_miss_once_with_its_skills():
    for template in TEMPLATES:
        found = load_replays(template)
        assert [r["id"] for r in found] == sorted(REAL_MISSES)
        assert all(r["skills"] for r in found)


def test_the_stand_in_report_is_a_third_set_that_names_its_kind_and_workspace():
    report = evaluate_replays(DEMO_B, stub=True, runs=1, env={})
    assert report.pass_rate() == 1.0
    assert (report.kind, report.template) == ("replays", DEMO_B.name)
    assert set(report.case_set) == set(REAL_MISSES)


# ---- each starts from the person's own action ----------------------------------------------------------------------


def test_a_replay_acts_through_the_entry_point_the_screen_uses(monkeypatch):
    called = []
    for name in ("not_a_project", "send_back", "apply_as_person"):
        original = getattr(pairs, name)
        monkeypatch.setattr(pairs, name, lambda *a, _o=original, _n=name, **k: called.append(_n) or _o(*a, **k))
    for case_id in (
        "not-a-project-is-one-piece",
        "a-moved-date-sent-back-leaves-no-calendar-entry",
        "already-asked-files-the-question-as-sent",
    ):
        assert run(DEMO_A, case_id).passed
    assert {"not_a_project", "send_back", "apply_as_person"} <= set(called)


# ---- each fails when its miss comes back ---------------------------------------------------------------------------


def test_marking_not_a_project_that_also_learns_a_lesson_of_its_own_fails(monkeypatch):
    real = pairs.not_a_project

    def and_a_lesson(store, cfg, changeset, index, **kwargs):
        done = real(store, cfg, changeset, index, **kwargs)
        with store.transaction() as tx:
            tx.create(
                "lesson",
                {
                    "text": "Names are never projects.",
                    "status": "proposed",
                    "origin": "assistant",
                    "trust": "trusted",
                    "learned_at": store.clock(),
                },
                pairs._PERSON,
            )
        return done

    monkeypatch.setattr(pairs, "not_a_project", and_a_lesson)
    result = run(DEMO_A, "not-a-project-is-one-piece")
    assert not result.passed and any(f.startswith("lesson(") for f in result.forbidden), problems(result)


def test_a_send_back_that_leaves_the_calendar_entry_in_place_fails(monkeypatch):
    real = pairs.send_back
    monkeypatch.setattr(
        pairs, "send_back", lambda store, cs, note, **k: real(store, cs, note, **{**k, "undo_first": False})
    )
    result = run(DEMO_B, "a-moved-date-sent-back-leaves-no-calendar-entry")
    assert not result.passed and any(f.startswith("event(") for f in result.forbidden)


def test_a_mark_as_asked_that_changes_nothing_fails(monkeypatch):
    monkeypatch.setattr(pairs, "apply_as_person", lambda *a, **k: "CS-none")
    result = run(DEMO_A, "already-asked-files-the-question-as-sent")
    assert not result.passed and any("question(" in m for m in result.missing)


def test_a_move_that_queues_no_follow_on_run_fails(monkeypatch):
    from engine import follow_on

    monkeypatch.setattr(follow_on, "queue", lambda *a, **k: None)
    result = run(DEMO_A, "moving-an-entry-asks-about-the-actions-tied-to-it")
    assert not result.passed and any("0 follow-on runs" in p for p in problems(result))


def test_a_follow_on_run_that_asks_nothing_fails_and_so_does_one_whose_question_cannot_be_undone(monkeypatch):
    case = "moving-an-entry-asks-about-the-actions-tied-to-it"
    nothing = edited(monkeypatch, DEMO_B, case, lambda r: r["ideal"]["follow_on"].update(ops=[]))
    assert not nothing.passed and any(m.startswith("question(") for m in nothing.missing)
    monkeypatch.undo()
    from engine import applier

    monkeypatch.setattr(applier, "undo", lambda *a, **k: None)
    kept = run(DEMO_B, case)
    assert not kept.passed and any("left the end state in place" in p for p in problems(kept))


def test_a_replay_that_expects_a_follow_on_run_carries_its_answer_and_an_edit_names_what_it_changes():
    with pytest.raises(ValueError, match="an edit names the record"):
        pairs._check_correction("replay x action", {"kind": "changed", "id": "EVT-1"})
    replay = next(r for r in load_replays(DEMO_A) if r["id"] == "moving-an-entry-asks-about-the-actions-tied-to-it")
    assert replay["expect_follow_on"] is True
    replay["ideal"] = {}
    with pytest.raises(ValueError, match="carries ideal.follow_on"):
        replays._check_replay(DEMO_A, replay)


# ---- how the end state is scored -----------------------------------------------------------------------------------


def test_an_expected_record_that_is_not_there_is_missing(monkeypatch):
    def never(replay):
        replay["expect_records"] = [{"kind": "glossary_entry", "text_has": ["never said"]}]

    result = edited(monkeypatch, DEMO_A, "not-a-project-is-one-piece", never)
    assert not result.passed and result.missing == ["glossary_entry(never said)"]


def test_a_count_of_records_is_exact(monkeypatch):
    def twice(replay):
        replay["expect_records"][0]["count"] = 2

    result = edited(monkeypatch, DEMO_A, "not-a-project-is-one-piece", twice)
    assert not result.passed and "(1 found, 2 wanted)" in result.missing[0]


def test_a_forbidden_record_that_is_there_and_a_signal_that_is_not_both_fail(monkeypatch):
    def change(replay):
        replay["forbid_records"] = [{"kind": "glossary_entry", "where": {"status": "active"}}]
        replay["expect_signals"] = ["never-recorded"]

    result = edited(monkeypatch, DEMO_A, "not-a-project-is-one-piece", change)
    assert not result.passed
    assert result.forbidden == ["glossary_entry(status=active)"] and result.missing == ["signal never-recorded"]


def test_learning_is_checked_both_ways(monkeypatch):
    queued = edited(monkeypatch, DEMO_A, "moved-decision-stays-a-decision", lambda r: r.update(expect_learning=False))
    assert not queued.passed and any("learning was queued" in m for m in queued.missing)
    none = edited(
        monkeypatch,
        DEMO_A,
        "already-asked-files-the-question-as-sent",
        lambda r: r.update(expect_learning=True, ideal={"learn": {"summary": "x", "ops": []}}),
    )
    assert not none.passed and any("queued no learning" in m for m in none.missing)


def test_a_setup_that_cannot_be_acted_on_stops_the_run_with_its_reason(monkeypatch):
    def no_project_held(replay):
        replay["setup"][0]["answer"] = {"summary": "Nothing.", "ops": []}

    result = edited(monkeypatch, DEMO_A, "not-a-project-is-one-piece", no_project_held)
    assert not result.passed and "holds no project.add" in (result.error or "")


# ---- loading -------------------------------------------------------------------------------------------------------


def write(folder, name, text):
    (folder / "replays").mkdir(exist_ok=True)
    (folder / "replays" / f"{name}.yaml").write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("action: {kind: asked, id: Q-1}\nexpect_records: [{kind: question}]\n", "name the skills"),
        ("skills: [dates]\nexpect_records: [{kind: question}]\n", "action is missing"),
        ("skills: [dates]\naction: {kind: sent_back, note: x}\nexpect_signals: [sent_back]\n", "give a setup input"),
        ("skills: [dates]\naction: {kind: asked, id: Q-1}\n", "say what the end state holds"),
        ("skills: [dates]\naction: {kind: nonsense}\nexpect_signals: [x]\n", "a correction is one of"),
        (
            "skills: [dates]\naction: {kind: asked, id: Q-1}\nexpect_learning: true\nexpect_signals: [x]\n",
            "ideal.learn",
        ),
        ("skills: [nonsense]\naction: {kind: asked, id: Q-1}\nexpect_signals: [x]\n", "nonsense"),
    ],
)
def test_a_replay_that_is_not_well_formed_does_not_load(tmp_path, body, message):
    write(tmp_path, "bad", f"id: bad\nreceived: '2026-10-09'\n{body}")
    with pytest.raises(ValueError, match=message):
        load_replays(tmp_path)


def test_a_replay_with_no_received_day_does_not_load_and_the_file_is_named_after_its_id(tmp_path):
    write(tmp_path, "bad", "id: bad\nskills: [dates]\naction: {kind: asked, id: Q-1}\nexpect_signals: [x]\n")
    with pytest.raises(ValueError, match="no received date"):
        load_replays(tmp_path)
    write(tmp_path, "bad", "id: other\nreceived: '2026-10-09'\n")
    with pytest.raises(ValueError, match="name the file after the id"):
        load_replays(tmp_path)


# ---- the command and the matrix -------------------------------------------------------------------------------------


def test_the_command_runs_the_replays_and_adds_them_to_the_matrix(tmp_path, capsys):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    code = main(["evaluate", "-w", str(ws.root), "--from", str(DEMO_B), "--stub", "--replays", "--runs", "1"])
    assert code == 0
    assert "Overall pass rate: 100%" in capsys.readouterr().out
    stored = json.loads((ws.private_dir / matrix.MATRIX_FILE).read_text())["models"]["stub/scripted"]
    assert set(stored["dates"]["sets"]) == {"replays:demo-b"}
    assert matrix.case_set_key("replays", "demo-b") in matrix.case_sets(DEMO_B)


def test_the_replays_and_the_pairs_are_not_asked_for_together(capsys):
    assert main(["evaluate", "--from", str(DEMO_B), "--stub", "--replays", "--pairs"]) == 1
    assert "not both" in capsys.readouterr().err


def test_a_workspace_with_no_replays_folder_says_so(tmp_path, capsys):
    assert main(["evaluate", "--from", str(tmp_path), "--stub", "--replays"]) == 1
    assert "has no replays/ folder" in capsys.readouterr().err
