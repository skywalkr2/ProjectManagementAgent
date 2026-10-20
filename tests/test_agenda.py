"""A meeting holds agenda items, linked to what they came from (design 5.x calendar entries and series, 6.33 endings):
`agenda.add` lists an action, a question or a note on a calendar entry or a series with who put it there, when and the
words, changing nothing else; from an input it waits for the person; Undo takes it off. An action called off because its
words move it into a meeting the workspace knows is put on that meeting's agenda by the same drop, so it isn't lost.
Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine import endings
from engine.ai.adapters.stub import set_responder
from engine.applier import Context, Inputs, apply_changeset, check, release, undo
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, PERSON_ONLY_OPS, TIERS
from engine.record_page import page as record_page
from engine.series_page import page as series_page
from engine.storage import Store, WriteContext
from engine.today import agenda as todays_agenda
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_endings_need_delivery import close_op, drop_op, from_input, own_note, someone_elses
from tests.test_knowledge_records import request

_PM = WriteContext("pm", "trusted", "test")
UTC_ZONE = ZoneInfo("UTC")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
SOON, LATER, PAST = "2026-10-20", "2026-10-27", "2026-10-06"
MEETING = "Planning sessions"
SAID = f"The {MEETING.lower()} will cover it"
PEOPLE = [p["id"] for p in fixture_records(DEMO_B, "person")]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def entry(store, start=SOON, title=MEETING, **more) -> str:
    with store.transaction() as tx:
        return tx.create("event", {"title": title, "start": start, "trust": "trusted", **more}, _PM).id


def make_series(store, *starts, title=MEETING) -> tuple[str, list[str]]:
    with store.transaction() as tx:
        sid = tx.create("series", {"title": title, "repeats": "every Tuesday", "trust": "trusted"}, _PM).id
    return sid, [entry(store, start, title=title, series=sid) for start in starts]


def a_question(store) -> str:
    with store.transaction() as tx:
        return tx.create("question", {"to": PEOPLE[1], "title": "Which proof is final?"}, _PM).id


def a_note(store) -> str:
    with store.transaction() as tx:
        return tx.create("note", {"text": "The printer asked about the trim size.", "trust": "trusted"}, _PM).id


def data(store, kind, record_id) -> dict:
    return store.read().get(kind, record_id).data


def data_version(store, record_id) -> int:
    return store.read().get("event", record_id).version


def put(store, cfg, op, *, own=True, raw="Put it on the agenda"):
    """Apply an `agenda.add` as the person's own note (`own`) or as read from an input: the changeset and statuses."""
    op = {"op": "agenda.add", "evidence": {"quote": raw}, **op}
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request(store, "pm" if own else "input"), None, "", raw, "trusted" if own else "untrusted"),
        confirmed_by_pm=False,
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def refusals(env, op, raw="Put it on the agenda"):
    _, cfg, store = env
    op = {"op": "agenda.add", "evidence": {"quote": raw}, **op}
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", None, "", raw, "trusted"))
    return [p.message for p in check(cs, ctx) if p.severity == "refuse"]


# ---- the op ---------------------------------------------------------------------------------------


def test_agenda_add_is_a_system_op_that_needs_evidence_unless_the_person_makes_it():
    from engine.ops import EVIDENCE_UNLESS_PERSON, NEEDS_EVIDENCE

    assert TIERS["agenda.add"] == "system" and "agenda.add" not in PERSON_ONLY_OPS
    assert "agenda.add" in NEEDS_EVIDENCE and "agenda.add" in EVIDENCE_UNLESS_PERSON
    op = OP_MODELS["agenda.add"].model_validate({"op": "agenda.add", "event": "EVT-1", "action": "ACT-1"})
    assert "ACT-1" not in op.describe() and "EVT-1" not in op.describe()  # named by title where a view is given


def test_an_agenda_item_names_one_meeting_and_one_record():
    model = OP_MODELS["agenda.add"]
    for bad in (
        {"event": "EVT-1", "series": "SER-1", "action": "ACT-1"},
        {"action": "ACT-1"},
        {"event": "EVT-1"},
        {"event": "EVT-1", "action": "ACT-1", "note": "NOTE-1"},
    ):
        with pytest.raises(ValueError):
            model.model_validate({"op": "agenda.add", **bad})


def test_the_persons_note_puts_an_action_on_a_meetings_agenda_linked_and_undo_takes_it_off(env):
    _, cfg, store = env
    meeting, action = entry(store), someone_elses(cfg)["id"]
    before = data(store, "action", action)
    cs_id, result = put(store, cfg, {"event": meeting, "action": action})
    assert result == ["applied"]
    [item] = data(store, "event", meeting)["agenda"]
    assert item["action"] == action and item["added_by"] == cfg.workspace.user.person
    assert item["text"] == " ".join(before["text"].split()) and item["added_at"]
    assert data(store, "action", action) == before  # the item is listed, not changed
    assert undo(store, cs_id).restored == [0]
    assert data(store, "event", meeting).get("agenda", []) == []


