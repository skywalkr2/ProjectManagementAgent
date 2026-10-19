"""The scope slice (design 6.18): a person's part in each project (run, design or watch), facts only on a project they
watch, and another team's item as a fact unless the words it quotes show the person owes it something.

Names, ids and teams come from the fictional workspace's records; the one project it has the person watching is found
by its role.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, apply_as_person, apply_changeset, check, release
from engine.dispatcher import process, undo_changeset
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET
from engine.scope import role_of
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, fixture_records, without_first_go
from tests.test_knowledge_records import apply, request, source

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.scope")
PEOPLE = fixture_records(DEMO_A, "person")
PROJECTS = fixture_records(DEMO_A, "project")
TEAMS = fixture_records(DEMO_A, "team")
WATCHED = next(p["id"] for p in PROJECTS if p.get("roles"))
PLAIN = next(p["id"] for p in PROJECTS if not p.get("roles"))
LINK = next(p for p in PROJECTS if p.get("links"))["links"][0]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_A, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def pm_of(cfg) -> str:
    return cfg.workspace.user.person


def pm_record(cfg) -> dict:
    return next(p for p in PEOPLE if p["id"] == pm_of(cfg))


def teammate(cfg) -> dict:
    mine = pm_record(cfg)["team"]
    return next(p for p in PEOPLE if p["team"] == mine and p["id"] != pm_of(cfg))


def outsider(cfg, *, skip: tuple[str, ...] = ()) -> dict:
    mine = pm_record(cfg)["team"]
    return next(p for p in PEOPLE if p.get("team") != mine and p["id"] not in skip)


def team_name(cfg) -> str:
    return next(t["name"] for t in TEAMS if t["id"] == pm_record(cfg)["team"])


PLAN_ACTION = "Send the revised plan"


def action(cfg, who, quote, project=None, **more):
    return {
        "op": "action.add",
        "text": PLAN_ACTION,
        "owners": [who["full_name"]],
        "project": project,
        "evidence": {"quote": quote},
        **more,
    }


def fact(project, quote):
    return {"op": "fact", "text": "The plan is due soon.", "project": project, "evidence": {"quote": quote}}


def question(cfg, who, project, **more):
    return {
        "op": "question.add",
        "to": who["full_name"],
        "title": "Is the plan final?",
        "links": [LINK],
        "matters_for": "The date the plan goes out",
        "project": project,
        **more,
    }


def problems(env, op, raw, name=None):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", "SRC-1", raw, "", "untrusted"),
    )
    return [p for p in check(cs, ctx) if name is None or p.check == name]


def from_input(env, ops, raw):
    """Apply ops as the assistant's reading of an input would: the changeset id and each op's status."""
    _, cfg, store = env
    return apply(store, cfg, ops, origin="input", trust="untrusted", source_id=source(store), raw=raw)


def from_note(env, ops, note):
    """Apply ops as the assistant's reading of the person's own typed note would."""
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request(store, "pm"), None, "", note, "trusted"),
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def actions_on(store, project):
    """The actions this file's mail makes on a project (the fixtures' own are about other things)."""
    return [
        a for a in store.read().list("action") if a.data.get("project") == project and a.data["text"] == PLAN_ACTION
    ]


def role_op(cfg, project, role, quote):
    return {"op": "project.role", "project": project, "person": pm_of(cfg), "role": role, "evidence": {"quote": quote}}


# ---- the role ------------------------------


def test_a_role_from_the_persons_own_note_applies_at_once_and_undo_puts_it_back(env):
    _, cfg, store = env
    words = "I'm only watching it now"
    cs_id, result = from_note(env, [role_op(cfg, PLAIN, "watch", words)], words)
    assert result == ["applied"]
    assert store.read().get("project", PLAIN).data["roles"] == [{"person": pm_of(cfg), "role": "watch"}]
    assert role_of(store.read(), PLAIN, pm_of(cfg)) == "watch"
    undo_changeset(store, cs_id)
    assert store.read().get("project", PLAIN).data["roles"] == []
    assert role_of(store.read(), PLAIN, pm_of(cfg)) == "run"


def test_a_role_from_an_input_waits_for_the_person_and_applies_when_they_confirm(env):
    _, cfg, store = env
    words = "they want you to run this one now"
    cs_id, result = from_input(env, [role_op(cfg, PLAIN, "run", words)], words)
    assert result == ["held"]
    assert store.read().get("project", PLAIN).data["roles"] == []
    release(store, cfg, cs_id, 0)
    assert store.read().get("project", PLAIN).data["roles"] == [{"person": pm_of(cfg), "role": "run"}]


def test_setting_a_role_again_replaces_the_one_before_and_the_assistant_must_quote_for_it(env):
    _, cfg, store = env
    words = "I'm designing for it now"
    from_note(env, [role_op(cfg, WATCHED, "design", words)], words)
    assert store.read().get("project", WATCHED).data["roles"] == [{"person": pm_of(cfg), "role": "design"}]
    bare = {k: v for k, v in role_op(cfg, WATCHED, "run", words).items() if k != "evidence"}
    _, result = from_note(env, [bare], words)
    assert result == ["refused"]  # the assistant's claim needs the words that say it
    cs_id = apply_as_person(store, cfg, [bare], "Set on screen")  # the person's own change needs none
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "applied"
    assert store.read().get("project", WATCHED).data["roles"] == [{"person": pm_of(cfg), "role": "run"}]


def test_a_role_needs_a_project_and_a_known_person(env):
    _, cfg, store = env
    words = "I'm running it now"
    _, result = from_note(env, [{**role_op(cfg, "PRJ-99", "run", words)}], words)
    assert result == ["refused"]
    _, result = from_note(env, [{**role_op(cfg, PLAIN, "run", words), "person": "Nobody Known"}], words)
    assert result == ["refused"]


# ---- a project the person watches ------------------------------


def test_on_a_watched_project_an_action_for_someone_else_is_returned_then_held_and_never_applied(env):
    _, cfg, store = env
    mate = teammate(cfg)
    quote = f"{mate['full_name']} will send the revised plan by Oct 20"
    op = action(cfg, mate, quote, WATCHED)
    (found,) = problems(env, op, quote, "watched-project")
    assert found.severity == "return" and "record it as a fact" in found.message
    cs_id, result = from_input(env, [op], quote)
    assert result == ["held"]  # it reaches no one else, and it is still held
    assert actions_on(store, WATCHED) == []
    assert "record it as a fact" in store.read().get("changeset", cs_id).data["ops"][0]["reason"]


def test_on_a_watched_project_a_question_to_someone_else_is_returned_then_held(env):
    _, cfg, store = env
    mate = teammate(cfg)
    op = question(cfg, mate, WATCHED)
    (found,) = problems(env, op, "", "watched-project")
    assert found.severity == "return" and "record it as a fact" in found.message
    _, result = from_input(env, [op], "")
    assert result == ["held"]
    assert [q for q in store.read().list("question") if WATCHED in (q.data.get("projects") or [])] == []


def test_on_a_watched_project_facts_notes_calendar_entries_and_the_persons_own_items_apply(env):
    _, cfg, store = env
    mate = teammate(cfg)
    quote = f"{mate['full_name']} will send the revised plan by Oct 20"
    ops = [
        fact(WATCHED, quote),
        {"op": "note", "text": "Keep an eye on the plan.", "project": WATCHED},
        {
            "op": "event.add",
            "title": "Plan due",
            "start": "2026-10-20",
            "project": WATCHED,
            "evidence": {"quote": quote},
        },
        action(cfg, pm_record(cfg), quote, WATCHED),
        {**question(cfg, pm_record(cfg), WATCHED), "kind": "decision", "links": []},
    ]
    assert not [p for p in problems(env, ops[3], quote) if p.check == "watched-project"]
    _, result = from_input(env, ops, quote)
    assert result == ["applied"] * len(ops)


def test_a_project_with_no_role_for_the_person_behaves_as_if_they_run_it(env):
    _, cfg, store = env
    mate = teammate(cfg)
    quote = f"{mate['full_name']} will send the revised plan by Oct 20"
    assert role_of(store.read(), PLAIN, pm_of(cfg)) == "run"
    assert role_of(store.read(), None, pm_of(cfg)) == "run"
    assert not problems(env, action(cfg, mate, quote, PLAIN), quote, "watched-project")
    _, result = from_input(env, [action(cfg, mate, quote, PLAIN)], quote)
    assert result == ["applied"]
    # a role for someone else on the watched project leaves the person's own part as it was
    other = outsider(cfg)["id"]
    assert role_of(store.read(), WATCHED, other) == "run"


def test_the_watched_check_is_a_setting_and_a_role_of_design_or_run_is_not_watching(env):
    _, cfg, store = env
    mate = teammate(cfg)
    quote = f"{mate['full_name']} will send the revised plan by Oct 20"
    op = action(cfg, mate, quote, WATCHED)
    cfg.checks.lints["watched-project"] = "off"
    assert not problems(env, op, quote, "watched-project")
    cfg.checks.lints["watched-project"] = "return"
    for role in ("design", "run"):
        apply_as_person(
            store, cfg, [{"op": "project.role", "project": WATCHED, "person": pm_of(cfg), "role": role}], "x"
        )
        assert not problems(env, op, quote, "watched-project")


# ---- another team's item ------------------------------


def test_another_teams_action_is_returned_then_held_and_never_applied(env):
    _, cfg, store = env
    them = outsider(cfg)
    quote = f"{them['full_name']} will send the revised plan by Oct 20"
    op = action(cfg, them, quote, PLAIN)
    (found,) = problems(env, op, quote, "other-team-item")
    assert found.severity == "return" and "record it as a fact" in found.message
    _, result = from_input(env, [op], quote)
    assert result == ["held"]
    assert actions_on(store, PLAIN) == []
    _, with_no_project = from_input(env, [action(cfg, them, quote)], quote)
    assert with_no_project == ["held"]  # on any project, or none


@pytest.mark.parametrize("words", ["you", "your team", "me", "please send it to the printer"])
def test_a_quote_that_addresses_the_person_is_one_the_person_owes(env, words):
    _, cfg, store = env
    them = outsider(cfg)
    quote = f"{them['full_name']} will send {words} the revised plan by Oct 20"
    assert not problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")
    _, result = from_input(env, [action(cfg, them, quote, PLAIN)], quote)
    assert result == ["applied"]


def test_another_teams_promise_to_the_person_is_one_the_person_waits_on(env):
    _, cfg, store = env
    them = outsider(cfg)
    quote = f"{them['full_name']} will send the revised plan by Oct 20"
    op = action(cfg, them, quote, PLAIN, promised_to=[pm_of(cfg)])
    assert not problems(env, op, quote, "other-team-item")
    _, result = from_input(env, [op], quote)
    assert result == ["applied"]


@pytest.mark.parametrize("words", ["we", "us", "our"])
def test_the_we_words_are_the_senders_own_team_and_are_not_owed_by_the_person(env, words):
    _, cfg, store = env
    them = outsider(cfg)
    quote = f"{them['full_name']} and {words} will send the revised plan by Oct 20, our own copy first"
    assert problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")


def test_a_request_addressed_by_name_is_owed_but_a_bare_name_only_says_who_it_is_for(env):
    _, cfg, store = env
    them = outsider(cfg)
    first = pm_record(cfg)["full_name"].split()[0]
    for addressed in (
        f"{first}, can you send the revised plan by Oct 20",
        f"{first}: please send the revised plan by Oct 20",
        f"{pm_record(cfg)['full_name']} needs to send the revised plan by Oct 20",
        f"{team_name(cfg)} will send the revised plan by Oct 20",
    ):
        quote = f"{them['full_name']} says {addressed}"
        assert not problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item"), addressed
    for names in (pm_record(cfg)["full_name"], first, team_name(cfg)):
        quote = f"{them['full_name']} will send the revised plan to {names} by Oct 20"
        assert problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item"), names
    # a word that only contains one of the words doesn't count
    quote = f"{them['full_name']} will send the revised plan to the usual contact by Oct 20"
    assert problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")


def test_the_words_of_a_request_by_name_are_a_setting(env):
    _, cfg, store = env
    them = outsider(cfg)
    first = pm_record(cfg)["full_name"].split()[0]
    quote = f"{them['full_name']} asks {first} quux send the revised plan by Oct 20"
    assert problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")
    cfg.language.request_words = ["quux"]
    assert not problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")


def test_an_action_with_an_owner_on_the_persons_team_is_not_another_teams_item(env):
    _, cfg, store = env
    mate, them = teammate(cfg), outsider(cfg)
    quote = f"{mate['full_name']} and {them['full_name']} will send the revised plan by Oct 20"
    one = action(cfg, mate, quote, PLAIN)
    both = {**one, "owners": [mate["full_name"], them["full_name"]]}
    assert not problems(env, one, quote, "other-team-item")
    assert not problems(env, both, quote, "other-team-item")  # only when every owner is outside
    assert not problems(env, action(cfg, pm_record(cfg), quote, PLAIN), quote, "other-team-item")


def test_a_person_with_no_team_has_no_other_team(env):
    _, cfg, store = env
    them = outsider(cfg)
    quote = f"{them['full_name']} will send the revised plan by Oct 20"
    with store.transaction() as tx:
        current = tx.get("person", pm_of(cfg))
        tx.update("person", pm_of(cfg), {"team": None}, _TEST, read_version=current.version)
    assert not problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")


def test_the_words_that_show_what_the_person_owes_and_the_severity_are_settings(env):
    _, cfg, store = env
    them = outsider(cfg)
    quote = f"{them['full_name']} will send us the revised plan by Oct 20"
    cfg.language.owed_words = ["quux"]
    assert problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")
    assert not problems(env, action(cfg, them, quote + " quux", PLAIN), quote + " quux", "other-team-item")
    cfg.checks.lints["other-team-item"] = "off"
    assert not problems(env, action(cfg, them, quote, PLAIN), quote, "other-team-item")
    cfg.checks.lints["other-team-item"] = "warn"
    _, result = from_input(env, [action(cfg, them, quote, PLAIN)], quote)
    assert result == ["applied"]  # warned, not held


def test_on_a_watched_project_only_the_role_is_named_when_both_would_apply(env):
    _, cfg, store = env
    them = outsider(cfg)
    quote = f"{them['full_name']} will send the revised plan by Oct 20"
    found = problems(env, action(cfg, them, quote, WATCHED), quote)
    assert [p.check for p in found if p.check in ("watched-project", "other-team-item")] == ["watched-project"]


def test_the_scope_lints_and_the_owed_words_have_defaults_and_demo_values_in_both_workspaces():
    from engine.config.schema import ChecksFile, LanguageFile
    from tests.conftest import DEMO_B

    assert ChecksFile().lints["watched-project"] == "return" and ChecksFile().lints["other-team-item"] == "return"
    assert LanguageFile().owed_words == ["you", "your", "please send", "me"]
    assert "can" in LanguageFile().request_words
    for template in (DEMO_A, DEMO_B):
        assert "watched-project: return" in (template / "config" / "checks.yaml").read_text()
        assert "owed_words:" in (template / "config" / "language.yaml").read_text()
        assert "request_words:" in (template / "config" / "language.yaml").read_text()
        assert next(p for p in fixture_records(template, "person") if p["id"] == "PER-1").get("team")


# ---- the project's page ------------------------------


@pytest.fixture
def client(env):
    ws, cfg, store = env
    store.close()
    application = create_app(ws, cfg, "scope-token", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer scope-token"}) as c:
        yield c, application.state.store, cfg.server.base_path.rstrip("/") + "/api"


def test_the_project_page_shows_the_persons_role_and_a_pick_changes_it_with_undo(client):
    c, store, api = client
    shown = {p["id"]: p["role"] for p in c.get(f"{api}/projects").json()}
    assert shown[WATCHED] == "watch" and shown[PLAIN] == "run"
    done = c.post(f"{api}/projects/{PLAIN}/role", json={"role": "design"})
    assert done.status_code == 200
    assert {p["id"]: p["role"] for p in c.get(f"{api}/projects").json()}[PLAIN] == "design"
    changed = next(
        i for i in c.get(f"{api}/changes").json() if i["changeset"] and i["changeset"]["id"] == done.json()["changeset"]
    )
    (op,) = changed["changeset"]["ops"]
    assert op["op"] == "project.role" and op["meta"]["role"] == "design" and op["status"] == "applied"
    assert c.post(f"{api}/changesets/{done.json()['changeset']}/undo", json={"ops": None}).status_code == 200
    assert {p["id"]: p["role"] for p in c.get(f"{api}/projects").json()}[PLAIN] == "run"


def test_the_role_pick_refuses_a_part_that_isnt_one_and_a_project_that_isnt_there(client):
    c, _, api = client
    assert c.post(f"{api}/projects/{PLAIN}/role", json={"role": "boss"}).status_code == 422
    assert c.post(f"{api}/projects/PRJ-99/role", json={"role": "run"}).status_code == 404


# ---- the person's path ------------------------------


def mail_for(cfg) -> tuple[str, str]:
    mate = teammate(cfg)
    quote = "will send the revised portal plan by Oct 20"
    return f"From: {mate['full_name']}\n\n{mate['full_name']} {quote}.", quote


def scripted(cfg, quote, *, insists):
    """A stand-in model: it reads the mail as an action and a fact, and sends the action back out as a fact when the
    checks return it, unless it insists."""
    mate = teammate(cfg)
    both = {
        "summary": "The plan is coming.",
        "ops": [
            action(cfg, mate, quote, WATCHED),
            fact(WATCHED, quote),
        ],
    }
    facts_only = {"summary": "The plan is coming.", "ops": [fact(WATCHED, quote)]}

    def answer(task):
        returned = "record it as a fact" in task.request
        return json.dumps(facts_only if returned and not insists else both)

    return answer


def read_mail(env, pasted):
    ws, cfg, store = env
    handed = hand_in(ws, store, pasted=pasted, now=NOW)
    return process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)


def statuses(store, cs_id):
    return {o["op"]["op"]: o["status"] for o in store.read().get("changeset", cs_id).data["ops"]}


def test_a_watched_projects_mail_gives_facts_only_and_after_the_role_becomes_run_the_same_mail_gives_an_action(env):
    ws, cfg, store = env
    pasted, quote = mail_for(cfg)
    set_responder(scripted(cfg, quote, insists=False))
    first = read_mail(env, pasted)
    assert statuses(store, first) == {"fact": "applied"}  # sent back once, it came back as a fact
    assert actions_on(store, WATCHED) == []
    assert [f.data["project"] for f in store.read().list("fact")].count(WATCHED) == 1
    apply_as_person(store, cfg, [{"op": "project.role", "project": WATCHED, "person": pm_of(cfg), "role": "run"}], "x")
    second = read_mail(env, pasted)
    assert statuses(store, second) == {"action.add": "applied", "fact": "applied"}
    (made,) = actions_on(store, WATCHED)
    assert [o["person"] for o in made.data["owners"]] == [teammate(cfg)["id"]]


def test_when_the_model_still_sends_the_action_after_it_was_returned_it_is_held_and_the_fact_applies(env):
    ws, cfg, store = env
    pasted, quote = mail_for(cfg)
    set_responder(scripted(cfg, quote, insists=True))
    cs_id = read_mail(env, pasted)
    assert statuses(store, cs_id) == {"action.add": "held", "fact": "applied"}
    assert actions_on(store, WATCHED) == []


def test_reading_notes_may_propose_a_role_and_an_ask_may_not():
    from engine.tasks import TASKS

    assert "project.role" in TASKS["notes"].ops
    assert "project.role" not in TASKS["ask"].ops


def test_the_persons_own_note_decides_what_they_track_and_the_scope_checks_read_only_what_came_in(env):
    _, cfg, store = env
    them = outsider(cfg)
    note = f"{them['full_name']} will send the revised plan by Oct 20"
    _, on_watched = from_note(env, [action(cfg, them, note, WATCHED)], note)
    _, other_team = from_note(env, [action(cfg, them, note, PLAIN)], note)
    assert on_watched == ["applied"] and other_team == ["applied"]


def test_the_packet_says_which_projects_the_person_only_watches(env):
    from engine.packet import _projects

    _, cfg, store = env
    listed = _projects(store, pm_of(cfg)).splitlines()
    watched = next(line for line in listed if line.startswith(f"- {WATCHED} "))
    plain = next(line for line in listed if line.startswith(f"- {PLAIN} "))
    assert "watch (record facts only)" in watched and "part" not in plain
