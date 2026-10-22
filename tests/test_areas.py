"""Areas of life under the personal project (design 6.32, "Personal life", S4).

An area has no end day and what a draft about it draws on stops at it: a draft in one area gets no facts, lessons or
open items from a sibling area. Which accounts read an area, and whether anything leaves the computer, is said on its
page. When enough items filed under the personal project share a word, one area is offered, and keeping the offer
starts the area and files the items as the person's own edits. Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from engine import action_work, areas, today_queue
from engine import packet as packets
from engine.intake import hand_in
from engine.records import Project
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, without_first_go

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 19)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.areas")
ZONE_UTC = {"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"}
HOSTED_HOST = "api.example.com"


def build(tmp_path, **env):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={**ZONE_UTC, **env})
    return ws, cfg, Store(ws.db_path)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = build(tmp_path)
    yield ws, cfg, store
    store.close()


_ASSISTANT = WriteContext(actor="assistant", trust="untrusted", op="notes")


def make(store, kind, **data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def made_by_the_assistant(store, kind, **data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _ASSISTANT).id


def personal_of(cfg) -> str:
    return cfg.workspace.project.personal


def tree(store, cfg) -> dict[str, str]:
    """Personal, two areas under it, a project inside the first area, and a project that is in no area."""
    personal = personal_of(cfg)
    health = make(store, "project", name="Health", area=True, parent=personal)
    home = make(store, "project", name="Garden", area=True, parent=personal)
    dental = make(store, "project", name="Dental plan", parent=health)
    trip = make(store, "project", name="Spring trip", parent=personal)
    return {"personal": personal, "health": health, "home": home, "dental": dental, "trip": trip}


def test_an_area_has_no_end_day_and_a_project_inside_it_may(env):
    _, cfg, store = env
    ids = tree(store, cfg)
    assert store.read().get("project", ids["health"]).data["area"] is True
    assert store.read().get("project", ids["dental"]).data["area"] is False
    with pytest.raises(ValueError, match="no target day"):
        Project.model_validate({"id": "PRJ-9", "name": "Health", "area": True, "target": "2027-01-01"})
    with store.transaction() as tx:
        cur = tx.get("project", ids["dental"])
        tx.update("project", ids["dental"], {"target": "2027-01-01"}, _TEST, read_version=cur.version)


def test_reach_is_the_area_what_is_inside_it_and_what_is_above_it(env):
    _, cfg, store = env
    ids = tree(store, cfg)
    view = store.read()
    assert areas.area_of(view, ids["dental"]) == ids["health"]
    assert areas.area_of(view, ids["health"]) == ids["health"]
    assert areas.area_of(view, ids["trip"]) is None and areas.area_of(view, ids["personal"]) is None
    assert areas.reach(view, [ids["dental"]]) == {ids["health"], ids["dental"], ids["personal"]}
    assert areas.reach(view, [ids["trip"]]) is None and areas.reach(view, [None]) is None
    out = areas.outside(areas.reach(view, [ids["health"]]))
    assert out({"project": ids["home"]}) and not out({"project": ids["dental"]}) and not out({"project": None})
    assert out({"projects": [ids["home"]]})  # a question names its projects in a list
    assert not areas.outside(None)({"project": ids["home"]})


def _fill(store, ids, me):
    """One of each kind of thing in each of two sibling areas and one above them, each with its own words."""
    for key in ("health", "home", "personal"):
        project = ids[key]
        make(store, "fact", text=f"The {key} fact", project=project, trust="trusted")
        make(store, "action", text=f"Do the {key} chore", owners=[{"person": me}], project=project)
        make(store, "question", to=me, title=f"Which {key} option?", projects=[project])
    for key in ("health", "home"):
        make(
            store,
            "lesson",
            text=f"The {key} lesson",
            origin="person",
            trust="trusted",
            status="active",
            learned_at=NOW.isoformat(),
            kept_by=me,
            kept_at=NOW.isoformat(),
            applies_to={"scope": "projects", "projects": [ids[key]]},
        )


def test_a_draft_in_one_area_gets_no_facts_lessons_or_records_from_a_sibling_area(env):
    ws, cfg, store = env
    me = cfg.workspace.user.person
    ids = tree(store, cfg)
    _fill(store, ids, me)

    def seen(packet) -> str:
        return "\n".join([packet.task.instructions, packet.task.stable, packet.task.request])

    # An input handed in for the health area: its own and what is above it are there, the home area's are not.
    handed = hand_in(ws, store, note="Look at this", pasted="Call about the visit.", project=ids["health"], cfg=cfg)
    text = seen(packets.build(ws, store, cfg, handed.request, TODAY))
    for kept in ("The health fact", "Do the health chore", "Which health option?", "The health lesson"):
        assert kept in text, kept
    assert "Do the personal chore" in text  # the personal project is above the area
    for left in ("The home fact", "Do the home chore", "Which home option?", "The home lesson", "| Garden"):
        assert left not in text, left

    # The same input about no project sees every area, as it did before.
    handed = hand_in(ws, store, note="Look at this", pasted="Call about the visit.", cfg=cfg)
    text = seen(packets.build(ws, store, cfg, handed.request, TODAY))
    assert "Do the home chore" in text and "Do the health chore" in text

    # The work an action in an area is handed to the assistant for follows the same reach.
    action = make(store, "action", text="Draft the note to the clinic", owners=[{"person": me}], project=ids["health"])
    request = action_work.hand_over(store, action)
    text = seen(packets.build(ws, store, cfg, request, TODAY))
    assert "The health lesson" in text and "The health fact" in text
    for left in ("The home fact", "The home lesson", "| Garden"):
        assert left not in text, left


def _with_accounts(tmp_path):
    """A workspace with a local server that takes only the private level, a hosted service that takes another, and the
    stand-in, which takes the other level too."""
    import yaml

    from engine.ai.adapters import GENERIC_ADAPTER

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    levels = ["open", "internal", "restricted"]
    data["content_levels"] = {"private": "Never leaves this computer", "other": "Everything else"}
    data["providers"]["stub"]["content_levels"] = ["other"]
    data["providers"]["localbox"] = {
        "adapter": GENERIC_ADAPTER,
        "base_url": "http://localhost:8080/v1",
        "models": {"default": "m"},
        "allowed_data": levels,
        "content_levels": ["private"],
    }
    data["providers"]["hosted"] = {
        "adapter": GENERIC_ADAPTER,
        "base_url": "https://" + HOSTED_HOST + "/v1",
        "models": {"default": "m"},
        "allowed_data": levels,
        "content_levels": ["other"],
    }
    data["tiers"] = {
        "routine": {"use": "localbox/default", "fallback": ["hosted/default"]},
        "deep": {"use": "stub/default"},
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = ws.config(env=ZONE_UTC)
    return ws, cfg


def test_a_private_area_is_read_only_by_the_accounts_that_take_its_level_and_the_line_says_where_that_runs(tmp_path):
    ws, cfg = _with_accounts(tmp_path)
    store = Store(ws.db_path)
    try:
        personal = personal_of(cfg)
        private = make(store, "project", name="Health", area=True, parent=personal, content_levels=["private"])
        found = areas.reading(store.read(), cfg, private)
        assert found.levels == ("private",)
        assert [(r.account, r.leaves) for r in found.readers] == [("localbox", False)] and found.state == "local"
        # A project inside it carries the area's level, so it is read by the same accounts.
        inside = make(store, "project", name="Dental plan", parent=private)
        assert areas.reading(store.read(), cfg, inside).levels == ("private",)
        # The other level is taken by the hosted service and the stand-in, so reading it sends material away.
        other = make(store, "project", name="Money", area=True, parent=personal, content_levels=["other"])
        found = areas.reading(store.read(), cfg, other)
        assert [r.account for r in found.readers] == ["stub", "hosted"] and found.state == "away"
        assert [r.account for r in found.readers if r.leaves] == ["stub", "hosted"]
        # A level that no account takes is read by none, and the page says nothing leaves because nothing reads it.
        odd = make(store, "project", name="Papers", area=True, parent=personal)
        cfg.ai.content_levels["nobody"] = "Nobody takes this"
        with store.transaction() as tx:
            cur = tx.get("project", odd)
            tx.update("project", odd, {"content_levels": ["nobody"]}, _TEST, read_version=cur.version)
        none = areas.reading(store.read(), cfg, odd)
        assert none.readers == () and none.state == "none"
    finally:
        store.close()


def test_the_projects_knows_page_carries_the_reading_line(tmp_path):
    from engine import project_knows

    ws, cfg = _with_accounts(tmp_path)
    store = Store(ws.db_path)
    try:
        area = make(store, "project", name="Health", area=True, parent=personal_of(cfg), content_levels=["private"])
        found = project_knows.knows(store.read(), area, cfg)
        assert found["area"] is True
        assert found["reading"] == {
            "state": "local",
            "levels": ["private"],
            "readers": [{"account": "localbox", "name": "localbox", "leaves": False}],
        }
        assert all(u["field"] != "target" for u in found["unknown"] if u["kind"] == "field")
    finally:
        store.close()


# ---- offering an area ----------------------------------------------------------------------------------------------


def _item(store, cfg, kind, text, project=None):
    """An item the assistant filed, so the person's move of it is a correction."""
    project = project or personal_of(cfg)
    if kind == "action":
        return made_by_the_assistant(
            store, "action", text=text, owners=[{"person": cfg.workspace.user.person}], project=project
        )
    if kind == "question":
        return made_by_the_assistant(store, "question", to=cfg.workspace.user.person, title=text, projects=[project])
    return made_by_the_assistant(store, "fact", text=text, project=project, trust="trusted")


