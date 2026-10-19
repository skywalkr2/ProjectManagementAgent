"""Stance on Today and in what is learned (design 6.33 "No news by its date", 6.34): the same overdue waiting-on reads
by who owes it, a correction can propose a stance that waits for the person's Keep, and the person's own choice of
stance is an edit with Undo. Names and ids come from the fictional workspace's records."""

from __future__ import annotations

from datetime import timedelta

import pytest

from engine.applier import apply_as_person, release, undo
from engine.ops import KNOWLEDGE_ADD_OPS, TIERS, reference_for
from engine.storage import WriteContext
from engine.tasks import LEARN_OPS
from tests import test_promise_lines
from tests.test_knowledge_records import apply, reasons, source
from tests.test_promise_lines import PAST, TODAY, lines, make, me, other, promise_lines

env = test_promise_lines.env  # the promise lines' workspace fixture


_TEST = WriteContext(actor="pm", trust="trusted", op="test.stance-lines")


def set_stance(store, person_id: str, stance: str | None) -> None:
    update_person(store, person_id, {"stance": stance})


def update_person(store, person_id: str, changes: dict) -> None:
    with store.transaction() as tx:
        tx.update("person", person_id, changes, _TEST, read_version=tx.get("person", person_id).version)


def waiting_on(env, stance: str | None):
    """An overdue, dated waiting-on owed by someone the person has this stance toward: its action and its line."""
    _, cfg, store = env
    them = other(cfg)
    set_stance(store, them, stance)
    action = make(store, [them], due=PAST, promised_to=[me(cfg)], basis="said")
    return action, promise_lines(env, action)


@pytest.mark.parametrize("stance", ["manage", "alongside"])
def test_someone_managed_or_worked_alongside_is_chased_as_before(env, stance):
    _, cfg, _ = env
    action, found = waiting_on(env, stance)
    (line,) = found
    assert (line.kind, line.group, line.person, line.stance) == ("promise", "send", other(cfg), stance)
    assert (line.text, line.due, line.waiting_days, line.actions) == (
        "Send the floor plan",
        PAST.isoformat(),
        3,
        [action],
    )


def test_someone_the_person_reports_to_is_waited_on_with_the_same_words_and_dates(env):
    _, cfg, _ = env
    action, found = waiting_on(env, "report_to")
    (line,) = found
    assert (line.kind, line.person, line.stance) == ("promise", other(cfg), "report_to")
    assert (line.text, line.due, line.waiting_days, line.actions) == (
        "Send the floor plan",
        PAST.isoformat(),
        3,
        [action],
    )


def chasing(env, action: str) -> list[str]:
    """The kinds of line that would chase or wait on this action: its own, a follow-up, or the person's overdue."""
    return [line.kind for line in lines(env) if action in line.actions and line.kind in ("promise", "nudge", "overdue")]


def test_someone_only_watched_has_no_line_at_all_and_the_action_is_on_no_other_line(env):
    _, cfg, store = env
    action, found = waiting_on(env, "watch")
    assert found == [] and chasing(env, action) == []
    # Marked track_only counts as watch, and so is the same.
    set_stance(store, other(cfg), None)
    update_person(store, other(cfg), {"track_only": True})
    assert chasing(env, action) == []


def test_the_default_stance_decides_for_someone_with_none(env):
    _, cfg, _ = env
    cfg.steward.default_stance = "report_to"
    _, (line,) = waiting_on(env, None)
    assert line.stance == "report_to"
    cfg.steward.default_stance = "watch"
    _, found = waiting_on(env, None)
    assert found == []


def test_a_watched_persons_action_is_not_on_the_follow_up_line_either(env):
    _, cfg, store = env
    them = other(cfg)
    # Told eleven days ago with no date: past the follow-up rule's ten days, short of the promise rule's fourteen, so
    # only the follow-up line would name it.
    undated = make(
        store,
        [them],
        due=None,
        made=TODAY - timedelta(days=11),
        told={them: (TODAY - timedelta(days=11)).isoformat()},
    )
    set_stance(store, them, "manage")
    assert chasing(env, undated) == ["nudge"]
    set_stance(store, them, "report_to")
    assert chasing(env, undated) == []
    set_stance(store, them, "watch")
    assert chasing(env, undated) == []
    set_stance(store, them, "alongside")
    assert chasing(env, undated) == ["nudge"]


@pytest.mark.parametrize("stance", ["manage", "alongside", "report_to", "watch"])
def test_a_reply_owed_is_never_gated_by_stance(env, stance):
    _, cfg, store = env
    asker = other(cfg)
    set_stance(store, asker, stance)
    owed = make(store, [me(cfg)], due=None, text="Reply to the question", reply_owed=True, asker=asker)
    assert [line.kind for line in lines(env) if owed in line.actions] == ["reply"]


# ---- a correction proposes a stance -----------------------------------------------------------------------------


def stance_op(env, stance: str = "report_to", **more) -> dict:
    _, cfg, store = env
    return {
        "op": "person.stance",
        "id": other(cfg),
        "stance": stance,
        "evidence": {"quote": "we are not their boss"},
        **more,
    }


def proposal(env, op: dict | None = None):
    """The op as a learning run's answer: a held change, nothing applied."""
    _, cfg, store = env
    return apply(
        store,
        cfg,
        [op or stance_op(env)],
        origin="schedule",
        trust="untrusted",
        source_id=source(store),
        raw="Not my job: we are not their boss.",
    )


