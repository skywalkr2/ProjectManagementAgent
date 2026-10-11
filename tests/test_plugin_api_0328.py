"""Plugin API 0.3.28: drafts over part of a text (a span an anchored draft revises, or a place a draft adds to),
per-run output sizes from the packet, and `where` tests for whether a field has a value."""

import pytest

from engine.ai.adapters.stub import set_responder
from engine.storage import WriteContext
from engine.texts import read_text
from tests.test_drafts import FIXTURE, NOW, answers, chapter, pending, prose, run, workspace

FIVE = "One.\n\nTwo.\n\nThree.\n\nFour.\n\nFive.\n"
ANCHORED = FIXTURE.replace('output="draft", field="body"', 'output="draft", field="body", anchored=True')


def five_paragraphs(env):
    record = chapter(env)
    from engine.applier import apply_as_person

    _, cfg, store = env
    version = pending(store, record)
    apply_as_person(
        store,
        cfg,
        [{"op": "text.edit", "record": {"kind": record.kind, "id": record.id}, "field": "body", "text": FIVE}],
        "Five paragraphs",
    )
    return store.read().get(record.kind, record.id), version


def start(env, record, part, task="p09/revise"):
    _, _, store = env
    with store.transaction() as tx:
        return tx.create(
            "request",
            {
                "task": task,
                "about": {"kind": record.kind, "id": record.id},
                "origin": "pm",
                "state": "queued",
                "created_at": NOW.isoformat(),
                "part": part,
            },
            WriteContext("pm", "trusted", "ui"),
        ).id


@pytest.fixture
def anchored(tmp_path):
    ws, cfg, store = workspace(tmp_path, ANCHORED)
    yield ws, cfg, store
    store.close()
    set_responder(None)


