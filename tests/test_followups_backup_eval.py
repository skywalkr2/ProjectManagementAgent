from datetime import UTC, date, datetime, timedelta

import pytest

from engine.backup import run_backup, state
from engine.evaluate import evaluate, load_cases
from engine.followups import FollowUpError, follow_up, mark_sent, sections, they_finished, undo_follow_up, unmark_sent
from engine.storage import Store, WriteContext
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


def _waiting_action(env, days_ago: int):
    """An open action with a told date `days_ago` days before NOW, and the person it waits on."""
    _, cfg, store = env
    action = next(a for a in store.read().list("action") if a.data["status"] == "open")
    owner = action.data["owners"][0]["person"]
    told = (NOW - timedelta(days=days_ago)).date().isoformat()
    with store.transaction() as tx:
        tx.update(
            "action",
            action.id,
            {"told": {owner: told}},
            WriteContext(actor="pm", trust="trusted", op="test"),
            read_version=action.version,
        )
    return action.id, owner, told


def _action_row(env, action_id, owner):
    _, cfg, store = env
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == owner)
    return next(a for a in sec.actions if a["id"] == action_id)


def _change_action(store, action_id, **changes):
    rec = store.read().get("action", action_id)
    with store.transaction() as tx:
        tx.update(
            "action", action_id, changes, WriteContext(actor="pm", trust="trusted", op="test"), read_version=rec.version
        )


def _told_action(env):
    """An open action with an owner, after the PM marked everything for that owner as sent on NOW."""
    _, cfg, store = env
    action = next(a for a in store.read().list("action") if a.data["status"] == "open" and a.data.get("owners"))
    owner = action.data["owners"][0]["person"]
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == owner)
    mark_sent(store, cfg, owner, sent_text=sec.message, now=NOW)
    assert _action_row(env, action.id, owner)["told"] == NOW.date().isoformat()
    return action, owner


@pytest.mark.parametrize("field,value", [("due", "2031-01-02"), ("text", "Send the corrected index to the typesetter")])
def test_a_changed_due_date_or_text_after_telling_puts_the_action_back_to_send_for_that_person(env, field, value):
    _, cfg, store = env
    action, owner = _told_action(env)
    _change_action(store, action.id, **{field: value})
    row = _action_row(env, action.id, owner)
    assert row["told"] is None and row["told_days"] is None and not row["chase_due"]
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == owner)
    shown = cfg.language.messages.date_format
    expected = date.fromisoformat(value).strftime(shown) if field == "due" else value
    assert sec.to_send >= 1 and expected in sec.message
    # Sending again, even on the same day, settles it: it is told again and stays told.
    mark_sent(store, cfg, owner, sent_text=sec.message, now=NOW)
    assert _action_row(env, action.id, owner)["told"] == NOW.date().isoformat()
    assert next(s for s in sections(store, cfg, NOW.date()) if s.person == owner).to_send == 0


def test_a_change_before_telling_or_one_put_back_to_what_was_told_does_not_reopen_the_action(env):
    _, cfg, store = env
    action = next(a for a in store.read().list("action") if a.data["status"] == "open" and a.data.get("owners"))
    owner = action.data["owners"][0]["person"]
    _change_action(store, action.id, due="2031-03-04")  # before the person is told
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == owner)
    mark_sent(store, cfg, owner, sent_text=sec.message, now=NOW)
    assert _action_row(env, action.id, owner)["told"] == NOW.date().isoformat()
    _change_action(store, action.id, due="2031-05-06")
    assert _action_row(env, action.id, owner)["told"] is None
    _change_action(store, action.id, due="2031-03-04")  # back to the date they were told
    assert _action_row(env, action.id, owner)["told"] == NOW.date().isoformat()


def test_a_change_to_an_action_leaves_other_owners_told_before_it_alone_only_when_it_is_the_same_for_them(env):
    _, cfg, store = env
    action = next(
        a for a in store.read().list("action") if a.data["status"] == "open" and len(a.data.get("owners", [])) > 1
    )
    first, second = (o["person"] for o in action.data["owners"][:2])
    mark_sent(store, cfg, first, now=NOW)
    _change_action(store, action.id, due="2031-07-08")
    mark_sent(store, cfg, second, now=NOW + timedelta(days=1))
    assert _action_row(env, action.id, first)["told"] is None, "told before the change, so told again"
    assert _action_row(env, action.id, second)["told"] == (NOW + timedelta(days=1)).date().isoformat()


