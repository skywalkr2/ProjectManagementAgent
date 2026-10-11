"""Organizations are records (design 5.1): a person refers to one by id, so its name lives in one place. A workspace
whose people held names is moved over when it opens; the assistant's names are matched by name or alias."""

import pytest
from fastapi.testclient import TestClient

from engine.config import load_config
from engine.storage import WriteContext
from tests.conftest import DEMO_B

W = WriteContext("pm", "trusted", "test")


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def test_people_who_held_names_are_moved_to_organizations(env):
    from engine.organizations import move_names

    _, _, store = env
    with store.transaction() as tx:
        org = tx.list("organization")[0]
        a = tx.create("person", {"full_name": "Pat Example", "org": org.data["name"].upper()}, W)
        b = tx.create("person", {"full_name": "Lee Example", "org": "  New   Place "}, W)
    assert move_names(store) == 2
    view = store.read()
    assert view.get("person", a.id).data["org"] == org.id  # matched without regard to case
    made = view.get("organization", view.get("person", b.id).data["org"])
    assert made.data["name"] == "New Place"
    assert move_names(store) == 0  # once only


def test_the_assistants_names_find_the_organization_or_make_one(env):
    from engine.organizations import resolve

    _, _, store = env
    with store.transaction() as tx:
        org = tx.list("organization")[0]
        tx.update("organization", org.id, {"aliases": ["The Shop"]}, W, read_version=org.version)
        assert resolve(tx, "the shop", W) == org.id
        assert resolve(tx, org.id, W) == org.id
        fresh = resolve(tx, "Elsewhere Ltd", W)
        assert fresh != org.id and tx.get("organization", fresh).data["name"] == "Elsewhere Ltd"
        assert resolve(tx, "  ", W) is None


def test_organizations_are_kept_from_the_screens(env):
    from api.app import create_app

    ws, cfg, store = env
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    orgs = c.get(f"{api}/organizations").json()
    assert orgs and all(o["people"] >= 0 for o in orgs)
    people = c.get(f"{api}/people").json()
    held = next(p for p in people if p["org"])
    named = next(o for o in orgs if o["id"] == held["org"])
    assert held["org_name"] == named["name"]
    assert c.post(f"{api}/organizations/{named['id']}", json={"name": "Renamed Co"}).status_code == 200
    again = next(p for p in c.get(f"{api}/people").json() if p["id"] == held["id"])
    assert again["org_name"] == "Renamed Co"  # one name, shown everywhere
    assert c.post(f"{api}/organizations/{named['id']}/remove").status_code == 409  # still in use
    new = c.post(f"{api}/organizations", json={"name": "Spare Co"}).json()["id"]
    assert c.post(f"{api}/organizations", json={"name": "spare co"}).status_code == 409
    assert c.post(f"{api}/people", json={"full_name": "Kim Example", "org": "ORG-999"}).status_code == 404
    assert c.post(f"{api}/people", json={"full_name": "Kim Example", "org": new}).status_code == 200
    unused = c.post(f"{api}/organizations", json={"name": "Gone Co"}).json()["id"]
    assert c.post(f"{api}/organizations/{unused}/remove").status_code == 200


def test_every_reference_marked_on_a_core_record_is_guarded():
    from engine.records import REFERENCES, REGISTRY, ref_fields

    for kind, model in REGISTRY.items():
        marked = set(ref_fields(model))
        assert marked <= set(REFERENCES.get(kind, [])), f"{kind}: {sorted(marked - set(REFERENCES.get(kind, [])))}"
