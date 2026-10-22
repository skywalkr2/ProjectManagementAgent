"""A sender's distribution limit travels with the content (design 6.35): a message that says who may see it limits its
source to the people it went to and came from; a question or reply drafted from it to anyone outside that group is
refused; the assistant may only narrow the group, and the person alone widens it, with Undo. Names, ids, addresses and
texts come from the fixtures; the few free words are about no one."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine import audience
from engine.applier import Context, Inputs, apply_as_person, apply_changeset, check
from engine.dispatcher import undo_changeset
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, PERSON_ONLY_OPS, TIERS
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.audience")
TOKEN = "audience-token"


def person(role: str) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


SENDER = person("Editor")  # the fixture gives this person an address
INSIDE = person("Cover designer")
OUTSIDE = person("Typesetter")
ADDRESSES = {
    "inside": "inside.person@example.com",
    "outside": "outside.person@example.com",
    "me": "the.person@example.com",
}
STRANGER = "Stranger.Contact@Example.com"
MARKING = "Internal only"
RESTRICTED_BODY = f"{MARKING}: the print team is moving the proof date, so please keep this among us. Thanks."
OPEN_BODY = "The proof date is moving, so please plan around it. Thanks."
LINK = fixture_records(DEMO_B, "project")[0]["links"][0]


def me(cfg) -> str:
    return cfg.workspace.user.person


def write(pair: tuple[str, str]) -> str:
    return f"{pair[0]} <{pair[1]}>"


def mail(body: str, *, to=(), cc=(), subject="Proof date") -> str:
    """A message as a mail source writes its text: the header lines, a blank line, then the body."""
    sender = (SENDER["full_name"], SENDER["how_to_reach"]["email"])
    lines = [f"From: {write(sender)}", f"To: {', '.join(write(p) for p in to)}"]
    if cc:
        lines.append(f"Cc: {', '.join(write(p) for p in cc)}")
    return "\n".join([*lines, f"Subject: {subject}", "", body])


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    with store.transaction() as tx:  # the addresses the people's records hold
        for pid, address in (
            (me(cfg), ADDRESSES["me"]),
            (INSIDE["id"], ADDRESSES["inside"]),
            (OUTSIDE["id"], ADDRESSES["outside"]),
        ):
            found = tx.get("person", pid)
            reach = {**found.data.get("how_to_reach", {}), "email": address}
            tx.update("person", pid, {"how_to_reach": reach}, _TEST, read_version=found.version)
    yield ws, cfg, store
    store.close()


def recipients(cfg, *extra):
    return [("The person", ADDRESSES["me"]), (INSIDE["full_name"], ADDRESSES["inside"]), *extra]


def hand(env, body: str, **kw) -> tuple[str, str]:
    """Hand in a pasted message; returns its text and its source id."""
    ws, cfg, store = env
    text = mail(body, to=kw.pop("to", None) or recipients(cfg), **kw)
    return text, hand_in(ws, store, pasted=text, now=NOW).source


def audience_of(store, source_id: str):
    return store.read().get("source", source_id).data.get("audience")


def question_to(who: dict, **more) -> dict:
    return {
        "op": "question.add",
        "to": who["id"],
        "title": "Is the file final?",
        "links": [LINK],
        "matters_for": "The date the file goes out",
        **more,
    }


def problems(env, op, source_id: str, raw: str, name="audience", *, actor="assistant"):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", source_id, raw, "", "untrusted"),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if p.check == name]


def run(env, ops: list[dict], source_id: str, raw: str):
    """Apply ops the way a run on this input does; returns the changeset id and each op's outcome."""
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create(
            "request",
            {"task": "notes", "origin": "input", "state": "done", "created_at": NOW, "source": source_id},
            _TEST,
        )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request.id, source_id, raw, "", "untrusted"),
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, store.read().get("changeset", cs_id).data["ops"]


# ---- reading the limit, by rules -------------------------------------------------------------------------------------


