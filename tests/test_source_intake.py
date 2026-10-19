"""A newly added source is taken in quietly (design 6.32): the first read of a source with `first_run: intake` hands in
the mail of the last `first_run_days` and everything else the source holds, prices it as one total, starts it at once
or holds it for one go, gathers the results into one line and one list, notes how far back it looked, and can look
further back under the same rules. Names and ids come from the fixtures; the AI is the stub."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
import yaml

from engine import source_intake
from engine.config import load_config
from engine.config.schema import Price
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
SENDER = "Colleague <colleague@work.example.com>"
_TEST = WriteContext(actor="pm", trust="trusted", op="test.source-intake")


def mail(key: str, days: float, subject: str | None = None, now: datetime = NOW) -> dict:
    """A fake source's mail message received `days` before `now`."""
    received = (now - timedelta(days=days)).isoformat()
    subject = subject or f"Subject of {key}"
    return {
        "key": key,
        "title": subject,
        "text": f"From: {SENDER}\nSubject: {subject}\n\nPlain words about {key}.",
        "author": SENDER,
        "message": {"sender": SENDER, "received": received, "unread": True},
    }


def item(key: str, days: float = 400, now: datetime = NOW) -> dict:
    """A fake source's item that isn't mail (a page, say), last changed `days` before `now`."""
    return {
        "key": key,
        "title": f"Page {key}",
        "text": f"Words on {key}.",
        "changed_at": (now - timedelta(days=days)).isoformat(),
    }


def make(tmp_path, items, *, price: float | None = 1.0, confirm: float = 0.10, confirm_unpriced=True, **source):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    entry = {"id": "m", "connector": "fake", "label": "Inbox", "settings": {"items": items}, **source}
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": [entry], "sorting": "rules"}))
    cfg = load_config(ws.config_dir, env={})
    use = cfg.ai.tiers["routine"].use
    cfg.ai.prices.pop(use, None)
    if price is not None:
        cfg.ai.prices[use] = Price(input_per_million=price, output_per_million=price)
    cfg.ai.budgets.confirm_above_usd = confirm
    cfg.ai.budgets.confirm_unpriced = confirm_unpriced
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), mail("mid", 10), mail("old", 30), item("page")])
    yield ws, cfg, store
    store.close()


def read(env):
    from engine.watch import refresh

    ws, cfg, store = env
    return refresh(ws, store, cfg, "m", NOW)


def requests_of(store, **match):
    return [r for r in store.read().list("request") if all(r.data.get(k) == v for k, v in match.items())]


def titles(store, requests):
    out = []
    for r in requests:
        out.append(store.read().get("source", r.data["source"]).data["title"])
    return sorted(out)


# ---- the setting --------------------------------------------------------------------------------------------


def test_intake_is_the_default_first_run_and_the_look_back_is_two_weeks():
    from engine.config.schema import WatchFile, WatchSource

    assert WatchSource.model_fields["first_run"].get_default() == "intake"
    assert WatchSource.model_fields["first_run_days"].get_default() == 14
    assert WatchFile().look_back_choices == [30, 90, 365]
    assert WatchSource.model_validate({"id": "x", "connector": "fake"}).first_run == "intake"


# ---- the window ---------------------------------------------------------------------------------------------


def test_the_first_read_takes_in_the_last_days_of_mail_and_all_of_another_kind_and_reports_nothing_as_new(env):
    ws, cfg, store = env
    result = read(env)
    assert result.outcome == "baseline"
    assert result.new == [] and result.changed == [] and result.removed == []
    taken = requests_of(store, intake="m")
    assert titles(store, taken) == ["Page page", "Subject of mid", "Subject of new"]
    assert len(result.taken_in) == 3 and {r.id for r in taken} == set(result.taken_in)
    # Everything is noted, so the older mail is there to look further back at; nothing is handed in for it.
    assert len(store.read().find("snapshot", {"source": "m"})) == 4
    run = store.read().find("watch_run", {"source": "m"})[0]
    assert (run.data["new"], run.data["changed"], run.data["removed"]) == (0, 0, 0)


def test_the_source_notes_the_day_before_which_its_mail_was_not_looked_at(env):
    ws, cfg, store = env
    read(env)
    run = source_intake.intake_run(store.read(), "m")
    assert run.data["looked_back_to"] == "2026-10-05"
    assert source_intake.back_to_of(store.read(), "m") == date(2026, 10, 5)
    assert source_intake.days_taken(store.read(), "m") == 14


