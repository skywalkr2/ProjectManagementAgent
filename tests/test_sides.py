"""Two sides in the data (design 6.32, roadmap S1-4a): a workspace made with no template has a Personal project; the
person's business is one top project they name; a project, a person and an item each belong to a side; and what
names no project is filed by the people it names (people first), with the Today line asking "Which side?" once for
whatever can't be placed. Names and ids come from the fixtures."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import sides
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, apply_changeset, restatements
from engine.config.yaml_edit import remove_key, set_key
from engine.dispatcher import process
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, ProjectAddOp
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.unfiled import unfiled
from engine.workspace import Workspace, init_workspace
from engine.yaml_load import load_yaml
from tests.conftest import DEMO_A, DEMO_B, fixture_records

SIDES_FIXTURES = Path(__file__).parent / "fixtures" / "sides"
WEEK_PEOPLE = load_yaml((SIDES_FIXTURES / "people.yaml").read_text(encoding="utf-8"))["people"]
WEEK = load_yaml((SIDES_FIXTURES / "week.yaml").read_text(encoding="utf-8"))
WEEK_PERSON = WEEK["person"]

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TOKEN = "sides-token"
_PM = WriteContext(actor="pm", trust="trusted", op="test.sides")

PEOPLE = fixture_records(DEMO_B, "person")
ME = PEOPLE[0]["id"]
# Who is on which side, by fixture position: two on each side, one on both, one with no side.
BUSINESS_PEOPLE = (PEOPLE[1], PEOPLE[2])
PERSONAL_PEOPLE = (PEOPLE[3], PEOPLE[4])
BOTH_PERSON = PEOPLE[5]
NO_SIDE_PERSON = PEOPLE[6]
SIDES = {
    **{p["id"]: "business" for p in BUSINESS_PEOPLE},
    **{p["id"]: "personal" for p in PERSONAL_PEOPLE},
    BOTH_PERSON["id"]: "both",
}
PROJECTS = fixture_records(DEMO_B, "project")
DEMO_CONFIG = load_yaml((DEMO_B / "config" / "workspace.yaml").read_text(encoding="utf-8"))["project"]
BUSINESS_ID, PERSONAL_ID = PROJECTS[0]["id"], DEMO_CONFIG["personal"]  # the fixture names no business; tests set one
BUSINESS_NAME = fixture_records(DEMO_B, "organization")[0]["name"]
OTHER_BUSINESS_NAME = fixture_records(DEMO_B, "organization")[1]["name"]


def address(person: dict) -> str:
    return f"{person['id'].lower()}@example.com"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """One workspace from the fixture, with the people's sides and addresses set; each test works on its own copy."""
    root = tmp_path_factory.mktemp("sides") / "base"
    ws = init_workspace(root, template=DEMO_B, git=False)
    store = Store(ws.db_path, cfg=ws.config(env={}))
    with store.transaction() as tx:
        for person in tx.list("person"):
            changes = {"how_to_reach": {"email": address(person.data | {"id": person.id})}}
            if person.id in SIDES:
                changes["side"] = SIDES[person.id]
            tx.update("person", person.id, changes, _PM, read_version=person.version)
        for who in WEEK_PEOPLE:  # the people the fictional week of mail comes from
            tx.create(
                "person",
                {
                    "full_name": who["name"],
                    "side": who["side"],
                    "relation": who["relation"],
                    "how_to_reach": {"email": who["address"]},
                    "name_verified": True,
                },
                _PM,
            )
        owner = tx.create(
            "person",
            {
                "full_name": WEEK_PERSON["name"],
                "how_to_reach": {"email": WEEK_PERSON["address"]},
                "name_verified": True,
            },
            _PM,
        )
    store.close()
    settings = root / "config" / "workspace.yaml"
    text = set_key(settings.read_text(encoding="utf-8"), ["user", "person"], owner.id)
    settings.write_text(set_key(text, ["project", "business"], BUSINESS_ID), encoding="utf-8")
    return root