def test_a_marking_in_the_new_text_limits_the_source_to_the_people_it_went_to_and_came_from(env):
    ws, cfg, store = env
    _, source = hand(env, RESTRICTED_BODY, cc=[("Someone Else", STRANGER)])
    found = audience_of(store, source)
    assert found["marking"].lower() == MARKING.lower()
    assert found["why"].startswith(MARKING) and found["why"].endswith("among us.")
    # the sender, the person and the cover designer by id, the stranger by address
    assert set(found["people"]) == {SENDER["id"], me(cfg), INSIDE["id"], STRANGER.lower()}
    assert found["widened_by"] is None and found["group"] is None


def test_a_message_with_no_marking_has_no_audience(env):
    _, _, store = env
    _, source = hand(env, OPEN_BODY)
    assert audience_of(store, source) is None


def test_a_marking_in_quoted_history_does_not_limit(env):
    _, _, store = env
    quoted = f"Thanks, I will plan around it.\n\nOn Mon, 12 Oct 2026, Someone wrote:\n> {RESTRICTED_BODY}\n"
    _, source = hand(env, quoted)
    assert audience_of(store, source) is None


def test_a_marking_matches_whole_words_ignoring_case(env):
    _, _, store = env
    _, source = hand(env, "This is not confidentially sensitive, but INTERNAL ONLY for now.")
    assert audience_of(store, source)["marking"].lower() == "internal only"
    _, other = hand(env, "The confidentiality of the plan is not in doubt.", subject="Other")
    assert audience_of(store, other) is None


def test_the_markings_are_a_setting(env, tmp_path):
    ws, cfg, store = env
    assert "internal only" in cfg.language.limit_markings and "confidential" in cfg.language.limit_markings
    text = mail("Please keep this for the print crew only.", to=recipients(cfg))
    people = People(store, cfg)
    assert audience.limit_of(text, cfg.language.limit_markings, people) is None
    changed = ws.config(env={"COCKPIT__LANGUAGE__LIMIT_MARKINGS": "[for the print crew only]"})
    found = audience.limit_of(text, changed.language.limit_markings, people)
    assert found is not None and found["marking"] == "for the print crew only"
    # and the hand-in reads the workspace's setting
    other_store = Store(ws.db_path, cfg=changed)
    try:
        source = hand_in(ws, other_store, pasted=text, now=NOW, cfg=changed).source
        assert audience_of(other_store, source) is not None
    finally:
        other_store.close()


def test_a_pasted_note_with_no_headers_has_no_audience_to_record(env):
    ws, cfg, store = env
    source = hand_in(ws, store, pasted=f"{MARKING}: a note to myself.", now=NOW).source
    assert audience_of(store, source) is None


# ---- the invariant ---------------------------------------------------------------------------------------------------


def test_a_question_to_someone_outside_a_limited_message_is_refused_and_the_open_one_is_not(env):
    _, cfg, store = env
    limited_text, limited = hand(env, RESTRICTED_BODY)
    open_text, open_source = hand(env, OPEN_BODY, subject="Other")
    (refused,) = problems(env, question_to(OUTSIDE), limited, limited_text)
    assert refused.severity == "refuse"
    names = ", ".join(People(store, cfg).name(p) for p in (SENDER["id"], me(cfg), INSIDE["id"]))  # From, then To
    assert refused.message == (f"this draws on a message limited to {names}, so it can't go to {OUTSIDE['full_name']}")
    assert problems(env, question_to(OUTSIDE), open_source, open_text) == []


def test_a_question_inside_the_audience_or_to_the_person_applies(env):
    _, cfg, store = env
    text, source = hand(env, RESTRICTED_BODY)
    assert problems(env, question_to(INSIDE), source, text) == []
    assert problems(env, question_to(SENDER), source, text) == []
    assert problems(env, {**question_to(INSIDE), "to": me(cfg), "links": []}, source, text) == []
    _, outcomes = run(env, [question_to(INSIDE)], source, text)
    assert [o["status"] for o in outcomes] == ["applied"]