def test_another_kind_of_source_is_taken_in_whole_and_has_no_look_back_date(tmp_path):
    ws, cfg, store = make(tmp_path, [item("a"), item("b", 900)])
    try:
        result = read((ws, cfg, store))
        assert len(result.taken_in) == 2
        assert source_intake.back_to_of(store.read(), "m") is None
        assert store.read().find("watch_run", {"source": "m"})[0].data["looked_back_to"] is None
    finally:
        store.close()


def test_the_window_follows_first_run_days(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), mail("mid", 10), mail("old", 30)], first_run_days=5)
    try:
        read((ws, cfg, store))
        assert titles(store, requests_of(store, intake="m")) == ["Subject of new"]
        assert source_intake.back_to_of(store.read(), "m") == date(2026, 10, 14)
    finally:
        store.close()


def test_a_source_already_read_keeps_reading_as_before_and_a_later_item_is_ordinary_news(env):
    from engine.watch import refresh

    ws, cfg, store = env
    read(env)
    cfg.watch.sources[0].settings["items"].append(mail("later", 0.1))
    result = refresh(ws, store, cfg, "m", NOW + timedelta(hours=1))
    assert len(result.new) == 1 and result.taken_in == []
    (later,) = [r for r in requests_of(store) if r.id in result.new]
    assert not later.data.get("intake")


def test_the_other_first_runs_are_unchanged(tmp_path):
    from engine.watch import refresh

    items = [mail("new", 2), mail("old", 30)]
    ws, cfg, store = make(tmp_path, items, first_run="baseline")
    try:
        result = refresh(ws, store, cfg, "m", NOW)
        assert result.new == [] and result.taken_in == [] and requests_of(store, intake="m") == []
        assert store.read().find("watch_run", {"source": "m"})[0].data["looked_back_to"] is None
    finally:
        store.close()


# ---- the one total: start by itself, or one go --------------------------------------------------------------


def test_below_the_amount_to_confirm_the_intake_starts_by_itself_and_every_request_is_marked(env):
    ws, cfg, store = env
    read(env)
    taken = requests_of(store, intake="m")
    assert {(r.data["state"], r.data.get("approval")) for r in taken} == {("queued", None)}
    assert all(r.data["estimate_usd"] > 0 for r in taken)
    assert sum(r.data["estimate_usd"] for r in taken) <= cfg.ai.budgets.confirm_above_usd
    assert not [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"]


def test_above_the_amount_to_confirm_the_requests_wait_for_one_go_with_the_total(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), mail("mid", 10), item("page")], confirm=0.0)
    try:
        read((ws, cfg, store))
        held = requests_of(store, intake="m")
        for r in held:
            assert (r.data["state"], r.data["approval"], r.data["waiting"]) == (
                "needs_you",
                "required",
                source_intake.WAITING,
            )
        (line,) = [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"]
        assert (line.group, line.source, line.subject, line.count, line.unpriced) == ("decide", "m", "Inbox", 3, 0)
        assert line.days == 14
        assert line.estimate_usd == pytest.approx(sum(r.data["estimate_usd"] for r in held))
        # No line of their own for each, and nothing has run.
        assert not [x for x in queue(ws, store, cfg, NOW) if x.kind in ("go", "refused", "failed", "first_go")]
        assert not store.read().has("run")
    finally:
        store.close()


def test_an_intake_with_no_price_is_held_for_the_go_and_says_how_many_have_none(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), item("page")], price=None)
    try:
        read((ws, cfg, store))
        (line,) = [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"]
        assert (line.count, line.estimate_usd, line.unpriced) == (2, None, 2)
    finally:
        store.close()


def test_an_unpriced_intake_starts_by_itself_when_unpriced_runs_need_no_go(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), item("page")], price=None, confirm_unpriced=False)
    try:
        read((ws, cfg, store))
        assert [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"] == []
        taken = [r for r in store.read().list("request") if r.data.get("intake") == "m"]
        assert len(taken) == 2 and {r.data["state"] for r in taken} == {"queued"}
    finally:
        store.close()


def test_a_source_with_no_mail_says_items_not_days(tmp_path):
    ws, cfg, store = make(tmp_path, [item("a"), item("b")], price=None)
    try:
        read((ws, cfg, store))
        (line,) = [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"]
        assert line.count == 2 and line.days is None
    finally:
        store.close()


def test_the_go_starts_every_held_request_of_the_source_once(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), mail("mid", 10), item("page")], confirm=0.0)
    try:
        read((ws, cfg, store))
        assert source_intake.grant_go(ws, store, cfg, "m") == 3
        assert {(r.data["state"], r.data["approval"]) for r in requests_of(store, intake="m")} == {
            ("queued", "granted")
        }
        assert source_intake.grant_go(ws, store, cfg, "m") == 0
        assert not [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"]
    finally:
        store.close()


def test_the_first_go_still_applies_on_top_of_an_intake_that_started_by_itself(env):
    from engine.ai.router import Router
    from engine.dispatcher import FIRST_GO, process

    ws, cfg, store = env
    cfg.ai.budgets.first_go = True
    read(env)
    (first, *_rest) = requests_of(store, intake="m")
    assert process(ws, store, cfg, Router(cfg, store, env={}), first.id, now=NOW) is None
    held = store.read().get("request", first.id).data
    assert (held["state"], held["approval"], held["waiting"]) == ("needs_you", "required", FIRST_GO)
    assert not store.read().has("run")


# ---- the results as one line --------------------------------------------------------------------------------


def with_changeset(store, request_id, ops):
    """Give a request the changeset the assistant would have made: its ops with their outcomes."""
    with store.transaction() as tx:
        cs = tx.create(
            "changeset",
            {
                "request": request_id,
                "summary": "Did things.",
                "ops": [
                    {"index": i, "op": {"op": name}, "status": status, "label": f"{name} {i}"}
                    for i, (name, status) in enumerate(ops)
                ],
                "status": "held" if any(s == "held" for _n, s in ops) else "applied",
                "trust": "untrusted",
                "created_at": NOW.isoformat(),
            },
            _TEST,
        )
        req = tx.get("request", request_id)
        tx.update("request", request_id, {"state": "review", "changeset": cs.id}, _TEST, read_version=req.version)
    return cs.id


def lines_of(env, *kinds):
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, NOW) if x.kind in kinds]