@pytest.fixture
def env(base, tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(base, root)
    ws = Workspace(root)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


# ---- a workspace made with no template, and the business route ---------------------------------------------------


def test_a_workspace_made_with_no_template_has_a_personal_project_and_no_business(tmp_path):
    ws = init_workspace(tmp_path / "fresh", git=False, you="Pat Example")
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        (project,) = store.read().list("project")
        assert cfg.workspace.project.personal == project.id and cfg.workspace.project.business is None
        assert project.data["name"] == sides.word(cfg, sides.PERSONAL_NAME_KEY)
        assert sides.side_of_project(store.read(), cfg, project.id) == "personal"
    finally:
        store.close()
    # The wording sheet carries the same default the engine writes, and the workspace's own wording wins.
    sheet = json.loads((DEMO_B.parents[1] / "web" / "src" / "wording" / "en.json").read_text(encoding="utf-8"))
    assert sheet[sides.PERSONAL_NAME_KEY] == sides.word(None, sides.PERSONAL_NAME_KEY)
    named = ws.config(env={"COCKPIT__UI__WORDING": json.dumps({sides.PERSONAL_NAME_KEY: BUSINESS_NAME})})
    assert sides.word(named, sides.PERSONAL_NAME_KEY) == BUSINESS_NAME
    # A template workspace keeps its own data: the fixture's projects, and no new one.
    template = init_workspace(tmp_path / "template", template=DEMO_B, git=False)
    kept = Store(template.db_path, cfg=template.config(env={}))
    try:
        assert [p.data["name"] for p in kept.read().list("project")] == [p["name"] for p in PROJECTS]
    finally:
        kept.close()


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", git=False, you="Pat Example")
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, ws, app.state.store


def test_the_business_route_makes_one_top_project_and_a_second_call_renames_it(api):
    client, ws, store = api
    first = client.post("/api/setup/business", json={"name": BUSINESS_NAME})
    assert first.status_code == 200, first.text
    made = first.json()
    assert made["created"] is True and made["name"] == BUSINESS_NAME
    cfg = ws.config(env={})
    assert cfg.workspace.project.business == made["project"]
    record = store.read().get("project", made["project"])
    assert record.data["name"] == BUSINESS_NAME and not record.data.get("parent")
    assert sides.side_of_project(store.read(), cfg, made["project"]) == "business"
    again = client.post("/api/setup/business", json={"name": OTHER_BUSINESS_NAME}).json()
    assert again["created"] is False and again["project"] == made["project"] and again["changeset"]
    assert len(store.read().list("project")) == 2  # Personal and the business, never a second business
    assert store.read().get("project", made["project"]).data["name"] == OTHER_BUSINESS_NAME
    undone = client.post(f"/api/changesets/{again['changeset']}/undo", json={})
    assert undone.status_code == 200, undone.text
    assert store.read().get("project", made["project"]).data["name"] == BUSINESS_NAME


def test_the_settings_offer_the_projects_to_pick_from_and_an_undone_business_counts_as_none(api):
    client, ws, store = api
    made = client.post("/api/setup/business", json={"name": BUSINESS_NAME}).json()
    shown = {s["key"]: s for s in client.get("/api/settings").json()["items"]}
    for key in ("workspace.project.personal", "workspace.project.business"):
        assert shown[key]["type"] == "choice" and shown[key]["choices"] == "projects"
        assert set(shown[key]["options"]) == {p.id for p in store.read().list("project")}
    assert client.post(f"/api/changesets/{made['changeset']}/undo", json={}).status_code == 200
    assert sides.business_project(store.read(), ws.config(env={})) is None
    remade = client.post("/api/setup/business", json={"name": BUSINESS_NAME}).json()
    assert remade["created"] is True and remade["project"] != made["project"]


def test_a_business_name_another_project_has_is_refused_in_plain_words(api):
    client, _, store = api
    personal = store.read().list("project")[0].data["name"]
    refused = client.post("/api/setup/business", json={"name": personal})
    assert refused.status_code == 409 and personal in refused.json()["detail"]


# ---- which side a project, a person and an item are on ---------------------------------------------------------------


def make_project(store, name, parent=None) -> str:
    with store.transaction() as tx:
        return tx.create("project", {"name": name, "parent": parent} if parent else {"name": name}, _PM).id


def test_a_project_is_on_the_side_its_parent_chain_ends_in(env):
    ws, cfg, store = env
    business_child = make_project(store, "Business child", BUSINESS_ID)
    business_grandchild = make_project(store, "Business grandchild", business_child)
    personal_child = make_project(store, "Personal child", PERSONAL_ID)
    loose = make_project(store, "Loose top project")
    view = store.read()
    side = lambda pid: sides.side_of_project(view, cfg, pid)  # noqa: E731
    assert [side(p) for p in (BUSINESS_ID, business_child, business_grandchild)] == ["business"] * 3
    assert [side(p) for p in (PERSONAL_ID, personal_child)] == ["personal"] * 2
    assert side(loose) is None and side("PRJ-999") is None and side(None) is None
    assert sides.top_of(view, business_grandchild) == BUSINESS_ID
    # With no business set, what hangs under the old business is on no side.
    other = without(ws, "business")
    assert sides.side_of_project(view, other, business_grandchild) is None
    assert sides.side_of_project(view, other, personal_child) == "personal"


def test_an_item_is_on_the_side_of_the_project_it_is_filed_under(env):
    _, cfg, store = env
    with store.transaction() as tx:
        note = tx.create("note", {"text": "A note.", "project": PERSONAL_ID}, _PM)
        question = tx.create("question", {"to": ME, "title": "A question?", "projects": [BUSINESS_ID]}, _PM)
        loose = tx.create("note", {"text": "A loose note."}, _PM)
    view = store.read()
    assert sides.side_of_item(view, cfg, view.get("note", note.id)) == "personal"
    assert sides.side_of_item(view, cfg, view.get("question", question.id)) == "business"
    assert sides.side_of_item(view, cfg, view.get("note", loose.id)) is None


def personal_only(env):
    """Shape the workspace as a person with no business keeps it: every other project under Personal (its areas and
    projects), so Personal is the only top-level project."""
    _, _, store = env
    with store.transaction() as tx:
        for project in tx.list("project"):
            if project.id != PERSONAL_ID and not project.data.get("parent"):
                tx.update("project", project.id, {"parent": PERSONAL_ID}, _PM, read_version=project.version)


def without(ws, *keys):
    """The workspace's settings with these project keys (business, personal) taken out, as the app would read them."""
    path = ws.config_dir / "workspace.yaml"
    text = path.read_text(encoding="utf-8")
    for key in keys:
        text = remove_key(text, ["project", key])
    path.write_text(text, encoding="utf-8")
    return ws.config(env={})


def test_a_persons_side_and_relation_are_set_by_record_set_and_refuse_a_side_that_is_not_one(env):
    _, cfg, store = env
    who = NO_SIDE_PERSON["id"]

    def set_field(field, value):
        cs = CHANGESET.validate_python(
            {"ops": [{"op": "record.set", "kind": "person", "id": who, "field": field, "value": value}]},
            context={"op_models": store.plugins.ops},
        )
        ctx = Context(store, cfg, People(store, cfg), ("record.set",), Inputs("REQ-1", None, "", "", "trusted"))
        cs_id = apply_changeset(cs, [], ctx, run=None)
        return store.read().get("changeset", cs_id).data["ops"][0]["status"]

    assert set_field("side", "personal") == "applied" and set_field("relation", "my sister") == "applied"
    assert store.read().get("person", who).data["side"] == "personal"
    assert store.read().get("person", who).data["relation"] == "my sister"
    assert set_field("side", "sideways") != "applied"
    assert store.read().get("person", who).data["side"] == "personal"


# ---- filing by people first -----------------------------------------------------------------------------------------


def new_op(kind="action.add", quote="said so", **fields):
    base = {
        "action.add": {"text": "Call about it"},
        "question.add": {"title": "Which one?"},
        "fact": {"text": "It is so."},
    }
    return OP_MODELS[kind].model_validate(
        {
            "op": kind,
            **base.get(kind, {"text": "A note."}),
            **fields,
            **({"evidence": {"quote": quote}} if kind in ("action.add", "fact") else {}),
        }
    )


def filed(env, ops, sender=None, cfg=None):
    _, found, store = env
    cfg = cfg or found
    return [
        getattr(o, "project", None) for o in sides.file_by_people(ops, store.read(), cfg, People(store, cfg), sender)
    ]


def name_of(person: dict) -> str:
    return person["full_name"]


def test_everyone_on_the_personal_side_files_under_personal_and_everyone_on_the_business_side_under_the_business(env):
    a, b = PERSONAL_PEOPLE
    x, y = BUSINESS_PEOPLE
    ops = [
        new_op(owners=[name_of(a), name_of(b)]),
        new_op(owners=[name_of(x)], promised_to=[name_of(y)]),
        new_op("question.add", to=name_of(a)),
        new_op("question.add", to=name_of(y)),
    ]
    assert filed(env, ops) == [PERSONAL_ID, BUSINESS_ID, PERSONAL_ID, BUSINESS_ID]


def test_the_sender_counts_with_the_people_named_and_decides_alone_when_nobody_is_named(env):
    a, _ = PERSONAL_PEOPLE
    x, _ = BUSINESS_PEOPLE
    plain = [new_op("fact"), new_op("note")]
    assert filed(env, plain, sender=a["id"]) == [PERSONAL_ID] * 2
    assert filed(env, plain, sender=x["id"]) == [BUSINESS_ID] * 2
    assert filed(env, [new_op(owners=[name_of(a)])], sender=a["id"]) == [PERSONAL_ID]


def test_people_who_disagree_leave_it_unfiled_and_people_on_both_sides_or_not_known_decide_nothing(env):
    a, _ = PERSONAL_PEOPLE
    x, _ = BUSINESS_PEOPLE
    mixed = new_op(owners=[name_of(a), name_of(x)])
    from_other_side = new_op(owners=[name_of(a)])
    assert filed(env, [mixed]) == [None]
    assert filed(env, [from_other_side], sender=x["id"]) == [None]
    assert filed(env, [new_op(owners=[name_of(BOTH_PERSON)])]) == [None]
    assert filed(env, [new_op(owners=[name_of(NO_SIDE_PERSON)])]) == [None]
    assert filed(env, [new_op(owners=["Somebody Nobody Knows"])]) == [None]
    assert filed(env, [new_op("fact")], sender=ME) == [None]  # the person's own record has no side
    # People who don't decide don't veto the ones who do.
    decided = new_op(owners=[name_of(a), name_of(BOTH_PERSON), name_of(NO_SIDE_PERSON), "Somebody Nobody Knows"])
    assert filed(env, [decided]) == [PERSONAL_ID]


# ---- filing by words when the people don't place an item (S1-4) ---------------------------------------------------

BUSINESS_PROJECT_NAME = PROJECTS[0]["name"]
PERSONAL_PROJECT_NAME = PROJECTS[1]["name"]
SIDE_WORDS = DEMO_CONFIG["side_words"]


def test_the_demo_workspaces_name_words_for_each_side():
    for demo in (DEMO_B, DEMO_A):
        found = load_yaml((demo / "config" / "workspace.yaml").read_text(encoding="utf-8"))["project"]["side_words"]
        assert found["personal"] and found["business"]


def test_the_words_of_one_side_file_an_item_there_whatever_their_case_and_only_as_whole_words(env):
    business_name, personal_name = BUSINESS_PROJECT_NAME, PERSONAL_PROJECT_NAME
    ops = [
        new_op(text=f"Check on {business_name.upper()} this week"),
        new_op("question.add", to=name_of(NO_SIDE_PERSON), title=f"When is {personal_name.lower()} due?"),
        new_op("fact", text="It is so.", quote=f"about the {business_name} plan"),
        new_op("note", text=f"Remember: {SIDE_WORDS['business'][0].title()}."),
        new_op(text=f"Ask about {SIDE_WORDS['personal'][0]}"),
    ]
    assert filed(env, ops) == [BUSINESS_ID, PERSONAL_ID, BUSINESS_ID, BUSINESS_ID, PERSONAL_ID]
    inside = [new_op(text=f"Check on x{business_name}y"), new_op(text=f"Check on {business_name}s")]
    assert filed(env, inside) == [None, None]


def test_the_words_of_both_sides_or_of_neither_place_nothing(env):
    both = new_op(text=f"Compare {BUSINESS_PROJECT_NAME} with {SIDE_WORDS['personal'][0]}")
    both_by_names = new_op(text=f"Compare {BUSINESS_PROJECT_NAME} with {PERSONAL_PROJECT_NAME}")
    neither = new_op(text="Call about it")
    assert filed(env, [both, both_by_names, neither]) == [None, None, None]


def test_words_that_name_a_project_under_a_side_file_the_item_under_that_project(env):
    _, _, store = env
    under = make_project(store, OTHER_BUSINESS_NAME, parent=BUSINESS_ID)
    assert filed(env, [new_op(text=f"Send the {OTHER_BUSINESS_NAME} report")]) == [under]
    both_named = new_op(text=f"Send the {OTHER_BUSINESS_NAME} report for {BUSINESS_PROJECT_NAME}")
    assert filed(env, [both_named]) == [BUSINESS_ID]  # two projects of the side: the side's top
    assert filed(env, [new_op(text=f"Send the {SIDE_WORDS['business'][0]} report")]) == [BUSINESS_ID]


def test_people_who_place_an_item_win_over_its_words(env):
    a, _ = PERSONAL_PEOPLE
    x, _ = BUSINESS_PEOPLE
    about_business = new_op(text=f"Check on {BUSINESS_PROJECT_NAME}", owners=[name_of(a)])
    assert filed(env, [about_business]) == [PERSONAL_ID]
    about_personal = new_op(text=f"Ask about {SIDE_WORDS['personal'][0]}")
    assert filed(env, [about_personal], sender=x["id"]) == [BUSINESS_ID]
    # People on both sides don't place it, so its words do.
    assert filed(env, [about_business.model_copy(update={"owners": [name_of(BOTH_PERSON)]})]) == [BUSINESS_ID]


def test_a_person_with_no_business_is_never_placed_by_words_and_asked_nothing(env):
    other = without(env[0], "business")
    personal_only(env)
    about_business = new_op(text=f"Check on {BUSINESS_PROJECT_NAME} and {SIDE_WORDS['business'][0]}")
    assert filed(env, [about_business], cfg=other) == [PERSONAL_ID]  # as before: everything unplaced is personal


def test_with_no_business_set_what_has_no_project_goes_to_personal_whoever_it_names(env):
    other = without(env[0], "business")
    personal_only(env)
    a, _ = PERSONAL_PEOPLE
    x, _ = BUSINESS_PEOPLE
    ops = [new_op(owners=[name_of(a), name_of(x)]), new_op(owners=[name_of(BOTH_PERSON)]), new_op("fact")]
    assert filed(env, ops, cfg=other) == [PERSONAL_ID] * 3


def test_with_no_business_and_other_work_on_top_what_has_no_project_stays_for_the_person_to_file(env):
    other = without(env[0], "business")
    a, _ = PERSONAL_PEOPLE
    assert filed(env, [new_op(owners=[name_of(a)]), new_op("fact")], cfg=other) == [None, None]


def test_an_answer_that_proposes_a_new_project_leaves_its_items_for_that_project(env):
    other = without(env[0], "business")
    personal_only(env)
    a, _ = PERSONAL_PEOPLE
    proposed = ProjectAddOp(op="project.add", name=OTHER_BUSINESS_NAME, evidence={"quote": OTHER_BUSINESS_NAME})
    assert filed(env, [new_op(owners=[name_of(a)]), proposed], cfg=other)[0] is None


def test_a_project_the_answer_gave_is_kept_and_a_workspace_with_neither_side_set_files_nothing(env):
    a, _ = PERSONAL_PEOPLE
    given = new_op(owners=[name_of(a)], project=BUSINESS_ID)
    assert filed(env, [given]) == [BUSINESS_ID]
    neither = without(env[0], "business", "personal")
    assert filed(env, [new_op(owners=[name_of(a)])], cfg=neither) == [None]


def test_the_rule_runs_for_the_assistants_work_and_not_for_a_change_the_person_made_on_screen(env):
    _, cfg, store = env
    a, _ = PERSONAL_PEOPLE
    cs = CHANGESET.validate_python(
        {"ops": [new_op(owners=[name_of(a)]).model_dump(mode="json", exclude_none=True)]},
        context={"op_models": store.plugins.ops},
    )
    inputs = Inputs("REQ-1", None, "", "", "untrusted")
    by_assistant = Context(store, cfg, People(store, cfg), ("action.add",), inputs)
    by_person = Context(store, cfg, People(store, cfg), ("action.add",), inputs, actor="pm")
    assert restatements(cs, by_assistant).ops[0].project == PERSONAL_ID
    assert restatements(cs, by_person).ops[0].project is None


def test_the_question_that_asks_who_owns_an_action_sits_under_the_actions_project(env):
    _, cfg, store = env
    op = new_op(project=PERSONAL_ID)
    cs = CHANGESET.validate_python(
        {"ops": [op.model_dump(mode="json", exclude_none=True)]}, context={"op_models": store.plugins.ops}
    )
    ctx = Context(store, cfg, People(store, cfg), ("action.add",), Inputs("REQ-1", None, "", "said so", "untrusted"))
    apply_changeset(cs, [], ctx, run=None)
    (action,) = store.read().list("action", include_deleted=False)[-1:]
    (asked,) = [q for q in store.read().list("question") if (q.data.get("resolves") or {}).get("action") == action.id]
    assert action.data["status"] == "held" and asked.data["projects"] == [PERSONAL_ID]


# ---- a week of mail through the stub --------------------------------------------------------------------------------


def representative_week() -> list[dict]:
    """The 24 messages take about two seconds each run, so the runs use ten: every message from someone on both
    sides, three from the business and two personal ones, in the order they came; then one more from someone on
    both sides whose last line names the business's project, which its words place there."""
    first = {side: [m for m in WEEK["emails"] if m["side"] == side] for side in ("business", "personal", "unclear")}
    chosen = {m["id"] for m in [*first["unclear"], *first["business"][:3], *first["personal"][:2]]}
    by_words = {
        "id": "mail-by-words",
        "from": first["unclear"][0]["from"],
        "subject": "A question about the plan",
        "side": "business",
        "body": f"Hi Robin,\nCould you send the latest numbers?\nThey are for {BUSINESS_PROJECT_NAME}.",
    }
    return [*(m for m in WEEK["emails"] if m["id"] in chosen), by_words]


def mail_text(mail: dict) -> str:
    return f"From: {mail['from']}\nTo: {WEEK_PERSON['address']}\nSubject: {mail['subject']}\n\n{mail['body']}"


def action_for(mail: dict) -> dict:
    """The one to-do the stub's answer makes from a message, for the person, quoting its last line."""
    return {
        "op": "action.add",
        "text": f"Look into: {mail['subject']}",
        "owners": [WEEK_PERSON["name"]],
        "evidence": {"quote": mail["body"].splitlines()[-1]},
    }


def run_week(env, cfg=None):
    """Hand in the week of mail one message at a time, answered by the stub; returns each message's project, Today's
    lines and how many items were unfiled before the week."""
    ws, found, store = env
    cfg = cfg or found
    week = representative_week()
    set_responder(
        lambda task: json.dumps(
            {"ops": [action_for(next(m for m in week if f"Subject: {m['subject']}" in task.request))]}
        )
    )
    router = Router(cfg, store, env={})
    before = len(unfiled(store.read()))
    for mail in week:
        process(ws, store, cfg, router, hand_in(ws, store, pasted=mail_text(mail), now=NOW).request, now=NOW)
    by_text = {a.data["text"]: a.data.get("project") for a in store.read().list("action")}
    return {m["id"]: by_text[action_for(m)["text"]] for m in week}, queue(ws, store, cfg, NOW), before


def test_the_week_has_the_mix_the_tests_rest_on():
    sides_of_mail = [m["side"] for m in WEEK["emails"]]
    assert [sides_of_mail.count(x) for x in ("business", "personal", "unclear")] == [10, 9, 5]
    assert len(WEEK["emails"]) == 24 and len({m["subject"] for m in WEEK["emails"]}) == 24


def test_a_week_of_mail_for_a_person_with_a_business_is_filed_by_people_and_asks_which_side_once(env):
    projects, lines, before = run_week(env)
    home = {"business": BUSINESS_ID, "personal": PERSONAL_ID, "unclear": None}
    week = representative_week()
    assert projects == {m["id"]: home[m["side"]] for m in week}
    from_both_sides = {m["from"] for m in week if m["side"] == "unclear"}
    by_words = [m["id"] for m in week if m["from"] in from_both_sides and projects[m["id"]] is not None]
    assert by_words == ["mail-by-words"]  # its people sit on both sides, so its words placed it under the business
    asks = [line for line in lines if line.kind == "unfiled"]
    unclear = sum(m["side"] == "unclear" for m in week)
    assert (
        unclear == 5 and len(asks) == 1 and asks[0].state == "which_side"
    )  # one batched question, never one line per message
    assert asks[0].count == before + unclear
    assert asks[0].subject == fixture_records(DEMO_B, "project")[0]["name"]  # the business, named from its record
    sheet = json.loads((DEMO_B.parents[1] / "web" / "src" / "wording" / "en.json").read_text(encoding="utf-8"))
    assert "{business}" in sheet["queue.sides.one"] and "{business}" in sheet["queue.sides.other"]
    assert "{n}" in sheet["queue.sides.other"]  # the line reads "Sort 5 items: Personal or <business>?"


def test_the_same_week_for_a_person_with_no_business_files_everything_and_asks_nothing(env):
    ws, _, _ = env
    personal_only(env)
    projects, lines, before = run_week(env, without(ws, "business"))
    assert set(projects.values()) == {PERSONAL_ID}
    assert [line for line in lines if line.kind == "unfiled"] == [] and before == 0


# ---- the Personal / business filter on Today and Follow-ups (S1-4b) --------------------------------------------


@pytest.fixture
def anytime(tmp_path):
    """The app with no hours held back, so a line is on Today whatever time the test runs."""
    ws = init_workspace(tmp_path / "ws", git=False, you="Pat Example")
    flags = {"server.base_path": "/", "storage.backups.automatic": False, "steward.hold_outside_hours": False}
    app = create_app(ws, ws.config(env={}, flags=flags), TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, ws, app.state.store


def seed_both_sides(client, store, cfg):
    """One question to the person and one to someone else, and one action for them, on each side and on neither;
    returns the ids by side (the business is made through its route)."""
    business = client.post("/api/setup/business", json={"name": BUSINESS_NAME}).json()["project"]
    me = cfg.workspace.user.person
    personal_id = cfg.workspace.project.personal
    with store.transaction() as tx:
        other = tx.create("person", {"full_name": "Casey Example"}, _PM).id
        homes = {"business": business, "personal": personal_id, "none": None}
        ids = {}
        for name, home in homes.items():
            project = {"projects": [home]} if home else {}
            mine = tx.create(
                "question", {"to": me, "title": f"Decide the {name} thing?", "kind": "decision", **project}, _PM
            )
            theirs = tx.create("question", {"to": other, "title": f"Ask about the {name} thing?", **project}, _PM)
            action = tx.create(
                "action",
                {"text": f"Do the {name} thing", "owners": [{"person": other}], **({"project": home} if home else {})},
                _PM,
            )
            ids[name] = {"line": f"question:{mine.id}", "question": theirs.id, "action": action.id}
    return ids, other


def test_each_line_and_follow_up_row_says_which_side_it_is_on_and_a_business_is_reported(anytime):
    client, ws, store = anytime
    assert client.get("/api/setup/business").json() == {"business": False, "name": None}
    ids, other = seed_both_sides(client, store, ws.config(env={}))
    assert client.get("/api/setup/business").json() == {"business": True, "name": BUSINESS_NAME}
    lines = {line["key"]: line for line in client.get("/api/today/queue").json()}
    for name, side in (("business", "business"), ("personal", "personal"), ("none", None)):
        assert lines[ids[name]["line"]]["side"] == side
    rows = {}
    for section in client.get("/api/followups").json():
        for row in [*section["questions"], *section["actions"]]:
            rows[row["id"]] = row["side"]
    for name, side in (("business", "business"), ("personal", "personal"), ("none", None)):
        assert rows[ids[name]["question"]] == side and rows[ids[name]["action"]] == side


def test_with_no_business_nothing_is_on_the_business_side_and_the_route_says_so(anytime):
    client, ws, store = anytime
    me = ws.config(env={}).workspace.user.person
    personal_id = ws.config(env={}).workspace.project.personal
    with store.transaction() as tx:
        home = tx.create("question", {"to": me, "title": "Which one?", "projects": [personal_id]}, _PM).id
        loose = tx.create("question", {"to": me, "title": "Which other?"}, _PM).id
    assert client.get("/api/setup/business").json() == {"business": False, "name": None}
    lines = {line["key"]: line["side"] for line in client.get("/api/today/queue").json()}
    assert lines[f"question:{home}"] == "personal" and lines[f"question:{loose}"] is None
    assert "business" not in lines.values()


def test_a_line_about_records_on_both_sides_is_on_neither_and_one_side_gives_it_that_side(env):
    _, cfg, store = env
    with store.transaction() as tx:
        mine = tx.create("action", {"text": "Mine", "owners": [{"person": ME}], "project": PERSONAL_ID}, _PM).id
        work = tx.create("action", {"text": "Work", "owners": [{"person": ME}], "project": BUSINESS_ID}, _PM).id
    view = store.read()
    of = lambda **line: sides.side_of_line(view, cfg, SimpleNamespace(project=None, **line))  # noqa: E731
    assert (
        of(actions=[mine, work]) is None and of(actions=[mine]) == "personal" and of(actions=[work, work]) == "business"
    )
    assert of(actions=[]) is None and of(actions=["ACT-999"]) is None
    assert sides.side_of_line(view, cfg, SimpleNamespace(project=BUSINESS_ID, actions=[mine])) == "business"