def test_the_refusal_stops_the_op_and_a_name_resolves_through_the_people(env):
    text, source = hand(env, RESTRICTED_BODY)
    named = question_to(OUTSIDE, to=OUTSIDE["full_name"])
    _, outcomes = run(env, [named], source, text)
    assert outcomes[0]["status"] == "refused" and "can't go to" in outcomes[0]["reason"]


def test_a_reply_that_is_not_the_reply_owed_goes_to_the_sender_who_may_be_outside_a_narrowed_audience(env):
    _, cfg, store = env
    text, source = hand(env, RESTRICTED_BODY)
    reply = {
        "op": "action.add",
        "text": "Tell the sender the proof date",
        "owners": [me(cfg)],
        "reply": "The proof date is moving to November 3.",
        "evidence": {"quote": "moving the proof date"},
    }
    assert problems(env, reply, source, text) == []  # the sender is on their own message
    _, outcomes = run(
        env,
        [
            {
                "op": "source.limit",
                "id": source,
                "people": [INSIDE["full_name"]],
                "group": "the cover designer",
                "evidence": {"quote": "keep this among us"},
            }
        ],
        source,
        text,
    )
    assert outcomes[0]["status"] == "applied", outcomes
    (refused,) = problems(env, reply, source, text)
    assert f"can't go to {SENDER['full_name']}" in refused.message
    # a reply owed answers this very message: its own limit is not counted against the asker
    assert problems(env, {**reply, "reply_owed": True}, source, text) == []


# ---- narrowing, and only narrowing ----------------------------------------------------------------------------------


def test_the_assistant_narrows_to_a_named_group_and_it_applies_at_once(env):
    _, cfg, store = env
    text, source = hand(env, RESTRICTED_BODY, cc=[(OUTSIDE["full_name"], ADDRESSES["outside"])])
    assert OUTSIDE["id"] in audience_of(store, source)["people"]
    assert problems(env, question_to(OUTSIDE), source, text) == []
    op = {
        "op": "source.limit",
        "id": source,
        "people": [INSIDE["full_name"]],
        "group": "the print team",
        "evidence": {"quote": "keep this among us"},
    }
    _, outcomes = run(env, [op], source, text)
    assert outcomes[0]["status"] == "applied", outcomes
    found = audience_of(store, source)
    assert found["people"] == [INSIDE["id"]] and found["group"] == "the print team"
    assert found["marking"].lower() == MARKING.lower()  # the rules' reading is kept
    assert len(problems(env, question_to(OUTSIDE), source, text)) == 1


def test_a_widening_by_source_limit_is_refused(env):
    text, source = hand(env, RESTRICTED_BODY)
    op = {
        "op": "source.limit",
        "id": source,
        "people": [INSIDE["full_name"], OUTSIDE["full_name"]],
        "group": "the print team and the typesetter",
        "evidence": {"quote": "keep this among us"},
    }
    _, outcomes = run(env, [op], source, text)
    assert outcomes[0]["status"] == "refused"
    assert OUTSIDE["full_name"] in outcomes[0]["reason"] and "can only narrow" in outcomes[0]["reason"]


def test_source_limit_on_an_open_message_narrows_to_the_messages_people_only(env):
    _, _, store = env
    text, source = hand(env, "Only the print team should see the new date, please.")
    inside = {
        "op": "source.limit",
        "id": source,
        "people": [INSIDE["full_name"]],
        "group": "the print team",
        "evidence": {"quote": "Only the print team"},
    }
    _, outcomes = run(env, [inside], source, text)
    assert outcomes[0]["status"] == "applied"
    assert audience_of(store, source)["people"] == [INSIDE["id"]]
    text2, source2 = hand(env, "Only the print team should see the other date, please.", subject="Other")
    outside = {**inside, "id": source2, "people": [OUTSIDE["full_name"]], "evidence": {"quote": "Only the print team"}}
    _, outcomes = run(env, [outside], source2, text2)
    assert outcomes[0]["status"] == "refused"