def test_while_the_intake_runs_its_results_have_no_lines_and_afterwards_one_line_counts_them(env):
    ws, cfg, store = env
    read(env)
    first, second, third = requests_of(store, intake="m")
    with_changeset(store, first.id, [("action.add", "applied"), ("action.add", "applied")])
    # Another request is still queued: nothing is shown yet, not even a line for the one that is done.
    assert lines_of(env, "review", "intake_review") == []
    with_changeset(store, second.id, [("question.add", "applied"), ("action.add", "held")])
    with store.transaction() as tx:
        cur = tx.get("request", third.id)
        tx.update("request", third.id, {"state": "done", "waiting": None}, _TEST, read_version=cur.version)
    assert lines_of(env, "held") == [], "a held item of the intake has no line of its own"
    (line,) = lines_of(env, "review", "intake_review")
    assert (line.kind, line.group, line.source, line.subject) == ("intake_review", "review", "m", "Inbox")
    assert line.count == 2, "two items have something to look over"
    assert line.outcome == {"actions_added": 3, "questions": 1, "held": 1}


def test_a_failed_intake_request_still_has_its_own_line_and_counts_as_finished(env):
    ws, cfg, store = env
    read(env)
    first, second, third = requests_of(store, intake="m")
    with_changeset(store, first.id, [("action.add", "applied")])
    for r in (second, third):
        with store.transaction() as tx:
            cur = tx.get("request", r.id)
            tx.update("request", r.id, {"state": "failed", "waiting": "It stopped."}, _TEST, read_version=cur.version)
    assert len(lines_of(env, "failed")) == 2
    assert len(lines_of(env, "intake_review")) == 1


def test_other_requests_keep_their_own_review_lines(env):
    ws, cfg, store = env
    read(env)
    with store.transaction() as tx:
        plain = tx.create(
            "request",
            {"task": "notes", "origin": "pm", "state": "queued", "created_at": NOW.isoformat()},
            _TEST,
        ).id
    with_changeset(store, plain, [("action.add", "applied")])
    assert [x.request for x in lines_of(env, "review")] == [plain]


def test_opening_the_list_marks_it_seen_and_the_individual_lines_come_back_and_undo_hides_them_again(env):
    ws, cfg, store = env
    read(env)
    first, second, third = requests_of(store, intake="m")
    with_changeset(store, first.id, [("action.add", "applied")])
    with_changeset(store, second.id, [("action.add", "held")])
    with store.transaction() as tx:
        cur = tx.get("request", third.id)
        tx.update("request", third.id, {"state": "done"}, _TEST, read_version=cur.version)
    assert len(lines_of(env, "intake_review")) == 1
    marked = source_intake.mark_seen(store, "m")
    assert sorted(marked) == sorted(r.id for r in (first, second, third))
    assert lines_of(env, "intake_review") == []
    assert {x.request for x in lines_of(env, "review")} == {first.id, second.id}, "each shows one by one again"
    assert len(lines_of(env, "held")) == 1
    assert source_intake.mark_seen(store, "m") == []
    assert source_intake.mark_unseen(store, marked) == 3
    assert len(lines_of(env, "intake_review")) == 1 and lines_of(env, "held") == []


