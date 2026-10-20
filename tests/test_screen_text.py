"""The wording check (api/screen_text.py): text the screen shows never names a settings file, a secret reference, a
settings key, a manifest field or a command. The checker's own cases, the response fields typed as screen text, the
refusal of an error message that fails the check, and the web wording sheet's matching list of commands."""

import re
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from api.screen_text import SWITCH, ScreenText, command_names, problems, settings_keys
from engine.config import load_config
from engine.config.schema import FILES
from engine.secrets import SecretHint
from engine.settings import describe
from tests.conftest import DEMO_B

# ---- the checker -----------------------------------------------------------------------------------------------------


def a_real_key() -> str:
    """A settings key read from the schema, with its file's name in front."""
    return next(s.key for s in describe(load_config(DEMO_B / "config", env={})) if s.key.count(".") >= 2)


@pytest.mark.parametrize("name", [f"{name}.yaml" for name in FILES] + ["plugin.yaml", "notes/other.yml", ".yaml"])
def test_a_settings_file_name_is_caught(name):
    assert problems(f"Open {name} and change it.")


@pytest.mark.parametrize(
    "text",
    [
        "The settings file refers to it.",
        "Changed in the workspace's settings files.",
        "Your Settings File has a problem.",
    ],
)
def test_naming_where_settings_are_kept_is_caught(text):
    assert problems(text)


@pytest.mark.parametrize("ref", ["env:NAME", "file:/run/secret", "keychain:item"])
def test_a_secret_reference_is_caught(ref):
    assert problems(f"The key is at {ref}.")


def test_a_real_settings_key_is_caught_with_and_without_its_file():
    with_file = a_real_key()
    without_file = with_file.partition(".")[2]
    assert problems(f"Raise {with_file} to go on.")
    assert problems(f"Raise {without_file} to go on.")
    assert problems(f"Raise {with_file}.")  # a sentence may end right after the key


def test_the_key_set_is_built_from_the_schema_and_covers_groups_and_mappings():
    keys = settings_keys()
    every = {s.key for s in describe(load_config(DEMO_B / "config", env={}))}
    assert every <= keys
    assert {k.partition(".")[2] for k in every if "." in k} <= keys
    # A path may go on under a key that holds a mapping, with names the person chose.
    mapping = next(s.key for s in describe(load_config(DEMO_B / "config", env={})) if s.type == "other")
    assert problems(f"{mapping}.chosen_name.field")


@pytest.mark.parametrize(
    "field",
    [
        "requires.secrets",
        "requires.network",
        "provides.data",
        "plugin_api",
        "interfaces.uses",
        "depends_on",
        "config_schema",
    ],
)
def test_a_manifest_field_is_caught(field):
    assert problems(f"The add-on's {field} lists it.")


def test_a_command_is_caught_and_the_subcommand_names_come_from_the_parser():
    names = command_names()
    assert {"serve", "init", "demo", "restore"} <= names
    for name in names:
        assert problems(f"Run `cockpit {name}` again."), name
    for text in ("Run uv run pytest.", "Use uv sync first.", "Then npm install.", "Try git pull."):
        assert problems(text), text


# ---- raw data ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"title": "Launch", "due": "2026-10-20"}',
        "Milestone {'name': 'Launch'} is due",
        "Milestone: {name: Launch, due: 2026-10-20}",
        'The fields are "title": and "due": in the data',
        'Review [{"id": 4}] before Friday',
        'Sent {  "to" : "Ana" } on Monday',
    ],
)
def test_raw_data_in_a_title_or_a_line_is_caught(text):
    assert any("raw data" in found for found in problems(text)), text


@pytest.mark.parametrize(
    "text",
    [
        "Write the plan for {full_name} first.",
        "The folder is plan/chapters/{order:02}-{slug}.",
        'Ask "Is the index final?" before Friday',
        "Notes: the printer wants PDF files.",
        "Decide: print now or wait?",
        "Review the list [Launch, Ship] with Robin",
        "Read the section titled 'Costs': it is short.",
        'A quote: "We ship on Tuesday."',
    ],
)
def test_an_ordinary_line_is_not_taken_for_raw_data(text):
    assert not any("raw data" in found for found in problems(text)), text


def test_screen_text_that_shows_raw_data_is_refused_while_the_check_is_on(monkeypatch):
    monkeypatch.setenv(SWITCH, "1")
    with pytest.raises(ValidationError, match="raw data"):
        Line(waiting='Milestone {"name": "Launch"} is due')
    assert Line(waiting="Milestone Launch is due").waiting