def _four_dentist_items(store, cfg):
    return [
        _item(store, cfg, "action", "Book the dentist for a cleaning"),
        _item(store, cfg, "action", "Ask the dentist about the crown"),
        _item(store, cfg, "fact", "The dentist is closed on Fridays"),
        _item(store, cfg, "question", "Which dentist takes the new plan?"),
    ]


def test_an_area_is_offered_once_enough_items_share_a_word_and_never_for_everyday_words(env):
    _, cfg, store = env
    _four_dentist_items(store, cfg)
    for text in ("Pick up the grocery order", "Return the library book", "Call about the order"):
        _item(store, cfg, "action", text)
    found = areas.proposals(store.read(), cfg)
    assert [p.name for p in found] == ["Dentist"] and len(found[0].items) == 4
    # The line on Today is a suggestion: the word, the proposed name and how many items it would take.
    (line,) = [x for x in today_queue.queue(*env[:1], store, cfg, NOW) if x.kind == "area"]
    assert (line.text, line.subject, line.count) == ("Dentist", "dentist", 4) and len(line.names) == 3


def test_three_items_are_too_few_and_the_setting_turns_the_offer_off(tmp_path):
    ws, cfg, store = build(tmp_path, COCKPIT__STEWARD__AREAS__PROPOSE_AFTER="4")
    try:
        for text in ("Book the dentist", "Ask the dentist about the crown", "The dentist is closed on Fridays"):
            _item(store, cfg, "action", text)
        assert areas.proposals(store.read(), cfg) == []
        _item(store, cfg, "action", "Pay the dentist")
        assert len(areas.proposals(store.read(), cfg)) == 1
        off = ws.config(env={**ZONE_UTC, "COCKPIT__STEWARD__AREAS__PROPOSE_AFTER": "0"})
        assert areas.proposals(store.read(), off) == []
    finally:
        store.close()