def test_the_op_is_a_system_op_learning_may_propose_and_it_says_what_each_stance_allows():
    assert TIERS["person.stance"] == "system"
    assert "person.stance" in LEARN_OPS and "person.stance" not in KNOWLEDGE_ADD_OPS
    text = reference_for(["person.stance"])
    for words in ("manage", "alongside", "report_to", "watch", "design", "nothing is drafted"):
        assert words in text


def test_a_proposed_stance_changes_nothing_until_the_person_keeps_it(env):
    _, cfg, store = env
    them = other(cfg)
    cs_id, statuses = proposal(env)
    assert statuses == ["held"] and "needs your confirmation" in reasons(store, cs_id)[0]
    assert store.read().get("person", them).data.get("stance") is None
    release(store, cfg, cs_id, 0)
    assert store.read().get("person", them).data["stance"] == "report_to"


def test_a_proposal_names_a_real_person_other_than_the_one_who_asks_and_quotes_the_words(env):
    _, cfg, store = env
    cs_id, statuses = proposal(env, stance_op(env, id="PER-9999"))
    assert statuses == ["refused"] and "there is no person" in reasons(store, cs_id)[0]
    cs_id, statuses = proposal(env, stance_op(env, id=me(cfg)))
    assert statuses == ["refused"] and "yourself" in reasons(store, cs_id)[0]
    no_quote = stance_op(env)
    no_quote.pop("evidence")
    cs_id, statuses = proposal(env, no_quote)
    assert statuses == ["refused"]
    cs_id, statuses = proposal(env, stance_op(env, evidence={"quote": "words that are not there"}))
    assert statuses == ["refused"] and "isn't in the input" in reasons(store, cs_id)[0]


def test_the_persons_own_note_sets_a_stance_at_once(env):
    _, cfg, store = env
    own = source(store, kind="note:action", trust="trusted")
    cs_id, statuses = apply(
        store,
        cfg,
        [stance_op(env, "watch")],
        origin="pm",
        source_id=own,
        raw="we are not their boss",
    )
    assert statuses == ["applied"]
    assert store.read().get("person", other(cfg)).data["stance"] == "watch"


# ---- the person's own choice -------------------------------------------------------------------------------------


def test_the_person_picks_a_stance_by_their_own_edit_and_undo_takes_it_back(env):
    _, cfg, store = env
    them = other(cfg)
    before = store.read().get("person", them)
    edit = {
        "op": "record.edit",
        "record": {"kind": "person", "id": them},
        "fields": {"stance": "report_to"},
        "read_version": before.version,
    }
    cs_id = apply_as_person(store, cfg, [edit], "Saved")
    assert store.read().get("person", them).data["stance"] == "report_to"
    report = undo(store, cs_id)
    assert report.restored and store.read().get("person", them).data.get("stance") == before.data.get("stance")
    # Use my default: the field is cleared.
    set_stance(store, them, "watch")
    now = store.read().get("person", them)
    clear = {**edit, "fields": {"stance": None}, "read_version": now.version}
    apply_as_person(store, cfg, [clear], "Saved")
    assert store.read().get("person", them).data.get("stance") is None


# ---- the learning pairs ------------------------------------------------------------------------------------------


def test_a_stance_pair_needs_the_persons_keep_for_the_next_input_to_be_read_with_it(monkeypatch):
    from tests.conftest import DEMO_B
    from tests.test_pairs import edited, run

    assert run(DEMO_B, "stance-report-to").passed
    result = edited(monkeypatch, DEMO_B, "stance-report-to", lambda pair: pair["first"].update(keep=False))
    assert not result.passed and any("the packet doesn't hold" in m for m in result.missing)


# ---- Settings ----------------------------------------------------------------------------------------------------


def test_settings_offer_the_default_stance_and_what_is_tracked_as_lists_to_pick_from(env):
    from engine.settings import describe

    ws, cfg, store = env
    items = {s.key: s for s in describe(cfg, store.plugins, ws.config_dir)}
    stance, tracks = items["steward.default_stance"], items["steward.tracks"]
    assert (stance.type, stance.editable, stance.options) == (
        "choice",
        True,
        ["manage", "alongside", "report_to", "watch"],
    )
    assert (tracks.type, tracks.editable, tracks.options) == ("list", True, ["dates", "decisions", "design"])


def test_the_tracked_list_saves_through_settings(env):
    from engine.settings import fingerprint, save

    ws, cfg, store = env
    save(ws, cfg, store, changes={"steward.tracks": ["dates"]}, reset=[], read_fingerprint=fingerprint(ws.config_dir))
    assert ws.config(env={}).steward.tracks == ["dates"]


def test_a_proposed_stance_waits_on_today_as_a_line_that_names_the_person_and_what_it_would_mean(env):
    _, cfg, store = env
    cs_id, _ = proposal(env)
    with store.transaction() as tx:
        asked = tx.get("changeset", cs_id).data["request"]
        tx.update("request", asked, {"changeset": cs_id}, _TEST, read_version=tx.get("request", asked).version)
    held = [line for line in lines(env) if line.kind == "held"]
    assert [line.text for line in held] == [
        f"Change who {store.read().get('person', other(cfg)).data['full_name']} is to you: you report to them"
    ]
