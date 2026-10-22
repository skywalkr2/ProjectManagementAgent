"""Voice notes (design 6.32, "What arrives"): a sound file handed in is turned into text by an account whose model is
listed as taking speech, and the words are then read as the person's own note.

Handing in stores the file (a trusted upload of the person's own) and queues a `transcribe` request about it. The
request is AI work like any other: it is estimated first, waits for the person's go above the configured amount (or
when its price isn't known and unpriced runs need a go), is recorded as a run with its cost, and stops with a plain
line when no account can take it. A model is never assumed to transcribe: only one an account lists, or one a service
says so about, is ever given a voice note. The words that come back become a trusted source of the person's own and
queue the usual notes work, so everything a note can do, a voice note can do, under the same rules.

Speech-to-text takes only the sound and returns only the words, so it carries no knowledge section; what the words
teach the assistant is read, and logged, by the notes work that follows."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.ai.router import (
    CANNOT_TRANSCRIBE,
    AccountPaused,
    BudgetReached,
    CannotTranscribe,
    NetworkOffline,
    NoProvider,
    Router,
)
from engine.ai.task import AiError, AiTask, Audio
from engine.config import Config
from engine.extract import AUDIO_EXTENSIONS
from engine.files import add_file, read_bytes
from engine.intake import IntakeError, own_words_in
from engine.storage import Store, WriteContext
from engine.workspace import Workspace

TASK = "transcribe"

#: The sound types a file may have to be handed in (the same as those the files setting accepts by default).
SAME_TYPE = {"audio/x-wav": "audio/wav", "audio/x-m4a": "audio/mp4", "audio/mp3": "audio/mpeg"}
AUDIO_TYPES = frozenset(AUDIO_EXTENSIONS.values()) | set(SAME_TYPE)

_PERSON = WriteContext(actor="pm", trust="trusted", op="capture.voice")
STARTING = "With the assistant, starting now"
#: What a voice note's request says once its words have gone on to be read.
TURNED = "Turned into text; the words went to the assistant."


def audio_type(name: str, media_type: str | None) -> str | None:
    """The sound type of a file, from the type its sender gave or else its ending; None when it isn't a sound file."""
    sent = (media_type or "").split(";")[0].strip().lower()
    if sent in AUDIO_TYPES:
        return SAME_TYPE.get(sent, sent)
    return AUDIO_EXTENSIONS.get(Path(name).suffix.lower()) if sent in ("", "application/octet-stream") else None


def hand_in(
    store: Store,
    cfg: Config,
    data: bytes,
    *,
    name: str,
    media_type: str | None = None,
    project: str | None = None,
    data_level: str | None = None,
    origin: str = "input",
    now: datetime | None = None,
) -> str:
    """Keep a voice note and queue turning it into text. Returns the request's id. A file that isn't sound, or is
    larger than `steward.capture.max_audio_mb`, is refused in plain words. Nothing is sent anywhere until the request
    runs."""
    found = audio_type(name, media_type)
    if found is None:
        raise IntakeError(f"{name} isn't a kind of sound this app can read.")
    cap = cfg.steward.capture.max_audio_mb
    if len(data) > cap * 1024 * 1024:
        raise IntakeError(f"{name} is larger than {cap:g} MB, so it was not handed in.")
    stored = add_file(
        store,
        cfg,
        data,
        name=name,
        media_type=found,
        project=project,
        data_level=data_level,
        origin="upload",
        now=now,
    )
    with store.transaction() as tx:
        request = tx.create(
            "request",
            {
                "task": TASK,
                "about": {"kind": "file", "id": stored.id},
                "origin": origin,
                "state": "queued",
                "waiting": STARTING,
                "created_at": (now or datetime.now(UTC)).isoformat(),
                **({"sensitivity": data_level} if data_level else {}),
                **({"project": project} if project else {}),
            },
            _PERSON,
        )
    return request.id


def _title(words: str) -> str:
    return " ".join(words.split())[:120]


