"""Stance per person (design 6.34): who each person is to the person decides what the assistant may ask them, and what
the person tracks decides what is asked at all. The gate is a lint, returned once and held if it comes back; the
person's own note decides for itself.

Names and ids come from the fictional workspace's records."""

from __future__ import annotations

import pytest

from engine.scope import stance_of
from engine.storage import WriteContext
from tests.test_scope_slice import PLAIN, env, from_input, from_note, outsider, pm_of, problems, question  # noqa: F401

_TEST = WriteContext(actor="pm", trust="trusted", op="test.stance")


def set_stance(store, person_id: str, stance: str | None) -> None:
    with store.transaction() as tx:
        cur = tx.get("person", person_id)
        tx.update("person", person_id, {"stance": stance}, _TEST, read_version=cur.version)


def ask(cfg, who, about: str, **more) -> dict:
    return question(cfg, who, PLAIN, asks_about=about, **more)


@pytest.mark.parametrize(
    ("stance", "about", "allowed"),
    [
        ("manage", "date", True),
        ("manage", "decision", True),
        ("alongside", "date", True),
        ("alongside", "decision", True),
        ("alongside", "design", False),
        ("report_to", "date", False),
        ("report_to", "decision", False),
        ("watch", "date", False),
        ("watch", "other", False),
    ],
)
def test_what_may_be_asked_follows_who_they_are_to_the_person(env, stance, about, allowed):
    _, cfg, store = env
    cfg.steward.tracks = ["dates", "decisions", "design"]
    them = outsider(cfg)
    set_stance(store, them["id"], stance)
    found = problems(env, ask(cfg, them, about), "", "stance")
    assert (found == []) is allowed, found


def test_a_design_question_to_someone_managed_is_asked_only_when_the_person_tracks_design(env):
    _, cfg, store = env
    them = outsider(cfg)
    set_stance(store, them["id"], "manage")
    assert cfg.steward.tracks == ["dates", "decisions"]  # the default
    (found,) = problems(env, ask(cfg, them, "design"), "", "stance")
    assert "don't track design" in found.message
    cfg.steward.tracks = ["dates", "decisions", "design"]
    assert problems(env, ask(cfg, them, "design"), "", "stance") == []


def test_a_mistake_needs_links_to_both_sides(env):
    _, cfg, store = env
    them = outsider(cfg)
    set_stance(store, them["id"], "manage")
    (found,) = problems(env, ask(cfg, them, "mistake"), "", "stance")
    assert "both sides" in found.message
    two = [*ask(cfg, them, "mistake")["links"], *ask(cfg, them, "mistake")["links"]]
    two[1] = {**two[1], "url": two[1]["url"] + "#other"}
    assert problems(env, ask(cfg, them, "mistake", links=two), "", "stance") == []


def test_the_default_stance_is_a_setting_and_track_only_counts_as_watch(env):
    _, cfg, store = env
    them = outsider(cfg)
    assert stance_of(store.read(), cfg.steward, them["id"]) == "alongside"
    cfg.steward.default_stance = "manage"
    assert stance_of(store.read(), cfg.steward, them["id"]) == "manage"
    with store.transaction() as tx:
        cur = tx.get("person", them["id"])
        tx.update("person", them["id"], {"track_only": True}, _TEST, read_version=cur.version)
    assert stance_of(store.read(), cfg.steward, them["id"]) == "watch"
    set_stance(store, them["id"], "alongside")
    assert stance_of(store.read(), cfg.steward, them["id"]) == "alongside"


def test_a_question_the_gate_stops_is_returned_then_held_and_never_applied(env):
    _, cfg, store = env
    them = outsider(cfg)
    set_stance(store, them["id"], "report_to")
    (found,) = problems(env, ask(cfg, them, "date"), "", "stance")
    assert found.severity == "return"
    _, result = from_input(env, [ask(cfg, them, "date")], "When will the plan be ready?")
    assert result == ["held"]


def test_the_persons_own_note_asks_whoever_they_say(env):
    _, cfg, store = env
    them = outsider(cfg)
    set_stance(store, them["id"], "report_to")
    _, result = from_note(env, [ask(cfg, them, "date")], f"Ask {them['full_name']} when the plan is ready")
    assert result == ["applied"]


def test_the_gate_is_a_setting_like_any_lint(env):
    _, cfg, store = env
    them = outsider(cfg)
    set_stance(store, them["id"], "watch")
    cfg.checks.lints["stance"] = "off"
    assert problems(env, ask(cfg, them, "date"), "", "stance") == []
