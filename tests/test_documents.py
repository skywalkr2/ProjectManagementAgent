"""Document panels (plugin API 0.3.51): a plugin composes a read-only page as Markdown; the core turns a small subset
into plain blocks the screens draw, with record links checked and outside links showing their domain."""

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.documents import MAX_CHARS, DocumentError, blocks
from tests.test_today_panels_jobs import FIXTURE, MANIFEST, workspace

WEB = "https" + "://"


def test_the_subset_becomes_blocks():
    text = "\n".join(
        [
            "# Start here",
            "",
            "The **plan** for *this* book, with `code`.",
            "Still the same paragraph.",
            "",
            "- one",
            "- two",
            "",
            "1. first",
            "2) second",
            "",
            "| Beat | Chapter |",
            "|---|---|",
            "| Opening | 1 |",
            "| Turn |",
            "",
            "---",
            "### Small heading",
        ]
    )
    found = blocks(text)
    assert [b["type"] for b in found] == ["heading", "paragraph", "list", "list", "table", "rule", "heading"]
    assert found[0] == {"type": "heading", "level": 1, "inlines": [{"text": "Start here"}]}
    assert found[1]["inlines"] == [
        {"text": "The "},
        {"text": "plan", "strong": True},
        {"text": " for "},
        {"text": "this", "em": True},
        {"text": " book, with "},
        {"text": "code", "code": True},
        {"text": ". Still the same paragraph."},
    ]
    assert found[2]["ordered"] is False and len(found[2]["items"]) == 2
    assert found[3]["ordered"] is True and found[3]["items"][1] == [{"text": "second"}]
    assert found[4]["header"] == [[{"text": "Beat"}], [{"text": "Chapter"}]]
    assert found[4]["rows"] == [[[{"text": "Opening"}], [{"text": "1"}]], [[{"text": "Turn"}], []]]
    assert found[6]["level"] == 3


def test_links_are_checked_and_html_stays_text():
    allowed = {("p18/goal", "GOL-1")}
    found = blocks(
        f"[Goal](record:p18/goal/GOL-1) [Gone](record:p18/goal/GOL-9) [Page]({WEB}example.com/a) "
        "[Bad](javascript:alert(1)) <script>x</script>",
        lambda kind, rid: (kind, rid) in allowed,
    )
    runs = found[0]["inlines"]
    assert {"text": "Goal", "record": {"kind": "p18/goal", "id": "GOL-1"}} in runs
    assert {"text": "Gone"} in runs
    assert {"text": "Page", "url": f"{WEB}example.com/a", "domain": "example.com"} in runs
    assert {"text": "Bad"} in runs
    assert any("<script>x</script>" in r["text"] for r in runs)


def test_a_document_too_long_is_refused():
    with pytest.raises(DocumentError):
        blocks("x" * (MAX_CHARS + 1))


CODE = FIXTURE.replace(
    "def register(registrar):\n",
    "def start_here(view, settings, project):\n"
    "    goals = view.list('p18/goal')\n"
    "    if not goals:\n"
    "        return None\n"
    "    lines = ['# Start here', '']\n"
    "    lines += [f'- [{g.data[\"title\"]}](record:p18/goal/{g.id})' for g in goals]\n"
    "    lines.append(f'Project: {project.id if project else None}')\n"
    "    return '\\n'.join(lines)\n\n"
    "def broken(view, settings, project):\n"
    "    raise RuntimeError('no')\n\n"
    "def register(registrar):\n"
    "    registrar.document('p18/start', title='Start here', render=start_here)\n"
    "    registrar.document('p18/broken', title='Broken', render=broken)\n",
)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path, CODE)
    store.close()
    manifest = dict(MANIFEST)
    manifest["provides"] = {**MANIFEST["provides"], "panels": ["p18/goals", "p18/start", "p18/broken"]}
    (ws.root / "plugins" / "p18" / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    from tests.test_plugin_api_0329 import reopen

    cfg, store = reopen(ws, cfg)
    yield ws, cfg, store
    store.close()


def test_a_document_panel_is_listed_and_read_through_the_api(env):
    from api.app import create_app
    from engine.applier import apply_as_person

    ws, cfg, store = env
    project = store.read().list("project")[0]
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    listed = {p["name"]: p for p in c.get(f"{api}/panels").json()}
    assert listed["p18/start"]["view"] == "document" and listed["p18/start"]["title"] == "Start here"
    assert c.get(f"{api}/panels/p18/start/document").json() == {"blocks": None}  # nothing yet
    apply_as_person(store, cfg, [{"op": "p18/add-goal", "title": "Map"}], "Add")
    goal = store.read().list("p18/goal")[-1]
    shown = c.get(f"{api}/panels/p18/start/document", params={"project": project.id}).json()["blocks"]
    assert shown[0]["type"] == "heading"
    link = shown[1]["items"][0][0]
    assert link["text"] == "Map" and link["record"] == {"kind": "p18/goal", "id": goal.id}
    assert shown[2]["inlines"][0]["text"] == f"Project: {project.id}"
    failed = c.get(f"{api}/panels/p18/broken/document")
    assert failed.status_code == 409 and "Broken couldn't be shown" in failed.text
    assert c.get(f"{api}/panels/p18/start/rows").status_code == 409  # a document has no rows
