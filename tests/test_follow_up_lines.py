"""Today's lines for backups and follow-ups (design 7.7): a backup that needs attention is an At risk line, and each
person the person is waiting on is one follow-up line, whatever the number of their items, which opens the one nudge
to them. Names, ids and texts come from the fictional workspace's records."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from engine import backup
from engine.config.schema import BackupTarget
from engine.followups import sections
from tests import test_promise_lines
from tests.test_promise_lines import NOW, PAST, TODAY, lines, make, me

env = test_promise_lines.env  # the promise lines' workspace fixture


# ---- the backup line -------------------------------------------------------------------------------------------------


def backing_up(env, *, target: bool, **status):
    """Set the workspace's backups: a target or none, and what the last attempt left in the status file."""
    ws, cfg, _ = env
    cfg.storage.backups.targets = [BackupTarget(path="/backups/example", label="drive")] if target else []
    if status:
        backup._save(ws, {"/backups/example": status})
    return [line for line in lines(env) if line.kind == "backup"]


def test_with_no_backup_folder_the_line_is_at_risk_and_says_unset(env):
    (line,) = backing_up(env, target=False)
    assert (line.group, line.key, line.state, line.age_hours) == ("risk", "backup", "unset", None)


def test_with_a_folder_and_no_backup_yet_it_says_never_and_a_failed_try_says_failed(env):
    (line,) = backing_up(env, target=True)
    assert line.state == "never"
    (line,) = backing_up(env, target=True, last_error="the folder is not there", last_attempt=NOW.isoformat())
    assert line.state == "failed"


def test_an_overdue_backup_says_how_many_hours_ago_the_last_one_was(env):
    _, cfg, _ = env
    old = NOW - timedelta(hours=3 * cfg.storage.backups.every_hours)
    (line,) = backing_up(env, target=True, last_success=old.isoformat())
    assert line.state == "overdue" and line.age_hours == 3 * cfg.storage.backups.every_hours


def test_a_current_backup_leaves_no_line(env):
    recent = NOW - timedelta(hours=1)
    assert backing_up(env, target=True, last_success=recent.isoformat()) == []


# ---- one follow-up line per person -----------------------------------------------------------------------------------


def someone(env) -> str:
    """A person other than the one asking who holds no action in the fixtures, so a case counts only what it makes."""
    _, cfg, store = env
    view = store.read()
    busy = {o["person"] for a in view.list("action") for o in a.data["owners"]}
    return next(p.id for p in view.list("person") if p.id != me(cfg) and p.id not in busy)


def nudges(env, person: str):
    return lines(env, kind="nudge", person=person)


def test_two_overdue_waiting_ons_are_one_follow_up_line_with_its_counts_and_oldest_date(env):
    _, cfg, store = env
    them = someone(env)
    older = make(store, [them], due=PAST - timedelta(days=2), promised_to=[me(cfg)], basis="said", text="Book the room")
    newer = make(store, [them], due=PAST, promised_to=[me(cfg)], basis="said")
    (line,) = nudges(env, them)
    assert (line.group, line.key, line.count, line.overdue) == ("send", f"nudge:{them}", 2, 2)
    assert line.due == (PAST - timedelta(days=2)).isoformat() and set(line.actions) == {older, newer}
    # Neither is a line of its own any more.
    assert [x for x in lines(env, kind="promise") if x.person == them] == []


def test_the_nudge_to_that_person_lists_what_the_line_covers(env):
    _, cfg, store = env
    them = someone(env)
    first = make(store, [them], due=PAST - timedelta(days=2), promised_to=[me(cfg)], basis="said", text="Book the room")
    second = make(store, [them], due=PAST, promised_to=[me(cfg)], basis="said")
    section = next(s for s in sections(store, cfg, TODAY) if s.person == them)
    assert section.nudge is not None and set(section.nudge.action_ids) == {first, second}
    assert "Book the room" in section.nudge.text


def test_a_waiting_on_someone_the_person_reports_to_stays_a_line_of_its_own(env):
    _, cfg, store = env
    them = someone(env)
    with store.transaction() as tx:
        from tests.test_stance_lines import _TEST

        tx.update("person", them, {"stance": "report_to"}, _TEST, read_version=tx.get("person", them).version)
    action = make(store, [them], due=PAST, promised_to=[me(cfg)], basis="said")
    assert [x.actions for x in lines(env, kind="promise", person=them)] == [[action]]
    assert nudges(env, them) == []


def test_the_persons_own_promise_stays_its_own_line(env):
    _, cfg, store = env
    action = make(store, [me(cfg)], due=PAST, promised_to=[someone(env)], basis="said")
    assert [x.actions for x in lines(env, kind="promise") if x.person is None] == [[action]]


def test_each_person_is_in_the_queue_at_most_once_per_verb(env):
    _, cfg, store = env
    them = someone(env)
    for n in range(3):
        make(store, [them], due=PAST - timedelta(days=n), promised_to=[me(cfg)], basis="said", text=f"Task {n}")
    make(store, [them], due=None, promised_to=[me(cfg)], text="Undated", made=TODAY - timedelta(days=40))
    found = Counter(
        (x.kind, x.person) for x in lines(env) if x.kind in ("send", "nudge", "escalate", "promise") and x.person
    )
    assert found and max(found.values()) == 1
    assert found[("nudge", them)] == 1 and ("promise", them) not in found


def test_a_follow_up_line_counts_only_what_is_overdue_as_overdue(env):
    _, cfg, store = env
    them = someone(env)
    make(store, [them], due=PAST, promised_to=[me(cfg)], basis="said")
    make(store, [them], due=None, promised_to=[me(cfg)], text="Undated", made=TODAY - timedelta(days=40))
    (line,) = nudges(env, them)
    assert (line.count, line.overdue, line.due) == (2, 1, PAST.isoformat())


def test_a_promise_whose_date_is_still_ahead_has_waited_no_days_on_the_follow_up_line(env):
    """A promise owed to the person that isn't due yet is on the follow-up line with a wait of zero days, never below
    (its days past the date are negative until the date comes)."""
    _, cfg, store = env
    them = someone(env)
    make(store, [them], due=TODAY + timedelta(days=1), promised_to=[me(cfg)], basis="said")
    found = nudges(env, them)
    assert found and all(line.waiting_days == 0 for line in found)