def test_a_question_and_a_note_go_on_the_agenda_in_the_order_they_were_put_there_under_the_words_given(env):
    _, cfg, store = env
    meeting, question, note = entry(store), a_question(store), a_note(store)
    put(store, cfg, {"event": meeting, "question": question, "text": "  Settle the  proof "})
    put(store, cfg, {"event": meeting, "note": note})
    first, second = data(store, "event", meeting)["agenda"]
    assert (first["question"], first["text"]) == (question, "Settle the proof")
    assert second["note"] == note and second["text"] == data(store, "note", note)["text"]


def test_an_item_on_a_series_goes_on_the_series_agenda(env):
    _, cfg, store = env
    series, _ = make_series(store, SOON, LATER)
    action = someone_elses(cfg)["id"]
    _, result = put(store, cfg, {"series": series, "action": action})
    assert result == ["applied"]
    assert [i["action"] for i in data(store, "series", series)["agenda"]] == [action]


def test_from_an_input_it_waits_for_the_person_and_their_keep_puts_it_there_as_theirs(env):
    _, cfg, store = env
    meeting, action = entry(store), someone_elses(cfg)["id"]
    cs_id, result = put(store, cfg, {"event": meeting, "action": action}, own=False)
    assert result == ["held"]
    assert data(store, "event", meeting).get("agenda", []) == []
    release(store, cfg, cs_id, 0)
    [item] = data(store, "event", meeting)["agenda"]
    assert item["added_by"] == cfg.workspace.user.person


def test_what_the_agenda_refers_to_must_exist_be_open_and_not_already_there(env):
    _, cfg, store = env
    meeting, action = entry(store), someone_elses(cfg)["id"]
    assert refusals(env, {"event": "EVT-999", "action": action})
    assert refusals(env, {"series": "SER-999", "action": action})
    assert refusals(env, {"event": meeting, "action": "ACT-999"})
    put(store, cfg, {"event": meeting, "action": action})
    assert "already on the agenda" in refusals(env, {"event": meeting, "action": action})[0]
    done = next(a for a in fixture_records(DEMO_B, "action") if a.get("status") == "done")["id"]
    assert "already done" in refusals(env, {"event": meeting, "action": done})[0]


def test_the_agenda_of_a_meeting_is_only_changed_by_the_op(env):
    _, cfg, store = env
    meeting = entry(store)
    from engine.applier import apply_as_person

    with pytest.raises(Exception, match="can't be changed this way"):
        apply_as_person(
            store,
            cfg,
            [
                {
                    "op": "record.edit",
                    "record": {"kind": "event", "id": meeting},
                    "fields": {"agenda": []},
                    "read_version": data_version(store, meeting),
                }
            ],
            "Changed on screen",
        )


# ---- what the screens read ------------------------------------------------------------------------


def test_a_meetings_page_and_its_todays_row_list_its_items_and_the_series_page_lists_the_series_and_its_next_meeting(
    env,
):
    ws, cfg, store = env
    series, (past, next_one, _) = make_series(store, PAST, SOON, LATER)
    action = someone_elses(cfg)["id"]
    put(store, cfg, {"event": next_one, "action": action})
    put(store, cfg, {"series": series, "question": a_question(store)})
    view = store.read()
    here = ZoneInfo(cfg.workspace.user.timezone)
    found = record_page(store, "event", next_one, pm=cfg.workspace.user.person, today=TODAY, here=here)
    words = [line["text"] for line in found["agenda"]]
    assert words[0] == " ".join(data(store, "action", action)["text"].split()) and len(words) == 2  # then the series'
    assert found["agenda"][0]["id"] == action and found["agenda"][0]["added_by_name"]
    assert not any(row["field"] == "agenda" for row in found["details"])
    other = record_page(store, "event", past, pm=cfg.workspace.user.person, today=TODAY, here=here)
    assert other["agenda"] == []
    shown = series_page(view, series, TODAY, here, pm=cfg.workspace.user.person)
    assert [line["id"] for line in shown["agenda"]][0] != action and len(shown["agenda"]) == 2
    on_today = [a for a in todays_agenda(store, cfg, datetime(2026, 10, 20, 9, tzinfo=UTC), through=date(2026, 10, 27))]
    row = next(a for a in on_today if a.snapshot == next_one)
    assert [line["id"] for line in row.agenda][0] == action


# ---- a call-off that moves an action into a meeting ----------------------------------------------------------


def test_the_meeting_words_have_a_description_a_default_and_demo_values_in_both_workspaces():
    import yaml

    from engine.config.schema import LanguageFile
    from tests.conftest import DEMO_A

    assert LanguageFile.model_fields["meeting_words"].description and LanguageFile().meeting_words
    for template in (DEMO_A, DEMO_B):
        language = yaml.safe_load((template / "config" / "language.yaml").read_text())
        assert language["meeting_words"] == list(endings.DEFAULT_MEETING_WORDS)