def process(
    ws: Workspace, store: Store, cfg: Config, router: Router, request_id: str, *, now: datetime | None = None
) -> str | None:
    """Run one queued voice note: find an account that can transcribe, estimate, wait for the person's go when the
    rules ask, turn the sound into text and hand the words in as the person's own note. Returns the id of the notes
    request it queued, or None when it stopped (the request says why)."""
    from engine.dispatcher import (
        FIRST_GO,
        UNPRICED_GO,
        _data_level,
        _data_level_cause,
        _set,
        about,
        needs_you,
        person_is_set,
        wait_for_network,
    )
    from engine.projects import budget_problem

    now = now or datetime.now(UTC)
    req = store.read().get("request", request_id)
    if req is None:
        raise KeyError(request_id)
    target = (req.data.get("about") or {}).get("id")
    stored = store.read().get("file", target) if target else None
    if stored is None:
        return needs_you(store, request_id, "The voice note this was for is gone.")
    if not person_is_set(store, cfg):
        return needs_you(store, request_id, "Say who you are first", cause={"kind": "no_person"})
    level = _data_level(store, req.data)
    try:
        router.transcribers(TASK, level)
    except CannotTranscribe:
        return needs_you(store, request_id, CANNOT_TRANSCRIBE)
    except NoProvider as err:
        return needs_you(store, request_id, str(err), cause=_data_level_cause(err))
    _, data = read_bytes(store, stored.id)
    task = AiTask(
        kind=TASK,
        instructions="",
        stable="",
        request="",
        output_schema={},
        output="text",
        audio=Audio(data, stored.data["media_type"], stored.data["name"]),
    )
    estimate = router.estimate(task, data_level=level)
    _set(store, request_id, range_usd=[round(estimate, 4), round(estimate, 4)] if estimate is not None else None)
    budgets = cfg.ai.budgets
    granted = req.data.get("approval") == "granted"
    if estimate is not None and estimate > budgets.per_run_usd:
        return needs_you(
            store,
            request_id,
            f"This would cost about ${estimate:.2f}, above the per-run limit of ${budgets.per_run_usd:.2f}. "
            "Raise “Most one run may cost” in Settings, AI spending.",
        )
    if over := budget_problem(store, req.data, estimate):
        return needs_you(store, request_id, over)
    if estimate is None and budgets.confirm_unpriced and not granted:
        _set(store, request_id, state="needs_you", approval="required", waiting=UNPRICED_GO)
        return None
    if budgets.first_go and not granted and (estimate is None or estimate > 0) and not store.read().has("run"):
        _set(store, request_id, state="needs_you", approval="required", waiting=FIRST_GO)
        return None
    if estimate is not None and estimate > budgets.confirm_above_usd and not granted:
        _set(
            store,
            request_id,
            state="needs_you",
            approval="required",
            estimate_usd=round(estimate, 4),
            waiting=f"{about(estimate, None)} Waiting for you to start it.",
        )
        return None
    _set(store, request_id, state="running", waiting="With the assistant now", cause=None)
    try:
        result, _, _ = router.call(
            task,
            request_id=request_id,
            data_level=level,
            spend_limit=budgets.per_run_usd if granted else min(budgets.per_run_usd, budgets.confirm_above_usd),
            unpriced_ok=not budgets.confirm_unpriced or granted,
        )
    except AccountPaused as err:
        cause = {"kind": "paused", "account": err.account, "until": err.until.isoformat(), "tier": err.tier or None}
        _set(store, request_id, state="queued", waiting=str(err), cause=cause)
        return None
    except NetworkOffline:
        return wait_for_network(store, cfg, request_id, now)
    except CannotTranscribe:
        return needs_you(store, request_id, CANNOT_TRANSCRIBE)
    except (BudgetReached, NoProvider) as err:
        return needs_you(store, request_id, str(err), cause=_data_level_cause(err))
    except AiError as err:
        return needs_you(store, request_id, f"Turning the voice note into text didn't work: {err.detail or err.kind}.")
    words = result.text.strip()
    if not words:
        return needs_you(store, request_id, "No words could be made out in this voice note.")
    handed = own_words_in(
        ws,
        store,
        cfg,
        text=words,
        title=_title(words),
        kind="voice",
        project=req.data.get("project"),
        data_level=req.data.get("sensitivity") or stored.data.get("sensitivity"),
        now=now,
    )
    _set(store, request_id, state="done", waiting=TURNED)
    return handed.request


def is_transcription(request: dict[str, Any]) -> bool:
    return request.get("task") == TASK