@pytest.mark.parametrize(
    "text",
    [
        "Use e.g. a short name.",
        "See example.com for more.",
        "Saved as notes.md.",
        "Version 1.2.3 is current.",
        "It ends with a period.",
        "The cockpit restarts when you choose.",
        "The git history stays.",
        "Hosted on the app's own address.",
        "Your settings are from a newer version of the app.",
        "Saved to the file you picked, and the settings apply at once.",
    ],
)
def test_look_alikes_pass(text):
    assert problems(text) == []


# ---- screen text on a response ---------------------------------------------------------------------------------------


class Line(BaseModel):
    waiting: ScreenText | None = None
    free: str = ""


def leaking() -> str:
    return f"Raise {a_real_key()} in ai.yaml."


def test_a_field_typed_as_screen_text_refuses_a_leak_while_the_check_is_on(monkeypatch):
    monkeypatch.setenv(SWITCH, "1")
    with pytest.raises(ValidationError, match="text for the screen"):
        Line(waiting=leaking())
    assert Line(waiting="Raise the limit in Settings.").waiting
    assert Line(free=leaking()).free  # a field that isn't screen text is never checked
    assert Line(waiting=None).waiting is None


def test_the_same_text_passes_when_the_check_is_off(monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)
    assert Line(waiting=leaking()).waiting == leaking()


def test_the_suite_runs_with_the_check_on():
    import os

    assert os.environ[SWITCH] == "1"


def test_a_secret_hint_is_the_one_text_allowed_to_name_the_reference_form(monkeypatch):
    monkeypatch.setenv(SWITCH, "1")
    hint = "A secret reference (env:NAME or file:/path), never the secret itself."
    assert Line(waiting=SecretHint(hint)).waiting == hint
    with pytest.raises(ValidationError):
        Line(waiting=hint)


def route_returning(text: str) -> TestClient:
    app = FastAPI()
    router = APIRouter()

    @router.get("/line")
    def line() -> Line:
        return Line(waiting=text)

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_a_route_returning_a_leaking_screen_text_fails_while_the_check_is_on(monkeypatch):
    monkeypatch.setenv(SWITCH, "1")
    assert route_returning(leaking()).get("/line").status_code == 500
    assert route_returning("Raise the limit in Settings.").get("/line").status_code == 200


def test_the_same_route_answers_when_the_check_is_off(monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)
    answered = route_returning(leaking()).get("/line")
    assert answered.status_code == 200 and answered.json()["waiting"] == leaking()


# ---- error messages --------------------------------------------------------------------------------------------------


def an_app(tmp_path):
    from api.app import create_app
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    Store(ws.db_path, cfg=cfg).close()
    app = create_app(ws, cfg, "t", start_worker=False)
    return app, cfg


def test_an_error_message_that_fails_the_check_is_refused_while_it_is_on(tmp_path, monkeypatch):
    app, cfg = an_app(tmp_path)
    if not isinstance(app, FastAPI):  # served under a base path: the app inside it
        app = app.routes[0].app
    from fastapi.routing import APIRoute

    def leak() -> None:
        raise HTTPException(status_code=400, detail=leaking())

    def plain() -> None:
        raise HTTPException(status_code=400, detail="That didn't work. Try again.")

    app.router.routes.insert(0, APIRoute("/api/__leak", leak))
    app.router.routes.insert(0, APIRoute("/api/__plain", plain))
    c = TestClient(app, raise_server_exceptions=False)
    c.headers["Authorization"] = "Bearer t"
    prefix = cfg.server.base_path.rstrip("/")
    monkeypatch.setenv(SWITCH, "1")
    refused = c.get(f"{prefix}/api/__leak")
    assert refused.status_code == 500 and "error text for the screen" in refused.json()["detail"]
    assert c.get(f"{prefix}/api/__plain").status_code == 400
    monkeypatch.delenv(SWITCH)
    assert c.get(f"{prefix}/api/__leak").status_code == 400


def test_the_refusal_when_the_token_is_missing_names_no_command(tmp_path):
    app, cfg = an_app(tmp_path)
    c = TestClient(app, raise_server_exceptions=False)
    answered = c.get(cfg.server.base_path.rstrip("/") + "/api/status")
    assert answered.status_code == 401
    assert problems(answered.json()["error"]) == []


# ---- the web wording sheet -------------------------------------------------------------------------------------------


def test_the_web_wording_test_lists_the_command_lines_own_subcommands():
    source = (Path(__file__).parent.parent / "web" / "src" / "wording" / "wording.test.ts").read_text()
    listed = re.search(r"const COMMANDS = \[(.*?)\];", source, re.S)
    assert listed, "the web wording test lists the commands it screens for"
    assert set(re.findall(r'"([a-z-]+)"', listed.group(1))) == set(command_names())
    files = re.search(r"const SETTINGS_FILES = \[(.*?)\];", source, re.S)
    assert files and set(re.findall(r'"([a-z]+)"', files.group(1))) == set(FILES)
