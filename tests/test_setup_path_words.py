"""The wording check reaches every label on the setup path (the first-run review's N5): not only the wording sheet but
the labels and descriptions the screens take from config schemas, from the connectors' settings and from add-on
manifests. Nothing a person sets up meets a time zone id, a language tag, a secret reference, IMAP, a port, TLS, a
token, CLI or a command; what has to stay technical is marked `advanced` and sits behind Advanced."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.screen_text import setup_problems
from engine import settings as config_screens
from engine import watch
from engine.config import load_config
from engine.settings import describe
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B

SHEET = json.loads((Path(__file__).parent.parent / "web" / "src" / "wording" / "en.json").read_text(encoding="utf-8"))


def a_workspace(tmp_path: Path, demo: Path):
    ws = init_workspace(tmp_path / demo.name, template=demo, git=False)
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


# ---- the check itself -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Use an area and city, such as Europe/Paris.",
        "The variety of English, as a language tag (en-US, en-GB).",
        "A secret reference (env:NAME or file:/path) to the password.",
        "The mail server's address (its IMAP host).",
        "Its port with TLS.",
        "Reads up to about 4,000 tokens at once.",
        "Start it with the CLI.",
        "Enter the app's command and options.",
        "Run this command first.",
    ],
)
def test_the_check_finds_a_technical_word_on_the_setup_path(text):
    assert setup_problems(text), text


@pytest.mark.parametrize(
    "text",
    [
        "Yes/No answers, and/or a list.",
        "Your time zone, such as New York (Eastern time).",
        "A report, a transport plan and the importance of both.",
        "Install the app and sign in to it.",
        "Choose American or British spelling.",
        "The key stays on this computer.",
        "Commanding views of the harbor.",
    ],
)
def test_the_check_lets_a_look_alike_through(text):
    assert setup_problems(text) == []


# ---- what is on the setup path --------------------------------------------------------------------------------------


def settings_on_the_path(tmp_path: Path, demo: Path):
    """Every setting a screen lists that isn't marked advanced, with the words the screen shows: its label from the
    wording sheet when it has one, and its description."""
    ws, cfg, store = a_workspace(tmp_path, demo)
    try:
        items = describe(cfg, store.plugins, ws.config_dir)
        for item in items:
            if not item.advanced:
                yield item.key, SHEET.get(f"settings.key.{item.key}", ""), item.description
        for name, connector in sorted(watch.connectors(store).items()):
            if connector.test_only:
                continue
            found: list = []
            config_screens._walk(connector.settings, ["source"], {}, {}, {}, found)
            yield f"connector {name}", connector.label, ""
            for item in found:
                if not item.advanced:
                    yield f"{name} {item.key}", "", item.description
    finally:
        store.close()


@pytest.mark.parametrize("demo", [DEMO_A, DEMO_B], ids=["demo-a", "demo-b"])
def test_no_setting_label_or_description_off_the_advanced_path_names_a_technical_thing(tmp_path, demo):
    leaks = [
        f"{where}: {text!r} {problems}"
        for where, *words in settings_on_the_path(tmp_path, demo)
        for text in words
        if text and (problems := setup_problems(text))
    ]
    assert leaks == []


def test_what_stays_technical_is_marked_advanced_and_still_listed(tmp_path):
    ws, cfg, store = a_workspace(tmp_path, DEMO_B)
    try:
        items = {i.key: i for i in describe(cfg, store.plugins, ws.config_dir)}
    finally:
        store.close()
    # Settings that name a secret reference, a token or a command-line way of working are reachable, behind Advanced.
    for key in ("ai.budgets.confirm_unpriced", "storage.backups.encrypt", "ui.notifications.webhook"):
        assert items[key].advanced, key
    assert not items["ai.budgets.per_run_usd"].advanced and items["ai.budgets.per_run_usd"].basic
    assert not items["ai.budgets.confirm_unpriced"].basic


def test_a_mail_server_asks_for_its_name_a_user_and_a_password_and_keeps_the_rest_behind_advanced(tmp_path):
    ws, cfg, store = a_workspace(tmp_path, DEMO_B)
    try:
        mailbox = watch.connectors(store)["mailbox"]
    finally:
        store.close()
    found: list = []
    config_screens._walk(mailbox.settings, ["source"], {}, {}, {}, found)
    shown = {i.key.removeprefix("source."): i for i in found}
    assert [k for k, i in shown.items() if not i.advanced] == ["host", "user", "password"]
    assert shown["password"].secret  # still a box for a secret, kept on this computer
    assert {"port", "timeout_seconds"} <= {k for k, i in shown.items() if i.advanced}


def test_the_source_kinds_a_person_picks_are_worded_without_technical_names():
    from engine.connectors import CORE

    for name, connector in CORE.items():
        if connector.test_only:
            continue
        assert setup_problems(connector.label) == [], (name, connector.label)


# ---- add-on manifests -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("demo", [DEMO_A, DEMO_B], ids=["demo-a", "demo-b"])
def test_an_add_ons_own_words_on_the_setup_path_are_plain(tmp_path, demo):
    ws, cfg, store = a_workspace(tmp_path, demo)
    try:
        said: list[tuple[str, str]] = []
        for name, manifest in store.plugins.manifests.items():
            said.append((f"{name} description", manifest.description))
        for plugin, step in store.plugins.setup_steps():
            said += [(f"{plugin} step {step.name} label", step.label), (f"{plugin} step explanation", step.explanation)]
        for name, sign_in in store.plugins.sign_ins().items():
            said += [(f"{name} label", sign_in.label), *((f"{name} allows", a) for a in sign_in.allows)]
    finally:
        store.close()
    assert said
    assert [(where, setup_problems(text)) for where, text in said if text and setup_problems(text)] == []
