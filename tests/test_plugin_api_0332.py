"""Plugin API 0.3.32: a packet knows its request and the part it names; an accepted version says which request drafted
it; `start_where` narrows only the runs the person starts, so a kind can continue part by part on a record it can't
be started on."""

import sys

import pytest

from engine.ai.adapters.stub import set_responder
from engine.applier import apply_as_person
from tests.test_drafts import FIXTURE, answers, chapter, pending, prose, run, workspace
from tests.test_plugin_api_0328 import five_paragraphs, start

SEEING = FIXTURE.replace(
    "def packet(target, view, settings, note):\n",
    "SEEN = []\n\ndef packet(target, view, settings, note):\n    SEEN.append((view.request, view.part))\n",
)
EMPTY_ONLY = SEEING.replace(
    'output="draft", field="body", on="p09/chapter", packet=packet',
    'output="draft", field="body", on="p09/chapter", packet=packet, start_where={"body": None}',
).replace("from engine.plugin_api import LintFinding", "from engine.plugin_api import ANY, LintFinding")


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path, SEEING)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def seen():
    return next(m for n, m in sys.modules.items() if n.endswith(".fixture") and hasattr(m, "SEEN")).SEEN


def test_the_packet_and_the_accepted_event_name_the_request_and_its_part(env, monkeypatch):
    _, cfg, store = env
    record, _ = five_paragraphs(env)
    answers(monkeypatch, prose("Six."))
    asked = start(env, record, {"after": "end"})
    run(env, asked)
    assert seen()[-1] == (asked, {"after": "end"})
    events = []
    original = store.plugins.publish
    store.plugins.publish = lambda event, data, **kw: (events.append((event, data)), original(event, data, **kw))
    version = pending(store, record)
    apply_as_person(
        store, cfg, [{"op": "text.accept", "version": version.id, "read_version": version.version}], "Keep it"
    )
    payload = next(data for event, data in events if event == "text.accepted")
    assert payload["request"] == asked and payload["part"] == {"after": "end"}


def test_start_where_holds_back_only_what_the_person_starts(tmp_path, monkeypatch):
    from engine.plugin_host import check_about
    from engine.storage import StoreError
    from engine.texts import text_presence

    ws, cfg, store = workspace(tmp_path, EMPTY_ONLY)
    env = (ws, cfg, store)
    try:
        assert store.plugins.active("p09"), store.plugins.status["p09"].reason
        record, _ = five_paragraphs(env)  # it has text now
        kind = store.plugins.task_kind("p09/revise")
        texts = text_presence(store, store.read(), record)
        assert kind.offered_on(record, texts) and not kind.startable_on(record, texts)
        about = {"kind": record.kind, "id": record.id}
        check_about(store.read(), kind, about, store)  # queued work may still run on it
        with pytest.raises(StoreError, match="isn't for this"):
            check_about(store.read(), kind, about, store, starting=True)
        answers(monkeypatch, prose("Six."))
        continued = start(env, record, {"after": "end"})  # the person's origin, but a later part
        run(env, continued)
        assert seen()[-1][0] == continued
        whole = start(env, record, None)  # the person starting it again on a record with text
        run(env, whole)
        assert "isn't for this" in store.read().get("request", whole).data["waiting"]
        empty = chapter(env)
        assert kind.startable_on(empty, text_presence(store, store.read(), empty)) is (
            not text_presence(store, store.read(), empty)("body")
        )
    finally:
        store.close()
        set_responder(None)
