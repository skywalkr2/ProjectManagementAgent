from datetime import UTC, datetime, timedelta

import pytest

from engine.backup import run_backup, state
from engine.evaluate import evaluate, load_cases
from engine.followups import mark_sent, sections, unmark_sent
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()


def by_role(role):
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


# ---- follow-ups ------------------------------------------------------------------------------------------------------


def test_the_pm_comes_first_then_everyone_a_to_z(env):
    _, cfg, store = env
    secs = sections(store, cfg, NOW.date())
    assert secs[0].is_pm and secs[0].person == cfg.workspace.user.person
    others = [s.name for s in secs[1:]]
    assert others == sorted(others, key=str.lower)


def test_a_message_has_greeting_questions_actions_and_closing(env):
    _, cfg, store = env
    editor = by_role("Editor")
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == editor["id"])
    words = cfg.language.messages
    lines = sec.message.splitlines()
    assert lines[0] == words.greeting.format(first_name=editor["full_name"].split()[0])
    assert lines[-1] == words.closing
    assert words.actions_heading in sec.message
    question = next(q for q in fixture_records(DEMO_B, "question") if q["to"] == editor["id"])
    assert question["title"] in sec.message
    assert sec.to_send == len(sec.questions) + len(sec.actions)


def test_mark_sent_records_questions_and_told_dates_and_edits(env):
    _, cfg, store = env
    editor = by_role("Editor")
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == editor["id"])
    counts = mark_sent(store, cfg, editor["id"], sent_text=sec.message + "\nP.S. one more thing", now=NOW)
    assert counts["questions"] >= 1 and counts["actions"] >= 1
    after = next(s for s in sections(store, cfg, (NOW + timedelta(days=3)).date()) if s.person == editor["id"])
    assert after.to_send == 0 and after.message == ""
    assert all(q["status"] == "sent" and q["waiting_days"] == 3 for q in after.questions)
    assert all(a["told_days"] == 3 for a in after.actions)
    assert [s.data["kind"] for s in store.read().list("signal")] == ["draft_edited"]


def test_sent_questions_carry_their_sent_date_and_the_message_leaves_sent_items_out(env):
    _, cfg, store = env
    editor = by_role("Editor")
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == editor["id"])
    counts = mark_sent(store, cfg, editor["id"], sent_text=sec.message, now=NOW)
    later = (NOW + timedelta(days=2)).date()
    sent = next(s for s in sections(store, cfg, later) if s.person == editor["id"])
    assert all(q["sent"] == NOW.date().isoformat() and q["waiting_days"] == 2 for q in sent.questions)
    # Put only the questions back: the told actions stay out of the next message and the count.
    unmark_sent(store, editor["id"], counts["question_ids"], [])
    partial = next(s for s in sections(store, cfg, later) if s.person == editor["id"])
    assert all(q["sent"] is None for q in partial.questions)
    assert partial.to_send == len(partial.questions)
    assert partial.questions and partial.message
    assert all(a["text"] not in partial.message for a in partial.actions)
    assert all(q["title"] in partial.message for q in partial.questions)
    assert cfg.language.messages.actions_heading not in partial.message


def test_an_unedited_message_records_no_signal(env):
    _, cfg, store = env
    editor = by_role("Editor")
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == editor["id"])
    mark_sent(store, cfg, editor["id"], sent_text=sec.message, now=NOW)
    assert store.read().list("signal") == []


# ---- backups ---------------------------------------------------------------------------------------------------------


def test_no_target_means_a_nag(env):
    ws, cfg, _ = env
    cfg = ws.config(env={}, flags={"storage.backups.targets": []})
    st = state(ws, cfg, NOW)
    assert st.needs_attention and not st.configured


def test_a_backup_copies_the_database_and_reports_its_age(env, tmp_path):
    ws, _, store = env
    target = tmp_path / "offsite"
    cfg = ws.config(env={}, flags={"storage.backups.targets": [{"path": str(target), "label": "test"}]})
    assert state(ws, cfg, NOW).needs_attention
    run_backup(ws, cfg, NOW)
    (copy,) = list(target.iterdir())
    restored = Store(copy / "cockpit.db")
    assert len(restored.read().list("person")) == len(store.read().list("person"))
    restored.close()
    st = state(ws, cfg, NOW + timedelta(hours=3))
    assert not st.needs_attention and "3 h ago" in st.message
    assert state(ws, cfg, NOW + timedelta(days=3)).needs_attention


def test_a_target_inside_the_workspace_is_refused(env):
    ws, _, _ = env
    cfg = ws.config(env={}, flags={"storage.backups.targets": [{"path": str(ws.root / "copies"), "label": "x"}]})
    status = run_backup(ws, cfg, NOW)
    assert "inside the workspace" in next(iter(status.values()))["last_error"]
    assert state(ws, cfg, NOW).needs_attention


def test_old_backups_are_pruned(env, tmp_path):
    ws, _, _ = env
    target = tmp_path / "offsite"
    cfg = ws.config(env={}, flags={"storage.backups.targets": [{"path": str(target)}], "storage.backups.keep": 2})
    for hours in range(3):
        run_backup(ws, cfg, NOW + timedelta(hours=hours))
    assert len(list(target.iterdir())) == 2


# ---- evaluation ------------------------------------------------------------------------------------------------------


def test_every_case_passes_with_its_ideal_answer():
    report = evaluate(DEMO_B, stub=True, runs=1, env={})
    failing = {r.case: r.missing + r.forbidden + [r.error or ""] for r in report.results if not r.passed}
    assert failing == {}
    assert len(report.cases()) == len(load_cases(DEMO_B)) >= 10


def test_a_wrong_answer_fails_the_case(monkeypatch):
    import engine.evaluate as ev

    original = ev.load_cases

    def with_bad_answer(template):
        cases = original(template)
        for c in cases:
            c["stub_answer"] = {"summary": "nothing", "ops": []}
        return cases

    monkeypatch.setattr(ev, "load_cases", with_bad_answer)
    report = evaluate(DEMO_B, stub=True, runs=2, env={}, only=["production-checkin", "nothing-to-record"])
    assert report.pass_rate("production-checkin") == 0.0
    assert report.pass_rate("nothing-to-record") == 1.0
    assert "production-checkin" in report.text()


def test_calls_the_account_refused_are_not_run_and_left_out_of_the_score():
    from engine.evaluate import Report, RunResult

    report = Report(
        "acct",
        1,
        [RunResult("a", 0, True), RunResult("b", 0, False, not_run=True, error="rate limited")],
    )
    assert report.pass_rate() == 1.0
    text = report.text()
    assert "n/a  b" in text and "not run: 1" in text


def test_a_failed_case_shows_what_the_model_produced():
    from engine.evaluate import Report, RunResult

    report = Report("acct", 1, [RunResult("a", 0, False, missing=["op=question.add"], got=["note() applied"])])
    assert "got: note() applied" in report.text()