def test_source_limit_is_a_data_op_that_needs_evidence_and_only_limits_the_input_it_came_from(env):
    text, source = hand(env, RESTRICTED_BODY)
    assert TIERS["source.limit"] == "data" and "source.limit" in OP_MODELS
    assert OP_MODELS["source.limit"].model_fields["evidence"].is_required()
    other_text, other = hand(env, OPEN_BODY, subject="Other")
    op = {
        "op": "source.limit",
        "id": other,
        "people": [INSIDE["full_name"]],
        "group": "the print team",
        "evidence": {"quote": "keep this among us"},
    }
    _, outcomes = run(env, [op], source, text)  # the run is on the restricted message; the op names another
    assert outcomes[0]["status"] == "refused" and "this input" in outcomes[0]["reason"]


# ---- widening is the person's ----------------------------------------------------------------------------------------


def test_widening_is_the_persons_alone(env):
    text, source = hand(env, RESTRICTED_BODY)
    assert "source.widen" in PERSON_ONLY_OPS and TIERS["source.widen"] == "data"
    _, outcomes = run(env, [{"op": "source.widen", "id": source, "people": [OUTSIDE["id"]]}], source, text)
    assert outcomes[0]["status"] == "refused" and "only the person" in outcomes[0]["reason"]


def test_the_person_widens_the_audience_and_undo_restores_the_narrower_one(env):
    _, cfg, store = env
    text, source = hand(env, RESTRICTED_BODY)
    before = audience_of(store, source)
    cs_id = apply_as_person(
        store, cfg, [{"op": "source.widen", "id": source, "people": [OUTSIDE["id"]]}], "Widened a limit"
    )
    after = audience_of(store, source)
    assert OUTSIDE["id"] in after["people"] and after["widened_by"] == me(cfg)
    assert set(before["people"]) < set(after["people"])
    assert problems(env, question_to(OUTSIDE), source, text) == []
    report = undo_changeset(store, cs_id)
    assert report.restored
    assert audience_of(store, source) == before
    assert len(problems(env, question_to(OUTSIDE), source, text)) == 1


def test_the_person_removes_the_limit_and_undo_puts_it_back(env):
    _, cfg, store = env
    text, source = hand(env, RESTRICTED_BODY)
    before = audience_of(store, source)
    cs_id = apply_as_person(store, cfg, [{"op": "source.widen", "id": source, "open": True}], "Removed a limit")
    assert audience_of(store, source) is None
    undo_changeset(store, cs_id)
    assert audience_of(store, source) == before


def test_widening_must_name_people_or_open_and_the_source_must_be_limited(env):
    _, cfg, store = env
    text, source = hand(env, RESTRICTED_BODY)
    with pytest.raises(ValidationError):
        apply_as_person(store, cfg, [{"op": "source.widen", "id": source}], "Nothing")
    with pytest.raises(StoreError, match="isn't one known person"):
        apply_as_person(store, cfg, [{"op": "source.widen", "id": source, "people": ["PER-99"]}], "Nobody")
    _, open_source = hand(env, OPEN_BODY, subject="Other")
    with pytest.raises(StoreError, match="isn't limited"):
        apply_as_person(store, cfg, [{"op": "source.widen", "id": open_source, "open": True}], "Nothing to do")


def test_the_limit_can_only_change_through_these_ops(env):
    _, cfg, store = env
    _, source = hand(env, RESTRICTED_BODY)
    version = store.read().get("source", source).version
    with pytest.raises(StoreError):
        apply_as_person(
            store,
            cfg,
            [
                {
                    "op": "record.edit",
                    "record": {"kind": "source", "id": source},
                    "fields": {"audience": None},
                    "read_version": version,
                }
            ],
            "Edited",
        )


# ---- what is made from a limited message carries its limit -----------------------------------------------------------

RESTRICTED_WORD = "tangerine"
OPEN_WORD = "marigold"
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
TODAY = NOW.date()