def test_called_off_into_a_meeting_it_is_dropped_and_put_on_that_meetings_agenda_and_undo_takes_both_back(env):
    _, cfg, store = env
    target, meeting = someone_elses(cfg), entry(store)
    cs_id, result = own_note(store, cfg, close_op(target["id"], SAID))
    assert result == ["applied"]
    gone = data(store, "action", target["id"])
    assert (gone["status"], gone["dropped_reason"]) == ("dropped", SAID)  # called off, nobody credited
    held = store.read().get("changeset", cs_id).data["ops"][0]["op"]
    assert held["op"] == "action.drop" and held["event"] == meeting
    [item] = data(store, "event", meeting)["agenda"]
    assert item["action"] == target["id"] and item["text"] == " ".join(target["text"].split())
    assert item["added_by"] == cfg.workspace.user.person
    assert undo(store, cs_id).restored == [0]
    assert data(store, "action", target["id"])["status"] == "open"
    assert data(store, "event", meeting).get("agenda", []) == []


def test_a_drop_the_assistant_proposed_with_such_words_is_put_on_the_agenda_too_and_waits_with_it_from_an_input(env):
    _, cfg, store = env
    target, meeting = someone_elses(cfg), entry(store)
    cs_id, result = from_input(store, cfg, drop_op(target["id"], SAID))
    assert result == ["held"]  # how a promise ends is the person's to keep when it came in
    assert data(store, "event", meeting).get("agenda", []) == []
    release(store, cfg, cs_id, 0)
    assert data(store, "action", target["id"])["status"] == "dropped"
    assert [i["action"] for i in data(store, "event", meeting)["agenda"]] == [target["id"]]


def test_a_series_the_words_name_gets_the_item_when_no_entry_is_ahead_and_the_next_meeting_gets_it_when_one_is(env):
    _, cfg, store = env
    series, _ = make_series(store, PAST)  # every instance has passed
    target = someone_elses(cfg)
    own_note(store, cfg, close_op(target["id"], SAID))
    assert [i["action"] for i in data(store, "series", series)["agenda"]] == [target["id"]]
    other = next(a for a in fixture_records(DEMO_B, "action") if a.get("owners") and a["id"] != target["id"])
    coming = entry(store, SOON, series=series)
    own_note(store, cfg, close_op(other["id"], SAID))
    assert [i["action"] for i in data(store, "event", coming)["agenda"]] == [other["id"]]


@pytest.mark.parametrize(
    "words",
    [
        "The planning sessions are moot",  # no meeting words: called off, but not moved anywhere
        "It will be covered by someone, we'll cover it",  # meeting words, but no meeting named
        "The sessions will cover it",  # not the meeting's whole name
    ],
)
def test_words_that_move_it_to_no_known_meeting_only_call_it_off(env, words):
    _, cfg, store = env
    meeting, target = entry(store), someone_elses(cfg)
    cs_id, result = own_note(store, cfg, close_op(target["id"], words))
    assert result == ["applied"] and data(store, "action", target["id"])["status"] == "dropped"
    assert data(store, "event", meeting).get("agenda", []) == []
    assert "event" not in store.read().get("changeset", cs_id).data["ops"][0]["op"]


def test_a_meeting_that_passed_or_was_called_off_or_is_named_twice_is_not_the_one_meant(env):
    _, cfg, store = env
    people = [a for a in fixture_records(DEMO_B, "action") if a.get("owners")]
    passed = entry(store, PAST)
    off = entry(store, SOON, cancelled=True)
    for record in (passed, off):
        assert store.read().get("event", record)
    first = people[0]
    own_note(store, cfg, close_op(first["id"], SAID))
    assert data(store, "event", passed).get("agenda", []) == [] and data(store, "event", off).get("agenda", []) == []
    # A second, different meeting named in the same words makes it ambiguous: none is chosen.
    entry(store, SOON, title="Planning")
    entry(store, LATER, title="Sessions")
    second = people[1]
    cs_id, _ = own_note(store, cfg, close_op(second["id"], f"{SAID} and the planning and the sessions"))
    assert "event" not in store.read().get("changeset", cs_id).data["ops"][0]["op"]


def test_the_same_changeset_gives_the_same_ops_for_the_check_and_the_apply(env):
    _, cfg, store = env
    entry(store)
    target = someone_elses(cfg)
    cs = CHANGESET.validate_python({"ops": [close_op(target["id"], SAID)]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request(store, "input"), None, "", SAID, "untrusted"),
    )
    once = endings.read_endings(cs, ctx)
    assert endings.read_endings(once, ctx).ops == once.ops and once.ops[0].event is not None
