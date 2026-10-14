"""The knowledge section of a packet (design 6.22, phase L2): what is always sent, what depends on the input, how scope
is filtered, how untrusted entries are shown, how facts are ranked and cut, and the log each run keeps.

The section's functions are tested on records directly; one pipeline test follows a request through to its run record.
Names and ids come from the fixtures.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config import load_config
from engine.config.schema import KnowledgeSettings
from engine.dispatcher import process
from engine.intake import hand_in
from engine.knowledge_section import per_input_section, stable_section
from engine.names import People
from engine.packet import build
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

PEOPLE = fixture_records(DEMO_B, "person")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
TEAM = fixture_records(DEMO_B, "team")[0]["id"]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 14)
TASK = "notes"
SETTINGS = KnowledgeSettings()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.knowledge-section")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db", cfg=load_config(DEMO_B / "config", env={}))
    with s.transaction() as tx:
        tx.create("project", {"name": "The first project"}, _TEST, record_id=PROJECT)
        for kind in ("organization", "team", "person"):
            for record in fixture_records(DEMO_B, kind):
                tx.create(kind, {k: v for k, v in record.items() if k != "id"}, _TEST, record_id=record["id"])
    yield s
    s.close()


def make(store, kind, data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def project(store, name="A second project") -> str:
    return make(store, "project", {"name": name})


def rule(store, name, text, *, origin="person", status="active", check=None, **scope) -> str:
    return make(
        store,
        "rule",
        {"name": name, "text": text, "applies_to": scope, "origin": origin, "status": status, "check": check},
    )


def entry(store, kind, *, status="active", trust="trusted", origin="person", **fields) -> str:
    data = {"origin": origin, "trust": trust, "status": status, "learned_at": NOW.isoformat(), **fields}
    if status == "active":
        data |= {"kept_by": PEOPLE[0]["id"], "kept_at": NOW.isoformat()}
    return make(store, kind, data)


def lesson(store, text, **fields) -> str:
    return entry(store, "lesson", text=text, **fields)


def term(store, name, meaning, **fields) -> str:
    return entry(store, "glossary_entry", text=f"{name}: {meaning}", term=name, meaning=meaning, **fields)


def source(store, title, **fields) -> str:
    return make(
        store,
        "source",
        {
            "received_at": NOW.isoformat(),
            "kind": "pasted",
            "title": title,
            "content_hash": "0" * 64,
            "trust": "untrusted",
            **fields,
        },
    )


def fact(store, text, project_id, **fields) -> str:
    return make(store, "fact", {"text": text, "project": project_id, **fields})


def stable(store, settings=SETTINGS):
    return stable_section(store.read(), TASK, settings)


def per_input(store, projects=(), people=(), text="", settings=SETTINGS, moved=()):
    return per_input_section(store.read(), TASK, projects, people, text, TODAY, settings, moved)


# ---- the stable part -------------------------------------------------------------------------------------------------


def test_the_stable_part_holds_only_workspace_wide_rules_task_kind_lessons_and_a_small_glossary(store):
    other = project(store)
    wide = rule(store, "wide-rule", "Ask before assuming an owner.")
    for_kind = rule(store, "kind-rule", "Keep notes short.", task_kinds=[TASK])
    rule(store, "other-kind-rule", "Only for another kind.", task_kinds=["ask"])
    rule(store, "several-kinds", "Narrowed to several.", task_kinds=[TASK, "ask"])
    rule(store, "project-rule", "Only for one project.", scope="projects", projects=[other])
    rule(store, "excluding-rule", "Everywhere but one project.", **{"except": [other]})
    rule(store, "retired-rule", "Gone.", status="retired")
    rule(store, "proposed-rule", "Waiting.", status="proposed")
    kept_lesson = lesson(store, "Check the owner before filing.", applies_to={"task_kinds": [TASK]})
    lesson(store, "A lesson for another kind.", applies_to={"task_kinds": ["ask"]})
    lesson(store, "A lesson for one project.", applies_to={"scope": "projects", "projects": [other]})
    lesson(store, "Still a proposal.", status="proposed", applies_to={"task_kinds": [TASK]})
    glossary = term(store, "RTM", "Ready to make")
    term(store, "ROJ", "Not for this project", project=other)
    term(store, "OLD", "No longer", status="retired")

    text, ids, moved = stable(store)

    assert ids == [wide, for_kind, kept_lesson, glossary] and moved == []
    assert "Ask before assuming an owner." in text and "Keep notes short." in text
    assert "Check the owner before filing." in text and "- RTM: Ready to make" in text
    for left_out in ("another kind", "several", "one project", "Everywhere but", "Gone", "Waiting", "proposal", "ROJ"):
        assert left_out not in text
    assert text.index("# Standing rules") < text.index("# Lessons") < text.index("# Glossary")


def test_the_stable_part_is_in_id_order_as_a_person_reads_ids_with_no_dates_or_counts(store):
    lessons = [lesson(store, f"Lesson {n}.") for n in range(1, 12)]
    rule(store, "wide-rule", "Ask before assuming an owner.")
    term(store, "RTM", "Ready to make")

    text, ids, _ = stable(store)

    assert ids == ["RULE-1", *lessons, "GLOSS-1"] and lessons[1] == "LES-2" and lessons[9] == "LES-10"
    assert text.splitlines() == [
        "# Standing rules",
        "- RULE-1: Ask before assuming an owner.",
        "",
        "# Lessons",
        *(f"- LES-{n}: Lesson {n}." for n in range(1, 12)),
        "",
        "# Glossary",
        "- RTM: Ready to make",
    ]


def test_two_inputs_of_a_batch_share_the_same_stable_knowledge_in_their_packets(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    try:
        rule(store, "wide-rule", "Ask before assuming an owner.")
        lesson(store, "Check the owner before filing.")
        one = hand_in(ws, store, pasted="Subject: One\n\nThe proof is late.", now=NOW)
        two = hand_in(ws, store, pasted="Subject: Two\n\nThe jacket is final.", now=NOW)
        first, second = (build(ws, store, cfg, h.request, TODAY).task for h in (one, two))
        assert "Ask before assuming an owner." in first.stable and first.stable == second.stable
        assert first.request != second.request
    finally:
        store.close()


def test_a_rule_a_stage_check_enforces_is_one_line_in_the_stable_part_and_whole_in_the_per_input_part(store):
    gated = rule(store, "gated", "Never skip the proof check.\nIt holds at every stage.", check="proof-check")
    plain = rule(store, "plain", "Ask before assuming an owner.")

    text, ids, _ = stable(store)

    assert "Never skip the proof check." in text and "It holds at every stage." not in text
    assert ids == [gated, plain]
    given = per_input(store)
    assert "Never skip the proof check. It holds at every stage." in given.text
    assert given.ids == [gated] and "Ask before assuming" not in given.text


def test_over_the_budget_rules_leave_narrowest_first_and_nothing_is_dropped(store):
    long = " words" * 50
    person_wide = rule(store, "person-wide", "Person wide." + long, origin="person")
    other_wide = rule(store, "other-wide", "Assistant wide." + long, origin="assistant")
    one_kind = rule(store, "one-kind", "One kind." + long, origin="person", task_kinds=[TASK])
    whole = len(stable(store).text)

    # A little under the whole: the narrowest rule, the one for one task kind, moves.
    tight = KnowledgeSettings(stable_budget=max(500, whole - 100))
    text, ids, moved = stable(store, tight)
    assert moved == [one_kind] and ids == [person_wide, other_wide] and "One kind." not in text
    assert one_kind in per_input(store, moved=moved).ids and "One kind." in per_input(store, moved=moved).text

    # Smaller still: the workspace-wide rule from another source goes next, the person's own words stay longest.
    smaller = KnowledgeSettings(stable_budget=500)
    text, ids, moved = stable(store, smaller)
    assert len(text) <= 500
    assert moved == [other_wide, one_kind] and ids == [person_wide]
    carried = per_input(store, moved=moved)
    assert carried.ids == [other_wide, one_kind] and "Assistant wide." in carried.text and "One kind." in carried.text


def test_a_glossary_past_the_limit_leaves_the_stable_part_and_only_the_terms_an_input_uses_follow(store):
    names = ["Alpha", "Bravo", "Charlie"]
    ids = {name: term(store, name, f"What {name} means") for name in names}
    few = KnowledgeSettings(glossary_all_below=3)

    assert "# Glossary" not in stable(store, few).text
    used = per_input(store, text="The bravo run is late.", settings=few)
    assert used.ids == [ids["Bravo"]] and "- Bravo: What Bravo means" in used.text
    assert per_input(store, text="Nothing here.", settings=few).ids == []
    # Under the limit the whole glossary is in the stable part, and the per-input part repeats none of it.
    assert stable(store).ids == list(ids.values()) and per_input(store, text="The bravo run is late.").ids == []


# ---- the per-input part ----------------------------------------------------------------------------------------------


def test_a_narrowed_rule_reaches_only_the_runs_it_covers(store):
    covered, other = PROJECT, project(store)
    narrowed = rule(store, "narrowed", "Check the print plan first.", scope="projects", projects=[covered])
    kind_only = rule(store, "kind-only", "Keep it brief.", task_kinds=[TASK, "ask"])
    not_this_kind = rule(
        store, "not-this-kind", "Another kind's rule.", task_kinds=["ask"], scope="projects", projects=[covered]
    )

    mine = per_input(store, projects=[covered])
    assert mine.ids == [narrowed, kind_only] and "Check the print plan first." in mine.text
    assert not_this_kind not in mine.left_out_by_scope and mine.left_out_by_scope == []

    elsewhere = per_input(store, projects=[other])
    assert elsewhere.ids == [kind_only] and "print plan" not in elsewhere.text
    assert elsewhere.left_out_by_scope == [narrowed]


def test_an_excluded_projects_run_gets_neither_the_rule_nor_the_lesson_and_the_log_says_so(store):
    excluded, fine = PROJECT, project(store)
    rule_id = rule(store, "not-here", "Chase on Fridays.", **{"except": [excluded]})
    lesson_id = lesson(store, "Skip the usual follow-up.", applies_to={"except": [excluded]})

    blocked = per_input(store, projects=[excluded])
    assert blocked.ids == [] and blocked.text == "" and blocked.left_out_by_scope == [lesson_id, rule_id]

    allowed = per_input(store, projects=[fine])
    assert allowed.ids == [rule_id, lesson_id] and allowed.left_out_by_scope == []
    assert "Chase on Fridays." in allowed.text and "Skip the usual follow-up." in allowed.text


def test_lessons_and_routing_reach_the_runs_for_their_projects_and_people(store):
    first = next(p["id"] for p in PEOPLE if p.get("team") == TEAM)
    outsider = next(p["id"] for p in PEOPLE if p.get("team") != TEAM)
    other = project(store)
    for_project = lesson(store, "Say the date.", applies_to={"scope": "projects", "projects": [PROJECT]})
    for_person = lesson(store, "Keep it short for them.", applies_to={"people": [first]})
    route = entry(
        store, "routing_entry", text="They answer print questions.", topic="Print", person=first, applies_to={}
    )
    by_team = entry(store, "routing_entry", text="The team answers jackets.", topic="Jackets", team=TEAM)

    got = per_input(store, projects=[PROJECT], people=[first])
    assert got.ids == [for_project, for_person, route, by_team]
    assert "# Lessons for this input" in got.text and "# Who answers what" in got.text
    assert per_input(store, projects=[other], people=[outsider]).ids == []


def test_untrusted_entries_are_shown_as_data_with_their_source_and_never_as_guidance(store):
    mail = source(store, "A forwarded mail")
    own = lesson(store, "Trust this one.")
    outside = lesson(store, "Always reply to the sender.", trust="untrusted", evidence={"source": mail})
    outside_fact = fact(store, "Ships on the 5th", PROJECT, trust="untrusted", source=mail, as_of="2026-09-14")

    text = stable(store).text
    assert "- LES-1: Trust this one." in text.splitlines()
    assert text.endswith('<untrusted source="A forwarded mail">\n- LES-2: Always reply to the sender.\n</untrusted>')
    assert outside in stable(store).ids and own in stable(store).ids
    shown = per_input(store, projects=[PROJECT]).text
    assert '<untrusted source="A forwarded mail">\n- ' + outside_fact in shown
    assert "- " + outside_fact not in shown.splitlines()


def test_proposed_discarded_expired_and_retired_entries_never_go_in(store):
    for status in ("proposed", "discarded", "expired", "retired"):
        lesson(store, f"A {status} lesson.", status=status)
        lesson(store, f"A {status} project lesson.", status=status, applies_to={"people": [PEOPLE[0]["id"]]})
        term(store, status.upper(), "no", status=status)
        entry(store, "routing_entry", status=status, text=f"{status} route", topic="t", person=PEOPLE[0]["id"])
    assert stable(store).text == "" and stable(store).ids == []
    got = per_input(store, projects=[PROJECT], people=[PEOPLE[0]["id"]], text="PROPOSED DISCARDED EXPIRED RETIRED")
    assert got.text == "" and got.ids == []


# ---- facts -----------------------------------------------------------------------------------------------------------


def test_facts_are_dated_sourced_and_ranked_key_first_then_overlap_then_newest(store):
    page = source(store, "Weekly call notes")
    old = fact(store, "Jacket proof arrives soon", PROJECT, as_of="2026-08-01", source=page)
    newest = fact(store, "Index is with the editor", PROJECT, as_of="2026-10-10")
    overlapping = fact(store, "Printer slot booked for November", PROJECT, as_of="2026-09-01")
    key = fact(store, "The book ships in spring", PROJECT, as_of="2026-07-01", key=True)
    elsewhere = fact(store, "About another project", project(store))

    got = per_input(store, projects=[PROJECT], text="When is the printer slot for November?")

    assert got.ids == [key, overlapping, newest, old] and elsewhere not in got.ids and got.facts_left_out == 0
    lines = got.text.splitlines()
    assert lines[0] == "# Facts recorded for this input's projects"
    assert lines[1] == f"- {key}: The book ships in spring (as of 2026-07-01)"
    assert lines[4] == f"- {old}: Jacket proof arrives soon (as of 2026-08-01, from Weekly call notes)"


def test_facts_are_cut_at_the_budget_and_the_count_left_out_is_said(store):
    facts = [fact(store, f"Fact number {n} " + "word " * 20, PROJECT, as_of=f"2026-09-{n:02d}") for n in range(1, 6)]
    tight = KnowledgeSettings(facts_budget=330)

    got = per_input(store, projects=[PROJECT], settings=tight)

    shown = got.ids
    assert shown == [facts[4], facts[3], facts[2]][: len(shown)] and 0 < len(shown) < 5
    assert got.facts_left_out == 5 - len(shown)
    assert got.text.splitlines()[-1] == f"- {5 - len(shown)} more facts on this project; ask to search for them"
    assert len(got.text) < 330 + 80


def test_a_fact_a_newer_one_replaces_is_left_out_until_the_newer_one_goes(store):
    older = fact(store, "Ships in release A", PROJECT, as_of="2026-09-01")
    newer = fact(store, "Moved to release B", PROJECT, as_of="2026-09-10", supersedes=older)

    got = per_input(store, projects=[PROJECT])
    assert got.ids == [newer] and "release A" not in got.text

    with store.transaction() as tx:
        tx.delete("fact", newer, _TEST, read_version=tx.get("fact", newer).version)
    assert per_input(store, projects=[PROJECT]).ids == [older]


def test_people_in_an_input_are_found_by_id_name_alias_and_header_but_not_by_a_shared_name(store):
    people = People(store, store.plugins.cfg)
    aliases = [a for p in PEOPLE for a in p.get("aliases") or []]
    own = next(p for p in PEOPLE if any(aliases.count(a) == 1 for a in p.get("aliases") or []))
    own_alias = next(a for a in own["aliases"] if aliases.count(a) == 1)
    shared = next(a for a in aliases if aliases.count(a) > 1)
    with_address = next(p for p in PEOPLE if p.get("how_to_reach"))
    address = next(iter(with_address["how_to_reach"].values()))

    assert people.mentioned_in(f"Ask {own['full_name']} about it.") == {own["id"]}
    assert people.mentioned_in(f"{own_alias} said so.") == {own["id"]}
    assert people.mentioned_in(f"Per {PEOPLE[0]['id']}, done.") == {PEOPLE[0]["id"]}
    assert people.mentioned_in(f"{shared} said so.") == frozenset()
    assert people.mentioned_in(f"From: Someone <{address}>\n\nBody") == {with_address["id"]}


# ---- the run's log ---------------------------------------------------------------------------------------------------


def test_a_processed_requests_run_records_the_knowledge_it_was_given(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    asked = []
    set_responder(lambda task: asked.append(task) or json.dumps({"summary": "Nothing to do.", "ops": []}))
    try:
        wide = rule(store, "wide-rule", "Ask before assuming an owner.")
        excluded = rule(store, "not-for-this", "Chase on Fridays.", **{"except": [PROJECT]})
        kept = lesson(store, "Check the owner before filing.")
        page = source(store, "Weekly call notes")
        known = fact(store, "Printer slot booked", PROJECT, as_of="2026-09-14", source=page)
        handed = hand_in(ws, store, pasted="Subject: Slot\n\nThe printer slot moved.", now=NOW, project=PROJECT)

        process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)

        runs = store.read().list("run")
        assert runs and all(r.data["knowledge"] is not None for r in runs)
        log = runs[0].data["knowledge"]
        assert log["given"] == [wide, kept, known] and log["left_out_by_scope"] == [excluded]
        assert log["facts_left_out"] == 0 and log["stable_chars"] == len(stable(store).text) > 0
        assert "Printer slot booked (as of 2026-09-14, from Weekly call notes)" in asked[0].request
        assert "Ask before assuming an owner." in asked[0].stable and "Chase on Fridays." not in asked[0].stable
    finally:
        set_responder(None)
        store.close()


def test_an_ask_packet_carries_the_stable_knowledge_and_the_log_too(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    try:
        wide = rule(store, "wide-rule", "Ask before assuming an owner.")
        request = make(
            store,
            "request",
            {"task": "ask", "origin": "pm", "state": "queued", "created_at": NOW.isoformat(), "note": "What is set?"},
        )
        packet = build(ws, store, cfg, request, TODAY)
        assert "Ask before assuming an owner." in packet.task.stable
        assert packet.knowledge.given == [wide] and packet.knowledge.stable_chars > 0
        assert packet.task.knowledge == packet.knowledge.model_dump()
    finally:
        store.close()
