"""The background worker: processes queued requests one at a time, makes scheduled backups, and tells listeners when
anything changes."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.ai.router import Router
from engine.config import Config
from engine.dispatcher import needs_you, process
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import Workspace

CODE_ROOTS = (Path(__file__).resolve().parent, Path(__file__).resolve().parents[1] / "api")
log = logging.getLogger(__name__)
RESTART_NEEDED = "Settings or code changed since the cockpit started; restart it to use them."
INTERRUPTED = "The app closed while this ran; it runs again now."
INTERRUPTED_TWICE = "Stopped twice when the app closed during it"
_REQUEUE_OP = "worker.requeue"
_INTERRUPTED_OP = "worker.interrupted"
#: What `Worker.restart_for` names when an add-on that is running was updated from the screen.
ADD_ONS = "add-ons"


#: Settings the running app takes in at once, without a restart: everything that reads them reads the shared config
#: each time it is used (AI accounts and tiers for each run; who the person is, the names and the screens' wording for
#: each request; where and how often backups go, for each backup; how often the readable export is written; the watched
#: sources, for each read). Any other change waits for a restart the person chooses.
LIVE_KEYS = (
    "ai.",
    "ui.",
    "workspace.user.",
    "workspace.name",
    "workspace.assistant_name",
    "workspace.our_accounts",
    "storage.backups.",
    "storage.export.every_minutes",
    "watch.",
)


def config_fingerprint(ws: Workspace) -> str:
    """A hash of the workspace's config files, to notice edits made while the process runs."""
    digest = hashlib.sha256()
    for path in sorted(ws.config_dir.rglob("*.yaml")):
        digest.update(str(path.relative_to(ws.config_dir)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def is_live(key: str) -> bool:
    """Whether a changed settings key is taken in without a restart."""
    return any(key.startswith(p) if p.endswith(".") else key == p or key.startswith(p + ".") for p in LIVE_KEYS)


def code_fingerprint() -> str:
    """The newest modification time of the running program's own source files."""
    newest = max((p.stat().st_mtime for root in CODE_ROOTS if root.is_dir() for p in root.rglob("*.py")), default=0.0)
    return repr(newest)


def waits_for_its_time(request: dict[str, Any], now: datetime) -> bool:
    """Whether a queued request is waiting for a time to come (an account's limit to reset, or the next automatic try)
    and that time is still ahead."""
    cause = request.get("cause") or {}
    if cause.get("kind") not in ("paused", "retry") or not cause.get("until"):
        return False
    until = datetime.fromisoformat(str(cause["until"]))
    return (until if until.tzinfo else until.replace(tzinfo=UTC)) > now


def release_paused(store: Store) -> int:
    """Lift every pause on the accounts and let the requests waiting for one try again at once: used when the AI
    accounts changed, since a different account may be able to take the work. Returns how many requests were let go."""
    from engine.ai.pauses import Pauses, pauses_path

    Pauses(pauses_path(store)).clear()
    ctx = WriteContext(actor="engine", trust="trusted", op="worker.release")
    released = 0
    with store.transaction() as tx:
        for r in tx.list("request"):
            if r.data["state"] == "queued" and (r.data.get("cause") or {}).get("kind") == "paused":
                tx.update(
                    "request",
                    r.id,
                    {"cause": None, "waiting": "With the assistant, next in line"},
                    ctx,
                    read_version=r.version,
                )
                released += 1
    return released


def requeue_interrupted(store: Store) -> tuple[list[str], list[str]]:
    """Put back the requests a stop left running: with the app closed nothing is running them. Each goes back in the
    queue with a note saying why. One found running after it was already put back once waits for the person instead
    (Try again and Dismiss apply, its approval untouched), so a request that stops the app can't loop. The number of
    times a request was interrupted is counted from its own history, not from how many runs it started, since
    a person's Try again also starts a run. Returns the ids queued again and the ids held for the person."""
    queued: list[str] = []
    held: list[str] = []
    with store.transaction() as tx:
        for r in tx.list("request"):
            if r.data["state"] != "running":
                continue
            history = tx.ledger(kind="request", record_id=r.id)
            if any(e["op"] in (_REQUEUE_OP, _INTERRUPTED_OP) for e in history):
                ctx = WriteContext(actor="engine", trust="trusted", op=_INTERRUPTED_OP)
                tx.update(
                    "request", r.id, {"state": "needs_you", "waiting": INTERRUPTED_TWICE}, ctx, read_version=r.version
                )
                held.append(r.id)
            else:
                ctx = WriteContext(actor="engine", trust="trusted", op=_REQUEUE_OP)
                tx.update("request", r.id, {"state": "queued", "waiting": INTERRUPTED}, ctx, read_version=r.version)
                queued.append(r.id)
    return queued, held


class Events:
    """A change counter that waiters can block on; the live-update stream reads it."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.version = 0
        self.closed = False

    def close(self) -> None:
        """Release every waiter and make later waits return at once, so live streams can end."""
        with self._cond:
            self.closed = True
            self._cond.notify_all()

    def changed(self) -> None:
        with self._cond:
            self.version += 1
            self._cond.notify_all()

    def wait(self, after: int, timeout: float) -> int:
        with self._cond:
            self._cond.wait_for(lambda: self.version > after or self.closed, timeout=timeout)
            return self.version


class Worker:
    #: How often the synced folder is checked for changes when nothing signals one.
    SYNC_CHECK_SECONDS = 10
    #: How often this install's lease in the synced folder is renewed when nothing else is written.
    HEARTBEAT_SECONDS = 60

    def __init__(
        self,
        ws: Workspace,
        store: Store,
        cfg: Config,
        events: Events,
        router_factory: Callable[[], Router] | None = None,
        on_restart: Callable[[], None] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.ws, self.store, self.cfg, self.events = ws, store, cfg, events
        self.now = now
        self.router_factory = router_factory or (lambda: Router(cfg, store, env=os.environ))
        # Called once, between requests, when settings or code changed: the process restarts to use them (6.14).
        self.on_restart = on_restart
        self.restarting = False
        self._wake = threading.Event()
        self._read_now = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._backups: threading.Thread | None = None
        self._sync: threading.Thread | None = None
        self._jobs: threading.Thread | None = None
        self._synced_at: int | None = -1
        self._said_no_git = False
        self._beat = 0.0
        self.sync_lost = False
        self.sync_result: Any = None
        self.sync_problem: str | None = None
        self._started_with = (config_fingerprint(ws), code_fingerprint())
        self._config_seen = self._started_with[0]
        self.restart_needed: str | None = None
        self.restart_requested = False
        #: The settings keys whose change waits for the restart, and "code" when the program itself changed.
        self.restart_for: list[str] = []

    def apply_live(self) -> bool:
        """Take in changed settings now when every changed key is live (an AI account, the person's name); returns
        whether anything was taken in. A change to any other key leaves the settings in use as they were, for the
        restart the person chooses. A file that doesn't load changes nothing."""
        seen = config_fingerprint(self.ws)
        if seen == self._config_seen:
            return False
        from engine.config import ConfigError, load_config

        try:
            fresh = load_config(self.ws.config_dir, env=dict(os.environ))
        except ConfigError as err:
            log.warning("Changed settings weren't taken in: %s", err)
            return False
        before = {k: v for k, v, _ in self.cfg.flat()}
        after = {k: v for k, v, _ in fresh.flat()}
        # A setting given on the command line stays as it was started with; the files can't change it here.
        given = {k for k, _, layer in self.cfg.flat() if layer == "flag"}
        changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)} - given
        waiting = sorted(k for k in changed if not is_live(k))
        if waiting:
            self.restart_for = sorted(set(self.restart_for) | set(waiting))
            return False
        for name in {k.split(".", 1)[0] for k in changed}:
            self.cfg.files[name] = fresh.files[name]
            for key in [k for k in self.cfg.sources if k.startswith(name + ".")]:
                del self.cfg.sources[key]
            self.cfg.sources.update({k: v for k, v in fresh.sources.items() if k.startswith(name + ".")})
        self._config_seen = seen
        if any(k.startswith(("ai.providers.", "ai.tiers.")) for k in changed):
            release_paused(self.store)
        if changed:
            log.info("Took in changed settings: %s", ", ".join(sorted(changed)))
            self.events.changed()
        return bool(changed)

    def _changed_since_start(self) -> bool:
        """Old code never runs new settings: once settings that need a restart or code changed, no new job starts in
        this process. Live settings are taken in first and don't count."""
        self.apply_live()
        code = code_fingerprint()
        if self.restart_needed is None and (self._config_seen, code) != (
            config_fingerprint(self.ws),
            self._started_with[1],
        ):
            self.restart_needed = RESTART_NEEDED
            if code != self._started_with[1] and "code" not in self.restart_for:
                self.restart_for.append("code")
        return self.restart_needed is not None

    def _hold_queued(self) -> None:
        ctx = WriteContext(actor="engine", trust="trusted", op="worker.hold")
        held = False
        now = self.now()
        with self.store.transaction() as tx:
            for r in tx.list("request"):
                if waits_for_its_time(r.data, now):
                    continue
                if r.data["state"] == "queued" and r.data.get("waiting") != RESTART_NEEDED:
                    tx.update("request", r.id, {"waiting": RESTART_NEEDED}, ctx, read_version=r.version)
                    held = True
        if held:
            self.events.changed()

    def start(self) -> None:
        if any(requeue_interrupted(self.store)):
            self.events.changed()
        self._thread = threading.Thread(target=self._loop, name="cockpit-worker", daemon=True)
        self._thread.start()
        self._backups = threading.Thread(target=self._backup_loop, name="cockpit-backups", daemon=True)
        self._backups.start()
        self._sync = threading.Thread(target=self._sync_loop, name="cockpit-sync", daemon=True)
        self._sync.start()
        self._jobs = threading.Thread(target=self._jobs_loop, name="cockpit-jobs", daemon=True)
        self._jobs.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._read_now.set()
        if self._thread:
            self._thread.join(timeout=10)
        if self._backups:
            self._backups.join(timeout=60)
        if self._jobs:
            self._jobs.join(timeout=60)
        if self._sync:
            self.events.changed()
            self._sync.join(timeout=60)
            self.release_folder()

    def read_sources_now(self) -> None:
        """A source was just added or a sign-in just started some: read what is due at once, not at the next minute's
        check, so the person sees their mail arrive while they are still looking."""
        self._read_now.set()

    def poke(self) -> None:
        self._wake.set()

    def needs_restart(self) -> bool:
        """Whether changed settings or code wait for a restart. Live settings are taken in first, so they never
        count. Nothing restarts until the person asks (`request_restart`)."""
        return self._changed_since_start()

    def add_ons_changed(self) -> None:
        """An add-on that is running was replaced on disk from the screen: the running app must not mix its old and new
        files, so a restart is waiting, with the add-ons named as what it is for. Installing or removing one that isn't
        running changes nothing the app is using, so it doesn't come here."""
        if ADD_ONS not in self.restart_for:
            self.restart_for.append(ADD_ONS)
        if self.restart_needed is None:
            self.restart_needed = RESTART_NEEDED
        self.events.changed()

    @property
    def can_restart(self) -> bool:
        """Whether this process can start itself again (it was started by `cockpit serve`)."""
        return self.on_restart is not None

    def request_restart(self) -> None:
        """The person asked for the restart: it starts between requests, at once if none is running."""
        self.restart_requested = True
        self.poke()

    def run_pending(self) -> int:
        """Process every queued request now. Returns how many were processed."""
        done = 0
        while not self._stop.is_set():
            now = self.now()
            queued = [
                r
                for r in self.store.read().list("request")
                if r.data["state"] == "queued" and not waits_for_its_time(r.data, now)
            ]
            if not queued:
                break
            if self._changed_since_start():
                self._hold_queued()
                break
            try:
                process(self.ws, self.store, self.cfg, self.router_factory(), queued[0].id, now=now)
            except StoreError as err:  # a write refused with a plain reason
                log.warning("Request %s couldn't be processed: %s", queued[0].id, err)
                needs_you(self.store, queued[0].id, f"This couldn't be processed: {str(err).rstrip('.')}.")
            except Exception:  # a failure in one request must not stop the worker
                log.exception("Request %s failed", queued[0].id)
                needs_you(
                    self.store,
                    queued[0].id,
                    "Something went wrong processing this. Try again; if it keeps happening, report it.",
                )
            done += 1
            self.events.changed()
        if not self._stop.is_set() and not self._changed_since_start():
            from engine.stages import move_ready_records

            if move_ready_records(self.store):
                self.events.changed()
        return done

    def backup_if_due(self) -> bool:
        """Make a scheduled backup when one is due. On its own thread, so a large copy never holds up other work."""
        from engine.backup import due, run_backup

        if not due(self.ws, self.cfg):
            return False
        run_backup(self.ws, self.cfg)
        self.events.changed()
        return True

    def export_if_due(self) -> bool:
        """Write the readable export to the workspace's git when it is due. A workspace with no git repository has
        nothing to commit to: that is said once in the log and nothing is written. Nothing is ever pushed. Returns
        whether anything was committed."""
        from engine import export_schedule

        if not export_schedule.has_git(self.ws):
            if not self._said_no_git:
                self._said_no_git = True
                log.info("The scheduled export is off: this workspace has no git repository to keep it in.")
            return False
        now = self.now()
        if not export_schedule.due(self.ws, self.cfg, now):
            return False
        return export_schedule.run(self.ws, self.store, self.cfg, now)

    def first_backup_soon(self) -> threading.Thread | None:
        """A backup folder was just chosen: when no backup has ever succeeded, make one now on its own thread, so the
        person isn't asked to back up right after choosing where. Uses the settings as the files hold them now, and
        the same lock as scheduled backups. Returns the thread, or None when a backup already succeeded."""
        from engine.backup import state
        from engine.config import ConfigError, load_config

        try:
            fresh = load_config(self.ws.config_dir, env=dict(os.environ))
        except ConfigError as err:
            log.warning("The first backup wasn't made: %s", err)
            return None
        if state(self.ws, fresh).last_success is not None:
            return None

        def run() -> None:
            from engine.backup import run_backup

            try:
                run_backup(self.ws, fresh)
            except Exception:  # a failed backup is recorded by run_backup; nothing here may break the request
                log.exception("the first backup failed")
            self.events.changed()

        thread = threading.Thread(target=run, name="cockpit-first-backup", daemon=True)
        thread.start()
        return thread

    def sync_if_changed(self) -> bool:
        """Write the synced folder when anything changed since it was last written, and keep this install's lease
        fresh. Stops for good if another computer has taken the workspace over. Returns whether it wrote."""
        from engine import handover
        from engine.sync import folder_problem, write_folder

        if not self.cfg.storage.sync.folder.strip() or self.sync_lost:
            return False
        problem = folder_problem(self.ws, self.cfg)
        if problem:
            self.sync_problem = problem
            return False
        other = handover.held_elsewhere(self.ws, self.cfg)
        if other is not None:
            self.sync_lost = True
            self.sync_problem = (
                f"The workspace was opened on {other.computer}, so this copy stopped writing to the synced folder. "
                "Close it here; changes made here since then are kept on this computer."
            )
            return False
        from engine import outside

        if self.cfg.storage.sync.watch_outside_edits and outside.pick_up(self.store, self.ws, self.cfg):
            self.events.changed()
        head, count = self.store.read().sql("SELECT max(seq), count(*) FROM ledger").fetchone()
        wrote = False
        if head != self._synced_at:
            try:
                self.sync_result = write_folder(
                    self.store, self.ws, self.cfg, may_overwrite=outside.settled(self.store, self.cfg)
                )
                outside.forget(self.cfg)
                self.sync_problem = None
            except (OSError, ValueError) as err:
                log.warning("The synced folder couldn't be written: %s", err)
                reason = err.strerror if isinstance(err, OSError) and err.strerror else None
                self.sync_problem = (
                    f"The synced folder couldn't be written ({reason})"
                    if reason
                    else ("The synced folder couldn't be written")
                )
                return False
            self._synced_at, wrote = head, True
        if wrote or time.monotonic() - self._beat >= self.HEARTBEAT_SECONDS:
            handover.take(self.ws, self.cfg, ledger=count)
            self._beat = time.monotonic()
        return wrote

    def release_folder(self) -> None:
        """On closing: a last write, then the lease marked released, so the other computer can open at once."""
        from engine import handover

        if not self.cfg.storage.sync.folder.strip():
            return
        try:
            self.sync_if_changed()
            if not self.sync_lost and self.sync_problem is None:
                count = self.store.read().sql("SELECT count(*) FROM ledger").fetchone()[0]
                handover.take(self.ws, self.cfg, ledger=count, released=True)
        except Exception:  # closing must go on even if the folder can't be written
            log.exception("releasing the synced folder failed")

    def _sync_loop(self) -> None:
        after = -1
        while not self._stop.is_set():
            try:
                self.sync_if_changed()
            except Exception:  # a failed write is retried on the next change; nothing here may stop the thread
                log.exception("writing the synced folder failed")
            after = self.events.wait(after, timeout=self.SYNC_CHECK_SECONDS)
            self._stop.wait(timeout=1)

    def run_due_jobs(self) -> int:
        """Run every plugin job that is due. Returns how many ran."""
        if self._changed_since_start():
            return 0
        now = self.now()
        due = self.store.plugins.due_jobs(now)
        for name in due:
            self.store.plugins.run_job(name, now)
        if due:
            self.events.changed()
            self.poke()
        return len(due)

    def run_due_watches(self) -> int:
        """Read every watched source that is due, once each however long the computer was asleep. Returns how many
        were read."""
        from engine.set_aside import purge_due
        from engine.watch import due, refresh

        if self._changed_since_start():
            return 0
        now = self.now()
        if purge_due(self.ws, self.store, self.cfg, now):
            self.events.changed()
        sources = due(self.store, self.cfg, now)
        handed = 0
        for source in sources:
            if self._stop.is_set():
                break
            result = refresh(self.ws, self.store, self.cfg, source, now)
            handed += len(result.new) + len(result.changed) + len(result.removed)
        if sources:
            self.events.changed()
        if handed:
            self.poke()
        return len(sources)

    def _jobs_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_due_jobs()
            except Exception:  # a job's failure is recorded on its run; nothing here may stop the thread
                log.exception("running scheduled jobs failed")
            try:
                self.run_due_watches()
            except Exception:  # a failed read is recorded on its run; nothing here may stop the thread
                log.exception("reading watched sources failed")
            try:
                self.export_if_due()
            except Exception:  # a failed export is logged by the export; nothing here may stop the thread
                log.exception("the scheduled export failed")
            self._read_now.wait(timeout=60)
            self._read_now.clear()

    def _backup_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.backup_if_due()
            except Exception:  # a failed backup is recorded by run_backup; nothing here may stop the thread
                log.exception("scheduled backup failed")
            self._stop.wait(timeout=60)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_pending()
            if self.restart_due():
                return
            self._wake.wait(timeout=5)
            self._wake.clear()

    def restart_due(self) -> bool:
        """Restart once the person asked for it, between requests. The app never restarts on its own: a change that
        needs one is shown, and new work waits, until the person chooses to restart."""
        if self.on_restart is None or self.restarting or not self.restart_requested:
            return False
        self.restarting = True
        log.warning("Restarting, as asked, to use changed settings or code.")
        self.events.changed()
        self.on_restart()
        return True
