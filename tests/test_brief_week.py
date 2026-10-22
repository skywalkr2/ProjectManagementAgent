"""The week's plan (design 6.32, the Monday briefing): the goals the person confirms and the message to whoever they
report to. Goals are the person's own words, between the fewest and the most the settings say, kept for the week with
Undo. The message is one request of a draft kind: estimated and held for the go like any other, filed as a pending
draft of the week's text, never sent, and copying it makes it the person's. Names and ids come from the fixtures; the
AI is the stub."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import packet as packets
from engine import week_plan
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import apply_as_person
from engine.config.schema import Price
from engine.dispatcher import process
from engine.storage import Store, StoreError, WriteContext
from engine.tasks import task_kind
from engine.texts import read_text, versions
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, without_first_go

# A Monday afternoon on the person's clock (UTC here); the week runs Monday to Friday.
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_PM = WriteContext("pm", "trusted", "test.week")
TOKEN = "week-plan-token"
GOALS = ["Ship the proof", "Close the print order", "Plan the launch"]
DRAFT = "Hello,\n\nThe proof shipped. The print order closes Thursday.\n\nThank you.\n"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def me(cfg) -> str:
    return cfg.workspace.user.person


def boss(store, name="Lena Fictional") -> str:
    with store.transaction() as tx:
        return tx.create("person", {"full_name": name, "stance": "report_to"}, _PM).id


def plans(store) -> list:
    return store.read().list("week_plan")


# ---- the goals ------------------------------------------------------------------------------------------------------


def test_the_week_is_the_one_that_ends_on_the_last_working_day(env):
    _, cfg, _ = env
    assert week_plan.week_bounds(cfg, TODAY) == (TODAY, TODAY + timedelta(days=4))
    assert week_plan.week_bounds(cfg, TODAY + timedelta(days=4)) == (TODAY, TODAY + timedelta(days=4))
    # After the last working day the next week is the one that counts.
    saturday = TODAY + timedelta(days=5)
    assert week_plan.week_bounds(cfg, saturday) == (TODAY + timedelta(days=7), TODAY + timedelta(days=11))


def test_confirming_goals_keeps_them_for_the_week_as_the_persons_own_and_says_what_they_replaced(env):
    _, cfg, store = env
    assert week_plan.set_goals(store, cfg, [f"  {g}  " for g in GOALS], NOW) == []
    (plan,) = plans(store)
    assert plan.data["goals"] == GOALS and plan.data["person"] == me(cfg) and plan.data["week"] == TODAY.isoformat()
    assert plan.data["confirmed_at"]
    ledger = [r for r in store.read().ledger(kind="week_plan") if r["field"] == "goals"]
    assert {r["actor"] for r in ledger} == {"pm"}
    again = ["Ship the proof", "Plan the launch", "Print the flyers", "Call the venue"]
    assert week_plan.set_goals(store, cfg, again, NOW) == GOALS  # what Undo sends back
    assert len(plans(store)) == 1 and plans(store)[0].data["goals"] == again


def test_a_later_day_of_the_same_week_confirms_on_the_same_record(env):
    _, cfg, store = env
    week_plan.set_goals(store, cfg, GOALS, NOW)
    week_plan.set_goals(store, cfg, GOALS[::-1], NOW + timedelta(days=2))
    assert len(plans(store)) == 1 and plans(store)[0].data["goals"] == GOALS[::-1]
    week_plan.set_goals(store, cfg, GOALS, NOW + timedelta(days=7))
    assert len(plans(store)) == 2  # the next week is its own record


def test_fewer_goals_than_the_fewest_or_more_than_the_most_are_refused_with_the_reason(env):
    _, cfg, store = env
    rule = cfg.steward.brief
    with pytest.raises(week_plan.GoalsError, match=str(rule.goals_min)):
        week_plan.set_goals(store, cfg, GOALS[: rule.goals_min - 1], NOW)
    with pytest.raises(week_plan.GoalsError, match=str(rule.goals_max)):
        week_plan.set_goals(store, cfg, [f"Goal {n}" for n in range(rule.goals_max + 1)], NOW)
    assert plans(store) == []


def test_blank_and_repeated_goals_are_left_out_before_they_are_counted(env):
    _, cfg, store = env
    with pytest.raises(week_plan.GoalsError):
        week_plan.set_goals(store, cfg, [GOALS[0], "  ", GOALS[0].upper()], NOW)
    week_plan.set_goals(store, cfg, [*GOALS, "", GOALS[1].lower()], NOW)
    assert plans(store)[0].data["goals"] == GOALS


def test_a_long_goal_is_cut_at_a_word_and_none_takes_the_goals_back_out(env):
    _, cfg, store = env
    long = " ".join(["word"] * 80)
    week_plan.set_goals(store, cfg, [long, *GOALS[:2]], NOW)
    assert len(plans(store)[0].data["goals"][0]) <= week_plan.GOAL_LIMIT
    assert week_plan.set_goals(store, cfg, [], NOW)[1:] == GOALS[:2]
    assert plans(store)[0].data["goals"] == [] and plans(store)[0].data["confirmed_at"] is None
    assert week_plan.goals_of(store.read(), me(cfg), TODAY) == []


# ---- who the message is for ----------------------------------------------------------------------------------------


def test_the_message_is_for_the_people_the_person_reports_to_and_nobody_else(env):
    _, cfg, store = env
    assert week_plan.report_to(store.read(), cfg) == []
    first = boss(store, "Lena Fictional")
    with store.transaction() as tx:
        tx.create("person", {"full_name": "Pat Fictional", "stance": "manage"}, _PM)
    second = boss(store, "Avi Fictional")
    assert week_plan.report_to(store.read(), cfg) == [second, first]  # by name


def test_asking_for_the_message_with_nobody_to_report_to_is_refused_and_makes_nothing(env):
    _, cfg, store = env
    with pytest.raises(StoreError, match="report to"):
        week_plan.ask_for_message(store, cfg, NOW)
    assert plans(store) == [] and [r for r in store.read().list("request") if r.data["task"] == week_plan.TASK] == []


def test_asking_queues_one_request_about_the_weeks_record_and_changes_nothing_else(env):
    _, cfg, store = env
    boss(store)
    request = week_plan.ask_for_message(store, cfg, NOW, note="  Keep it short.  ")
    (plan,) = plans(store)
    queued = store.read().get("request", request).data
    assert queued["about"] == {"kind": "week_plan", "id": plan.id} and queued["note"] == "Keep it short."
    assert (queued["origin"], queued["state"], queued["task"]) == ("pm", "queued", week_plan.TASK)
    assert plan.data["goals"] == [] and plan.data.get("message") is None
    with pytest.raises(StoreError, match="already"):
        week_plan.ask_for_message(store, cfg, NOW)


# ---- the kind and its packet ---------------------------------------------------------------------------------------


def test_the_kind_is_a_draft_on_the_weeks_message_text_started_by_the_person(env):
    kind = task_kind(week_plan.TASK)
    assert (kind.output, kind.on, kind.field, kind.ops) == ("draft", "week_plan", "message", ("text.draft",))


def test_the_packet_has_the_weeks_facts_marked_as_data_after_the_stable_parts(env):
    ws, cfg, store = env
    boss(store, "Lena Fictional")
    mine = "Send the proof pages"
    with store.transaction() as tx:
        tx.create(
            "action",
            {"text": mine, "owners": [{"person": me(cfg)}], "due": (TODAY + timedelta(days=2)).isoformat()},
            _PM,
        )
    week_plan.set_goals(store, cfg, GOALS, NOW)
    request = week_plan.ask_for_message(store, cfg, NOW, note="Keep it to three lines.")
    built = packets.build(ws, store, cfg, request, TODAY)
    text = built.task.request
    assert built.task.kind == week_plan.TASK and built.task.output == "text"
    assert built.about[0] == "week_plan" and built.untrusted_material and built.draft_base is None
    assert mine in text and all(goal in text for goal in GOALS) and "Lena Fictional" in text
    assert "Keep it to three lines." in text and text.count("<untrusted") >= 1
    assert "<untrusted" not in built.task.stable and built.task.instructions.startswith("You are")
    assert built.knowledge is not None


def test_a_packet_for_a_week_with_nobody_to_report_to_is_refused(env):
    ws, cfg, store = env
    someone = boss(store)
    request = week_plan.ask_for_message(store, cfg, NOW)
    with store.transaction() as tx:
        found = tx.get("person", someone)
        tx.update("person", someone, {"stance": "alongside"}, _PM, read_version=found.version)
    with pytest.raises(packets.PacketRefused, match="reports to"):
        packets.build(ws, store, cfg, request, TODAY)


# ---- the run, the draft and Copy ------------------------------------------------------------------------------------


def run(env, request_id: str):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def drafted(env, text: str = DRAFT):
    _, cfg, store = env
    boss(store)
    asked: list = []
    set_responder(lambda task: asked.append(task) or text)
    request = week_plan.ask_for_message(store, cfg, NOW)
    run(env, request)
    return request, asked


def test_a_run_files_a_pending_draft_and_the_state_says_a_draft_waits_with_its_words(env):
    _, cfg, store = env
    request, asked = drafted(env)
    (plan,) = plans(store)
    (draft,) = versions(store.read(), "week_plan", plan.id, "message")
    assert (draft.data["status"], draft.data["source"]) == ("pending", "draft")
    assert plan.data.get("message") is None  # nothing is the person's text until they copy it
    message = week_plan.message_of(store.read(), cfg, store, NOW)
    assert (message.state, message.draft, message.text.strip()) == ("draft", draft.id, DRAFT.strip())
    assert message.to and asked and asked[0].kind == week_plan.TASK
    assert store.read().get("request", request).data["state"] == "review"
    assert store.read().list("run")[-1].data["knowledge"]  # the knowledge log, like every kind


def test_the_run_is_estimated_and_waits_for_the_go_above_the_amount_to_confirm(env):
    ws, cfg, store = env
    use = cfg.ai.tiers["routine"].use
    cfg.ai.prices[use] = Price(input_per_million=500_000.0, output_per_million=500_000.0)
    cfg.ai.budgets.per_run_usd = 1000.0
    cfg.ai.budgets.confirm_above_usd = 0.0
    boss(store)
    asked: list = []
    set_responder(lambda task: asked.append(task) or DRAFT)
    request = week_plan.ask_for_message(store, cfg, NOW)
    assert week_plan.message_of(store.read(), cfg, store, NOW).state == "working"
    run(env, request)
    held = store.read().get("request", request).data
    assert (held["state"], held["approval"]) == ("needs_you", "required") and held["estimate_usd"] > 0
    assert asked == []
    message = week_plan.message_of(store.read(), cfg, store, NOW)
    assert (message.state, message.estimate_usd) == ("needs_go", held["estimate_usd"])


def test_copying_the_message_makes_the_draft_the_persons_and_the_state_says_kept(env):
    _, cfg, store = env
    drafted(env)
    assert week_plan.copied(store, cfg, NOW) is True
    (plan,) = plans(store)
    assert read_text(store, plan.data["message"]).strip() == DRAFT.strip()
    message = week_plan.message_of(store.read(), cfg, store, NOW)
    assert (message.state, message.text.strip()) == ("kept", DRAFT.strip())
    assert week_plan.copied(store, cfg, NOW) is False  # nothing is waiting any more
    assert store.read().list("signal") == []  # copying as it is corrects nothing


def test_setting_the_draft_aside_is_a_signal_and_the_message_can_be_asked_for_again(env):
    _, cfg, store = env
    drafted(env)
    (plan,) = plans(store)
    (draft,) = versions(store.read(), "week_plan", plan.id, "message")
    found = store.read().get("text_version", draft.id)
    apply_as_person(
        store, cfg, [{"op": "text.discard", "version": draft.id, "read_version": found.version}], "Set aside"
    )
    (signal,) = store.read().list("signal")
    assert signal.data["kind"] == "dropped" and signal.data["refs"] == [plan.id]
    assert week_plan.message_of(store.read(), cfg, store, NOW).state == "none"
    week_plan.ask_for_message(store, cfg, NOW)


def test_a_draft_waiting_is_not_asked_for_again(env):
    _, cfg, store = env
    drafted(env)
    with pytest.raises(StoreError, match="already"):
        week_plan.ask_for_message(store, cfg, NOW)


# ---- the routes ---------------------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={}, flags={"server.base_path": "/"})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as http:
        yield http, app.state.store, ws
    set_responder(None)


def test_the_goal_route_confirms_answers_with_what_it_replaced_and_explains_a_refusal(client):
    http, store, _ = client
    first = http.put("/api/brief/goals", json={"goals": GOALS})
    assert first.status_code == 200 and first.json() == {"previous": []}
    second = http.put("/api/brief/goals", json={"goals": GOALS[::-1]})
    assert second.json() == {"previous": GOALS}
    refused = http.put("/api/brief/goals", json={"goals": GOALS[:1]})
    assert refused.status_code == 422 and "at least" in refused.json()["detail"]
    undone = http.put("/api/brief/goals", json={"goals": second.json()["previous"]})
    assert undone.json() == {"previous": GOALS[::-1]}


def test_the_brief_route_names_the_form_the_goals_and_the_message_state(client):
    http, store, ws = client
    monday = http.get("/api/brief", params={"form": "monday"})
    assert monday.status_code == 200
    body = monday.json()
    assert body["form"] == "monday" and body["goals"]["confirmed"] is False and body["message"] is None
    morning = http.get("/api/brief", params={"form": "morning"}).json()
    assert morning["form"] == "morning" and morning["goals"] is None
    assert http.get("/api/brief", params={"form": "noon"}).status_code == 422
    with store.transaction() as tx:
        tx.create("person", {"full_name": "Lena Fictional", "stance": "report_to"}, _PM)
    asked = http.post("/api/brief/message", json={"note": "Short."})
    assert asked.status_code == 200 and asked.json()["request"]
    again = http.post("/api/brief/message", json={})
    assert again.status_code == 409
    body = http.get("/api/brief", params={"form": "monday"}).json()
    assert (
        body["message"]["state"] in ("working", "needs_go", "draft")
        and body["message"]["to"][0]["name"] == "Lena Fictional"
    )


def test_copying_with_no_message_waiting_is_refused(client):
    http, _, _ = client
    assert http.post("/api/brief/message/copied").status_code == 409


def test_asking_for_a_message_with_nobody_to_report_to_is_refused_on_the_route(client):
    http, _, _ = client
    assert http.post("/api/brief/message", json={}).status_code == 409
