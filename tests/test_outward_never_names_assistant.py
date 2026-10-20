"""Outward material never names the assistant (design 6.7, 6.12; roadmap B-7).

What others read (a history line, a reporter, an author, the text of a shared item) never holds one of the names the
assistant has gone by, whoever wrote it, and a history row's source is the evidence: the input and its date, or the
person for their own note. Guarded four times: the op check (an invariant), the render for readers, the send step, and
the sweep of what was already written. Names, ids and words come from the fixtures and the settings.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import outward
from engine.applier import Context, Inputs, apply_changeset, release, undo
from engine.config.schema import WorkspaceFile
from engine.history import changes_for_readers
from engine.names import People
from engine.ops import CHANGESET
from engine.plugin_api import ReadView
from engine.settings import fingerprint, save
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_knowledge_records import apply, request, source

TOKEN = "outward-token"
_TEST = WriteContext(actor="pm", trust="trusted", op="test.outward")
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
RECEIVED = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
DEFAULT_NAME = WorkspaceFile.model_fields["assistant_name"].default
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
OPEN = [
    a
    for a in fixture_records(DEMO_B, "action")
    if a.get("status", "open") == "open" and a.get("owners") and a["owners"][0]["person"] != "PER-1"
]
DELIVERED = "She sent it yesterday"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.store, cfg, ws


def name_of(cfg) -> str:
    return cfg.workspace.assistant_name


def rename(ws, cfg, store, new: str):
    saved = save(
        ws,
        cfg,
        store,
        changes={"workspace.assistant_name": new},
        reset=[],
        read_fingerprint=fingerprint(ws.config_dir),
    )
    return ws.config(env={}), saved


def log_op(text: str) -> dict:
    return {"op": "record.log", "project": PROJECT, "text": text}


def from_input(store, cfg, ops, **fields):
    src = source(store, received_at=RECEIVED, title="Sync notes", **fields)
    return src, apply(store, cfg, ops, origin="input", trust="untrusted", source_id=src, raw=DELIVERED)


def status_row(store, action_id):
    rows = changes_for_readers(store.read(), "action", action_id)
    return [r for r in rows if r["field"] == "status"][-1]


# ---- the owner's three tests ----------------------------------------------------------------------------------------


def test_closing_someones_action_from_an_unattributed_input_writes_a_row_sourced_by_the_input(env):
    _, cfg, store = env
    target = OPEN[0]
    src, (cs_id, result) = from_input(
        store, cfg, [{"op": "action.close", "id": target["id"], "evidence": {"quote": DELIVERED}}]
    )
    assert result == ["held"]
    release(store, cfg, cs_id, 0)
    closed = store.read().get("action", target["id"]).data
    assert closed["status"] == "done" and closed["reported_by"] is None  # the input names no one known person
    row = status_row(store, target["id"])
    expected = cfg.language.messages.source_input.format(date="Oct 14", what="Sync notes")
    assert row["source"] == expected
    assert outward.name_in(row["source"], outward.assistant_names(store.read(), name_of(cfg))) is None
    assert row["actor"] != "assistant"


def test_an_op_for_what_others_read_naming_the_assistant_is_refused_with_the_reason(env):
    _, cfg, store = env
    name = name_of(cfg)
    for text in (f"Reported by {name}, Oct 20", f"{name.upper()} PM judgment, Oct 6"):
        cs_id, result = apply(store, cfg, [log_op(text)], origin="input", trust="untrusted", source_id=source(store))
        assert result == ["refused"]
        reason = store.read().get("changeset", cs_id).data["ops"][0]["reason"]
        assert name in reason and "others read" in reason
    assert store.read().get("project", PROJECT).data.get("log", []) == []
    # Another word that only contains the name, and the same text with the name taken out, go through.
    for text in (f"{name}ton shipped the proofs", "Reported by the Oct 14 sync notes"):
        assert apply(store, cfg, [log_op(text)], origin="input", trust="untrusted", source_id=source(store))[1] == [
            "applied"
        ]
    # A reporter or an author is checked on every op, and so is the text of a question to someone else.
    fact = {"op": "fact", "text": "A date was agreed.", "said_by": name, "evidence": {"quote": DELIVERED}}
    assert apply(store, cfg, [fact], origin="input", trust="untrusted", source_id=source(store), raw=DELIVERED)[1] == [
        "refused"
    ]


def test_renaming_the_assistant_blocks_the_new_name_and_the_old_one_on_what_others_read(env):
    ws, cfg, store = env
    old = name_of(cfg)
    new_cfg, _ = rename(ws, cfg, store, "Pip")
    names = outward.assistant_names(store.read(), name_of(new_cfg))
    assert {n.lower() for n in names} >= {old.lower(), "pip", DEFAULT_NAME.lower()}
    for blocked in (old, "Pip", "pip", DEFAULT_NAME):
        _, result = apply(
            store, new_cfg, [log_op(f"Noted by {blocked}")], origin="input", trust="untrusted", source_id=source(store)
        )
        assert result == ["refused"], blocked


# ---- one test per guard ---------------------------------------------------------------------------------------------


def test_the_render_for_readers_leaves_an_assistant_source_out_and_shows_the_evidence(env):
    _, cfg, store = env
    target = OPEN[0]
    src, (cs_id, _) = from_input(
        store, cfg, [{"op": "action.close", "id": target["id"], "evidence": {"quote": DELIVERED}}]
    )
    release(store, cfg, cs_id, 0)
    # An assistant's own change from the same input reads as the input too, never as the assistant.
    rec = store.read().get("action", target["id"])
    own = request(store, "input", source=src)
    with store.transaction() as tx:
        tx.update(
            "action",
            target["id"],
            {"notes": "Checked"},
            WriteContext("assistant", "untrusted", "record.set#0", cs_id, own),
            read_version=rec.version,
        )
    rows = changes_for_readers(store.read(), "action", target["id"])
    assert rows and all(r["actor"] in ("pm", "input") for r in rows)
    assert all(r["source"] for r in rows)
    assert not any("assistant" in str(r["actor"]).lower() for r in rows)
    changes = ReadView(store.read(), "demo").changes("action", target["id"])
    assert [c.actor for c in changes] == [r["actor"] for r in rows]
    assert [c.source for c in changes] == [r["source"] for r in rows]
    # What the person's own screens show is untouched: the ledger still says who did it.
    assert any(e["actor"] == "assistant" for e in store.read().ledger(kind="action", record_id=target["id"]))


def test_the_send_step_refuses_what_still_names_the_assistant_and_says_where(api):
    client, base, store, cfg, _ = api
    name = name_of(cfg)
    target = OPEN[0]
    owner = target["owners"][0]["person"]
    sections = {s["person"]: s for s in client.get(f"{base}/followups").json()}
    assert sections[owner]["message"] and sections[owner].get("withheld") is None
    rec = store.read().get("action", target["id"])
    with store.transaction() as tx:  # written before the guard existed, or before a rename
        tx.update("action", target["id"], {"text": f"{target['text']} ({name})"}, _TEST, read_version=rec.version)
    shown = {s["person"]: s for s in client.get(f"{base}/followups").json()}[owner]
    assert shown["message"] == "" and name in shown["withheld"]
    refused = client.post(f"{base}/followups/{owner}/mark-sent", json={"text": f"Hello {name}"})
    assert refused.status_code == 409 and name in refused.json()["detail"]
    with pytest.raises(StoreError) as caught:
        outward.check_outgoing(store.read(), cfg, {"the message to Ana": f"From {name}"})
    assert "the message to Ana" in str(caught.value) and name in str(caught.value)
    outward.check_outgoing(store.read(), cfg, {"the message": "Nothing here"})


def test_the_sweep_resources_an_old_row_from_the_ledger_and_keeps_its_date(env):
    _, cfg, store = env
    name = name_of(cfg)
    src = source(store, received_at=RECEIVED, title="Sync notes")
    req = request(store, "input", source=src)
    rec = store.read().get("project", PROJECT)
    line = {"on": "2026-10-08", "text": f"Reported by {name}, 10/8"}
    with store.transaction() as tx:  # a line written before the guard, with the ledger's evidence behind it
        tx.update(
            "project",
            PROJECT,
            {"log": [line]},
            WriteContext("assistant", "untrusted", "record.log#0", "CS-OLD", req, {"source": src, "quote": "x"}),
            read_version=rec.version,
        )
    cs_id = outward.sweep(store, cfg)
    assert cs_id is not None
    kept = store.read().get("project", PROJECT).data["log"]
    assert [e["on"] for e in kept] == ["2026-10-08"]
    assert name not in kept[0]["text"] and "Sync notes" in kept[0]["text"]
    assert outward.sweep(store, cfg) is None  # nothing left to do
    assert any(e["changeset"] == cs_id for e in store.read().ledger(kind="project", record_id=PROJECT))
    assert undo(store, cs_id).restored == [0]  # the core's own change, with Undo
    assert store.read().get("project", PROJECT).data["log"] == [line]


def test_a_rename_sweeps_and_the_sweep_runs_when_the_app_starts(api):
    client, base, store, cfg, ws = api
    old = name_of(cfg)
    rec = store.read().get("project", PROJECT)
    with store.transaction() as tx:
        tx.update(
            "project",
            PROJECT,
            {"log": [{"on": "2026-10-06", "text": f"{old} PM judgment, 10/6"}]},
            _TEST,
            read_version=rec.version,
        )
    new_cfg, _ = rename(ws, cfg, store, "Pip")
    log = store.read().get("project", PROJECT).data["log"]
    assert old not in log[0]["text"] and log[0]["on"] == "2026-10-06"
    assert outward.sweep(store, new_cfg) is None


def test_the_sweeps_change_is_listed_in_what_changed_and_undone_from_there(api):
    client, base, store, cfg, _ = api
    rec = store.read().get("project", PROJECT)
    line = {"on": "2026-10-06", "text": f"{name_of(cfg)} PM judgment, 10/6"}
    with store.transaction() as tx:
        tx.update("project", PROJECT, {"log": [line]}, _TEST, read_version=rec.version)
    cs_id = outward.sweep(store, cfg)
    listed = client.get(f"{base}/changes")
    assert listed.status_code == 200
    assert cs_id in {(item["changeset"] or {}).get("id") for item in listed.json()}
    undone = client.post(f"{base}/changesets/{cs_id}/undo", json={})
    assert undone.status_code == 200
    assert store.read().get("project", PROJECT).data["log"] == [line]


def test_the_sweep_runs_when_the_app_starts(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    rec = store.read().get("project", PROJECT)
    line = {"on": "2026-10-06", "text": f"{name_of(cfg)} PM judgment, 10/6"}
    with store.transaction() as tx:
        tx.update("project", PROJECT, {"log": [line]}, _TEST, read_version=rec.version)
    store.close()
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}):
        kept = app.state.store.read().get("project", PROJECT).data["log"]
    assert [e["on"] for e in kept] == ["2026-10-06"] and name_of(cfg) not in kept[0]["text"]


def test_the_names_are_whole_words_ignoring_case(env):
    _, cfg, store = env
    name = name_of(cfg)
    assert outward.name_in(f"Asked {name} to check", [name]) == name
    assert outward.name_in(f"{name.upper()} said", [name]) == name
    assert outward.name_in(f"a {name.lower()}ed pen", [name]) is None
    assert outward.name_in(f"{name}'s note", [name]) == name
    assert outward.names_in({"a": ["fine", {"b": f"ask {name.lower()}"}]}, [name]) == name
    people = People(store, cfg)  # the fixture's people are never taken for the assistant
    assert all(outward.name_in(people.name(p), [name_of(cfg)]) is None for p in people.records)
    own = Inputs(request(store, "pm"), None, "", "x", "trusted")
    cs = CHANGESET.validate_python(
        {"ops": [log_op(f"Kept by {name_of(cfg)}")]}, context={"op_models": store.plugins.ops}
    )
    ctx = Context(store, cfg, people, tuple(store.plugins.ops), own, actor="pm")
    # The person's own screen is the person's own words: not checked.
    cs_id = apply_changeset(cs, [], ctx, run=None)
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "applied"


def test_an_ordinary_word_that_is_also_the_default_name_counts_only_where_it_attributes():
    from engine.outward import DEFAULT_NAME, name_in

    names = [DEFAULT_NAME]
    for sentence in (f"Hire an executive {DEFAULT_NAME.lower()}", f"{DEFAULT_NAME} professor joins the review"):
        assert name_in(sentence, names) is None
    for attributed in (
        f"Reported by {DEFAULT_NAME}, 10/20",
        f"{DEFAULT_NAME}, 10/8",
        f"{DEFAULT_NAME} PM judgment, 10/6",
    ):
        assert name_in(attributed, names) == DEFAULT_NAME


def test_the_sweep_replaces_a_whole_attribution_with_the_source_not_only_the_name():
    from engine.outward import DEFAULT_NAME, _resourced

    fixed = _resourced(f"Status set at risk ({DEFAULT_NAME} PM judgment, 10/6)", [DEFAULT_NAME], "the Oct 6 sync notes")
    assert fixed == "Status set at risk (the Oct 6 sync notes)"
