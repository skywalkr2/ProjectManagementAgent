"""The first-week lints (design 8.8): quoted words are in the material cited, names are spelled as the workspace has
them, links come from somewhere the person can trust, no tool version number goes to someone else, a project's summary
is status, and a change that says it made a draft or a file holds it. Names, ids and links come from the fixtures."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.applier import Context, Inputs, _FirstWeek, check
from engine.check_text import links_in
from engine.config import load_config
from engine.draft_checks import (
    KnownLinks,
    name_phrases,
    says_it_made,
    summary_problems,
    unknown_links,
    unverified_quotes,
    version_numbers,
)
from engine.files import store_blob
from engine.made import made_by
from engine.names import People
from engine.ops import CHANGESET, RecordRef, TextDraftOp
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B, fixture_records
from tests.test_knowledge_records import apply, source

_TEST = WriteContext(actor="pm", trust="trusted", op="test.first-week")
PEOPLE = fixture_records(DEMO_B, "person")
PROJECT = fixture_records(DEMO_B, "project")[0]
LINK = PROJECT["links"][0]["url"]
DOMAIN = LINK.split("/")[2].split(".", 1)[1]  # the fixtures' own domain
ORGS = fixture_records(DEMO_B, "organization")
TYPESETTER = next(p for p in PEOPLE if p.get("role") == "Typesetter")
EDITOR = next(p for p in PEOPLE if p.get("aliases"))
FIRST, LAST = EDITOR["full_name"].split()[0], EDITOR["full_name"].split()[-1]
STRANGER = f"{TYPESETTER['full_name'].split()[-1]} {FIRST}"  # two capitalized words no one on file goes by
SAID = "The printer wrote that the proof is final and ready to go, and the run starts on Monday."
NEW_NAMES = {
    "unverified-quote",
    "unverified-name",
    "unknown-link",
    "version-number",
    "summary-is-status",
    "unlinked-made",
}


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def question_to(person: str, **more) -> dict:
    return {
        "op": "question.add",
        "to": person,
        "title": "Is the proof final?",
        "text": "The proof came back this morning.",
        "matters_for": "the cover schedule",
        "links": [{"label": "Page", "url": LINK}],
        **more,
    }


def to_other(**more) -> dict:
    return question_to(TYPESETTER["id"], **more)


def found(env, op, name, *, text=SAID, actor="assistant", summary="") -> list:
    _, cfg, store = env
    cs = CHANGESET.validate_python({"summary": summary, "ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, text, text, "untrusted"),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if p.check == name]


def to_the_pm(env, **more) -> dict:
    return question_to(env[1].workspace.user.person, kind="decision", **more)


# ---- quotes only from verbatim sources -------------------------------------------------------------------------------


def test_words_in_quotation_marks_that_are_not_in_the_input_are_returned(env):
    _, cfg, _ = env
    inside = to_other(text='The printer says "the proof is final and ready to go". Is that right?')
    assert not found(env, inside, "unverified-quote")
    outside = to_other(text='The printer says "the proof arrives on Friday morning". Is that right?')
    (problem,) = found(env, outside, "unverified-quote")
    assert problem.severity == "return" and problem.passage == "the proof arrives on Friday morning"
    assert "paraphrase" in problem.guidance
    # A paraphrase has no quotation marks, a term in quotation marks is shorter than a quote, and the person's own
    # changes are not checked.
    assert not found(env, to_other(text="The printer says the proof arrives on Friday."), "unverified-quote")
    assert not found(env, to_other(text='Is "Proof B" the one?'), "unverified-quote")
    assert not found(env, outside, "unverified-quote", actor="pm")
    cfg.checks.tuning.unverified_quote.min_words = 10
    assert not found(env, outside, "unverified-quote")
    cfg.checks.tuning.unverified_quote.min_words = 3
    cfg.checks.lints["unverified-quote"] = "off"
    assert not found(env, outside, "unverified-quote")


def test_a_quote_is_compared_ignoring_case_punctuation_and_the_kind_of_quotation_mark():
    sources = ["She said, “It's final; ship it Monday, please.” Then she left."]
    assert unverified_quotes('He wrote "its final" and “ship it monday”', sources, 2) == ["its final"]
    assert unverified_quotes("She said “It’s final; ship it Monday, please.”", sources, 2) == []
    # An ellipsis splits a quote into pieces that must each be there.
    assert unverified_quotes('"It\'s final ... ship it Monday"', sources, 2) == []
    assert unverified_quotes('"It\'s final ... ship it Tuesday"', sources, 2) == ["It's final ... ship it Tuesday"]


def test_an_unverified_quote_holds_a_question_to_someone_else_and_only_records_one_to_the_person(env):
    _, cfg, store = env
    raw = SAID
    quote = '"the proof arrives on Friday morning"'
    cs_id, statuses = apply(
        store,
        cfg,
        [to_other(text=f"The printer says {quote}.")],
        origin="input",
        trust="untrusted",
        source_id=source(store),
        raw=raw,
    )
    assert statuses == ["held"]
    held = store.read().get("changeset", cs_id).data["ops"][0]
    assert any(p["check"] == "unverified-quote" for p in held["problems"])
    _, own = apply(
        store,
        cfg,
        [to_the_pm(env, text=f"The printer says {quote}.")],
        origin="input",
        trust="untrusted",
        source_id=source(store),
        raw=raw,
    )
    assert own == ["applied"]


def test_a_draft_is_checked_for_links_but_not_quotes_and_does_not_go_to_anyone_by_itself(env):
    _, cfg, store = env
    view = store.read()
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, SAID, "", "untrusted"),
        actor="assistant",
    )
    text = (
        'The printer wrote "the proof arrives on Friday morning" (see ' + f"https://x.{DOMAIN}/page). "
        f"v2.3.1 by {STRANGER}."
    )
    op = TextDraftOp(record=RecordRef(kind="project", id=PROJECT["id"]), field="summary", text=text)
    names = [p.check for p in _FirstWeek(ctx, view).problems(0, op, cfg.checks.lints)]
    # Quotation marks in long text may be the work itself (dialogue), and a version or a name matters only in what is
    # sent to someone.
    assert names == ["unknown-link"]


# ---- names spelled from a primary source -----------------------------------------------------------------------------


def test_a_name_no_person_goes_by_is_a_warning_on_a_question_to_someone_else(env):
    _, cfg, _ = env
    spelled = to_other(text=f"{STRANGER} asked who signs this off.")
    (problem,) = found(env, spelled, "unverified-name")
    assert problem.severity == "warn" and problem.passage == STRANGER
    for fine in (
        f"{EDITOR['full_name']} asked who signs this off.",  # a full name on file
        f"{EDITOR['full_name']}'s proof is in.",  # the same name, possessive
        f"{ORGS[0]['name']} asked who signs this off.",  # an organization the workspace knows
        f"{' '.join(PROJECT['name'].split()[:3])} needs a date.",  # part of a project's name
        f"Thanks {EDITOR['full_name']} for the proof.",  # an everyday word at the edge is not part of a name
    ):
        assert not found(env, to_other(text=fine), "unverified-name"), fine
    # The input spelling a name is a source for it.
    assert not found(env, spelled, "unverified-name", text=f"{STRANGER} is on the thread.")
    greeting = to_other(text=f"Hi {LAST},\nWhich date do you want?")
    assert found(env, greeting, "unverified-name")  # a surname alone is not how anyone on file is greeted
    assert found(env, to_other(text=f"Hi {STRANGER.split()[0]},\nWhich date?"), "unverified-name")
    assert not found(env, to_other(text=f"Hi {FIRST},\nWhich date?"), "unverified-name")
    assert not found(env, to_the_pm(env, text=f"{STRANGER} asked."), "unverified-name")  # stays internal
    cfg.checks.lints["unverified-name"] = "off"
    assert not found(env, spelled, "unverified-name")


def test_name_phrases_trim_the_everyday_words_at_either_edge():
    skip = ["the", "hi", "and"]
    title = " ".join(PROJECT["name"].split()[1:3])
    full = EDITOR["full_name"]
    assert name_phrases(f"The {title} and {full} met.", skip) == [title, full]
    assert name_phrases(f"Hi {FIRST},\n{full}'s file.", skip, "Hi {first_name},") == [full, FIRST]


def test_a_name_is_verified_when_the_person_gave_it(env):
    _, cfg, store = env
    op = {"op": "person.add", "full_name": STRANGER}
    cs_id, statuses = apply(store, cfg, [op], origin="pm", trust="trusted")
    assert statuses == ["applied"]
    made = store.read().get("changeset", cs_id).data["ops"][0]["records"][0]
    assert store.read().get("person", made["id"]).data["name_verified"] is True
    assert all(p.data["name_verified"] is False for p in store.read().list("person") if p.id != made["id"])
    other = {"op": "person.add", "full_name": f"{FIRST} {LAST}s"}
    cs_id, statuses = apply(
        store, cfg, [other], origin="input", trust="untrusted", source_id=source(store), confirmed=True
    )
    assert statuses == ["applied"]
    made = store.read().get("changeset", cs_id).data["ops"][0]["records"][0]
    assert store.read().get("person", made["id"]).data["name_verified"] is False


# ---- links -----------------------------------------------------------------------------------------------------------


def test_a_link_nothing_holds_is_returned_and_one_the_input_a_record_or_a_source_holds_passes(env):
    _, cfg, store = env
    stray = f"https://elsewhere.{DOMAIN}/page?id=7"
    (problem,) = found(env, to_other(text=f"See {stray} for the proof."), "unknown-link")
    assert problem.severity == "return" and problem.passage == stray
    assert [p.passage for p in found(env, to_other(links=[{"label": "Page", "url": stray}]), "unknown-link")] == [stray]
    assert not found(env, to_other(text=f"See {LINK} for the proof."), "unknown-link")  # a project's link
    assert not found(env, to_other(text=f"See {stray}."), "unknown-link", text=f"Look at {stray}")  # the input's
    assert not found(env, to_other(text=f"See {LINK.replace('https://', 'www.')}/ for it."), "unknown-link")
    host = LINK.split("/")[2]
    assert not found(env, to_other(text=f"It is on {host}."), "unknown-link")  # a known address's host alone
    # An address a configured source reads from.
    feed = next(s for s in load_config(DEMO_A / "config", env={}).watch.sources if "url" in s.settings)
    cfg.watch.sources.append(feed)
    assert not found(env, to_other(text=f"See {feed.settings['url']}."), "unknown-link")
    assert not found(env, to_other(text=f"Write to someone@{DOMAIN}."), "unknown-link")  # a mail address isn't one
    cfg.checks.lints["unknown-link"] = "off"
    assert not found(env, to_other(text=f"See {stray}."), "unknown-link")


def test_links_are_read_from_text_and_compared_by_address():
    full = f"https://a.{DOMAIN}/x?y=1"
    text = f"See {full}. Or www.b.{DOMAIN}/p, c.{DOMAIN}, me@{DOMAIN}."
    assert links_in(text) == [full, f"www.b.{DOMAIN}/p", f"c.{DOMAIN}"]
    known = KnownLinks()
    known.add_text(f"https://Docs.{DOMAIN}/guide/#top")
    here = f"docs.{DOMAIN}"
    assert unknown_links(f"{here}/guide/ and {here} and {here}/other", [], known) == [f"{here}/other"]


# ---- version numbers -------------------------------------------------------------------------------------------------


def test_a_version_number_in_a_message_to_someone_else_is_returned(env):
    _, cfg, store = env
    for said in ("The page on v2.3.1 moved.", "Build 1042 is out.", "Version 4 is out.", "Use release 2.4 now."):
        (problem,) = found(env, to_other(text=said), "version-number")
        assert problem.severity == "return", said
    assert [p.passage for p in found(env, to_other(text="The page on v2.3.1 moved."), "version-number")] == ["v2.3.1"]
    for fine in ("The date is 10.14.2026.", "The run is 2.5 times larger.", "It costs 3.50 each."):
        assert not found(env, to_other(text=fine), "version-number"), fine
    assert not found(env, to_the_pm(env, text="The page on v2.3.1 moved."), "version-number")  # stays internal
    assert not found(env, to_other(text='The page says "v2.3.1" now.'), "version-number", text="It says v2.3.1 now")
    cfg.language.version_patterns = [r"\bB\d+\b"]
    assert found(env, to_other(text="Use B7 now."), "version-number")
    assert not found(env, to_other(text="The page on v2.3.1 moved."), "version-number")
    cfg.checks.lints["version-number"] = "off"
    assert not found(env, to_other(text="Use B7 now."), "version-number")


def test_a_version_inside_a_name_the_workspace_knows_passes(env):
    _, cfg, store = env
    name = f"{ORGS[0]['name']} Suite 4.2.1"
    assert version_numbers(f"We use {name} daily and v3.1.", cfg.language.version_patterns, [name]) == ["v3.1"]
    with store.transaction() as tx:
        tx.create("organization", {"name": name}, _TEST)
    assert not found(env, to_other(text=f"We use {name} daily."), "version-number")
    assert found(env, to_other(text=f"We use {name} daily on v3.1."), "version-number")


# ---- a project's summary is status ---------------------------------------------------------------------------------


def test_a_summary_longer_than_the_setting_or_holding_findings_is_returned(env):
    _, cfg, _ = env

    def summary(text, actor="assistant"):
        op = {"op": "record.set", "kind": "project", "id": PROJECT["id"], "field": "summary", "value": text}
        return found(env, op, "summary-is-status", actor=actor)

    assert not summary("On track for the date.\nProofs due Friday.\nPrinter booked.")
    (problem,) = summary("One.\nTwo.\nThree.\nFour.")
    assert problem.severity == "return" and "4 lines" in problem.message and "at most 3" in problem.message
    (problem,) = summary("We found a mismatch between the two dates.")
    assert "reports a finding" in problem.message
    assert not summary("The founding team is in place.")  # whole words only
    assert not summary("One.\nTwo.\nThree.\nFour.", actor="pm")
    cfg.workspace.project.summary_max_lines = 4
    assert not summary("One.\nTwo.\nThree.\nFour.")
    cfg.language.findings_words = []
    assert not summary("We found a mismatch between the two dates.")
    cfg.checks.lints["summary-is-status"] = "off"
    cfg.workspace.project.summary_max_lines = 1
    assert not summary("One.\nTwo.")
    project = {"op": "project.add", "name": f"{PROJECT['name']} again", "summary": "One.\nTwo."}
    assert not found(env, project, "summary-is-status")
    cfg.checks.lints["summary-is-status"] = "return"
    assert found(env, project, "summary-is-status")
    assert summary_problems("A.\nB.", 1, []) == ["it has 2 lines and a summary has at most 1"]


# ---- what a change made is linked ------------------------------------------------------------------------------------


def test_a_summary_that_says_it_made_something_the_change_does_not_hold_is_returned(env):
    _, cfg, _ = env
    note = {"op": "note", "text": "Minutes of the call."}
    (problem,) = found(env, note, "unlinked-made", summary="Drafted the minutes of the call.")
    assert problem.severity == "return" and problem.op is None and "'drafted'" in problem.message
    assert not found(env, note, "unlinked-made", summary="Recorded a note about the call.")
    assert not found(env, note, "unlinked-made", summary="Drafted the minutes.", actor="pm")
    report = {"op": "report.draft", "title": "A missing button", "text": "It would help to have one."}
    assert not found(env, report, "unlinked-made", summary="Drafted a report for the maintainers.")
    assert not found(
        env,
        {"op": "file.add", "id": "FILE-9", "name": "a.png", "media_type": "image/png", "size": 1, "sha256": "0" * 64},
        "unlinked-made",
        summary="Saved a file with the proof.",
    )
    cfg.language.made_phrases = ["minuted"]
    assert not found(env, note, "unlinked-made", summary="Drafted the minutes of the call.")
    assert found(env, note, "unlinked-made", summary="Minuted the call.")
    cfg.checks.lints["unlinked-made"] = "off"
    assert not found(env, note, "unlinked-made", summary="Minuted the call.")
    assert says_it_made("We wrote up the call.", ["wrote up"]) == "wrote up"
    assert says_it_made("They redrafted it.", ["drafted"]) is None  # whole words


def test_made_by_lists_the_drafts_and_files_of_applied_ops_that_still_exist():
    data = {
        "TXT-1": {"source": "draft", "status": "pending", "owner_kind": "project", "owner_id": "PRJ-1"},
        "TXT-2": {"source": "draft", "status": "discarded", "owner_kind": "project", "owner_id": "PRJ-1"},
        "TXT-3": {"source": "edit", "status": "accepted", "owner_kind": "project", "owner_id": "PRJ-1"},
        "FILE-1": {"name": "proof.pdf"},
    }
    view = SimpleNamespace(
        get=lambda kind, rid: (
            SimpleNamespace(id=rid, data={"name": "The Launch", **data[rid]})
            if rid in data
            else (SimpleNamespace(id=rid, data={"name": "The Launch"}) if (kind, rid) == ("project", "PRJ-1") else None)
        )
    )
    refs = lambda *pairs: [{"kind": k, "id": i} for k, i in pairs]  # noqa: E731
    outcomes = [
        {"status": "applied", "records": refs(("text_version", "TXT-1"), ("text_version", "TXT-2"))},
        {"status": "applied", "records": refs(("text_version", "TXT-3"), ("file", "FILE-1"), ("file", "FILE-2"))},
        {"status": "held", "records": refs(("file", "FILE-1"))},
        {"status": "applied", "records": refs(("text_version", "TXT-1"))},  # listed once
    ]
    made = made_by(view, outcomes)
    assert [(m.kind, m.id, m.label, m.record) for m in made] == [
        ("draft", "TXT-1", "The Launch", ("project", "PRJ-1")),
        ("file", "FILE-1", "proof.pdf", ("file", "FILE-1")),
    ]


def test_the_change_view_gives_what_the_change_made(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "made-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer made-token"}) as client:
        store = application.state.store
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        file_op = {
            "op": "file.add",
            "id": "FILE-7",
            "name": "proof.png",
            "media_type": "image/png",
            "size": len(png),
            "sha256": store_blob(store, png),
        }
        cs_id, statuses = apply(store, cfg, [file_op, {"op": "note", "text": "Proof saved."}], actor="pm")
        assert statuses == ["applied", "applied"]
        with store.transaction() as tx:
            request = tx.get("request", tx.get("changeset", cs_id).data["request"])
            tx.update("request", request.id, {"changeset": cs_id}, _TEST, read_version=request.version)
        shown = next(c["changeset"] for c in client.get("/api/changes").json() if c["id"] == request.id)
    assert shown["made"] == [
        {"kind": "file", "id": "FILE-7", "label": "proof.png", "record": {"kind": "file", "id": "FILE-7"}}
    ]


# ---- settings --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("workspace", [DEMO_A, DEMO_B], ids=lambda p: p.name)
def test_every_new_setting_has_a_demo_value_in_both_workspaces(workspace):
    cfg = load_config(workspace / "config", env={})
    checks = yaml.safe_load((workspace / "config" / "checks.yaml").read_text())
    language = yaml.safe_load((workspace / "config" / "language.yaml").read_text())
    settings = yaml.safe_load((workspace / "config" / "workspace.yaml").read_text())
    assert set(checks["lints"]) >= NEW_NAMES and set(cfg.checks.lints) >= NEW_NAMES
    assert checks["tuning"]["unverified_quote"]["min_words"] == cfg.checks.tuning.unverified_quote.min_words
    assert {"version_patterns", "findings_words", "made_phrases", "name_skip_words"} <= set(language)
    assert settings["project"]["summary_max_lines"] == cfg.workspace.project.summary_max_lines == 3
    assert all(re.compile(p) for p in cfg.language.version_patterns)
