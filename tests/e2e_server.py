"""A server for the browser tests: a fresh copy of the imprint fixture whose stand-in AI answers each pasted case with
that case's ideal answer, so the run checks the UI and the pipeline rather than a model.

    uv run python -m tests.e2e_server --port 8781 --base-path /

It also serves the cases at /__e2e/cases so the browser test reads names from the fixture instead of writing them out,
and a few read-only checks of what no screen shows: the ledger of a record, whether the rules and settings are as they
were, and the export round trip of the workspace as it stands. /__e2e/backup-targets switches the configured backup
folder off and on, for the step about having none.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
import yaml
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.cleaning import normalize
from engine.cli import KEEP_ALIVE
from engine.evaluate import load_cases
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.roundtrip import round_trip

TOKEN = "e2e-token"
#: The id of the extra stand-in account `--standin-account` adds; the browser test reads its label from the screen.
STANDIN_ACCOUNT = "standin"
LAYOUT_FIXTURE = Path(__file__).parents[1] / "web" / "e2e" / "fixtures" / "layout-strings.json"

# The browser tests run with the wording check on, so a message that names a file, a key or a command fails there too.
os.environ["COCKPIT_CHECK_WORDING"] = "1"


#: The layout check's sources: a mailbox and a calendar that failed to be read, so Today's right column has problems.
LAYOUT_SOURCES = [
    {
        "id": "layout-mail",
        "connector": "mailbox",
        "label": "Work mail",
        "every_minutes": 43200,
        "settings": {"host": "mail.example.com", "user": "rowan@example.com", "password": "env:LAYOUT_PASSWORD"},
    },
    {
        "id": "layout-calendar",
        "connector": "calendar",
        "label": "Work calendar",
        "every_minutes": 43200,
        "settings": {"address": "env:LAYOUT_CALENDAR"},
    },
]


def layout_strings() -> dict[str, str]:
    """Long unbroken made-up strings from the shared layout fixture, by the place each is put."""
    found = {s["id"]: s["text"] for s in json.loads(LAYOUT_FIXTURE.read_text(encoding="utf-8"))}
    return {
        "title": found["token-02"],
        "note": found["web-02"] + " " + found["path-02"],
        "name": found["email-03"],
        "summary": found["token-06"],
        "refusal": found["mail-01"],
        "question": found["invisible-03"],
    }


def seed_layout(store, cfg, stress: dict[str, str]) -> None:
    """Records and a failed read that hold the long strings, so every screen has some to lay out."""
    from datetime import UTC, datetime

    pm = cfg.workspace.user.person
    ctx = WriteContext(actor="pm", trust="trusted", op="e2e.layout")
    with store.transaction() as tx:
        tx.create("project", {"name": stress["title"], "summary": stress["summary"]}, ctx)
        tx.create("person", {"full_name": stress["name"], "role": stress["summary"]}, ctx)
        if pm:
            tx.create(
                "question",
                {"to": pm, "title": stress["title"], "text": stress["question"], "kind": "decision"},
                ctx,
            )
        now = datetime.now(UTC).isoformat()
        for source in LAYOUT_SOURCES:
            tx.create(
                "watch_run",
                {
                    "source": source["id"],
                    "started_at": now,
                    "outcome": "failed",
                    "error_kind": "auth",
                    "error": stress["refusal"],
                },
                WriteContext(actor="watcher", trust="trusted", op="watch.run"),
            )


def seed_outgoing(store, cfg):
    """The core's stand-in channel, registered, and one message drafted to a known person who has an address, waiting
    for the person's yes. Returns the channel and what the browser test reads from the fixture."""
    from engine.applier import apply_as_person
    from engine.channels import FakeChannel
    from engine.names import People

    channel = FakeChannel()
    store.plugins.core_channels["fake"] = channel.registration()
    pm = cfg.workspace.user.person
    person = next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != pm)
    address = "outgoing.recipient@example.com"
    with store.transaction() as tx:
        found = tx.get("person", person)
        reach = {**(found.data.get("how_to_reach") or {}), "email": address}
        tx.update(
            "person",
            person,
            {"how_to_reach": reach},
            WriteContext(actor="pm", trust="trusted", op="e2e.outgoing"),
            read_version=found.version,
        )
    parts = {"subject": "The proofs", "body": "The proofs ship on Monday."}
    op = {
        "op": "act.draft",
        "channel": "fake",
        "target": {"kind": "message", "recipients": [{"person": person, "kind": "email"}]},
        "parts": parts,
    }
    apply_as_person(store, cfg, [op], "Drafted a message to send")
    return channel, {"name": People(store, cfg).name(person), "address": address, **parts}


