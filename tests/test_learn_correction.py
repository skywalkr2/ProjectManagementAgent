"""Learning from corrections (design 6.22, phase L3a): a correction queues one learning request, at once when the
person wrote something and with the next batch when it was silent; the packet shows what was corrected; at most one
proposal comes out, and it waits for Keep. Names and ids come from the fixtures; the AI is the stub.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta

import pytest
import yaml

from engine import learn
from engine import packet as packets
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, apply_changeset, pick_owner
from engine.dispatcher import process, send_back, signal, undo_changeset
from engine.followups import mark_sent, sections, unmark_sent
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.tasks import settings as task_settings
from engine.tasks import task_kind
from engine.worker import Events, Worker
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records, without_first_go

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.learn")
NOTHING = {"summary": "Nothing to generalize.", "topic": "", "ops": []}


def person(role: str) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def scripted(*bodies: dict) -> list:
    """Make the stub answer with these answers in turn (the last repeats), and record what it was asked."""
    asked: list = []
    queue = [json.dumps(b) for b in bodies]

    def responder(task):
        asked.append(task)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    set_responder(responder)
    return asked


def read(env, pasted: str, answer: dict, *, at: datetime = NOW) -> tuple:
    """Hand something in and let the assistant read it with this answer. Returns the hand-in and its changeset."""
    ws, cfg, store = env
    scripted(answer)
    handed = hand_in(ws, store, pasted=pasted, now=at)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=at)
    set_responder(None)
    return handed, cs_id


def interior(env) -> tuple[str, str, str]:
    """An original run that made one action for a teammate. Returns its changeset, the action and the input."""
    setter = person("Editor")
    words = f"{setter['full_name']} will send the final interior file to the printer by the 16th."
    _, cs_id = read(
        env,
        f"Interior: {words}",
        {
            "summary": "One action.",
            "ops": [
                {
                    "op": "action.add",
                    "text": "Send the final interior file to the printer",
                    "owners": [setter["full_name"]],
                    "due": "2026-10-16",
                    "project": "PRJ-1",
                    "evidence": {"quote": "will send the final interior file to the printer by the 16th"},
                }
            ],
        },
    )
    action = env[2].read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]
    return cs_id, action, words


def learning(store) -> list:
    return [r for r in store.read().list("request") if r.data["task"] == learn.TASK]


def run_learning(env, request_id: str, *, at: datetime = NOW):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=at)


def lesson_answer(quote: str, **more) -> dict:
    return {
        "summary": "A lesson.",
        "topic": "interior files",
        "ops": [
            {
                "op": "lesson.add",
                "text": "Interior files go to the editor before the printer.",
                "guard": "Name the editor as the first recipient of interior files.",
                "evidence": {"quote": quote},
                **more,
            }
        ],
    }


def ops_of(store, request_id: str) -> list[dict]:
    return store.read().get("changeset", store.read().get("request", request_id).data["changeset"]).data["ops"]


def test_a_lesson_whose_answer_fills_the_signal_itself_is_tied_to_the_real_correction_with_no_fix_round(env):
    """The correction a lesson comes from is the app's to say: whatever the answer writes there is replaced before the
    answer is checked, so a model that fills it in is neither sent back nor refused."""
    _, _, store = env
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "Interior files go to the editor first.", now=NOW)
    (made,) = store.read().list("signal")
    (queued,) = learning(store)
    asked = scripted(lesson_answer("go to the editor first", signal="Interior files go to the editor first."))
    run_learning(env, queued.id)
    assert len(asked) == 1, "no fix round"
    (lesson,) = store.read().list("lesson")
    assert lesson.data["signal"] == made.id


# ---- when it runs ----------------------------------------------------------------------------------------------------


def test_a_send_back_with_a_note_queues_one_learning_request_at_once_and_its_proposal_waits_for_keep(env):
    ws, cfg, store = env
    cs_id, _, _ = interior(env)
    note = "Interior files go to the editor first."
    send_back(store, cs_id, note, now=NOW)
    (made,) = store.read().list("signal")
    (queued,) = learning(store)
    assert queued.data["about"] == {"kind": "signal", "id": made.id}
    assert queued.data["state"] == "queued" and queued.data["origin"] == "schedule"
    assert not queued.data.get("cause"), "a correction the person wrote is not batched"
    scripted(lesson_answer("go to the editor first"))
    run_learning(env, queued.id)
    (lesson,) = store.read().list("lesson")
    assert lesson.data["status"] == "proposed" and lesson.data["origin"] == "assistant"
    assert lesson.data["kept_by"] is None and lesson.data["signal"] == made.id
    assert lesson.data["evidence"]["quote"] == "go to the editor first"
    assert lesson.data["evidence"]["signal"] == made.id and lesson.data["evidence"]["changeset"] == cs_id
    assert store.read().get("request", queued.id).data["state"] == "done", "the run itself needs no review"
    (learned_run,) = [r for r in store.read().list("run") if r.data["task"] == learn.TASK]
    assert learned_run.data["tier"] == task_settings(cfg, task_kind(learn.TASK)).tier == "deep"


def test_picking_an_owner_queues_learning_at_once_and_a_routing_proposal_can_quote_the_input(env):
    ws, cfg, store = env
    words = "Launch: someone should book a photographer."
    _, cs_id = read(
        env,
        words,
        {"ops": [{"op": "action.add", "text": "Book a photographer", "evidence": {"quote": "book a photographer"}}]},
    )
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    chosen = person("Publicist")["id"]
    pick_owner(store, outcome["question"], chosen)
    (queued,) = learning(store)
    assert store.read().get("signal", queued.data["about"]["id"]).data["kind"] == "routed"
    assert queued.data["state"] == "queued" and not queued.data.get("cause")
    scripted(
        {
            "summary": "Who books photographers.",
            "topic": "photography",
            "ops": [
                {
                    "op": "routing.add",
                    "text": "Photography work goes to the publicist.",
                    "topic": "photography",
                    "person": chosen,
                    "evidence": {"quote": "someone should book a photographer"},
                }
            ],
        }
    )
    run_learning(env, queued.id)
    (entry,) = store.read().list("routing_entry")
    assert entry.data["status"] == "proposed" and entry.data["person"] == chosen


def test_silent_corrections_wait_for_the_next_batch_and_run_together(env):
    ws, cfg, store = env
    cs_id, _, _ = interior(env)
    undo_changeset(store, cs_id)
    signal(store, "pulled_back", [cs_id], note="Closed by a rule", changeset=cs_id)
    first, second = learning(store)
    cause = first.data["cause"]
    until = datetime.fromisoformat(cause["until"])
    assert cause["kind"] == "retry" and "next batch" in first.data["waiting"]
    assert second.data["cause"]["until"] == cause["until"], "corrections in one window share one batch"
    clock = [until - timedelta(minutes=1)]
    worker = Worker(ws, store, cfg, Events(), router_factory=lambda: Router(cfg, store, env={}), now=lambda: clock[0])
    assert worker.run_pending() == 0, "nothing is learned from a silent correction before its batch"
    assert {r.data["state"] for r in learning(store)} == {"queued"}
    clock[0] = until
    assert worker.run_pending() == 2
    assert {r.data["state"] for r in learning(store)} == {"done"}


def test_learning_offers_the_knowledge_ops_a_lesson_change_and_a_rule_but_never_a_report_and_takes_settings_at_once():
    from engine.worker import is_live

    ops = set(task_kind(learn.TASK).ops)
    assert ops == {"lesson.add", "lesson.update", "glossary.add", "routing.add", "style.add", "rule.add"}
    assert task_kind(learn.TASK).max_ops == 1
    assert is_live("dispatch.knowledge.learn") and is_live("dispatch.knowledge.learn_every_minutes")


def test_the_next_batch_is_the_next_multiple_of_the_setting_since_midnight():
    assert learn.next_batch(datetime(2026, 10, 9, 14, 0, tzinfo=UTC), 30) == datetime(2026, 10, 9, 14, 30, tzinfo=UTC)
    assert learn.next_batch(datetime(2026, 10, 9, 14, 29, 59, tzinfo=UTC), 30) == datetime(
        2026, 10, 9, 14, 30, tzinfo=UTC
    )
    assert learn.next_batch(datetime(2026, 10, 9, 23, 50, tzinfo=UTC), 30) == datetime(2026, 10, 10, 0, 0, tzinfo=UTC)


def test_learning_off_queues_no_request_and_one_queued_before_it_was_switched_off_closes_without_a_call(env):
    ws, cfg, store = env
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "Interior files go to the editor first.", now=NOW)
    (queued,) = learning(store)
    for found in (cfg, store.plugins.cfg):
        found.dispatch.knowledge.learn = False
    asked = scripted(lesson_answer("go to the editor first"))
    run_learning(env, queued.id)
    closed = store.read().get("request", queued.id).data
    assert closed["state"] == "done" and "switched off" in closed["waiting"] and asked == []
    signal(store, "undone", [cs_id], note="ops [0]", changeset=cs_id)
    assert len(learning(store)) == 1, "no new request while learning is off"


def test_mail_set_aside_as_not_work_is_never_learned_from(env):
    _, _, store = env
    with store.transaction() as tx:
        aside = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "input",
                "state": "done",
                "created_at": NOW.isoformat(),
                "set_aside": {"section": "personal"},
            },
            _TEST,
        ).id
    signal(store, "pulled_back", [aside], note="Set aside: personal", now=NOW)
    assert learning(store) == []


# ---- netting ---------------------------------------------------------------------------------------------------------


def test_a_message_the_person_took_back_within_its_undo_time_teaches_nothing(env):
    ws, cfg, store = env
    editor = person("Editor")
    sec = next(s for s in sections(store, cfg, NOW.date()) if s.person == editor["id"])
    counts = mark_sent(store, cfg, editor["id"], sent_text=sec.message + "\nP.S. one more thing", now=NOW)
    (queued,) = learning(store)
    assert queued.data["state"] == "queued"
    unmark_sent(store, editor["id"], counts["question_ids"], counts["action_ids"])
    closed = store.read().get("request", queued.id).data
    assert closed["state"] == "done" and closed["waiting"] == learn.NETTED_WAITING
    assert len(store.read().list("signal")) == 1, "the signal itself stays"
    asked = scripted(lesson_answer("one more thing"))
    assert run_learning(env, queued.id) is None and asked == []


def test_learning_that_already_ran_is_undone_when_its_correction_is_netted(env):
    ws, cfg, store = env
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "Interior files go to the editor first.", now=NOW)
    (queued,) = learning(store)
    scripted(lesson_answer("go to the editor first"))
    run_learning(env, queued.id)
    assert len(store.read().list("lesson")) == 1
    assert learn.net_out(store, "sent_back", [cs_id]) == [queued.id]
    assert store.read().list("lesson") == []
    assert store.read().get("request", queued.id).data["waiting"] == learn.NETTED_WAITING
    assert len(store.read().list("signal")) == 1
    assert learn.net_out(store, "sent_back", [cs_id]) == [queued.id], "netting again changes nothing more"


# ---- what comes out --------------------------------------------------------------------------------------------------


def test_nothing_to_generalize_makes_no_knowledge(env):
    ws, cfg, store = env
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "Typo in the title.", now=NOW)
    (queued,) = learning(store)
    before = {k: len(store.read().list(k)) for k in ("lesson", "glossary_entry", "routing_entry", "style_note", "rule")}
    scripted(NOTHING)
    run_learning(env, queued.id)
    after = {k: len(store.read().list(k)) for k in before}
    assert after == before
    assert ops_of(store, queued.id) == [] and store.read().get("request", queued.id).data["state"] == "done"


def test_more_than_one_proposal_refuses_the_whole_answer_and_asks_for_one(env):
    ws, cfg, store = env
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "Interior files go to the editor first.", now=NOW)
    (queued,) = learning(store)
    two = lesson_answer("go to the editor first")
    two["ops"].append({**two["ops"][0], "text": "Another thing entirely."})
    asked = scripted(two)
    run_learning(env, queued.id)
    assert len(asked) == 2 and "at most 1" in asked[1].request, "the answer went back once to be cut to one"
    outcomes = ops_of(store, queued.id)
    assert [o["status"] for o in outcomes] == ["refused", "refused"]
    assert all("at most 1" in o["reason"] for o in outcomes)
    assert store.read().list("lesson") == []


def test_a_lesson_naming_kinds_of_work_must_include_the_one_corrected_and_the_packet_says_which_it_was(env):
    ws, cfg, store = env
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "Interior files go to the editor first.", now=NOW)
    (queued,) = learning(store)
    elsewhere = lesson_answer("go to the editor first", applies_to={"task_kinds": ["ask"]})
    right = lesson_answer("go to the editor first", applies_to={"task_kinds": ["notes", "ask"]})
    asked = scripted(elsewhere, right)
    run_learning(env, queued.id)
    assert 'The work corrected is the kind of work "notes"' in asked[0].request
    assert len(asked) == 2 and 'must include "notes"' in asked[1].request, "the answer went back once"
    (lesson,) = store.read().list("lesson")
    assert lesson.data["applies_to"]["task_kinds"] == ["notes", "ask"]


def test_a_lesson_change_from_learning_is_held_and_a_rule_from_learning_is_a_proposal(env):
    ws, cfg, store = env
    with store.transaction() as tx:
        active = tx.create(
            "lesson",
            {
                "text": "Send interior files to the printer.",
                "origin": "person",
                "learned_at": NOW.isoformat(),
                "status": "active",
                "kept_by": cfg.workspace.user.person,
                "kept_at": NOW.isoformat(),
            },
            _TEST,
        ).id
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "From now on interior files go to the editor first.", now=NOW)
    (queued,) = learning(store)
    rules = len(store.read().list("rule"))
    scripted(
        {
            "summary": "Fix the lesson.",
            "ops": [
                {
                    "op": "lesson.update",
                    "id": active,
                    "text": "Send interior files to the editor, then the printer.",
                }
            ],
        }
    )
    run_learning(env, queued.id)
    (held,) = ops_of(store, queued.id)
    assert held["status"] == "held"
    assert store.read().get("lesson", active).data["text"] == "Send interior files to the printer."
    assert store.read().get("request", queued.id).data["state"] == "review", "a held change stays on Today"
    signal(store, "sent_back", [cs_id], note="Never send them straight to the printer.", changeset=cs_id, now=NOW)
    (_, second) = learning(store)
    scripted({"summary": "A rule.", "ops": [{"op": "rule.add", "text": "Interior files go to the editor first."}]})
    run_learning(env, second.id)
    (proposed_rule,) = ops_of(store, second.id)
    made = [r for r in store.read().list("rule") if r.data["text"] == "Interior files go to the editor first."]
    assert proposed_rule["status"] == "applied" and len(store.read().list("rule")) == rules + 1
    assert [r.data["status"] for r in made] == ["proposed"], "a rule from learning waits for Keep"


# ---- the packet ------------------------------------------------------------------------------------------------------


def test_the_packet_holds_the_original_output_the_correction_and_the_given_knowledge_and_the_run_logs_it(env):
    ws, cfg, store = env
    with store.transaction() as tx:
        lesson = tx.create(
            "lesson",
            {
                "text": "Send interior files to the printer.",
                "origin": "person",
                "learned_at": NOW.isoformat(),
                "status": "active",
                "kept_by": cfg.workspace.user.person,
                "kept_at": NOW.isoformat(),
            },
            _TEST,
        ).id
    cs_id, action, words = interior(env)
    (original_run,) = store.read().list("run")
    assert lesson in original_run.data["knowledge"]["given"]
    note = "Interior files go to the editor first."
    send_back(store, cs_id, note, now=NOW)
    (queued,) = learning(store)
    made = packets.build(ws, store, cfg, queued.id, NOW.date())
    stable, request = made.task.stable, made.task.request
    assert "Send interior files to the printer." in stable and "# Lessons" in stable, "stable: the active lessons"
    assert f"<note>\n{note}\n</note>" in request, "the person's own words"
    assert "Send the final interior file to the printer" in request, "the original output"
    assert request.index("# What the assistant had been given") < request.index("# The input the assistant read")
    given = request.split("# What the assistant had been given")[1].split("# The input")[0]
    assert f"- {lesson}: Send interior files to the printer." in given
    assert words in request.split("# The input the assistant read")[1] and '<untrusted source="' in request
    assert action in request.split("# What the assistant did")[0], "the item as it is now"
    assert made.knowledge.given == [lesson] and made.untrusted_material
    scripted(NOTHING)
    run_learning(env, queued.id)
    (learned_run,) = [r for r in store.read().list("run") if r.data["task"] == learn.TASK]
    assert learned_run.data["knowledge"]["given"] == [lesson]
    assert learned_run.data["knowledge"]["stable_chars"] > 0


def test_a_silent_corrections_packet_holds_the_inputs_that_arrived_after_the_original_run(env):
    ws, cfg, store = env
    cs_id, action, words = interior(env)
    moved = "The printer moved the interior deadline to the 23rd."
    read(
        env,
        moved,
        {
            "ops": [
                {
                    "op": "record.set",
                    "kind": "action",
                    "id": action,
                    "field": "due",
                    "value": "2026-10-23",
                    "evidence": {"quote": "moved the interior deadline to the 23rd"},
                }
            ]
        },
        at=NOW + timedelta(hours=1),
    )
    elsewhere = "The launch party venue is booked."
    read(env, elsewhere, {"ops": [{"op": "note", "text": "Venue booked."}]}, at=NOW + timedelta(hours=2))
    signal(store, "undone", [cs_id], note="ops [0]", changeset=cs_id, now=NOW + timedelta(hours=3))
    (queued,) = learning(store)
    request = packets.build(ws, store, cfg, queued.id, NOW.date()).task.request
    later = request.split("# Inputs that arrived after that work")[1]
    assert moved in later and '<untrusted source="' in later, "an input about the same item, marked as outside"
    assert elsewhere not in later and words not in later, "not one about other items, and not the input itself"
    cfg.dispatch.knowledge.learn_later_inputs = 0
    none = packets.build(ws, store, cfg, queued.id, NOW.date()).task.request
    assert none.split("# Inputs that arrived after that work")[1].strip().endswith("None.")


# ---- a report that is a rule -----------------------------------------------------------------------------------------


def _apply(store, cfg, ops):
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create(
            "request", {"task": "ask", "origin": "pm", "state": "done", "created_at": NOW.isoformat()}, _TEST
        ).id
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request, None, "", "", "trusted"),
        actor="assistant",
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return store.read().get("changeset", cs_id).data["ops"]


def test_a_report_to_the_maintainers_whose_content_is_a_rule_is_refused_and_a_real_one_is_not(env):
    _, cfg, store = env
    rule = {
        "op": "report.draft",
        "title": "Questions to other teams",
        "text": "From now on, rows scoped to another team should get no impact question unless they name our work.",
    }
    (refused,) = _apply(store, cfg, [rule])
    assert refused["status"] == "refused" and "propose it as a rule" in refused["reason"]
    assert store.read().list("report") == []
    real = {"op": "report.draft", "title": "No export", "text": "The person wanted a yearly summary file; none exists."}
    (kept,) = _apply(store, cfg, [real])
    assert kept["status"] == "applied" and len(store.read().list("report")) == 1


# ---- account independence --------------------------------------------------------------------------------------------


def test_the_learning_proposal_applies_on_a_command_line_agent_account(env, tmp_path):
    ws, cfg, store = env
    without_first_go(ws.config_dir)
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, "Interior files go to the editor first.", now=NOW)
    (queued,) = learning(store)
    answer = lesson_answer("go to the editor first")
    script = tmp_path / "agent.py"
    script.write_text(
        "import re, sys\n"
        "prompt = sys.stdin.read()\n"
        "path = re.findall(r'(/\\S+?answer\\.json)', prompt)[-1]\n"
        f"open(path, 'w').write({json.dumps(answer)!r})\n"
    )
    path = ws.config_dir / "ai.yaml"
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    settings["providers"] = {
        "agent": {
            "adapter": "cli-agent",
            "models": {"default": "agent-model"},
            "allowed_data": ["open", "internal", "restricted"],
            "timeout_seconds": 10,
            "agent": {"command": [sys.executable, str(script)], "output_via": "outbox"},
        }
    }
    settings["tiers"] = {tier: {"use": "agent/default", "fallback": []} for tier in ("routine", "deep")}
    path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    agent_cfg = ws.config(env={})
    process(ws, store, agent_cfg, Router(agent_cfg, store, env={}), queued.id, now=NOW)
    (lesson,) = store.read().list("lesson")
    assert lesson.data["status"] == "proposed" and lesson.data["signal"] == store.read().list("signal")[0].id
    assert [r.data["provider"] for r in store.read().list("run") if r.data["task"] == learn.TASK] == ["agent"]
