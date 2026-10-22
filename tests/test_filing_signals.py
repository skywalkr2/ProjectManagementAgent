"""Filing by ranked signals (design 6.32, roadmap B-12 batch 1): the people an item names and its sender, then the
sender's mail domain, then a project's aliases, then the names of projects that count by themselves, then the configured
side words; the first rank that decides, decides, and a rank that points to both sides decides nothing. Every item filed
by a signal keeps why (`filed_by`), says so on its line and its page, and moves to the other side in one step the
person's own change records as a correction. Names, ids and words come from the fixtures."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from engine import sides, since_yesterday
from engine.applier import Context, Inputs, apply_as_person, apply_changeset, undo
from engine.everyday_words import shipped
from engine.names import People
from engine.ops import CHANGESET
from engine.record_page import page
from engine.set_aside import shipped_public_domains
from engine.yaml_load import load_yaml
from tests import test_sides as shared
from tests.conftest import DEMO_A, DEMO_B, fixture_records
from tests.roundtrip import round_trip
from tests.test_sides import (
    _PM,
    BOTH_PERSON,
    BUSINESS_ID,
    BUSINESS_PEOPLE,
    BUSINESS_PROJECT_NAME,
    NOW,
    PERSONAL_ID,
    PERSONAL_PEOPLE,
    PERSONAL_PROJECT_NAME,
    SIDE_WORDS,
    make_project,
    name_of,
    new_op,
    run_week,
)

# The workspace fixtures the sides tests build: each test here works on its own copy.
base, env, api = shared.base, shared.env, shared.api

ORG_ONE, ORG_TWO = (o["id"] for o in fixture_records(DEMO_B, "organization")[:2])
BUSINESS_DOMAIN = "vendor.example.net"
OTHER_DOMAIN = "supplier.example.net"
# Made-up words that are no everyday word and appear in no fixture.
BUSINESS_CODE, PERSONAL_CODE = "qzx-bus", "qzx-per"
BUSINESS_WORD, PERSONAL_WORD = SIDE_WORDS["business"][0], SIDE_WORDS["personal"][0]


def mail_from(address: str) -> str:
    return f"From: Someone <{address}>\nTo: me@example.com\nSubject: A subject\n\nA body."


def file_ops(env, ops, raw=None, sender=None):
    _, cfg, store = env
    return sides.file_by_people(ops, store.read(), cfg, People(store, cfg), sender, raw)


def at_domain(env, person: dict, domain: str, org: str | None):
    """Put a fixture person at an address in a domain, working for an organization."""
    _, _, store = env
    record = store.read().get("person", person["id"])
    with store.transaction() as tx:
        tx.update(
            "person",
            record.id,
            {"how_to_reach": {"email": f"{record.id.lower()}@{domain}"}, "org": org},
            _PM,
            read_version=record.version,
        )


def set_aliases(env, project: str, aliases: list[str]):
    _, _, store = env
    record = store.read().get("project", project)
    with store.transaction() as tx:
        tx.update("project", project, {"aliases": aliases}, _PM, read_version=record.version)


def by(result) -> tuple[str | None, str | None, str | None]:
    """The project an op was filed under and why: its signal and word."""
    stamp = getattr(result, "filed_by", None)
    return result.project, stamp.by if stamp else None, stamp.word if stamp else None


# ---- each rank decides when the ones before it don't ------------------------------------------------------------


def test_each_rank_decides_when_the_ones_before_it_do_not(env):
    _, _, store = env
    personal_item = make_project(store, "Personal item", PERSONAL_ID)
    business_item = make_project(store, "Business thing here", BUSINESS_ID)
    set_aliases(env, personal_item, [PERSONAL_CODE])
    a, b = BUSINESS_PEOPLE
    for person in (a, b):
        at_domain(env, person, BUSINESS_DOMAIN, ORG_ONE)
    everything = f"{PERSONAL_CODE} and Business thing here and {PERSONAL_WORD}"
    # 1. people: a personal owner outranks the sender's business domain, the alias, the name and the words.
    owner = PERSONAL_PEOPLE[0]
    got = file_ops(env, [new_op(text=everything, owners=[name_of(owner)])], mail_from(f"stranger@{BUSINESS_DOMAIN}"))
    assert by(got[0]) == (PERSONAL_ID, "people", None)
    # 2. the domain of a sender nobody knows: business, though the text names a personal alias.
    got = file_ops(env, [new_op(text=everything)], mail_from(f"stranger@{BUSINESS_DOMAIN}"))
    assert by(got[0]) == (BUSINESS_ID, "domain", BUSINESS_DOMAIN)
    # 3. an alias, with no domain to read: its project, ahead of a name of the other side.
    got = file_ops(env, [new_op(text=everything)])
    assert by(got[0]) == (personal_item, "alias", PERSONAL_CODE)
    # 4. a name, when no alias is in the text: the project it names, ahead of the other side's configured word.
    got = file_ops(env, [new_op(text=f"Business thing here and {PERSONAL_WORD}")])
    assert by(got[0]) == (business_item, "name", "Business thing here")
    # 5. a configured word, when nothing else is.
    got = file_ops(env, [new_op(text=f"About {PERSONAL_WORD}")])
    assert by(got[0]) == (PERSONAL_ID, "word", PERSONAL_WORD)
    # Nothing decides: it stays unfiled, with no reason.
    assert by(file_ops(env, [new_op(text="Call about it")])[0]) == (None, None, None)


def test_every_kind_of_item_is_filed_and_says_why(env):
    owner = PERSONAL_PEOPLE[0]
    ops = [
        new_op(owners=[name_of(owner)]),
        new_op("question.add", to=name_of(owner)),
        new_op("fact", quote=f"about {BUSINESS_WORD}"),
        new_op("note", text=f"{BUSINESS_WORD}"),
    ]
    got = file_ops(env, ops)
    assert [by(o) for o in got] == [
        (PERSONAL_ID, "people", None),
        (PERSONAL_ID, "people", None),
        (BUSINESS_ID, "word", BUSINESS_WORD),
        (BUSINESS_ID, "word", BUSINESS_WORD),
    ]


def test_a_rank_that_points_to_both_sides_decides_nothing_and_the_next_is_read(env):
    _, _, store = env
    personal_item = make_project(store, "Personal item", PERSONAL_ID)
    business_item = make_project(store, "Business thing here", BUSINESS_ID)
    set_aliases(env, personal_item, [PERSONAL_CODE])
    set_aliases(env, business_item, [BUSINESS_CODE])
    both_aliases = f"{PERSONAL_CODE} and {BUSINESS_CODE}"
    # Both sides' aliases: the aliases decide nothing, so the name of one side's project does.
    got = file_ops(env, [new_op(text=f"{both_aliases} for Business thing here")])
    assert by(got[0]) == (business_item, "name", "Business thing here")
    # Both names and both configured words too: nothing decides.
    both_all = f"{both_aliases} Business thing here Personal item {BUSINESS_WORD} {PERSONAL_WORD}"
    assert by(file_ops(env, [new_op(text=both_all)])[0]) == (None, None, None)
    # The people of one organization on both sides: the domain decides nothing and the words are read.
    a, c = BUSINESS_PEOPLE[0], PERSONAL_PEOPLE[0]
    at_domain(env, a, BUSINESS_DOMAIN, ORG_ONE)
    at_domain(env, c, BUSINESS_DOMAIN, ORG_ONE)
    raw = mail_from(f"stranger@{BUSINESS_DOMAIN}")
    assert by(file_ops(env, [new_op(text=f"About {PERSONAL_WORD}")], raw)[0]) == (PERSONAL_ID, "word", PERSONAL_WORD)
    assert by(file_ops(env, [new_op(text="Call about it")], raw)[0]) == (None, None, None)
    # People on both sides (a person who is on both) decide nothing either, so the alias is read.
    got = file_ops(env, [new_op(text=both_aliases, owners=[name_of(BOTH_PERSON)])])
    assert got[0].project is None


# ---- a one-word everyday name never files, an alias of it does -------------------------------------------------


def test_the_everyday_words_come_from_a_shipped_file_the_setting_defaults_to():
    from engine.config.schema import LanguageFile

    words = LanguageFile().everyday_words
    assert words == shipped() and len(words) > 500
    assert words == [w.lower() for w in words] and len(set(words)) == len(words)
    shipped_file = Path(sides.__file__).parent / "defaults" / "everyday_words.yaml"
    assert load_yaml(shipped_file.read_text(encoding="utf-8"))["en"] == words


def test_a_one_word_everyday_project_name_never_files_an_item_but_the_same_word_as_an_alias_does(env):
    _, cfg, store = env
    everyday = cfg.language.everyday_words[0]
    project = make_project(store, everyday.title(), BUSINESS_ID)
    text = f"Please sort out the {everyday} soon"
    assert by(file_ops(env, [new_op(text=text)])[0]) == (None, None, None)
    # A name of two words counts, and so does one word that is no everyday word.
    two = make_project(store, f"{everyday.title()} plan", BUSINESS_ID)
    assert by(file_ops(env, [new_op(text=f"The {everyday} plan is late")])[0]) == (
        two,
        "name",
        f"{everyday.title()} plan",
    )
    uncommon = make_project(store, BUSINESS_CODE.title(), PERSONAL_ID)
    assert by(file_ops(env, [new_op(text=f"About {BUSINESS_CODE}")])[0]) == (uncommon, "name", BUSINESS_CODE.title())
    # The person giving the word as an alias makes it count, even as one word.
    set_aliases(env, project, [everyday.title()])
    assert by(file_ops(env, [new_op(text=text)])[0]) == (project, "alias", everyday.title())
    # The words are the setting's: with none, a one-word name counts as any other.
    ws, _, _ = env
    emptied = ws.config(env={"COCKPIT__LANGUAGE__EVERYDAY_WORDS": "[]"})
    assert emptied.language.everyday_words == []
    got = sides.file_by_people(
        [new_op(text=f"The {everyday} plan")], store.read(), emptied, People(store, emptied), None
    )
    assert got[0].project is not None


# ---- the sender's domain ------------------------------------------------------------------------------------------


def test_a_domain_shared_by_people_of_two_organizations_never_votes(env):
    at_domain(env, BUSINESS_PEOPLE[0], BUSINESS_DOMAIN, ORG_ONE)
    at_domain(env, BUSINESS_PEOPLE[1], BUSINESS_DOMAIN, ORG_TWO)
    raw = mail_from(f"stranger@{BUSINESS_DOMAIN}")
    assert by(file_ops(env, [new_op(text="Call about it")], raw)[0]) == (None, None, None)
    # A person with no organization at the domain never votes either.
    at_domain(env, BUSINESS_PEOPLE[1], BUSINESS_DOMAIN, None)
    assert by(file_ops(env, [new_op(text="Call about it")], raw)[0]) == (None, None, None)


def test_a_public_mail_domain_a_domain_nobody_knows_and_a_known_sender_never_vote(env):
    public = sorted(shipped_public_domains())[0]
    for person in BUSINESS_PEOPLE:
        at_domain(env, person, public, ORG_ONE)
    assert by(file_ops(env, [new_op(text="Call about it")], mail_from(f"stranger@{public}"))[0])[1] is None
    # Nobody known has an address at this domain.
    unknown = mail_from(f"stranger@{OTHER_DOMAIN}")
    assert by(file_ops(env, [new_op(text="Call about it")], unknown)[0])[1] is None
    # The sender is a known person on both sides: the domain is not read, only people and words.
    at_domain(env, BOTH_PERSON, BUSINESS_DOMAIN, ORG_ONE)
    at_domain(env, BUSINESS_PEOPLE[1], BUSINESS_DOMAIN, ORG_ONE)
    known = mail_from(f"{BOTH_PERSON['id'].lower()}@{BUSINESS_DOMAIN}")
    assert by(file_ops(env, [new_op(text="Call about it")], known)[0])[1] is None


def test_the_domain_of_one_organization_on_one_side_files_what_a_stranger_there_sends(env):
    for person in BUSINESS_PEOPLE:
        at_domain(env, person, BUSINESS_DOMAIN, ORG_ONE)
    raw = mail_from(f"stranger@{BUSINESS_DOMAIN.upper()}")  # the domain's case never matters
    got = file_ops(env, [new_op(text="Call about it"), new_op("question.add", to=name_of(PERSONAL_PEOPLE[0]))], raw)
    assert by(got[0]) == (BUSINESS_ID, "domain", BUSINESS_DOMAIN)
    assert by(got[1]) == (PERSONAL_ID, "people", None)  # a person it names still decides first


# ---- filed_by is written by the applier, kept, exported and imported ---------------------------------------------


def apply_ops(env, ops, **context):
    _, cfg, store = env
    cs = CHANGESET.validate_python(
        {"ops": [o.model_dump(mode="json", exclude_none=True) for o in ops]}, context={"op_models": store.plugins.ops}
    )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        ("action.add", "question.add", "fact", "note"),
        Inputs("REQ-1", None, "", f"said so {BUSINESS_WORD}", "untrusted"),
        **context,
    )
    apply_changeset(cs, [], ctx, run=None)
    return store.read()


def test_filed_by_is_written_with_the_item_and_survives_export_and_import(env, tmp_path):
    _, cfg, store = env
    ops = [
        new_op(text=f"Check {BUSINESS_WORD}", owners=[name_of(PERSONAL_PEOPLE[0])]),
        new_op(text=f"About {BUSINESS_WORD}", owners=[name_of(BUSINESS_PEOPLE[0])]),
        new_op("question.add", to=cfg.workspace.user.person, title=f"About {BUSINESS_WORD}?"),
        new_op("fact", text=f"{BUSINESS_WORD} is so.", quote=f"said so {BUSINESS_WORD}"),
        new_op("note", text=f"About {BUSINESS_WORD}."),
    ]
    view = apply_ops(env, ops)
    (personal_action, business_action) = [
        a for a in view.list("action") if a.data["text"].startswith(("Check", "About"))
    ]
    assert personal_action.data["filed_by"] == {"by": "people", "word": None, "project": PERSONAL_ID}
    assert business_action.data["filed_by"] == {"by": "people", "word": None, "project": BUSINESS_ID}
    (question,) = [q for q in view.list("question") if q.data["title"] == f"About {BUSINESS_WORD}?"]
    assert question.data["projects"] == [BUSINESS_ID] and question.data["filed_by"]["project"] == BUSINESS_ID
    (fact,) = [f for f in view.list("fact") if f.data["text"].startswith(BUSINESS_WORD)]
    assert fact.data["filed_by"] == {"by": "word", "word": BUSINESS_WORD, "project": BUSINESS_ID}
    (note,) = [n for n in view.list("note") if n.data["text"].startswith("About")]
    assert note.data["filed_by"] == {"by": "word", "word": BUSINESS_WORD, "project": BUSINESS_ID}
    set_aliases(env, BUSINESS_ID, [BUSINESS_CODE])
    assert round_trip(store, cfg, tmp_path / "round-trip")["differences"] == []
    exported = tmp_path / "round-trip" / "export-1"
    assert json.loads((exported / "fact.json").read_text(encoding="utf-8"))[0]["filed_by"]["by"] == "word"
    assert json.loads((exported / "project.json").read_text(encoding="utf-8"))[0]["aliases"] == [BUSINESS_CODE]


def test_what_the_assistant_writes_in_filed_by_is_cleared_and_an_item_it_filed_itself_has_none(env):
    stamp = {"by": "word", "word": "made up", "project": BUSINESS_ID}
    own = new_op(text="Call about it", filed_by=stamp)
    placed = new_op(text="Call about it too", project=PERSONAL_ID, filed_by=stamp)
    view = apply_ops(env, [own, placed])
    found = {a.data["text"]: a.data for a in view.list("action")}
    assert found["Call about it"]["filed_by"] is None and found["Call about it"]["project"] is None
    assert found["Call about it too"]["filed_by"] is None and found["Call about it too"]["project"] == PERSONAL_ID


@pytest.mark.parametrize("context", [{"actor": "pm"}, {"confirmed_by_pm": True}])
def test_a_reason_for_filing_that_arrives_where_no_filing_is_done_is_not_kept(env, context):
    stamp = {"by": "word", "word": "made up", "project": BUSINESS_ID}
    view = apply_ops(env, [new_op(text="Call them back", project=PERSONAL_ID, filed_by=stamp)], **context)
    kept = next(a for a in view.list("action") if a.data["text"] == "Call them back")
    assert kept.data["project"] == PERSONAL_ID and kept.data["filed_by"] is None


def test_the_demo_workspaces_give_a_project_an_alias_and_the_language_everyday_words():
    for demo in (DEMO_A, DEMO_B):
        assert any(p.get("aliases") for p in fixture_records(demo, "project"))
        language = load_yaml((demo / "config" / "language.yaml").read_text(encoding="utf-8"))
        assert language["everyday_words"]


# ---- the line and the page say why, and Move is the person's own change that teaches ------------------------------


def filed_action(env, text):
    """An action the assistant filed under the business by a configured word, as the applier writes it."""
    view = apply_ops(env, [new_op(text=text)])
    return next(a for a in view.list("action") if a.data["text"] == text)


def test_the_page_says_why_and_names_the_other_side_to_move_to(env):
    ws, cfg, store = env
    action = filed_action(env, f"About {BUSINESS_WORD}")
    shown = page(store, "action", action.id, pm=None, cfg=cfg)
    assert shown["filed"] == {
        "by": "word",
        "word": BUSINESS_WORD,
        "project": BUSINESS_ID,
        "project_name": BUSINESS_PROJECT_NAME,
        "move_to": PERSONAL_ID,
        "move_to_name": PERSONAL_PROJECT_NAME,
        "field": "project",
        "version": action.version,
    }
    assert all(row["field"] != "filed_by" for row in shown["details"])
    # What people placed says nothing; so does an item that has since been moved by hand.
    by_people = apply_ops(env, [new_op(text="By people", owners=[name_of(BUSINESS_PEOPLE[0])])])
    placed = next(a for a in by_people.list("action") if a.data["text"] == "By people")
    assert page(store, "action", placed.id, pm=None, cfg=cfg)["filed"] is None


def test_move_changes_the_items_project_as_the_person_records_one_correction_and_undo_restores_it(env):
    ws, cfg, store = env
    action = filed_action(env, f"About {BUSINESS_WORD}")
    filed = sides.filed_view(store.read(), cfg, "action", action)
    op = {
        "op": "record.edit",
        "record": {"kind": "action", "id": action.id},
        "fields": {filed["field"]: filed["move_to"]},
        "read_version": filed["version"],
    }
    changeset = apply_as_person(store, cfg, [op], "Changed on screen")
    moved = store.read().get("action", action.id)
    assert moved.data["project"] == PERSONAL_ID
    assert sides.filed_view(store.read(), cfg, "action", moved) is None  # the line goes once it is moved
    corrections = [s for s in store.read().list("signal") if s.data["kind"] == "edited" and action.id in s.data["refs"]]
    assert len(corrections) == 1 and "project" in corrections[0].data["note"]
    assert BUSINESS_ID in corrections[0].data["note"] and PERSONAL_ID in corrections[0].data["note"]
    assert undo(store, changeset).restored
    back = store.read().get("action", action.id)
    assert back.data["project"] == BUSINESS_ID
    assert sides.filed_view(store.read(), cfg, "action", back)["move_to"] == PERSONAL_ID  # the line comes back


def test_a_question_moves_by_its_list_of_projects_and_that_is_a_correction_too(env):
    _, cfg, store = env
    title = f"About {BUSINESS_WORD}?"
    view = apply_ops(env, [new_op("question.add", to=cfg.workspace.user.person, title=title)])
    question = next(q for q in view.list("question") if q.data["title"] == title)
    filed = sides.filed_view(view, cfg, "question", question)
    assert question.data["projects"] == [BUSINESS_ID]
    assert filed["field"] == "projects" and filed["move_to"] == PERSONAL_ID
    op = {
        "op": "record.edit",
        "record": {"kind": "question", "id": question.id},
        "fields": {"projects": [filed["move_to"]]},
        "read_version": filed["version"],
    }
    apply_as_person(store, cfg, [op], "Changed on screen")
    assert store.read().get("question", question.id).data["projects"] == [PERSONAL_ID]
    corrections = [
        s for s in store.read().list("signal") if s.data["kind"] == "edited" and question.id in s.data["refs"]
    ]
    assert len(corrections) == 1 and "projects" in corrections[0].data["note"]


def test_the_week_still_asks_which_side_once_and_what_words_filed_says_why(env):
    projects, lines, before = run_week(env)
    asks = [line for line in lines if line.kind == "unfiled"]
    assert len(asks) == 1 and asks[0].state == "which_side"
    _, _, store = env
    by_words = [a for a in store.read().list("action") if (a.data.get("filed_by") or {}).get("by") == "alias"]
    assert len(by_words) == 1
    assert by_words[0].data["filed_by"]["project"] == BUSINESS_ID and by_words[0].data["filed_by"]["word"]


def test_what_changed_carries_why_a_new_item_was_filed_and_where_it_can_move(env):
    ws, cfg, store = env
    at = NOW
    with store.transaction() as tx:
        request = tx.create(
            "request", {"task": "notes", "origin": "input", "state": "done", "created_at": at.isoformat()}, _PM
        ).id
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request, None, "", f"said so {BUSINESS_WORD}", "untrusted"),
    )
    ops = [
        new_op(text=f"By words {BUSINESS_WORD}", owners=[cfg.workspace.user.person]),
        new_op(text="By people", owners=[name_of(BUSINESS_PEOPLE[0])]),
        new_op(text="By nothing", owners=[cfg.workspace.user.person]),
    ]
    cs = CHANGESET.validate_python(
        {"ops": [o.model_dump(mode="json", exclude_none=True) for o in ops]}, context={"op_models": store.plugins.ops}
    )
    apply_changeset(cs, [], ctx, run=None, now=at)
    plan = since_yesterday.build(ws, store.read(), cfg, People(store, cfg), at + timedelta(hours=1))
    texts = {a.id: a.data["text"] for a in store.read().list("action")}
    found = {texts[e.record[1]]: e.filed for e in plan.entries if e.record and e.record[0] == "action"}
    assert found["By words " + BUSINESS_WORD]["by"] == "word"
    assert found["By words " + BUSINESS_WORD]["word"] == BUSINESS_WORD
    assert found["By words " + BUSINESS_WORD]["move_to"] == PERSONAL_ID
    assert found["By people"] is None and found["By nothing"] is None


# ---- the screens' routes -------------------------------------------------------------------------------------------


def test_a_projects_aliases_are_set_and_listed_and_an_items_page_carries_its_filing(api):
    client, ws, store = api
    business = client.post("/api/setup/business", json={"name": "Business"}).json()["project"]
    assert client.post(f"/api/projects/{business}", json={"aliases": [BUSINESS_CODE, PERSONAL_CODE]}).status_code == 200
    listed = {p["id"]: p for p in client.get("/api/projects").json()}
    assert listed[business]["aliases"] == [BUSINESS_CODE, PERSONAL_CODE]
    made = client.post("/api/projects", json={"name": "Other", "aliases": [BUSINESS_CODE + "-2"]})
    assert made.status_code == 200
    assert client.get("/api/projects").json()[-1]["aliases"] == [BUSINESS_CODE + "-2"]
    personal = ws.config(env={}).workspace.project.personal
    with store.transaction() as tx:
        action = tx.create(
            "action",
            {
                "text": "Do it",
                "project": business,
                "owners": [{"person": ws.config(env={}).workspace.user.person}],
                "filed_by": {"by": "domain", "word": BUSINESS_DOMAIN, "project": business},
            },
            _PM,
        )
    shown = client.get(f"/api/record-pages/{action.id}", params={"kind": "action"}).json()
    assert shown["filed"] == {
        "by": "domain",
        "word": BUSINESS_DOMAIN,
        "project": business,
        "project_name": "Business",
        "move_to": personal,
        "move_to_name": store.read().get("project", personal).data["name"],
        "field": "project",
        "version": action.version,
    }
    moved = client.post(
        "/api/records/edit",
        json={"kind": "action", "id": action.id, "fields": {"project": personal}, "read_version": action.version},
    )
    assert moved.status_code == 200
    assert client.get(f"/api/record-pages/{action.id}", params={"kind": "action"}).json()["filed"] is None
