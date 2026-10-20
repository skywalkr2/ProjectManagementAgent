"""Forms and settings (batch B-6a): what a refused save tells the person, and the other form fixes of the batch."""

from datetime import UTC, datetime

from tests.test_setup import client, make


def test_the_settings_say_when_the_files_last_changed_so_a_refused_save_can_say_when(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    first = c.get(f"{api}/settings").json()
    stamp = datetime.fromisoformat(first["changed_at"])
    assert stamp.tzinfo is not None and abs((datetime.now(UTC) - stamp).total_seconds()) < 3600
    import os

    for path in ws.config_dir.glob("workspace.yaml"):
        os.utime(path, (stamp.timestamp() + 600, stamp.timestamp() + 600))
    later = datetime.fromisoformat(c.get(f"{api}/settings").json()["changed_at"])
    assert (later - stamp).total_seconds() == 600


def test_a_record_says_when_it_last_changed_so_a_refused_edit_can_say_when(tmp_path):
    ws, cfg, store = make(tmp_path)
    person = store.read().list("person")[0]
    c, api = client(ws, cfg, store)
    before = c.get(f"{api}/record", params={"kind": "person", "id": person.id}).json()
    assert datetime.fromisoformat(before["changed_at"]).tzinfo is not None
    done = c.post(
        f"{api}/records/edit",
        json={"kind": "person", "id": person.id, "fields": {"role": "Moved"}, "read_version": before["version"]},
    )
    assert done.status_code == 200, done.text
    after = c.get(f"{api}/record", params={"kind": "person", "id": person.id}).json()
    assert after["version"] > before["version"]
    assert datetime.fromisoformat(after["changed_at"]) >= datetime.fromisoformat(before["changed_at"])


# ---- an unknown status stays unknown ------------------------------------------------------------------------

import pytest  # noqa: E402

from engine.applier import PROJECT_WAITS  # noqa: E402
from engine.storage import Store  # noqa: E402
from engine.workspace import init_workspace  # noqa: E402
from tests.conftest import DEMO_B  # noqa: E402
from tests.test_knowledge_records import apply, reasons, source  # noqa: E402

PAGE = "https" + "://example.com/pages/harvest"
STATED = "The harvest plan is on track and shipping next month."
NEW_NAME = "Harvest " + "Plan"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def statuses_of(store):
    return {p.data["name"]: p.data.get("status") for p in store.read().list("project")}


def a_status(store):
    """The first value of the shipped project-status list, which every workspace starts with."""
    from pathlib import Path

    import yaml

    import engine

    text = (Path(engine.__file__).parent / "defaults" / "value_lists.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)["lists"]["project-status"]["values"][0]


def test_project_add_refuses_a_status_with_no_words_behind_it(env):
    ws, cfg, store = env
    op = {"op": "project.add", "name": NEW_NAME, "status": a_status(store)}
    cs, done = apply(store, cfg, [op], origin="pm", trust="trusted", raw=STATED)
    assert done == ["refused"] and "needs evidence" in reasons(store, cs)[0]
    assert NEW_NAME not in statuses_of(store)


def test_project_add_refuses_a_status_whose_quote_is_not_in_the_input(env):
    ws, cfg, store = env
    op = {"op": "project.add", "name": NEW_NAME, "status": a_status(store), "evidence": {"quote": "words nobody wrote"}}
    _, done = apply(store, cfg, [op], origin="pm", trust="trusted", raw=STATED)
    assert done == ["refused"]


def test_project_add_with_a_stated_status_waits_for_the_person_and_keeps_the_status(env):
    ws, cfg, store = env
    status = a_status(store)
    op = {"op": "project.add", "name": NEW_NAME, "status": status, "evidence": {"quote": "is on track"}}
    given = {"origin": "input", "trust": "untrusted", "source_id": source(store), "raw": STATED}
    cs, done = apply(store, cfg, [op], **given)
    assert done == ["held"] and reasons(store, cs)[0] == PROJECT_WAITS
    _, done = apply(store, cfg, [op], confirmed=True, **given)
    assert done == ["applied"] and statuses_of(store)[NEW_NAME] == status


def test_project_add_with_no_status_leaves_it_unknown_never_not_started(env):
    ws, cfg, store = env
    _, done = apply(store, cfg, [{"op": "project.add", "name": NEW_NAME}], origin="pm", confirmed=True)
    assert done == ["applied"] and statuses_of(store)[NEW_NAME] is None


def test_a_status_the_list_does_not_have_is_refused(env):
    ws, cfg, store = env
    op = {"op": "project.add", "name": NEW_NAME, "status": "no such status", "evidence": {"quote": "is on track"}}
    _, done = apply(store, cfg, [op], origin="pm", trust="trusted", raw=STATED, confirmed=True)
    assert done == ["refused"]


def test_an_add_from_a_link_nothing_set_up_can_open_says_not_read_and_fills_nothing_from_the_link(env):
    ws, cfg, store = env
    op = {"op": "project.add", "name": NEW_NAME, "link": PAGE}
    _, done = apply(
        store, cfg, [op], origin="pm", trust="trusted", raw=f"Track this as a project, from {PAGE}", confirmed=True
    )
    assert done == ["applied"]
    project = next(p for p in store.read().list("project") if p.data["name"] == NEW_NAME)
    assert project.data.get("status") is None and not project.data.get("summary")
    assert [(link["url"], link["label"]) for link in project.data["links"]] == [
        (PAGE, "Not read: nothing set up can open this link")
    ]


def test_an_add_from_a_link_a_configured_source_holds_is_not_marked_unread(env):
    ws, cfg, store = env
    cfg.watch.sources.append(_feed_source(PAGE))
    op = {"op": "project.add", "name": NEW_NAME, "link": PAGE}
    _, done = apply(store, cfg, [op], origin="pm", trust="trusted", raw=f"From {PAGE}", confirmed=True)
    assert done == ["applied"]
    project = next(p for p in store.read().list("project") if p.data["name"] == NEW_NAME)
    assert all("Not read" not in link["label"] for link in project.data["links"])


def _feed_source(url):
    from engine.config.schema import WatchSource

    return WatchSource(id="pages", connector="feed", label="Pages", every_minutes=60, settings={"url": url})


def test_the_held_project_in_the_change_list_carries_the_not_read_note(env):
    from api.routes import _op_view
    from engine.names import People

    ws, cfg, store = env
    cs, done = apply(
        store,
        cfg,
        [{"op": "project.add", "name": NEW_NAME, "link": PAGE}],
        origin="input",
        trust="untrusted",
        source_id=source(store),
        raw=PAGE,
    )
    assert done == ["held"]
    held = store.read().get("changeset", cs).data["ops"][0]
    shown = _op_view(held, store, People(store, cfg), {}, cfg)
    assert shown.meta.note == "Not read: nothing set up can open this link"
    # A link a configured source reads says nothing.
    cfg.watch.sources.append(_feed_source(PAGE))
    assert _op_view(held, store, People(store, cfg), {}, cfg).meta.note is None


# ---- dates are lists ----------------------------------------------------------------------------------------


def test_the_date_formats_are_lists_of_known_formats_that_keep_a_value_set_outside_them(tmp_path):
    from engine.config import load_config
    from engine.settings import describe

    ws, cfg, store = make(tmp_path)
    store.close()
    shown = {s.key: s for s in describe(cfg)}
    for key, name in (
        ("language.messages.date_format", "date_formats"),
        ("language.messages.date_time_format", "date_time_formats"),
    ):
        assert shown[key].type == "choice" and shown[key].choices == name
        assert getattr(cfg.language.messages, key.rsplit(".", 1)[1]) in shown[key].options
        assert len(shown[key].options) > 3
    odd = load_config(ws.config_dir, env={}, flags={"language.messages.date_format": "%d.%m.%y"})
    kept = {s.key: s for s in describe(odd)}["language.messages.date_format"]
    assert kept.options[-1] == "%d.%m.%y"


# ---- found by the first journeys ----------------------------------------------------------------------------


def test_a_custom_address_needs_no_key_because_the_service_may_take_none(tmp_path):
    from engine.setup import known_endpoints

    custom = next(e for e in known_endpoints() if e["id"] == "other")
    assert custom["base_url"] == "" and custom["needs_key"] is False
    # A service with its own address that does need one still does.
    assert any(e["needs_key"] and e["base_url"] for e in known_endpoints())


def test_asking_a_custom_address_for_its_models_without_a_key_is_not_refused_for_want_of_one(tmp_path):
    from engine.setup import LIST_PROBLEMS, known_endpoints, list_models

    ws, cfg, store = make(tmp_path)
    store.close()
    custom = next(e for e in known_endpoints() if e["id"] == "other")
    _, problem = list_models(custom, "http://127.0.0.1:9/v1", None)
    assert problem != LIST_PROBLEMS["no_key"]


# ---- lists, not typing --------------------------------------------------------------------------------------


def _screen_items(tmp_path):
    ws, cfg, store = make(tmp_path)
    people = [p.id for p in store.read().list("person")]
    c, api = client(ws, cfg, store)
    return {i["key"]: i for i in c.get(f"{api}/settings").json()["items"]}, people, cfg


def test_the_persons_own_record_and_a_roles_tier_are_picked_from_the_people_and_tiers_that_exist(tmp_path):
    items, people, cfg = _screen_items(tmp_path)
    me = items["workspace.user.person"]
    assert me["type"] == "choice" and me["choices"] == "people" and set(people) <= set(me["options"])
    for role in ("write", "check", "research"):
        tier = items[f"ai.roles.{role}.tier"]
        assert tier["type"] == "choice" and tier["choices"] == "tiers"
        assert set(cfg.ai.tiers) <= set(tier["options"])


def test_how_an_owner_is_shown_is_picked_from_the_ways_it_can_be_written_and_keeps_one_written_by_hand(tmp_path):
    from engine.config import load_config
    from engine.settings import describe

    items, _, cfg = _screen_items(tmp_path)
    shown = items["workspace.owner_format"]
    assert shown["type"] == "choice" and shown["choices"] == "owner_formats"
    assert {"{full_name}", "{team} ({full_name})"} <= set(shown["options"])
    ws, own, store = make(tmp_path / "other")
    store.close()
    odd = load_config(ws.config_dir, env={}, flags={"workspace.owner_format": "{full_name} of {team}"})
    kept = {s.key: s for s in describe(odd)}["workspace.owner_format"]
    assert kept.options[-1] == "{full_name} of {team}"


def test_the_file_types_that_may_be_added_are_ticked_from_the_known_types_and_keep_one_added_by_hand(tmp_path):
    items, _, cfg = _screen_items(tmp_path)
    types = items["storage.files.accepted_types"]
    assert types["type"] == "list" and types["choices"] == "media_types"
    assert set(cfg.storage.files.accepted_types) <= set(types["options"])
    assert "application/pdf" in types["options"] and "text/csv" in types["options"]