#: The mailbox the act journey's saved messages came in on, and the account acting is switched on for.
ACTS_SOURCE = "e2e-mail"
ACTS_ACCOUNT = f"mailbox:{ACTS_SOURCE}"
ACTS_SENDER = "sender.one@example.com"
ACTS_ORGANIZER = "organizer@example.com"


def seed_acts(ws, store, cfg):
    """The stand-in channel serving a plain mailbox, with acting on for it, and what the journey acts on: two saved
    messages (one to reply to, one to file away) and an invitation on the calendar. The mailbox's folders are a fixed
    list, since nothing reads a real one. Returns the channel and what the browser test reads from the fixture."""
    from types import SimpleNamespace

    import engine.connectors.mailbox as mailbox
    from engine.channels import FakeChannel

    channel = FakeChannel(accounts=("mailbox",))
    store.plugins.core_channels.pop("mailbox", None)
    store.plugins.core_channels["fake"] = channel.registration()
    mailbox.list_folders = lambda _settings: SimpleNamespace(names=("Inbox", "Projects", "Sent"), sent="Sent")
    pm = cfg.workspace.user.person
    ctx = WriteContext(actor="engine", trust="trusted", op="e2e.acts")
    ws.sources_dir.mkdir(exist_ok=True)

    def message(title: str, text: str, key: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()
        (ws.sources_dir / f"{digest}.txt").write_text(text, encoding="utf-8")
        with store.transaction() as tx:
            return tx.create(
                "source",
                {
                    "received_at": datetime.now(UTC).isoformat(),
                    "kind": "watched:mailbox",
                    "title": title,
                    "content_hash": digest,
                    "trust": "untrusted",
                    "watched": {"source": ACTS_SOURCE, "key": key, "change": "new", "author": ACTS_SENDER},
                },
                ctx,
            ).id

    me = f"{pm or 'me'}@example.com"
    ask = message(
        "Interior proofs",
        f"From: Sender One <{ACTS_SENDER}>\nTo: {me}\nSubject: Interior proofs\n\nCan you confirm the proof date?",
        "<proofs@example.com>",
    )
    tidy = message(
        "Printer invoice",
        f"From: Sender One <{ACTS_SENDER}>\nTo: {me}\nSubject: Printer invoice\n\nThe invoice is attached.",
        "<invoice@example.com>",
    )
    invite = message(
        "Invitation: Planning session",
        f"From: The Organizer <{ACTS_ORGANIZER}>\nTo: {me}\nSubject: Invitation: Planning session\n\nPlease join.",
        "<invite@example.com>",
    )
    with store.transaction() as tx:
        entry = tx.create(
            "event",
            {
                "title": "Planning session",
                "start": "2026-11-03T14:00:00+00:00",
                "end": "2026-11-03T15:00:00+00:00",
                "key": "<planning@example.com>",
                "source": invite,
                "invitation": True,
                "organizer": {"address": ACTS_ORGANIZER, "name": "The Organizer"},
                "trust": "untrusted",
            },
            ctx,
        ).id
    return channel, {
        "account": "E2E mail",
        "reply": {"id": ask, "title": "Interior proofs", "sender": ACTS_SENDER},
        "tidy": {"id": tidy, "title": "Printer invoice"},
        "invitation": {"id": entry, "title": "Planning session", "organizer": ACTS_ORGANIZER},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--base-path", default="/")
    parser.add_argument(
        "--layout-stress",
        action="store_true",
        help="hold long unbroken made-up text in titles, a Today row, a failing source and a note",
    )
    parser.add_argument(
        "--standin-account",
        action="store_true",
        help="add a second stand-in AI account whose person said Not now about reading work mail and notes, so Today "
        "has the line that offers Allow",
    )
    parser.add_argument(
        "--fake-channel",
        action="store_true",
        help="register the core's stand-in channel and draft one message to a known person on it, so the browser test "
        "can approve and send it; /__e2e/delivered says what the channel was handed",
    )
    parser.add_argument(
        "--acts",
        action="store_true",
        help="serve the stand-in channel for a plain mailbox with acting on, and seed two saved messages and an "
        "invitation for the browser test to reply to, file away and answer; /__e2e/acts says what the channel was "
        "handed and what it took back",
    )
    parser.add_argument(
        "--clock-at",
        metavar="MOMENT",
        help="start the clock at this ISO 8601 moment in UTC (for example 2026-10-21T00:30:00Z); it keeps ticking",
    )
    args = parser.parse_args()
    if args.clock_at:
        import time_machine

        moment = datetime.fromisoformat(args.clock_at.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        time_machine.travel(moment, tick=True).start()
    stress = layout_strings() if args.layout_stress else {}

    tmp = Path(tempfile.mkdtemp(prefix="cockpit-e2e-"))
    ws = init_workspace(tmp / "ws", template=DEMO_B, git=False, history=True)
    (tmp / "offsite").mkdir(exist_ok=True)
    flags = {
        "server.base_path": args.base_path,
        "server.port": args.port,
        "ai.tiers.routine.use": "stub/default",
        "ai.tiers.routine.fallback": [],
        "storage.backups.targets": [{"path": str(tmp / "offsite"), "label": "test folder"}],
        # Backups only on request, so the browser tests see the state before the first one.
        "storage.backups.automatic": False,
        # A stage that starts work when entered, so the browser tests can exercise waiting for the go.
        "stages.types.project.stages": [
            {"id": "planned", "label": "Planned"},
            {"id": "active", "label": "In progress", "starts": ["notes"]},
            {"id": "complete", "label": "Complete"},
        ],
    }
    if stress:
        flags["storage.backups.automatic"] = False
        flags["watch.sources"] = LAYOUT_SOURCES
    if args.acts:
        # A mailbox that is never read (nothing here reaches a real one), with acting switched on for it. In the
        # settings file, so every screen reads it as it would a person's own.
        path = ws.config_dir / "watch.yaml"
        watch = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        watch["sources"] = [
            {"id": ACTS_SOURCE, "connector": "mailbox", "label": "E2E mail", "enabled": False, "every_minutes": 43200}
        ]
        watch["acting"] = [ACTS_ACCOUNT]
        path.write_text(yaml.safe_dump(watch, sort_keys=False), encoding="utf-8")
    if args.standin_account:
        # In the settings file, not a flag, so Allow's save is what the app reads afterwards.
        path = ws.config_dir / "ai.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["providers"][STANDIN_ACCOUNT] = {
            "adapter": "stub",
            "label": "Second stand-in",
            "models": {"default": "scripted"},
            "allowed_data": ["open"],
            "work_data": "not_now",
        }
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    cfg = ws.config(env={}, flags=flags)
    cases = load_cases(DEMO_B)
    project = fixture_records(DEMO_B, "project")[0]["id"]

    def responder(task):  # the case whose longest pasted line is in the request
        request = normalize(task.request)
        for case in cases:
            longest = max(case.get("pasted", "").splitlines() or [""], key=len)
            if longest.strip() and normalize(longest) in request:
                return json.dumps(case["stub_answer"])
        # A note that says it belongs to a project is filed under the fixture's first one; any other is filed loose.
        note = {
            "op": "note",
            "text": "Kept this note for later.",
            **({"project": project} if "under the project" in request else {}),
        }
        if stress:
            note["text"] = stress["note"]
            return json.dumps({"summary": "Filed as a note.", "topic": stress["title"], "ops": [note]})
        return json.dumps({"summary": "Filed as a note.", "ops": [note]})

    set_responder(responder)
    app = create_app(ws, cfg, TOKEN, start_worker=True)

    store = app.state.store
    if stress:
        seed_layout(store, cfg, stress)
    folder_targets = list(cfg.storage.backups.targets)
    fake_channel = seed_outgoing(store, cfg) if args.fake_channel else None
    acts = seed_acts(ws, store, cfg) if args.acts else None

    async def case_list(_request):
        return JSONResponse(cases)

    async def ledger(request):
        """The ledger rows of one record, oldest first."""
        kind, record_id = request.query_params["kind"], request.query_params["id"]
        return JSONResponse(store.read().ledger(kind=kind, record_id=record_id))

    async def standing(_request):
        """What the rules and settings are: how many rules, and a hash of the settings files and of the settings as the
        app reads them, plus how many changes to settings were proposed or made."""
        files = sorted(ws.config_dir.rglob("*"))
        on_disk = hashlib.sha256(b"".join(p.read_bytes() for p in files if p.is_file())).hexdigest()
        effective = hashlib.sha256(json.dumps(cfg.flat(), default=str).encode()).hexdigest()
        reader = store.read()
        return JSONResponse(
            {
                "rules": len(cfg.rules.rules),
                "settings_files": on_disk,
                "settings": effective,
                "setting_proposals": len(reader.list("setting_proposal", include_deleted=True)),
                "setting_changes": len(reader.list("setting_change", include_deleted=True)),
            }
        )

    async def export_round_trip(_request):
        """Export the workspace as it stands, load that into a fresh database and compare."""
        with tempfile.TemporaryDirectory(prefix="cockpit-e2e-round-trip-") as work:
            return JSONResponse(round_trip(store, cfg, Path(work)))

    async def backup_targets(request):
        """Turn the configured backup folder off (`configured=0`) or back on (`configured=1`)."""
        cfg.storage.backups.targets = folder_targets if request.query_params["configured"] == "1" else []
        return JSONResponse({"configured": len(cfg.storage.backups.targets)})

    async def delivered(_request):
        """What the stand-in channel was handed and the message waiting for it: who, where and the parts as drafted."""
        if fake_channel is None:
            return JSONResponse({"enabled": False})
        channel, drafted = fake_channel
        return JSONResponse(
            {
                "enabled": True,
                **drafted,
                "delivered": [
                    {"parts": a.parts, "to": [r.address for r in a.recipients]} for a, _key in channel.delivered
                ],
            }
        )

    async def acted(_request):
        """What the act journey's records are, what the stand-in channel was handed (each act with what it is about, who
        it goes to and what it carries) and what it was asked to take back."""
        if acts is None:
            return JSONResponse({"enabled": False})
        channel, seeded = acts

        def shown(act):
            return {
                "kind": act.kind,
                "action": act.action,
                "parts": act.parts,
                "to": [r.address for r in act.recipients],
                "about": [a.id for a in act.about],
                "label": act.label,
                "folder": act.folder,
                "answer": act.answer,
                "proposed_start": act.proposed_start,
                "proposed_end": act.proposed_end,
            }

        return JSONResponse(
            {
                "enabled": True,
                **seeded,
                "delivered": [shown(a) for a, _key in channel.delivered],
                "undone": [shown(a) for a, _service_id in channel.undone],
            }
        )

    outer = Starlette(
        routes=[
            Route("/__e2e/delivered", delivered),
            Route("/__e2e/acts", acted),
            Route("/__e2e/cases", case_list),
            Route("/__e2e/ledger", ledger),
            Route("/__e2e/standing", standing),
            Route("/__e2e/round-trip", export_round_trip),
            Route("/__e2e/backup-targets", backup_targets, methods=["POST"]),
            Mount("/", app=app),
        ],
        lifespan=_lifespan(app),
    )
    uvicorn.run(outer, host="127.0.0.1", port=args.port, log_level="warning", timeout_keep_alive=KEEP_ALIVE)


def _lifespan(app):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_outer):
        async with app.router.lifespan_context(app):
            yield

    return lifespan


if __name__ == "__main__":
    main()