@pytest.fixture
def plain(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def text_of(store, version):
    return read_text(store, version.data["sha256"])


def test_an_anchored_draft_revises_only_its_span(anchored, monkeypatch):
    _, _, store = anchored
    record, _ = five_paragraphs(anchored)
    asked = answers(monkeypatch, prose("[p2] Two, revised.\n\n[p3,p4] Three and four.\nRemoved: none"))
    run(anchored, start(anchored, record, {"first": 2, "last": 4}))
    request = asked[0].request
    assert "[p2] Two." in request and "[p4] Four." in request
    assert "[p1]" not in request and "[p5]" not in request and "paragraphs p2 to p4" in request
    assert '<untrusted source="Text to revise">' in request  # the text is material, never instructions
    version = pending(store, record)
    assert text_of(store, version) == "One.\n\nTwo, revised.\n\nThree and four.\n\nFive.\n"
    assert [m["from"] for m in version.data["paragraph_map"]] == [["p1"], ["p2"], ["p3", "p4"], ["p5"]]
    kinds = [s["kind"] for s in version.data["authorship"]]
    assert kinds[0] == "person" and kinds[-1] == "person"


def test_a_span_answer_must_account_for_its_own_paragraphs_only(anchored, monkeypatch):
    record, _ = five_paragraphs(anchored)
    asked = answers(
        monkeypatch,
        prose("[p1] One.\n\n[p2] Two, revised.\nRemoved: none"),
        prose("[p2] Two, revised.\n\n[p3] Three.\nRemoved: none"),
    )
    run(anchored, start(anchored, record, {"first": 2, "last": 3}))
    assert "p1 isn't a paragraph of the text" in asked[1].request


def test_a_span_on_a_text_that_moved_on_is_refused(anchored, monkeypatch):
    _, _, store = anchored
    record, _ = five_paragraphs(anchored)
    answers(monkeypatch, prose("[p2] Two.\nRemoved: none"))
    current = [v for v in store.read().list("text_version") if v.data["owner_id"] == record.id][-1]
    stale = start(anchored, record, {"first": 2, "last": 2, "base": current.data["number"] - 1})
    run(anchored, stale)
    assert "text changed since this part" in store.read().get("request", stale).data["waiting"]
    beyond = start(anchored, record, {"first": 4, "last": 9})
    run(anchored, beyond)
    assert "aren't there" in store.read().get("request", beyond).data["waiting"]


def test_a_draft_adds_new_text_after_a_paragraph(plain, monkeypatch):
    _, _, store = plain
    record, _ = five_paragraphs(plain)
    asked = answers(monkeypatch, prose("Two and a half.\n\nTwo and three quarters.\n"))
    run(plain, start(plain, record, {"after": 2}))
    assert "goes after paragraph 2" in asked[0].request
    version = pending(store, record)
    assert text_of(store, version) == (
        "One.\n\nTwo.\n\nTwo and a half.\n\nTwo and three quarters.\n\nThree.\n\nFour.\n\nFive.\n"
    )
    assert [m["from"] for m in version.data["paragraph_map"]] == [["p1"], ["p2"], [], [], ["p3"], ["p4"], ["p5"]]
    assert [s["kind"] for s in version.data["authorship"]] == ["person", "assistant", "person"]


def test_a_draft_adds_at_the_end(plain, monkeypatch):
    _, _, store = plain
    record, _ = five_paragraphs(plain)
    answers(monkeypatch, prose("Six."))
    run(plain, start(plain, record, {"after": "end"}))
    assert text_of(store, pending(store, record)).endswith("Five.\n\nSix.\n")


def test_a_part_must_fit_its_task_kind():
    from engine.tasks import TaskKind
    from engine.texts import check_part

    drafting = TaskKind("x", (), "p", "p", output="draft", field="body")
    revising = TaskKind("x", (), "p", "p", output="draft", field="body", anchored=True)
    assert check_part(revising, {"first": 2, "last": 3}) == {"first": 2, "last": 3, "base": None}
    assert check_part(drafting, {"after": "end", "base": 4}) == {"after": "end", "base": 4}
    for kind, part in (
        (revising, {"after": 1}),
        (drafting, {"first": 1, "last": 2}),
        (revising, {"first": 3, "last": 2}),
    ):
        with pytest.raises(ValueError):
            check_part(kind, part)
    with pytest.raises(ValueError):
        check_part(TaskKind("x", (), "p", "p"), {"after": 1})


def test_a_packet_sizes_its_run(tmp_path, monkeypatch):
    sized = FIXTURE.replace(
        'return PacketParts(request=[Part("Current text", view.text(target, "body"))])',
        'return PacketParts(request=[Part("Current text", view.text(target, "body"))], max_output=9000, '
        "expected_output=2500)",
    )
    ws, cfg, store = workspace(tmp_path, sized)
    env = (ws, cfg, store)
    try:
        record = chapter(env)
        asked = answers(monkeypatch, prose("New text."))
        from tests.test_drafts import start as start_plain

        run(env, start_plain(env, record))
        assert asked[0].max_output == 9000 and asked[0].expected_output == 2500
    finally:
        store.close()
        set_responder(None)


def test_where_can_ask_whether_a_field_or_its_text_has_a_value(tmp_path):
    from engine.texts import text_presence

    offered = FIXTURE.replace(
        'output="draft", field="body", on="p09/chapter", packet=packet',
        'output="draft", field="body", on="p09/chapter", packet=packet, where={"body": ANY}',
    ).replace("from engine.plugin_api import LintFinding", "from engine.plugin_api import ANY, LintFinding")
    ws, cfg, store = workspace(tmp_path, offered)
    env = (ws, cfg, store)
    try:
        assert store.plugins.active("p09"), store.plugins.status["p09"].reason
        record = chapter(env)
        kind = store.plugins.task_kind("p09/revise")
        assert kind.offered_on(record, text_presence(store, store.read(), record))
        from engine.applier import apply_as_person

        apply_as_person(store, cfg, [{"op": "p09/add-chapter", "title": "Empty", "text": " "}], "An empty one")
        empty = store.read().list("p09/chapter")[-1]
        assert not kind.offered_on(empty, text_presence(store, store.read(), empty))
    finally:
        store.close()
