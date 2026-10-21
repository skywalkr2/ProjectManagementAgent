"""Failures kept in detail so a person can send them with feedback (design 7, Help): what a report holds, what is never
in it, and how far back and how many. Names, addresses and keys come from the fixtures or are built here, never
written out."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.app import create_app
from engine import problems
from engine.ai.smoke import SmokeResult, record
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, add_example_account, fixture_records

TOKEN = "test-token-value"
WRITE = WriteContext(actor="engine", trust="trusted", op="test")
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

# Built at run time so no key-shaped text sits in the repository.
KEY = "-".join(["tk", "fixture", "Zq81Lm4Xv92Rt70Bn3Pw"])
RESOLVED = "plainresolvedvalue"  # the workspace's own secret: no key shape, found only by being a resolved secret
SCHEME, HOST = "https", "api.example.com"  # a URL is written in two parts, as code holds no URL
PACKET_TEXT = "Packet text about the quarterly reorganization of the warehouse"


def person() -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("aliases") and p.get("how_to_reach"))


def project() -> dict:
    return fixture_records(DEMO_B, "project")[0]


def address() -> str:
    return next(iter(person()["how_to_reach"].values()))


def make_run(store, at, *, provider, task, detail, outcome="error", kind="provider_down", tier="routine"):
    data = {
        "task": task,
        "provider": provider,
        "model": "example-small-model",
        "tier": tier,
        "outcome": outcome,
        "started_at": at.isoformat(),
        "error_kind": kind,
        "error_detail": detail,
    }
    with store.transaction() as tx:
        tx.create("run", data, WRITE)


def make_read(store, at, *, source, error, kind="outage", outcome="failed"):
    data = {"source": source, "started_at": at.isoformat(), "outcome": outcome, "error_kind": kind, "error": error}
    with store.transaction() as tx:
        tx.create("watch_run", data, WRITE)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXAMPLE_TEST_AI_KEY", RESOLVED)
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    ai = ws.config_dir / "ai.yaml"
    name, _, _ = add_example_account(ai)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    return ws, cfg, name


@pytest.fixture
def api(home):
    ws, cfg, name = home
    app = create_app(ws, cfg, TOKEN, ui_dist=ws.root / "no-ui")

    def boom() -> dict:
        raise RuntimeError(f"it broke for {person()['full_name']} at {address()} with {KEY}")

    app.router.routes.insert(0, APIRoute("/api/boom", boom))  # ahead of the page route that answers every other path

    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}, raise_server_exceptions=False) as client:
        yield client, app.state.store, app.state.worker, ws, cfg, name


def test_a_failed_calls_report_holds_the_parameters_and_the_error_and_no_packet_text_secret_or_address(api):
    client, store, worker, ws, cfg, account = api
    who, where = person(), project()
    task = next(iter(cfg.ai.tasks))
    # A hand-in puts text in a request record; it is never part of a report.
    assert client.post("/api/handin", json={"note": PACKET_TEXT, "pasted": ""}).status_code == 200
    echoed = (
        f'HTTP 400: {{"error": {{"message": "bad key {KEY} for {who["full_name"]} <{address()}> in {where["name"]}; '
        f'token={RESOLVED} see {SCHEME}://user:pw@{HOST}:8443/v1/secret/path?q={KEY}"}}}}'
    )
    now = datetime.now(UTC)
    make_run(store, now - timedelta(hours=1), provider=account, task=task, detail=echoed, kind="other")
    folder = ws.root / "inbox" / f"{who['full_name']} notes.txt"
    make_read(store, now - timedelta(hours=2), source="inbox", error=f"couldn't read {folder} for {who['aliases'][0]}")
    assert client.get("/api/boom").status_code == 500

    got = client.get("/api/feedback/problems")
    assert got.status_code == 200
    lines = got.json()["problems"]
    blob = json.dumps(lines)
    for hidden in (
        KEY,
        RESOLVED,
        address(),
        who["full_name"],
        *who["full_name"].split(),
        *who["aliases"],
        where["name"],
        PACKET_TEXT,
        folder.name,
        str(ws.root),
        "/v1/secret/path",
        "user:pw",
        "8443",
    ):
        assert hidden not in blob, hidden

    by_doing = {}
    for line in lines:
        by_doing.setdefault(line["doing"], line)
    call = by_doing["task"]
    assert call["what"] == task
    assert call["status"] == 400 and call["error_kind"] == "other"
    assert call["adapter"] == cfg.ai.providers[account].adapter
    assert call["params"]["tier"] == "routine" and call["params"]["model"] == "example-small-model"
    settings = cfg.ai.tasks[task]
    assert call["params"]["temperature"] == str(settings.temperature)
    assert call["params"]["max_output"] == str(settings.max_output)
    for setting in ("send_temperature", "json_mode", "max_tokens_param"):
        assert setting in call["params"]
    assert "<secret>" in call["text"] and "<address>" in call["text"] and "<name>" in call["text"]
    assert f"{SCHEME}://{HOST}" in call["text"] and f"{HOST}:" not in call["text"]
    read = by_doing["source_read"]
    assert read["what"] == "folder" and read["error_kind"] == "outage" and "<path>" in read["text"]
    app_error = by_doing["app"]
    assert app_error["what"] == "GET /api/boom" and app_error["error_kind"] == "RuntimeError"
    assert "<secret>" in app_error["text"] and "<address>" in app_error["text"]
    assert "Traceback" not in blob


def test_a_failed_account_check_is_reported_with_its_parameters_and_the_services_text(home):
    ws, cfg, account = home
    store = Store(ws.db_path, cfg=cfg)
    detail = f'HTTP 401: {{"error": {{"message": "incorrect key {KEY}"}}}}'
    failed = SmokeResult(
        "routine",
        f"{account}/small (notes)",
        True,
        False,
        "It refused the key. Check the key.",
        provider=account,
        ref=f"{account}/small",
        params=["notes", 0.2, 800, "high"],
        error_kind="auth",
        error_detail=detail,
    )
    record(ws, [failed, failed])
    found = problems.recent(ws, store, cfg, datetime.now(UTC), program_version=lambda _name: None)
    store.close()
    assert len(found) == 1  # the same failure for the same parameters is one line
    line = found[0]
    assert (line.doing, line.what, line.status, line.error_kind) == ("account_check", "call", 401, "auth")
    assert (
        line.params["temperature"] == "0.2" and line.params["max_output"] == "800" and line.params["effort"] == "high"
    )
    assert line.params["model"] == "example-small-model" and line.params["tier"] == "routine"
    assert KEY not in line.text and "<secret>" in line.text


def test_the_days_and_the_most_bound_the_list(home):
    ws, cfg, account = home
    store = Store(ws.db_path, cfg=cfg)
    task = next(iter(cfg.ai.tasks))
    for hours in (1, 2, 3, 30, 80):
        make_run(store, NOW - timedelta(hours=hours), provider=account, task=task, detail=f"HTTP 500: down {hours}")
    base = {"storage.backups.automatic": False}

    def seen(**flags):
        cfg_now = ws.config(env={}, flags={**base, **flags})
        return problems.recent(ws, store, cfg_now, NOW, program_version=lambda _name: None)

    everything = seen(**{"ui.feedback_problem_days": 7, "ui.feedback_problem_max": 20})
    assert [p.text for p in everything] == [f"HTTP 500: down {h}" for h in (1, 2, 3, 30, 80)]  # newest first
    assert [p.text for p in seen(**{"ui.feedback_problem_days": 2})] == [f"HTTP 500: down {h}" for h in (1, 2, 3, 30)]
    assert len(seen(**{"ui.feedback_problem_days": 1})) == 3
    assert [p.text for p in seen(**{"ui.feedback_problem_max": 2})] == ["HTTP 500: down 1", "HTTP 500: down 2"]
    store.close()


def test_nothing_is_reported_when_there_were_no_problems(api):
    client, store, worker, ws, cfg, account = api
    assert client.get("/api/feedback/problems").json() == {"problems": []}
    make_run(
        store, datetime.now(UTC), provider=account, task=next(iter(cfg.ai.tasks)), detail="", outcome="ok", kind=None
    )
    make_run(store, datetime.now(UTC), provider=account, task=next(iter(cfg.ai.tasks)), detail="", kind="offline")
    make_read(store, datetime.now(UTC), source="inbox", error="", outcome="offline", kind=None)
    assert client.get("/api/feedback/problems").json() == {"problems": []}  # ok, no network and offline are no failure


def test_an_error_in_the_worker_is_kept_without_a_traceback_and_the_file_keeps_only_the_newest(api, monkeypatch):
    client, store, worker, ws, cfg, account = api

    def broken(*_args, **_kwargs):
        raise ValueError(f"cannot handle {address()} {KEY}")

    assert client.post("/api/handin", json={"note": "hello", "pasted": ""}).status_code == 200
    monkeypatch.setattr("engine.worker.process", broken)
    worker.run_pending()
    kept = (ws.private_dir / problems.FILE).read_text().splitlines()
    assert len(kept) == 1
    row = json.loads(kept[0])
    assert row["type"] == "ValueError" and row["where"] == "processing a request"
    assert KEY not in kept[0] and address() not in kept[0] and "<address>" in row["message"]
    assert "Traceback" not in kept[0] and 'File "' not in kept[0]

    tiny = ws.config(env={}, flags={"ui.feedback_problem_max": 1})
    for n in range(8):
        problems.note(ws, store, tiny, f"place {n}", RuntimeError(f"error {n}"), now=NOW + timedelta(minutes=n))
    lines = [json.loads(x) for x in (ws.private_dir / problems.FILE).read_text().splitlines()]
    assert [x["where"] for x in lines] == [f"place {n}" for n in range(3, 8)]  # five times the most


@pytest.mark.parametrize(
    ("text", "gone", "kept"),
    [
        (f"Authorization: Bearer {KEY}", KEY, "Bearer <secret>"),
        ("Incorrect API key provided: abc123def", "abc123def", "key provided"),
        ('{"api_key": "hunter2"}', "hunter2", "api_key"),
        ("password=correct-horse-staple", "correct-horse-staple", "password="),
        ("token: xk29a", "xk29a", "token:"),
        (f"see {SCHEME}://user:pw@{HOST}:8443/a/b?c=d#e", "/a/b", f"{SCHEME}://{HOST}"),
        ("mail someone.name+tag@sub.example.com now", "someone.name", "<address>"),
        ("couldn't open /home/someone/notes/plan.txt or C:\\Users\\Someone\\plan.txt", "plan.txt", "<path>"),
        ("a token like eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEF123", "eyJhbGci", "<secret>"),
    ],
)
def test_text_that_looks_like_a_key_an_address_a_path_or_a_url_is_masked(text, gone, kept):
    masked = problems.mask(text)
    assert gone not in masked
    assert kept in masked


def test_plain_error_words_and_a_models_id_stay_readable():
    model = "vendor-model-2026-01-15-preview"
    text = f"key: missing. The model {model} does not exist; max_tokens: 4096 is too large; status 404."
    assert problems.mask(text, keep=[model]) == text
    assert problems.mask("unsupported value for max_tokens_param") == "unsupported value for max_tokens_param"


def test_the_workspaces_own_secret_values_are_masked_wherever_they_appear():
    assert (
        problems.mask(f"failed ({RESOLVED}) twice: {RESOLVED}", secrets=[RESOLVED])
        == "failed (<secret>) twice: <secret>"
    )
    assert problems.mask("short ab", secrets=["ab"]) == "short ab"  # too short to be taken for a secret by value
    assert problems.mask("for Ada Quinn only", names=["Quinn"]) == "for Ada <name> only"
