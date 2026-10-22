"""Capture from anywhere (design 6.32, "What arrives", S4): a capture folder takes in what the person drops there as
their own words, and a voice note is turned into text by an account that is listed as taking speech, with the estimate
and the hold of any other AI work, and a plain line when no account can. Names and ids come from the fixtures; the AI is
the stub and nothing reaches a network."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine import transcribe
from engine.ai.adapters.stub import set_responder
from engine.ai.router import CANNOT_TRANSCRIBE, Router
from engine.config import load_config
from engine.dispatcher import process
from engine.intake import IntakeError
from engine.storage import Store
from engine.watch import refresh
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
SOUND = b"\x00\x01fake sound bytes" * 200
HOST = "api.example.com"


def workspace(tmp_path, *, speech=True, price=None, ai=None, watch=None, budgets=None):
    """A workspace whose one account (the stand-in) is listed as taking speech, unless `speech` is off."""
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["budgets"] = {"first_go": False, "confirm_unpriced": False, **(budgets or {})}
    if speech:
        data["providers"]["stub"]["transcribe_models"] = ["default"]
    if price is not None:
        data["prices"] = {"stub/default": {"audio_per_minute": price}}
    for key, value in (ai or {}).items():
        data["providers"]["stub"][key] = value
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    if watch is not None:
        (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": watch}))
    cfg = load_config(ws.config_dir, env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture(autouse=True)
def _no_responder():
    yield
    set_responder(None)


def run(ws, cfg, store, request_id):
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def requests_of(store, task):
    return [r for r in store.read().list("request") if r.data["task"] == task]


# ---- a voice note ---------------------------------------------------------------------------------------------------


def test_a_voice_note_is_kept_and_turned_into_the_persons_own_note(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    try:
        set_responder(lambda task: "Ring the dentist on Friday." if task.audio else "{}")
        request = transcribe.hand_in(store, cfg, SOUND, name="memo.m4a", media_type="")
        (file,) = store.read().list("file")
        assert file.data["media_type"] == "audio/mp4" and file.data["trust"] == "trusted"
        queued = store.read().get("request", request)
        assert queued.data["about"] == {"kind": "file", "id": file.id} and queued.data["task"] == "transcribe"

        made = run(ws, cfg, store, request)
        assert store.read().get("request", request).data["state"] == "done"
        notes = store.read().get("request", made)
        assert (notes.data["task"], notes.data["origin"], notes.data["state"]) == ("notes", "pm", "queued")
        source = store.read().get("source", notes.data["source"])
        assert source.data["trust"] == "trusted" and source.data["kind"] == "capture:voice"
        assert source.data["author"] == cfg.workspace.user.person
        assert (ws.sources_dir / f"{source.data['content_hash']}.txt").read_text() == "Ring the dentist on Friday."
        (counted,) = store.read().list("run")  # it is AI work like any other: a run is recorded for it
        assert counted.data["task"] == "transcribe" and counted.data["outcome"] == "ok"
    finally:
        store.close()


def test_with_no_account_listed_as_taking_speech_it_says_so_plainly_and_calls_nothing(tmp_path):
    ws, cfg, store = workspace(tmp_path, speech=False)
    try:
        set_responder(lambda task: pytest.fail("no account was to be called"))
        request = transcribe.hand_in(store, cfg, SOUND, name="memo.m4a", media_type="audio/mp4")
        assert run(ws, cfg, store, request) is None
        stopped = store.read().get("request", request)
        assert stopped.data["state"] == "needs_you" and stopped.data["waiting"] == CANNOT_TRANSCRIBE
        assert "can't transcribe" in CANNOT_TRANSCRIBE
        assert not store.read().list("run") and not requests_of(store, "notes")
    finally:
        store.close()


def test_a_model_is_never_assumed_to_take_speech_from_its_name_or_its_account(tmp_path):
    ws, cfg, store = workspace(tmp_path, ai={"transcribe_models": ["a-different-model"]})
    try:
        router = Router(cfg, store, env={})
        with pytest.raises(Exception, match="can't transcribe"):
            router.transcribers(transcribe.TASK, "internal")
    finally:
        store.close()


def test_the_estimate_comes_first_and_the_run_waits_for_the_persons_go_above_the_amount(tmp_path):
    ws, cfg, store = workspace(tmp_path, price=0.5, budgets={"confirm_above_usd": 0.0, "per_run_usd": 5.0})
    try:
        set_responder(lambda task: "Pay the invoice on Monday.")
        request = transcribe.hand_in(store, cfg, SOUND * 50, name="long.m4a", media_type="audio/mp4")
        assert run(ws, cfg, store, request) is None
        held = store.read().get("request", request)
        assert held.data["state"] == "needs_you" and held.data["approval"] == "required"
        assert held.data["estimate_usd"] > 0 and "Waiting for you to start it" in held.data["waiting"]
        assert not store.read().list("run") and not requests_of(store, "notes")
        # It is a line on Today asking for the go, with the estimate, and the line names the voice note.
        from engine.today_queue import queue

        (ask,) = [x for x in queue(ws, store, cfg, NOW) if x.request == request]
        assert ask.kind == "go" and ask.waiting == held.data["waiting"] and "About $" in ask.waiting
        assert ask.title.task == "transcribe" and ask.title.subject == "long.m4a"
        # The size of the file, not a guess, sets the estimate: twice the sound costs twice as much.
        bigger = transcribe.hand_in(store, cfg, SOUND * 100, name="longer.m4a", media_type="audio/mp4")
        run(ws, cfg, store, bigger)
        assert store.read().get("request", bigger).data["estimate_usd"] == pytest.approx(
            2 * held.data["estimate_usd"], rel=0.01
        )
        # Their go starts it.
        with store.transaction() as tx:
            cur = tx.get("request", request)
            from engine.storage import WriteContext

            tx.update(
                "request",
                request,
                {"approval": "granted", "state": "queued"},
                WriteContext("pm", "trusted", "test.go"),
                read_version=cur.version,
            )
        made = run(ws, cfg, store, request)
        assert made is not None and store.read().get("request", request).data["state"] == "done"
    finally:
        store.close()


def test_a_price_nobody_knows_waits_for_a_go_when_unpriced_runs_need_one(tmp_path):
    ws, cfg, store = workspace(tmp_path, budgets={"confirm_unpriced": True})
    try:
        request = transcribe.hand_in(store, cfg, SOUND, name="memo.m4a", media_type="audio/mp4")
        assert run(ws, cfg, store, request) is None
        held = store.read().get("request", request)
        assert held.data["approval"] == "required" and "can't be estimated" in held.data["waiting"]
    finally:
        store.close()


def test_a_note_with_no_words_in_it_stops_with_a_plain_line(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    try:
        set_responder(lambda task: "   ")
        request = transcribe.hand_in(store, cfg, SOUND, name="quiet.m4a", media_type="audio/mp4")
        assert run(ws, cfg, store, request) is None
        assert "No words could be made out" in store.read().get("request", request).data["waiting"]
        assert not requests_of(store, "notes")
    finally:
        store.close()


def test_a_file_that_is_not_sound_or_is_too_large_is_refused_in_plain_words(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    try:
        with pytest.raises(IntakeError, match="isn't a kind of sound"):
            transcribe.hand_in(store, cfg, b"text", name="notes.txt", media_type="text/plain")
        small = ws.config(env={"COCKPIT__STEWARD__CAPTURE__MAX_AUDIO_MB": "0.0001"})
        with pytest.raises(IntakeError, match="larger than"):
            transcribe.hand_in(store, small, SOUND, name="memo.m4a", media_type="audio/mp4")
        assert not store.read().list("file")
    finally:
        store.close()


def test_an_adapter_that_cannot_transcribe_refuses_a_voice_note_and_never_guesses(tmp_path):
    from engine.ai.adapters import ADAPTERS, GENERIC_ADAPTER
    from engine.ai.task import AiError, AiTask, Audio

    task = AiTask("transcribe", "", "", "", {}, audio=Audio(b"x", "audio/mp4", "a.m4a"))
    settings = type("S", (), {"base_url": "https://" + HOST, "timeout_seconds": 5})()
    native = [cls for name, cls in ADAPTERS.items() if name not in ("stub", GENERIC_ADAPTER, "cli-agent")]
    assert native
    for cls in native:
        with pytest.raises(AiError, match="doesn't turn speech into text"):
            cls(settings, "key").run(task, "m")


def test_the_generic_adapter_sends_the_sound_to_the_speech_path_and_reads_the_words():
    import httpx

    from engine.ai.adapters import ADAPTERS, GENERIC_ADAPTER
    from engine.ai.task import AiTask, Audio

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"], seen["body"] = request.url.path, request.read()
        return httpx.Response(200, json={"text": " Call back on Tuesday. "})

    settings = type(
        "S",
        (),
        {
            "base_url": "https://" + HOST + "/v1",
            "timeout_seconds": 5,
            "json_mode": True,
            "max_tokens_param": "max_tokens",
        },
    )()
    adapter = ADAPTERS[GENERIC_ADAPTER](settings, "key", transport=httpx.MockTransport(handler))
    result = adapter.run(AiTask("transcribe", "", "", "", {}, audio=Audio(b"RIFFdata", "audio/wav", "m.wav")), "m")
    assert result.text == "Call back on Tuesday." and seen["path"].endswith("/audio/transcriptions")
    assert b"RIFFdata" in seen["body"] and b'name="model"' in seen["body"]


# ---- the API ---------------------------------------------------------------------------------------------------------


def test_the_hand_in_route_takes_a_voice_note_and_refuses_what_is_not_sound(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    store.close()
    app = create_app(ws, cfg, "token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": "Bearer token"}) as client:
        done = client.post("/api/handin/audio?name=memo.m4a", content=SOUND, headers={"Content-Type": "audio/mp4"})
        assert done.status_code == 200 and done.json()["source"] is None
        request = app.state.store.read().get("request", done.json()["request"])
        assert request.data["task"] == "transcribe"
        bad = client.post("/api/handin/audio?name=notes.txt", content=b"words", headers={"Content-Type": "text/plain"})
        assert bad.status_code == 409 and "isn't a kind of sound" in bad.json()["detail"]


# ---- a capture folder ----------------------------------------------------------------------------------------------


def capture(tmp_path, folder, **more):
    source = {"id": "inbox", "connector": "capture", "label": "Drop box", "settings": {"path": str(folder)}, **more}
    return workspace(tmp_path, watch=[source])


def test_what_lands_in_a_capture_folder_is_handed_in_as_the_persons_own_words_on_the_first_read(tmp_path):
    folder = tmp_path / "drop"
    folder.mkdir()
    (folder / "ideas.txt").write_text("Remember to renew the parking permit.")
    ws, cfg, store = capture(tmp_path, folder)
    try:
        result = refresh(ws, store, cfg, "inbox", NOW)
        assert result.outcome == "ok" and len(result.new) == 1 and not result.taken_in
        request = store.read().get("request", result.new[0])
        assert (request.data["task"], request.data["origin"]) == ("notes", "pm")
        source = store.read().get("source", request.data["source"])
        assert source.data["trust"] == "trusted" and source.data["author"] == cfg.workspace.user.person
        assert source.data["kind"] == "capture:folder" and source.data["title"] == "ideas.txt"
        assert (ws.sources_dir / f"{source.data['content_hash']}.txt").read_text() == (
            "Remember to renew the parking permit."
        )
        # Nothing new, nothing handed in; a change to the file is handed in again.
        assert refresh(ws, store, cfg, "inbox", NOW).new == []
        (folder / "ideas.txt").write_text("Remember to renew the parking permit and the library card.")
        again = refresh(ws, store, cfg, "inbox", NOW)
        assert again.new == [] and len(again.changed) == 1
    finally:
        store.close()


def test_a_sound_file_dropped_in_a_capture_folder_becomes_a_voice_note_to_transcribe(tmp_path):
    folder = tmp_path / "drop"
    folder.mkdir()
    (folder / "walk.m4a").write_bytes(SOUND)
    ws, cfg, store = capture(tmp_path, folder)
    try:
        result = refresh(ws, store, cfg, "inbox", NOW)
        (request,) = [store.read().get("request", r) for r in result.new]
        assert request.data["task"] == "transcribe" and request.data["origin"] == "input"
        file = store.read().get("file", request.data["about"]["id"])
        assert file.data["name"] == "walk.m4a" and file.data["media_type"] == "audio/mp4"
        assert refresh(ws, store, cfg, "inbox", NOW).new == []  # the same sound is not handed in twice
    finally:
        store.close()


def test_a_capture_folder_is_not_the_outside_world_and_an_ordinary_folder_still_is(tmp_path):
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "plan.md").write_text("Line one\n")
    ws, cfg, store = workspace(
        tmp_path,
        watch=[
            {
                "id": "shared",
                "connector": "folder",
                "first_run": "all",
                "settings": {"path": str(folder)},
            }
        ],
    )
    try:
        result = refresh(ws, store, cfg, "shared", NOW)
        source = store.read().get("source", store.read().get("request", result.new[0]).data["source"])
        assert source.data["trust"] == "untrusted" and source.data["kind"] == "watched:folder"
    finally:
        store.close()