def test_followed_up_records_a_chase_keeps_the_action_open_and_counts_as_told(env):
    _, cfg, store = env
    action_id, owner, told = _waiting_action(env, cfg.ui.today.nudge_after_days + 2)
    assert _action_row(env, action_id, owner)["chase_due"]
    done = follow_up(store, action_id, owner, now=NOW)
    assert done == {"on": NOW.date().isoformat(), "previous_told": told}
    data = store.read().get("action", action_id).data
    assert data["status"] == "open"
    assert [str(d) for d in data["followed_up"][owner]] == [NOW.date().isoformat()]
    assert str(data["told"][owner]) == NOW.date().isoformat()
    row = _action_row(env, action_id, owner)
    assert row["followed_up"] == NOW.date().isoformat() and row["told_days"] == 0 and not row["chase_due"]


def test_undoing_a_chase_restores_the_told_day_and_removes_the_chase(env):
    _, cfg, store = env
    action_id, owner, told = _waiting_action(env, cfg.ui.today.nudge_after_days + 2)
    done = follow_up(store, action_id, owner, now=NOW)
    undo_follow_up(store, action_id, owner, done["on"], done["previous_told"])
    data = store.read().get("action", action_id).data
    assert data.get("followed_up", {}) == {} and str(data["told"][owner]) == told and data["status"] == "open"


def test_they_finished_credits_the_owner_and_reports_it_as_the_pm(env):
    _, cfg, store = env
    action_id, owner, _ = _waiting_action(env, 1)
    they_finished(store, cfg, action_id, owner)
    data = store.read().get("action", action_id).data
    assert data["status"] == "done" and data["done_by"] == [owner]
    assert data["reported_by"] == cfg.workspace.user.person
    with pytest.raises(FollowUpError):
        they_finished(store, cfg, action_id, owner)


def test_a_chase_is_refused_for_someone_who_doesnt_own_the_action(env):
    _, _, store = env
    action_id, owner, _ = _waiting_action(env, 1)
    owners = [o["person"] for o in store.read().get("action", action_id).data["owners"]]
    stranger = next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] not in owners)
    with pytest.raises(FollowUpError):
        follow_up(store, action_id, stranger, now=NOW)


# ---- backups ---------------------------------------------------------------------------------------------------------


def test_no_target_means_a_nag(env):
    ws, cfg, _ = env
    cfg = ws.config(env={}, flags={"storage.backups.targets": []})
    st = state(ws, cfg, NOW)
    assert st.needs_attention and not st.configured


def test_a_backup_copies_the_database_and_reports_its_age(env, tmp_path):
    ws, _, store = env
    target = tmp_path / "offsite"
    target.mkdir()
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
    target.mkdir()
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


def test_a_missing_backup_folder_is_never_created(env, tmp_path):
    from engine.backup import run_backup

    ws, _, _ = env
    target = tmp_path / "drive-not-connected" / "cockpit"
    cfg = ws.config(env={}, flags={"storage.backups.targets": [{"path": str(target)}]})
    status = run_backup(ws, cfg)
    assert not target.exists() and "isn't there" in status[str(target)]["last_error"]


def test_scheduled_backups_run_when_due_and_retry_after_a_wait(env, tmp_path):
    from datetime import UTC, datetime, timedelta

    from engine.backup import due, run_backup

    ws, _, _ = env
    target = tmp_path / "offsite"
    flags = {"storage.backups.targets": [{"path": str(target)}], "storage.backups.every_hours": 24}
    cfg = ws.config(env={}, flags=flags)
    now = datetime.now(UTC)
    assert due(ws, cfg, now)  # never backed up
    run_backup(ws, cfg, now)  # the folder isn't there yet: a failed try
    assert not due(ws, cfg, now + timedelta(minutes=10))  # waits before retrying
    assert due(ws, cfg, now + timedelta(minutes=61))
    target.mkdir()
    run_backup(ws, cfg, now + timedelta(minutes=61))
    assert not due(ws, cfg, now + timedelta(hours=23))
    assert due(ws, cfg, now + timedelta(hours=26))  # a computer waking after a day catches up at once
    off = ws.config(env={}, flags={**flags, "storage.backups.automatic": False})
    assert not due(ws, off, now + timedelta(hours=26))


def test_the_worker_makes_a_due_backup_on_its_own(env, tmp_path):
    from engine.worker import Events, Worker

    ws, _, store = env
    target = tmp_path / "offsite"
    target.mkdir()
    cfg = ws.config(env={}, flags={"storage.backups.targets": [{"path": str(target)}]})
    worker = Worker(ws, store, cfg, Events())
    assert worker.backup_if_due() and list(target.iterdir())
    assert not worker.backup_if_due()
