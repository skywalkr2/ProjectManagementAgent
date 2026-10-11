"""Every event the host publishes carries exactly the payload fields the plugin guide documents."""

from engine.applier import undo
from engine.files import add_file
from engine.plugin_host import EVENT_SPECS
from tests.test_plugin_api_02 import apply, env  # noqa: F401 - the fixture is reused

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_published_payloads_match_their_specs(env):  # noqa: F811
    _, cfg, store = env
    seen = []
    original = store.plugins.publish
    store.plugins.publish = lambda event, data: (seen.append((event, data)), original(event, data))
    add_file(store, cfg, PNG, name="cover.png", media_type="image/png")
    cs_id, _ = apply(env, [{"op": "note", "text": "A note for the event check."}], pm=True)
    undo(store, cs_id)
    assert {event for event, _ in seen} >= {"record.changed", "file.added", "changeset.applied", "changeset.undone"}
    for event, payload in seen:
        assert event in EVENT_SPECS, event
        assert set(payload) == set(EVENT_SPECS[event][1]), (event, payload)


def test_stage_moved_and_request_payloads_match_their_specs():
    from engine.storage.store import Tx

    class Fake(Tx):
        def __init__(self, pending):
            self.pending = pending

    pending = [
        ("note", "NOTE-1", 2, "stage", None, "draft", "stage.move#0"),
        ("request", "REQ-1", 2, "state", "running", "queued", "x"),
        ("question", "Q-1", 2, "status", "open", "answered", "x"),
    ]
    for event, payload in Fake(pending).events():
        assert set(payload) == set(EVENT_SPECS[event][1]), (event, payload)
