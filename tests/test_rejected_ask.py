"""A rejected ask is dropped, not reworded (design 6.22): a "Change this" note that rejects asking a question at all
returns the same ask in other words once and then holds it, while a drop with the note's words applies; a note about
the wording gets its new wording. The words that reject an ask are a setting.

Ids come from the fictional workspace's records."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.corrections import request_change
from engine.dispatcher import process
from tests import test_corrections
from tests.test_corrections import LINK, make_items, question_of

env = test_corrections.env  # the corrections tests' workspace fixture

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


def answer(*ops: dict) -> None:
    body = json.dumps({"summary": "Changed.", "ops": list(ops)})
    set_responder(lambda task: body)


def again(env, title: str) -> dict:
    """The same ask in other words: a new question to the person the corrected one was for."""
    _, cfg, store = env
    to = question_of(store, make_items(store, cfg)["question"][1])["to"]
    return {"op": "question.add", "to": to, "title": title, "links": [LINK], "matters_for": "The page proof"}


def run_note(env, note: str):
    ws, cfg, store = env
    _, question_id = make_items(store, cfg)["question"]
    request, _ = request_change(ws, store, cfg, "question", question_id, note)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    return question_id, store.read().get("changeset", cs_id).data["ops"]


def test_a_note_that_rejects_the_asking_holds_a_reword_and_never_applies_it(env):
    note = "Why are we asking this? It's not my job to chase them."
    question_id = make_items(env[2], env[1])["question"][1]
    answer({"op": "question.drop", "id": question_id, "reason": "Reworded"}, again(env, "Could you confirm, please?"))
    _, (_, outcome) = run_note(env, note)
    assert outcome["status"] == "held"
    assert any(p["check"] == "rejected-ask" for p in outcome["problems"])


def test_a_drop_with_the_notes_words_applies(env):
    note = "Not my job to ask them this."
    question_id = make_items(env[2], env[1])["question"][1]
    answer({"op": "question.drop", "id": question_id, "reason": note, "evidence": {"quote": note}})
    _, (outcome,) = run_note(env, note)
    assert outcome["status"] == "applied"
    assert question_of(env[2], question_id)["status"] == "dropped"


def test_a_note_about_the_wording_rewords_and_the_words_are_a_setting(env):
    answer(again(env, "Is the page final?"))
    _, (outcome,) = run_note(env, "Shorter, please.")
    assert not any(p["check"] == "rejected-ask" for p in outcome["problems"])
    env[1].language.rejecting_words = []
    answer(again(env, "Is it final?"))
    _, (outcome,) = run_note(env, "Why are we asking this so formally? Shorter.")
    assert not any(p["check"] == "rejected-ask" for p in outcome["problems"])