def fact_from(env, source: str, raw: str, word: str, quote: str) -> str:
    """Record a fact quoted from a message, the way a run on it does; returns the fact's id."""
    _, cfg, store = env
    op = {"op": "fact", "text": f"The {word} proof date is moving.", "project": PROJECT, "evidence": {"quote": quote}}
    _, outcomes = run(env, [op], source, raw)
    assert outcomes[0]["status"] == "applied", outcomes
    return next(f.id for f in store.read().list("fact") if word in f.data["text"])


def action_from(env, source: str, raw: str, word: str, quote: str) -> str:
    _, cfg, store = env
    op = {"op": "action.add", "text": f"Check the {word} proof", "owners": [me(cfg)], "evidence": {"quote": quote}}
    _, outcomes = run(env, [op], source, raw)
    assert outcomes[0]["status"] == "applied", outcomes
    return next(a.id for a in store.read().list("action") if word in a.data["text"])


def mail_from(who: dict, address: str, body: str, *, to, subject="Proof date") -> str:
    lines = [f"From: {who['full_name']} <{address}>", f"To: {', '.join(write(p) for p in to)}"]
    return "\n".join([*lines, f"Subject: {subject}", "", body])


def test_a_fact_quoted_from_a_limited_message_carries_its_limit_read_from_the_source(env):
    _, cfg, store = env
    text, limited = hand(env, RESTRICTED_BODY)
    open_text, open_source = hand(env, OPEN_BODY, subject="Other")
    fact = fact_from(env, limited, text, RESTRICTED_WORD, "moving the proof date")
    plain = fact_from(env, open_source, open_text, OPEN_WORD, "The proof date is moving")
    view = store.read()
    carried = audience.limit_of_record(view, view.get("fact", fact).data)
    assert carried is not None and carried["people"] == audience_of(store, limited)["people"]
    assert audience.limit_of_record(view, view.get("fact", plain).data) is None
    # derived, not copied: widening the source widens what was made from it, with nothing else to update
    assert "audience" not in view.get("fact", fact).data
    apply_as_person(store, cfg, [{"op": "source.widen", "id": limited, "people": [OUTSIDE["id"]]}], "Widened")
    again = store.read()
    assert OUTSIDE["id"] in audience.limit_of_record(again, again.get("fact", fact).data)["people"]


def test_a_record_drawing_on_several_sources_carries_the_narrowest_limit(env):
    _, cfg, store = env
    _, limited = hand(env, RESTRICTED_BODY)
    narrow_text, narrower = hand(env, RESTRICTED_BODY.replace("print team", "cover team"), subject="Narrower")
    limit = {
        "op": "source.limit",
        "id": narrower,
        "people": [INSIDE["full_name"]],
        "group": "the cover designer",
        "evidence": {"quote": "keep this among us"},
    }
    assert run(env, [limit], narrower, narrow_text)[1][0]["status"] == "applied"
    record = {"source": limited, "evidence": {"source": narrower, "quote": "x"}}
    got = audience.limit_of_record(store.read(), record)
    assert got is not None and got["people"] == [INSIDE["id"]]
    assert audience.limit_of_record(store.read(), {"evidence": {"source": "note", "quote": "x"}}) is None


