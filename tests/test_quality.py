"""The measures the learning loop is judged by (design 6.20, 6.13, 6.16): the knowledge ids a run says it applied, the
knowledge-used rate, the repeat-correction rate with its weekly gate, the missing-op list, accounts in a fallback chain
and the learning round-trip of the account check. The measures are plain functions over records and are tested on
records; the pipeline tests follow a request to its changeset. Names and ids come from the fixtures; the AI is the stub
and the fake agent.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine import learn, quality
from engine.ai.adapters.stub import set_responder
from engine.ai.checked import account_fingerprint, chain_problems, is_checked, remember
from engine.ai.learning_check import CHECK_REQUEST
from engine.ai.router import Router
from engine.ai.smoke import account_test, smoke_test
from engine.ai.task import AiError, AiResult
from engine.config.schema import KnowledgeSettings
from engine.dispatcher import process, signal
from engine.intake import hand_in
from engine.settings import SettingsError, fingerprint, save
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, connection_answer, fixture_records, without_first_go

PM = fixture_records(DEMO_B, "person")[0]["id"]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)  # a Wednesday
THIS_WEEK = datetime(2026, 10, 12).date()
LAST_WEEK = THIS_WEEK - timedelta(weeks=1)
UTC_ZONE = ZoneInfo("UTC")
_TEST = WriteContext(actor="pm", trust="trusted", op="test.quality")
HOLD = "an op to put an action on hold"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def make(store, kind, data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def lesson(store, *, text="Ask whoever owns the work.", **scope) -> str:
    return make(
        store,
        "lesson",
        {
            "text": text,
            "origin": "person",
            "status": "active",
            "learned_at": NOW.isoformat(),
            "kept_by": PM,
            "kept_at": NOW.isoformat(),
            "applies_to": scope,
        },
    )


def note(store) -> str:
    return make(store, "note", {"text": "Something kept."})


def run_record(store, *, task="notes", given=(), at=NOW, outcome="ok") -> str:
    return make(
        store,
        "run",
        {
            "task": task,
            "provider": "stub",
            "model": "stub",
            "tier": "routine",
            "outcome": outcome,
            "started_at": at.isoformat(),
            "knowledge": {"given": list(given)},
        },
    )


def changeset_record(store, run, *, task="notes", records=(), at=NOW, **fields) -> str:
    request = make(store, "request", {"task": task, "origin": "pm", "state": "done", "created_at": at.isoformat()})
    ops = [{"index": 0, "op": {}, "status": "applied", "records": [{"kind": k, "id": i} for k, i in records]}]
    return make(
        store,
        "changeset",
        {
            "request": request,
            "ops": ops,
            "status": "applied",
            "trust": "trusted",
            "run": run,
            "created_at": at.isoformat(),
            **fields,
        },
    )


def correction(store, run, changeset, *, kind="sent_back", at=NOW) -> str:
    data = {"kind": kind, "refs": [changeset], "run": run, "changeset": changeset, "note": None, "at": at.isoformat()}
    return make(store, "signal", data)


def corrected(store, *, given, scope, at=NOW, task="notes", item=None) -> str:
    """One correction of a note by a run that was given these entries. Returns the lesson-free signal id."""
    run = run_record(store, task=task, given=given, at=at)
    changeset = changeset_record(store, run, task=task, records=[("note", item or note(store))], at=at)
    return correction(store, run, changeset, at=at)


# ---- what an answer claims -------------------------------------------------------------------------------------------


def test_applied_ids_are_kept_only_when_the_run_was_given_them_and_the_rest_are_counted_and_missing_is_kept(env):
    ws, cfg, store = env
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    given = lesson(store)
    set_responder(
        lambda task: json.dumps(
            {
                "summary": "Filed it.",
                "ops": [{"op": "note", "text": "Something to keep."}],
                "applied": [given, given, "LES-9999", "not an id", 4],
                "missing": [HOLD, "An op to put an action on hold.", ""],
            }
        )
    )
    request = hand_in(ws, store, pasted="Interior files are due.", now=NOW).request
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    stored = store.read().get("changeset", cs_id).data
    run = store.read().get("run", stored["run"]).data
    assert given in run["knowledge"]["given"], "the lesson reached the run, so its claim stands"
    assert stored["applied"] == [given]
    assert stored["applied_dropped"] == 2, "an id it wasn't given and a word that isn't an id, counted not kept"
    assert stored["missing"] == [HOLD, "An op to put an action on hold."]
    assert not stored["first_on_account"]


def test_an_answer_with_nothing_to_claim_leaves_the_changeset_fields_empty(env):
    ws, cfg, store = env
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    set_responder(lambda task: json.dumps({"summary": "Filed it.", "ops": [{"op": "note", "text": "Something."}]}))
    request = hand_in(ws, store, pasted="Interior files are due.", now=NOW).request
    stored = store.read().get("changeset", process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)).data
    assert (stored["applied"], stored["applied_dropped"], stored["missing"]) == ([], 0, [])


# ---- the knowledge-used rate -----------------------------------------------------------------------------------------


def test_the_knowledge_used_rate_counts_runs_given_something_and_only_those_that_made_a_changeset(env):
    _, _, store = env
    entry = lesson(store)
    for given, applied in [([entry], [entry]), ([entry], []), ([], []), ([entry], [entry])]:
        changeset_record(store, run_record(store, given=given), applied=applied)
    run_record(store, given=[entry])  # a call that never became a changeset (a fix round) counts for nothing
    changeset_record(store, run_record(store, task="ask", given=[entry]), applied_dropped=3)
    old = NOW - timedelta(days=60)
    changeset_record(store, run_record(store, given=[entry], at=old), applied=[entry], at=old)  # outside the window
    found = {k.task: k for k in quality.knowledge_used(store.read(), NOW, 28)}
    assert (found["notes"].given, found["notes"].applied, found["notes"].dropped) == (3, 2, 0)
    assert found["notes"].rate == pytest.approx(2 / 3)
    assert (found["ask"].given, found["ask"].applied, found["ask"].dropped, found["ask"].rate) == (1, 0, 3, 0.0)


# ---- the repeat-correction rate --------------------------------------------------------------------------------------


def weeks(store, minimum=3, days=28):
    return quality.repeat_corrections(store.read(), store.plugins.records, NOW, days, minimum, UTC_ZONE)


def test_a_correction_repeats_only_when_the_run_was_given_knowledge_whose_target_matched_the_corrected_item(env):
    _, _, store = env
    matching = lesson(store, task_kinds=["notes"], records=["note.text"])
    other_kind = lesson(store, task_kinds=["ask"], records=["note"])
    other_record = lesson(store, task_kinds=["notes"], records=["action"])
    no_target = lesson(store)  # names nothing, so it is about everything and so about nothing in particular
    retired = lesson(store, task_kinds=["notes"], records=["note"])
    first = corrected(store, given=[matching], scope=None)
    unmatched = [
        corrected(store, given=[other_kind], scope=None),
        corrected(store, given=[other_record], scope=None),
        corrected(store, given=[no_target], scope=None),
        corrected(store, given=[], scope=None),
    ]
    view = store.read()
    repeat = lambda s: quality.is_repeat(view, store.plugins.records, view.get("signal", s))  # noqa: E731
    assert repeat(first)
    assert not any(repeat(s) for s in unmatched)
    assert retired and not repeat(corrected(store, given=[retired], scope=None, task="ask"))


def test_a_lesson_for_other_projects_does_not_match_and_one_for_the_corrected_projects_does(env):
    _, _, store = env
    mine = fixture_records(DEMO_B, "project")[0]["id"]
    elsewhere = make(store, "project", {"name": "Another project"})
    scoped_here = lesson(store, task_kinds=["notes"], scope="projects", projects=[mine])
    scoped_there = lesson(store, task_kinds=["notes"], scope="projects", projects=[elsewhere])
    item = make(store, "note", {"text": "About the first project.", "project": mine})
    here = corrected(store, given=[scoped_here], scope=None, item=item)
    there = corrected(store, given=[scoped_there], scope=None, item=item)
    view = store.read()
    assert quality.is_repeat(view, store.plugins.records, view.get("signal", here))
    assert not quality.is_repeat(view, store.plugins.records, view.get("signal", there))


def test_a_week_has_a_rate_only_with_the_configured_number_of_corrections(env):
    _, _, store = env
    entry = lesson(store, task_kinds=["notes"], records=["note"])
    for _ in range(2):
        corrected(store, given=[entry], scope=None)
    corrected(store, given=[], scope=None)
    for _ in range(2):
        corrected(store, given=[entry], scope=None, at=NOW - timedelta(weeks=1))
    this, last = (next(w for w in weeks(store) if w.week == day) for day in (THIS_WEEK, LAST_WEEK))
    assert (this.corrections, this.repeats, this.enough) == (3, 2, True) and this.rate == pytest.approx(2 / 3)
    assert (last.corrections, last.repeats, last.enough, last.rate) == (2, 2, False, None)
    assert [w.week for w in weeks(store)] == [LAST_WEEK, THIS_WEEK]
    assert all(w.rate is None for w in weeks(store, minimum=4)), "a bigger minimum hides a week that is too small"
    assert KnowledgeSettings().min_corrections_per_week == 10


def test_corrections_the_person_took_back_or_that_no_run_made_are_not_counted(env):
    _, _, store = env
    entry = lesson(store, task_kinds=["notes"], records=["note"])
    for _ in range(3):
        corrected(store, given=[entry], scope=None)
    make(  # of something no run made
        store, "signal", {"kind": "put_on_hold", "refs": [], "run": None, "changeset": None, "at": NOW.isoformat()}
    )
    run = run_record(store, given=[entry])
    changeset = changeset_record(store, run, records=[("note", note(store))])
    taken_back = signal(store, "sent_back", [changeset], note="No, redo it", now=NOW, changeset=changeset)
    assert weeks(store)[0].corrections == 4
    assert learn.net_out(store, "sent_back", [changeset])
    assert taken_back and weeks(store)[0].corrections == 3
    kept = signal(store, "kept", [entry], now=NOW)  # what the person does to what was learned isn't a correction
    assert kept and weeks(store)[0].corrections == 3


# ---- the missing-op list ---------------------------------------------------------------------------------------------


def test_what_runs_lacked_is_grouped_by_wording_with_counts_week_by_week(env):
    _, _, store = env
    run = run_record(store)
    changeset_record(store, run, missing=[HOLD, "Merge two projects"])
    changeset_record(store, run, missing=["An op to put an action on hold."], task="ask")
    changeset_record(store, run, missing=["The op to put an action on hold!"], at=NOW - timedelta(weeks=1))
    changeset_record(store, run, missing=["Old news"], at=NOW - timedelta(days=90))
    found = quality.missing_list(store.read(), NOW, 28, UTC_ZONE)
    assert [w.week for w in found] == [THIS_WEEK, LAST_WEEK], "newest week first; outside the window is left out"
    this = found[0].groups
    assert [(g.count, quality.wording_key(g.wording)) for g in this] == [
        (2, "op to put an action on hold"),
        (1, "merge two projects"),
    ]
    assert this[0].tasks == ["ask", "notes"] and len(this[0].changesets) == 2
    assert [g.count for g in found[1].groups] == [1]


def drop_signals(store, kind: str, count: int, at=NOW, note: str | None = "No longer needed.") -> None:
    for _ in range(count):
        make(store, "signal", {"kind": kind, "refs": [], "note": note, "at": at.isoformat()})


def test_a_drop_is_not_a_correction_of_the_assistant_and_leaves_the_counts_and_the_repeat_rate(env):
    _, _, store = env
    assert "dropped" not in quality.CORRECTIONS
    assert {"held_declined", "missed", "sent_back"} <= quality.CORRECTIONS
    entry = lesson(store, task_kinds=["notes"], records=["note"])
    run = run_record(store, task="notes", given=[entry])
    item = note(store)
    changeset = changeset_record(store, run, task="notes", records=[("note", item)])
    correction(store, run, changeset, kind="sent_back")
    correction(store, run, changeset, kind="held_declined")
    before = weeks(store, minimum=1)
    for _ in range(5):
        correction(store, run, changeset, kind="dropped")  # a week of drops of this run's work
    after = weeks(store, minimum=1)
    assert before == after, "five drops changed neither the corrections counted nor the repeats"
    (week,) = after
    assert (week.corrections, week.enough) == (2, True)


def test_missed_declined_and_dropped_are_counted_apart_for_each_week_and_never_added_together(env):
    _, _, store = env
    drop_signals(store, "missed", 1)
    drop_signals(store, "held_declined", 2)
    drop_signals(store, "dropped", 9)
    drop_signals(store, "dropped", 4, at=NOW - timedelta(weeks=1))
    drop_signals(store, "sent_back", 3)  # a correction of another kind is in none of the three
    drop_signals(store, "missed", 1, at=NOW - timedelta(days=90))  # outside the window
    rows = quality.apart_per_week(store.read(), NOW, 28, UTC_ZONE)
    by_week = {r.week: (r.missed, r.declined, r.dropped) for r in rows}
    assert by_week[THIS_WEEK] == (1, 2, 9)
    assert by_week[LAST_WEEK] == (0, 0, 4)
    assert [r.week for r in rows] == sorted(by_week) and len(rows) == 5, "every week of the window, oldest first"


def test_the_quality_route_gives_missed_declined_and_dropped_apart(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "quality-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer quality-token"}) as client:
        now = datetime.now(UTC)
        store = application.state.store
        drop_signals(store, "missed", 2, at=now)
        drop_signals(store, "held_declined", 1, at=now)
        drop_signals(store, "dropped", 7, at=now)
        body = client.get("/api/quality").json()
    apart = body["apart"]
    assert (apart["missed"], apart["declined"], apart["dropped"]) == (2, 1, 7)
    assert sum(w["dropped"] for w in apart["weeks"]) == 7 and sum(w["missed"] for w in apart["weeks"]) == 2
    last = apart["weeks"][-1]
    assert date.fromisoformat(last["week_end"]) - date.fromisoformat(last["week"]) == timedelta(days=6)
    assert body["repeat_corrections"] == [], "drops and misses with no run are no repeat-correction week"


def test_the_quality_route_reports_the_three_measures_and_the_default_gate_hides_a_small_week(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "quality-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer quality-token"}) as client:
        store = application.state.store
        entry = lesson(store, task_kinds=["notes"], records=["note"])
        now = datetime.now(UTC)
        for _ in range(3):
            corrected(store, given=[entry], scope=None, at=now)
        run = run_record(store, given=[entry], at=now)
        changeset_record(store, run, applied=[entry], missing=[HOLD], at=now)
        body = client.get("/api/quality").json()
    assert body["days"] == 28 and body["min_corrections_per_week"] == 10
    used = next(k for k in body["knowledge_used"] if k["task"] == "notes")
    assert (used["runs_given"], used["runs_applied"], used["rate"]) == (4, 1, 0.25)
    (week,) = body["repeat_corrections"]
    assert (week["corrections"], week["repeats"], week["enough"], week["rate"]) == (3, 3, False, None)
    assert [(g["wording"], g["count"]) for g in body["missing"][0]["groups"]] == [(HOLD, 1)]


# ---- fallback chains -------------------------------------------------------------------------------------------------


def add_account(ws, name, **more) -> None:
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"][name] = {"adapter": "stub", "models": {"default": "scripted"}, "allowed_data": ["open"], **more}
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def add_to_chain(ws, cfg, store, name, tier="routine"):
    return save(
        ws,
        cfg,
        store,
        changes={f"ai.tiers.{tier}.fallback": [f"{name}/default"]},
        reset=[],
        read_fingerprint=fingerprint(ws.config_dir),
        env={},
        allow=("ai.tiers.",),
    )


def test_an_unchecked_account_is_refused_from_a_chain_until_it_passes_for_that_tier_or_the_person_accepts_it(env):
    ws, _, store = env
    add_account(ws, "second")
    add_account(ws, "third", accepted_unchecked=True)
    cfg = ws.config(env={})
    with pytest.raises(SettingsError) as refused:
        add_to_chain(ws, cfg, store, "second")
    reason = str(refused.value)
    assert "second" in reason and "connection check" in reason
    assert not any(word in reason for word in ("ai.yaml", "accepted_unchecked", "ai.tiers", "routine", "tier"))
    assert ws.config(env={}).ai.tiers["routine"].fallback == [], "nothing was written"
    # A test without a tier uses no kind of work's parameters, so it doesn't count; one for this tier's exact
    # parameters does, and stops counting when a kind of work's parameters change.
    remember(ws, cfg, account_test(cfg, {}, "second", store=store))
    assert not is_checked(ws, cfg, "second/default", "routine")
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    assert is_checked(ws, cfg, "second/default", "routine")
    warmer = ws.config(env={}, flags={"ai.tasks.notes.temperature": 0.7})
    assert not is_checked(ws, warmer, "second/default", "routine")
    assert add_to_chain(ws, cfg, store, "second").changes
    assert ws.config(env={}).ai.tiers["routine"].fallback == ["second/default"]
    # The person accepting an account unchecked is enough, with no test.
    assert add_to_chain(ws, ws.config(env={}), store, "third", tier="deep").changes
    assert ws.config(env={}).ai.tiers["deep"].fallback == ["third/default"]


def test_a_failed_check_or_a_changed_account_is_not_checked_and_an_account_already_in_a_chain_stays(env):
    ws, _, store = env
    add_account(ws, "second")
    cfg = ws.config(env={})
    set_responder(lambda task: (_ for _ in ()).throw(AiError("other", "refused")))
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    assert not is_checked(ws, cfg, "second/default", "routine")
    set_responder(connection_answer)
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    assert is_checked(ws, cfg, "second/default", "routine")
    add_account(ws, "second", timeout_seconds=77)
    changed = ws.config(env={})
    assert account_fingerprint(changed, "second/default") != account_fingerprint(cfg, "second/default")
    assert not is_checked(ws, changed, "second/default", "routine"), "a changed account is checked again"
    # A chain that already holds the account isn't questioned by a later save.
    chained = ws.config(env={}, flags={"ai.tiers.routine.fallback": ["second/default"]})
    assert chain_problems(ws, ws.config(env={}), chained) != []
    assert chain_problems(ws, chained, chained) == []


def first_run_env(ws, store):
    """A workspace whose routine tier uses an account that is down and falls back to a second one."""
    add_account(ws, "second", timeout_seconds=77, accepted_unchecked=True)
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["tiers"]["routine"]["fallback"] = ["second/default"]
    data["providers"]["stub"]["allowed_data"] = ["open", "internal", "restricted"]
    data["providers"]["second"]["allowed_data"] = ["open", "internal", "restricted"]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})

    class Down:
        def run(self, task, model):
            raise AiError("provider_down", "unreachable")

    class Answers:
        def run(self, task, model):
            body = {"summary": "Filed it.", "ops": [{"op": "note", "text": "Something."}]}
            return AiResult(text=json.dumps(body), model_served="served", seconds=0.0)

    def factory(adapter, settings, secret):
        return Answers() if settings.timeout_seconds == 77 else Down()

    return cfg, Router(cfg, store, env={}, adapter_factory=factory)


def test_the_first_run_on_a_fallback_account_is_tagged_on_its_changeset_and_a_later_one_is_not(env):
    ws, _, store = env
    cfg, router = first_run_env(ws, store)
    tags = []
    for n in range(2):
        request = hand_in(ws, store, pasted=f"Interior files are due, item {n}.", now=NOW).request
        cs_id = process(ws, store, cfg, router, request, now=NOW)
        tags.append(store.read().get("changeset", cs_id).data["first_on_account"])
    assert tags == ["second", None]


def test_a_run_on_the_tiers_main_account_is_never_tagged(env):
    ws, cfg, store = env
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    set_responder(lambda task: json.dumps({"summary": "Filed it.", "ops": [{"op": "note", "text": "Something."}]}))
    request = hand_in(ws, store, pasted="Interior files are due.", now=NOW).request
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    assert store.read().get("changeset", cs_id).data["first_on_account"] is None


# ---- the learning round-trip -----------------------------------------------------------------------------------------


def learning_results(results):
    return [r for r in results if r.part == "learning"]


def test_the_account_check_gives_every_account_one_learning_call_and_a_proposal_the_app_accepts_passes(env):
    ws, cfg, store = env
    asked = []

    def responder(task):
        asked.append(task)
        return connection_answer(task)

    set_responder(responder)
    results = smoke_test(cfg, {}, store=store)
    (found,) = learning_results(results)
    assert found.ok and found.ref == "stub/default" and "proposal" in found.detail
    learning = [t for t in asked if t.request == CHECK_REQUEST]
    assert len(learning) == 1, "one small call for the account, however many tiers use it"
    assert learning[0].size < 3000 and learning[0].kind == learn.TASK
    assert store.read().list("lesson") == [], "the check applies nothing"


@pytest.mark.parametrize(
    ("answer", "part"),
    [
        ("not json at all", "couldn't be read"),
        (json.dumps({"summary": "None.", "ops": []}), "gave none"),
        (
            json.dumps({"summary": "Two.", "ops": [{"op": "lesson.add", "text": "One."}] * 2}),
            "gave 2",
        ),
        (json.dumps({"summary": "A note.", "ops": [{"op": "note", "text": "Not a proposal."}]}), "isn't something"),
        (
            json.dumps(
                {
                    "summary": "A lesson.",
                    "ops": [{"op": "lesson.add", "text": "One.", "applies_to": {"projects": ["PRJ-0"]}}],
                }
            ),
            "app's own checks",
        ),
    ],
)
def test_the_learning_round_trip_fails_saying_which_part_failed(env, answer, part):
    _, cfg, store = env
    set_responder(lambda task: answer if task.request == CHECK_REQUEST else '{"ok": true}')
    (found,) = learning_results(smoke_test(cfg, {}, store=store))
    assert not found.ok and part in found.detail, found.detail


def test_the_learning_round_trip_passes_when_the_answer_fills_the_correction_it_came_from(env):
    """A real learning run ties the lesson to its correction whatever the answer says there, so the check does too."""
    _, cfg, store = env
    lesson = {"op": "lesson.add", "text": "Delivery dates are asked of the delivery's owner.", "signal": CHECK_REQUEST}
    answer = json.dumps({"summary": "A lesson.", "ops": [lesson]})
    set_responder(lambda task: answer if task.request == CHECK_REQUEST else connection_answer(task))
    (found,) = learning_results(smoke_test(cfg, {}, store=store))
    assert found.ok, found.detail


def test_a_failing_learning_round_trip_stops_the_account_from_counting_as_checked(env):
    ws, _, store = env
    add_account(ws, "second")
    cfg = ws.config(env={})
    set_responder(lambda task: json.dumps({"summary": "None.", "ops": []}) if task.request == CHECK_REQUEST else "{}")
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    assert not is_checked(ws, cfg, "second/default", "routine")


def test_a_command_line_agent_account_takes_the_learning_round_trip_too(env, tmp_path):
    ws, cfg, store = env
    answer = {"summary": "A lesson.", "ops": [{"op": "lesson.add", "text": "Ask whoever owns it."}]}
    script = tmp_path / "agent.py"
    script.write_text(
        "import re, sys\n"
        "prompt = sys.stdin.read()\n"
        "path = re.findall(r'(/\\S+?answer\\.json)', prompt)[-1]\n"
        f"open(path, 'w').write({json.dumps(json.dumps(answer))})\n"
    )
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"]["agent"] = {
        "adapter": "cli-agent",
        "models": {"default": "agent-model"},
        "allowed_data": ["open", "internal", "restricted"],
        "timeout_seconds": 10,
        "agent": {"command": [sys.executable, str(script)], "output_via": "outbox"},
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    agent_cfg = ws.config(env={})
    found = learning_results(account_test(agent_cfg, {}, "agent", store=store))
    assert [(r.ref, r.ok) for r in found] == [("agent/default", True)], [r.detail for r in found]