def test_nothing_applied_is_hidden_from_the_changes_or_undone(env):
    ws, cfg, store = env
    read(env)
    first = requests_of(store, intake="m")[0]
    cs = with_changeset(store, first.id, [("action.add", "applied")])
    source_intake.mark_seen(store, "m")
    assert store.read().get("changeset", cs).data["status"] == "applied"
    assert store.read().get("request", first.id).data["state"] == "review"


# ---- looking further back -----------------------------------------------------------------------------------


@pytest.fixture
def old_mail(tmp_path):
    items = [mail("new", 2), mail("a", 20), mail("b", 40), mail("c", 100), mail("d", 300), item("page")]
    ws, cfg, store = make(tmp_path, items)
    yield ws, cfg, store
    store.close()


def test_the_preview_counts_what_a_longer_look_would_take_in_and_prices_it_and_writes_nothing(old_mail):
    ws, cfg, store = old_mail
    read(old_mail)
    before = len(store.read().list("request"))
    thirty = source_intake.look_back_preview(ws, store, cfg, "m", 30, NOW)
    assert (thirty.count, thirty.reaches, thirty.from_date) == (2, True, date(2026, 9, 5))
    ninety = source_intake.look_back_preview(ws, store, cfg, "m", 90, NOW)
    assert ninety.count == 3 and ninety.estimate_usd > thirty.estimate_usd > 0
    year = source_intake.look_back_preview(ws, store, cfg, "m", 365, NOW)
    assert year.count == 4 and year.unpriced == 0
    assert len(store.read().list("request")) == before and source_intake.back_to_of(store.read(), "m") == date(
        2026, 10, 5
    )


def test_a_look_back_with_no_price_says_how_many_have_none(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), mail("a", 20)], price=None)
    try:
        read((ws, cfg, store))
        found = source_intake.look_back_preview(ws, store, cfg, "m", 30, NOW)
        assert (found.count, found.estimate_usd, found.unpriced) == (1, None, 1)
    finally:
        store.close()


def test_only_the_listed_choices_can_be_asked_for(old_mail):
    from engine.storage import StoreError

    ws, cfg, store = old_mail
    read(old_mail)
    with pytest.raises(StoreError):
        source_intake.look_back_preview(ws, store, cfg, "m", 45, NOW)


def test_looking_further_back_takes_in_the_older_mail_the_same_way_and_moves_the_date(old_mail):
    ws, cfg, store = old_mail
    read(old_mail)
    done = source_intake.look_further_back(ws, store, cfg, "m", 90, NOW)
    assert (done.taken, done.started, done.reaches) == (3, True, True)
    assert source_intake.back_to_of(store.read(), "m") == date(2026, 7, 7)
    taken = requests_of(store, intake="m")
    assert titles(store, taken) == ["Page page", "Subject of a", "Subject of b", "Subject of c", "Subject of new"]
    assert {r.data["state"] for r in taken} == {"queued"}
    # What was already taken in isn't taken again, and the dates add up: the next look starts from the new date.
    again = source_intake.look_further_back(ws, store, cfg, "m", 30, NOW)
    assert again.taken == 0
    assert source_intake.back_to_of(store.read(), "m") == date(2026, 6, 7)


def test_a_look_back_is_held_for_the_go_by_the_same_rule_and_joins_the_sources_line(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), mail("a", 20)], confirm=0.0)
    try:
        read((ws, cfg, store))
        done = source_intake.look_further_back(ws, store, cfg, "m", 30, NOW)
        assert (done.taken, done.started) == (1, False)
        (line,) = [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"]
        assert line.count == 2, "one line for the source, with what is already waiting"
        assert source_intake.grant_go(ws, store, cfg, "m") == 2
    finally:
        store.close()


def test_when_the_source_doesnt_reach_that_far_the_result_says_so_and_the_date_stops_where_the_mail_does(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("new", 2), mail("a", 20)])
    try:
        read((ws, cfg, store))
        found = source_intake.look_back_preview(ws, store, cfg, "m", 90, NOW)
        assert (found.reaches, found.available_from) == (False, (NOW - timedelta(days=20)).date())
        done = source_intake.look_further_back(ws, store, cfg, "m", 90, NOW)
        assert (done.taken, done.reaches) == (1, False)
        assert source_intake.back_to_of(store.read(), "m") == (NOW - timedelta(days=20)).date()
    finally:
        store.close()


def test_a_source_without_mail_has_no_look_back(tmp_path):
    from engine.storage import StoreError

    ws, cfg, store = make(tmp_path, [item("a")])
    try:
        read((ws, cfg, store))
        with pytest.raises(StoreError):
            source_intake.look_back_preview(ws, store, cfg, "m", 30, NOW)
    finally:
        store.close()