def test_a_draft_naming_a_record_made_from_a_limited_message_is_refused_outside_its_audience(env):
    _, cfg, store = env
    text, limited = hand(env, RESTRICTED_BODY)
    open_text, open_source = hand(env, OPEN_BODY, subject="Other")
    secret = fact_from(env, limited, text, RESTRICTED_WORD, "moving the proof date")
    plain = fact_from(env, open_source, open_text, OPEN_WORD, "The proof date is moving")
    # a later run, on a message that is itself open, names the fact in what it asks
    later = mail_from(OUTSIDE, ADDRESSES["outside"], "Is the date still right? Thanks.", to=recipients(cfg))
    later_source = hand_in(env[0], store, pasted=later, now=NOW).source
    op = question_to(OUTSIDE, matters_for=f"The date in {secret}")
    (refused,) = problems(env, op, later_source, later)
    assert refused.severity == "refuse" and f"can't go to {OUTSIDE['full_name']}" in refused.message
    assert problems(env, question_to(OUTSIDE, matters_for=f"The date in {plain}"), later_source, later) == []
    assert problems(env, question_to(INSIDE, matters_for=f"The date in {secret}"), later_source, later) == []
    # an action's reply naming it is refused to a reader outside, as a question is
    reply = {
        "op": "action.add",
        "text": "Tell them the date",
        "owners": [me(cfg)],
        "reply": f"As {secret} says, it is moving.",
        "evidence": {"quote": "Is the date still right"},
    }
    (refused,) = problems(env, reply, later_source, later)
    assert f"can't go to {OUTSIDE['full_name']}" in refused.message


def test_a_packet_for_a_draft_outside_a_limited_message_leaves_it_and_what_was_made_from_it_out(env):
    ws, cfg, store = env
    text, limited = hand(env, RESTRICTED_BODY)
    open_text, open_source = hand(env, OPEN_BODY, subject="Other")
    fact_from(env, limited, text, RESTRICTED_WORD, "moving the proof date")
    fact_from(env, open_source, open_text, OPEN_WORD, "The proof date is moving")
    action_from(env, limited, text, RESTRICTED_WORD, "moving the proof date")
    action_from(env, open_source, open_text, OPEN_WORD, "The proof date is moving")
    with store.transaction() as tx:  # a question made from the limited message, still to be asked
        tx.create(
            "question",
            {"to": INSIDE["id"], "title": f"Is the {RESTRICTED_WORD} file final?", "source": limited},
            _TEST,
        )
    from engine.packet import build

    def packet(sender: dict, address: str) -> str:
        raw = mail_from(sender, address, "Which proof date should I plan around? Thanks.", to=recipients(cfg))
        request = hand_in(ws, store, pasted=raw, now=NOW, project=PROJECT).request
        built = build(ws, store, cfg, request, TODAY).task
        return built.stable + "\n" + built.request

    outside = packet(OUTSIDE, ADDRESSES["outside"])  # the sender of this one is outside the limited message
    assert OPEN_WORD in outside and RESTRICTED_WORD not in outside
    inside = packet(INSIDE, ADDRESSES["inside"])  # someone it went to may see all of it
    assert OPEN_WORD in inside and inside.count(RESTRICTED_WORD) >= 3


# ---- on screen -------------------------------------------------------------------------------------------------------


@pytest.fixture
def client(env, tmp_path):
    ws, cfg, store = env
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        yield c


def test_the_source_says_who_it_is_limited_to_and_widen_calls_a_route_with_undo(env, client):
    _, cfg, store = env
    _, source = hand(env, RESTRICTED_BODY, cc=[("Someone Else", STRANGER)])
    shown = client.get(f"/api/sources/{source}").json()["limit"]
    assert shown["marking"].lower() == MARKING.lower() and shown["why"].startswith(MARKING)
    assert {p["name"] for p in shown["people"]} >= {SENDER["full_name"], INSIDE["full_name"], STRANGER.lower()}
    assert shown["widened_by"] is None
    done = client.post(f"/api/sources/{source}/widen", json={"people": [OUTSIDE["id"]]})
    assert done.status_code == 200
    assert OUTSIDE["id"] in audience_of(store, source)["people"]
    undone = client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={})
    assert undone.status_code == 200
    assert OUTSIDE["id"] not in audience_of(store, source)["people"]
    opened = client.post(f"/api/sources/{source}/widen", json={"open": True})
    assert opened.status_code == 200 and client.get(f"/api/sources/{source}").json()["limit"] is None


def test_the_widen_route_refuses_an_empty_widening(env, client):
    _, source = hand(env, RESTRICTED_BODY)
    assert client.post(f"/api/sources/{source}/widen", json={}).status_code in (400, 422)
