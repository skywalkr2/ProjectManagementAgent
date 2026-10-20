"""What the assistant knows about one project (design 7.18): its sources and the last input from each, its facts with
who they rest on and when, the glossary terms used there, who answers what, and what is still unknown with the question
asked for it. Reads only. Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.project_knows import knows
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

_PM = WriteContext("pm", "trusted", "test")
_ASSISTANT = WriteContext("assistant", "trusted", "test")
PEOPLE = fixture_records(DEMO_B, "person")
ME, OTHER = PEOPLE[0], PEOPLE[1]
TEAM = fixture_records(DEMO_B, "team")[0]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
KEPT = {
    "origin": "person",
    "status": "active",
    "kept_by": ME["id"],
    "kept_at": NOW.isoformat(),
    "learned_at": NOW.isoformat(),
}


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    yield store, cfg
    store.close()


def make(store, kind, data, ctx=_PM) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, ctx).id


def project(store, **fields) -> str:
    return make(store, "project", {"name": "Harbor", "status": None, **fields})


def source(store, projects, title="Print notes", received="2026-10-12T09:00:00+00:00", **fields) -> str:
    return make(
        store,
        "source",
        {
            "received_at": received,
            "kind": "pasted",
            "title": title,
            "content_hash": "0" * 64,
            "trust": "trusted",
            "projects": projects,
            **fields,
        },
    )


def seen(store, cfg, prj):
    return knows(store.read(), prj, cfg)


def test_an_unknown_project_has_nothing_to_know(env):
    store, cfg = env
    assert seen(store, cfg, "PRJ-999") is None


def test_a_project_nothing_is_known_about_has_empty_sections_and_its_blank_fields_unknown(env):
    store, cfg = env
    prj = project(store)
    view = seen(store, cfg, prj)
    assert (view["sources"], view["facts"], view["terms"], view["routing"]) == ([], [], [], [])
    assert [u["field"] for u in view["unknown"]] == ["status", "phase", "target", "owner", "summary"]
    assert all(u["kind"] == "field" and u["question"] is None for u in view["unknown"])


def test_a_field_with_a_value_is_not_unknown(env):
    store, cfg = env
    prj = project(store, status="On track", owner=ME["id"], summary="A book.")
    assert [u["field"] for u in seen(store, cfg, prj)["unknown"]] == ["phase", "target"]


def test_each_source_shows_how_many_inputs_it_gave_and_the_last_one(env):
    store, cfg = env
    prj, other = project(store), project(store, name="Another")
    first = source(store, [prj], "Monday notes", "2026-10-05T09:00:00+00:00")
    latest = source(store, [prj], "Thursday notes", "2026-10-08T09:00:00+00:00")
    source(store, [prj], "A mail", "2026-10-10T09:00:00+00:00", kind="email")
    source(store, [other], "Not about this one", "2026-10-11T09:00:00+00:00")
    rows = {s["key"]: s for s in seen(store, cfg, prj)["sources"]}
    assert set(rows) == {"kind:pasted", "kind:email"}
    pasted = rows["kind:pasted"]
    assert (pasted["kind"], pasted["label"], pasted["inputs"]) == ("pasted", None, 2)
    assert pasted["last"]["id"] == latest and pasted["last"]["title"] == "Thursday notes"
    assert first != latest
    assert [s["key"] for s in seen(store, cfg, prj)["sources"]] == ["kind:email", "kind:pasted"]


def test_a_watched_source_is_named_as_set_up_and_a_removed_one_by_its_id(env):
    store, cfg = env
    prj = project(store)
    configured = cfg.watch.sources[0] if cfg.watch.sources else None
    watched = {"source": configured.id if configured else "gone", "key": "k", "change": "new"}
    source(store, [prj], "A change", watched=watched)
    source(store, [prj], "Another", watched={**watched, "source": "removed-one", "key": "j"})
    rows = {s["key"]: s for s in seen(store, cfg, prj)["sources"]}
    if configured:
        assert rows[f"watch:{configured.id}"]["label"] == (configured.label or configured.id)
    assert rows["watch:removed-one"]["label"] == "removed-one" and rows["watch:removed-one"]["kind"] is None


def test_facts_carry_who_they_rest_on_key_ones_first_and_a_replaced_one_is_not_shown(env):
    store, cfg = env
    prj = project(store)
    src = source(store, [prj], "Print notes")
    old = make(store, "fact", {"text": "The proof is due Friday.", "project": prj, "basis": "person"})
    new = make(
        store, "fact", {"text": "The proof is due Monday.", "project": prj, "basis": "person", "supersedes": old}
    )
    key = make(store, "fact", {"text": "Trim size is fixed.", "project": prj, "key": True, "basis": "person"})
    guess = make(
        store,
        "fact",
        {"text": "Both spines are in the folder.", "project": prj, "basis": "inferred", "source": src},
        _ASSISTANT,
    )
    make(store, "fact", {"text": "About another project.", "project": project(store, name="Another")})
    facts = seen(store, cfg, prj)["facts"]
    assert [f["id"] for f in facts][0] == key
    assert old not in [f["id"] for f in facts] and {new, guess} <= {f["id"] for f in facts}
    inferred = next(f for f in facts if f["id"] == guess)
    assert inferred["source"]["basis"] == "inferred" and inferred["source"]["kind"] == "note"
    assert inferred["source"]["origin"] is not None and inferred["version"] == 1
    assert next(f for f in facts if f["id"] == key)["key"] is True


def test_a_fact_with_no_source_and_no_day_of_its_own_is_dated_by_the_day_it_was_filed(env):
    store, cfg = env
    prj = project(store)
    fact = make(store, "fact", {"text": "Both spines are in the folder.", "project": prj})
    [shown] = seen(store, cfg, prj)["facts"]
    assert shown["id"] == fact and shown["source"]["kind"] is None and shown["source"]["basis"] is None
    assert shown["source"]["on"] == str(store.read().ledger(kind="fact", record_id=fact)[0]["at"])[:10]


def test_a_fact_about_a_series_of_books_reaches_the_book_only_when_it_says_so(env):
    store, cfg = env
    series = project(store, name="The series")
    book = project(store, name="Book one", parent=series)
    reaching = make(store, "fact", {"text": "All books are 5.5 by 8.5.", "project": series, "reaches_children": True})
    make(store, "fact", {"text": "The series is open to bids.", "project": series})
    assert [f["id"] for f in seen(store, cfg, book)["facts"]] == [reaching]


def term(store, text, confidence="assumed", status="active", **fields) -> str:
    data = {
        "text": f"{text}: it means something.",
        "term": text,
        "meaning": "it means something",
        "confidence": confidence,
    }
    data |= {
        "applies_to": {},
        **(KEPT if status == "active" else {"origin": "input", "status": status, "learned_at": NOW.isoformat()}),
        **fields,
    }
    data.setdefault("trust", "trusted")
    return make(store, "glossary_entry", data)


def test_terms_are_those_for_the_project_and_those_its_words_use_marked_by_how_sure(env):
    store, cfg = env
    prj = project(store)
    for_it = term(store, "spine", "confirmed", project=prj)
    used = term(store, "bleed", "assumed")
    term(store, "gutter", "confirmed")  # nothing here uses it
    term(store, "folio", "confirmed", project=project(store, name="Another"))
    make(store, "fact", {"text": "The bleed is 0.125 in.", "project": prj})
    rows = {t["id"]: t for t in seen(store, cfg, prj)["terms"]}
    assert set(rows) == {for_it, used}
    assert (rows[for_it]["term"], rows[for_it]["confidence"]) == ("spine", "confirmed")
    assert rows[used]["meaning"] == "it means something" and rows[used]["confidence"] == "assumed"


def test_a_term_that_is_still_a_proposal_is_not_in_the_glossary_but_an_unknown_one_is_still_unknown(env):
    store, cfg = env
    prj = project(store, status="On track", phase="Design", target="2027-01-10", owner=ME["id"], summary="A book.")
    make(store, "fact", {"text": "The gutter is wide.", "project": prj})
    proposed = term(store, "gutter", "unknown", status="proposed")
    kept = term(store, "bleed", "unknown", project=prj)
    view = seen(store, cfg, prj)
    assert [t["id"] for t in view["terms"]] == [kept]
    assert {(u["kind"], u["entry"]) for u in view["unknown"]} == {("term", proposed), ("term", kept)}


def ask(store, title, to=None, status="open", text="", **fields) -> str:
    return make(
        store,
        "question",
        {"to": to or OTHER["id"], "title": title, "text": text, "status": status, **fields},
    )


def test_an_unknown_term_names_the_open_question_asked_about_it_or_none(env):
    store, cfg = env
    prj = project(store, status="On track", phase="Design", target="2027-01-10", owner=ME["id"], summary="A book.")
    make(store, "fact", {"text": "The gutter and the bleed matter.", "project": prj})
    term(store, "gutter", "unknown", status="proposed")
    term(store, "bleed", "unknown", status="proposed")
    asked = ask(store, "What does gutter mean here?", projects=[prj])
    ask(store, "What does bleed mean here?", status="dropped", projects=[prj])
    ask(store, "What does bleed mean for another book?", projects=[project(store, name="Another")])
    rows = {u["term"]: u for u in seen(store, cfg, prj)["unknown"]}
    assert rows["gutter"]["question"]["id"] == asked
    assert rows["gutter"]["question"]["to_name"] == OTHER["full_name"]
    assert rows["gutter"]["question"]["status"] == "open"
    assert rows["bleed"]["question"] is None


def routing(store, topic, scope=None, **fields) -> str:
    data = {"text": f"{topic} goes to someone.", "topic": topic, "applies_to": scope or {}, **KEPT, **fields}
    data.setdefault("person", OTHER["id"])
    data.setdefault("trust", "trusted")
    return make(store, "routing_entry", data)


def test_who_answers_what_lists_the_routing_that_reaches_the_project_by_person_or_team(env):
    store, cfg = env
    prj, other = project(store), project(store, name="Another")
    everywhere = routing(store, "printing")
    by_team = routing(store, "legal", person=None, team=TEAM["id"])
    here = routing(
        store, "covers", scope={"scope": "projects", "projects": [prj]}, negative=True, look_up="the style sheet"
    )
    routing(store, "indexing", scope={"scope": "projects", "projects": [other]})
    routing(store, "proofing", status="proposed", origin="input", kept_by=None, kept_at=None)
    rows = {r["id"]: r for r in seen(store, cfg, prj)["routing"]}
    assert set(rows) == {everywhere, by_team, here}
    assert rows[everywhere]["who"] == OTHER["full_name"] and rows[by_team]["who"] == TEAM["name"]
    assert (rows[here]["negative"], rows[here]["look_up"]) == (True, "the style sheet")


def test_the_route_returns_the_view_and_an_unknown_project_is_not_found(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    app = create_app(ws, ws.config(env={}, flags={"server.base_path": "/"}), "t", ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": "Bearer t"}) as client:
        prj = project(app.state.store, name="Harbor")
        make(app.state.store, "fact", {"text": "Trim size is fixed.", "project": prj, "basis": "person"})
        found = client.get(f"/api/projects/{prj}/knows")
        assert found.status_code == 200
        body = found.json()
        assert body["id"] == prj and body["name"] == "Harbor"
        assert [f["text"] for f in body["facts"]] == ["Trim size is fixed."]
        assert client.get("/api/projects/PRJ-999/knows").status_code == 404