def test_an_item_already_in_an_area_or_finished_is_no_part_of_the_pattern(env):
    _, cfg, store = env
    ids = tree(store, cfg)
    for text in ("Book the dentist", "Ask the dentist about the crown", "The dentist is closed on Fridays"):
        _item(store, cfg, "action", text, project=ids["health"])
    done = _item(store, cfg, "action", "Pay the dentist")
    with store.transaction() as tx:
        cur = tx.get("action", done)
        tx.update("action", done, {"status": "done"}, _TEST, read_version=cur.version)
    assert areas.proposals(store.read(), cfg) == []


def test_keeping_the_offer_starts_the_area_files_the_items_and_each_filing_is_a_correction(env):
    _, cfg, store = env
    items = _four_dentist_items(store, cfg)
    kept = areas.keep(store, cfg, "dentist")
    view = store.read()
    area = view.get("project", kept.project)
    assert area.data["name"] == "Dentist" and area.data["area"] is True and area.data["parent"] == personal_of(cfg)
    for kind, record_id in zip(("action", "action", "fact", "question"), items, strict=True):
        data = view.get(kind, record_id).data
        assert (data.get("projects") or [data.get("project")]) == [kept.project]
    assert areas.proposals(view, cfg) == []  # the offer is gone: the area exists
    corrections = [s for s in view.list("signal") if s.data["kind"] == "edited"]
    assert {r for s in corrections for r in s.data["refs"]} == set(items)  # one correction for each item moved


def test_an_offer_that_no_longer_stands_is_refused_in_plain_words(env):
    _, cfg, store = env
    with pytest.raises(StoreError, match="no longer stands"):
        areas.keep(store, cfg, "dentist")


def test_undoing_both_changes_puts_everything_back(env):
    from engine.dispatcher import undo_changeset

    _, cfg, store = env
    items = _four_dentist_items(store, cfg)
    kept = areas.keep(store, cfg, "dentist")
    undo_changeset(store, kept.filed)
    undo_changeset(store, kept.started)
    view = store.read()
    assert view.get("project", kept.project) is None or view.get("project", kept.project).deleted
    assert view.get("action", items[0]).data["project"] == personal_of(cfg)
