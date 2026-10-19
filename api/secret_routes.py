"""Secrets typed on the screen that no source's form holds: the secrets an add-on declares, and the key that encrypts
the backups. A local app keeps a typed (or made) value in the workspace's private keys folder and writes only where it
is kept into the settings; a hosted app takes only where it is kept instead. A value never reaches a settings file, the
ledger, a log or an answer. The one exception is the key the person asked the app to make: it is in that one answer so
it can be copied, and nowhere else."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    AddonSecretIn,
    AddonSecretsView,
    AddonSecretView,
    BackupKeyIn,
    BackupKeySaved,
    BackupKeyView,
    SettingChangeView,
    SettingsSaved,
)
from api.setup_routes import HOSTED_KEY, asked_reference
from engine import settings as config_screens
from engine import setup
from engine.config import Config, ConfigError, load_config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace

#: The name the backup key is kept under in the private keys folder.
BACKUP_KEY_NAME = "backup-key"

#: How many random bytes a made backup key has: more than enough, and short enough to copy.
MADE_KEY_BYTES = 32


def build_secret_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")
    local = cfg.server.mode == "local"

    def current() -> Config:
        """The settings as the files hold them now; the running app may have started with older ones."""
        try:
            return load_config(ws.config_dir, env=dict(os.environ))
        except ConfigError:
            return cfg

    def save(changes: dict[str, Any], fingerprint: str, allow: tuple[str, ...]) -> config_screens.Saved:
        try:
            done = config_screens.save(
                ws,
                cfg,
                store,
                changes=changes,
                reset=[],
                read_fingerprint=fingerprint,
                env=dict(os.environ),
                allow=allow,
            )
        except config_screens.SettingsConflict as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        except StoreError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        events.changed()
        return done

    def kept_or_named(
        name: str, value: str | None, reference: str | None, make: bool = False
    ) -> tuple[str, str | None, Path | None]:
        """What a secret setting holds, from what the person gave: the reference, the key just made (when asked to
        make one) and the file this call made, to take away again if the save is refused. Nothing typed is kept when
        the person gave where it is kept instead."""
        typed = value is not None and value.strip() != ""
        named = reference is not None and reference.strip() != ""
        if (value is not None and not typed and not named) or [typed, named, make].count(True) != 1:
            raise HTTPException(status_code=400, detail="Type it, or give where it is kept: one of the two.")
        if named:
            return asked_reference(reference or ""), None, None
        if not local:
            raise HTTPException(status_code=400, detail=HOSTED_KEY)
        kept = setup.unused_secret_name(ws, name)
        made = secrets.token_urlsafe(MADE_KEY_BYTES) if make else None
        try:
            return setup.keep_secret(ws, kept, made or value or ""), made, setup.secret_path(ws, kept)
        except StoreError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    def declared() -> dict[str, list[str]]:
        """The secrets each running add-on declares, by add-on."""
        host = store.plugins
        return {
            name: list(manifest.requires.secrets)
            for name, manifest in sorted(host.manifests.items())
            if manifest.requires.secrets and host.active(name)
        }

    @r.get("/addon-secrets")
    def addon_secrets() -> list[AddonSecretsView]:
        """Each running add-on's declared secrets and where each is read from now; never a value."""
        held = current().workspace.plugins.secrets
        return [
            AddonSecretsView(
                plugin=plugin,
                secrets=[
                    AddonSecretView(secret=name, where=where, name=read_from)
                    for name in names
                    for where, read_from in [setup.secret_where(ws, held.get(plugin, {}).get(name))]
                ],
            )
            for plugin, names in declared().items()
        ]

    @r.post("/addons/{plugin}/secrets/{secret}")
    def addon_secret(plugin: str, secret: str, body: AddonSecretIn) -> SettingsSaved:
        """Give one secret an add-on declares, with Undo: typed (kept on this computer, a local app only) or as
        where it is kept. The settings hold only where."""
        names = declared().get(plugin)
        if names is None:
            raise HTTPException(
                status_code=404, detail="There is no add-on running now by that name that needs secrets."
            )
        if secret not in names:
            raise HTTPException(status_code=404, detail="That isn't one of the secrets this add-on says it needs.")
        reference, _, fresh = kept_or_named(setup.secret_name("addon", plugin, secret), body.value, body.reference)
        try:
            done = save(
                {f"workspace.plugins.secrets.{plugin}.{secret}": reference},
                body.fingerprint,
                ("workspace.plugins.secrets.",),
            )
        except HTTPException:
            if fresh:
                fresh.unlink(missing_ok=True)
            raise
        return _saved(done, worker)

    @r.get("/backup-key")
    def backup_key() -> BackupKeyView:
        """Where the key that encrypts the backups is read from; never the key."""
        where, name = setup.secret_where(ws, current().storage.backups.encrypt)
        return BackupKeyView(where=where, name=name)

    @r.post("/backup-key")
    def backup_key_set(body: BackupKeyIn) -> BackupKeySaved:
        """Give the key that encrypts the backups, with Undo: typed, made by the app, or as where it is kept. A local
        app keeps a typed or made key on this computer. Backups already made stay sealed with the key they were made
        with, so an earlier key is kept, not replaced."""
        reference, made, fresh = kept_or_named(BACKUP_KEY_NAME, body.value, body.reference, bool(body.make))
        try:
            done = save({"storage.backups.encrypt": reference}, body.fingerprint, ())
        except HTTPException:
            if fresh:
                fresh.unlink(missing_ok=True)
            raise
        return BackupKeySaved(**_saved(done, worker).model_dump(), made=made)

    return r


def _saved(result: config_screens.Saved, worker: Worker) -> SettingsSaved:
    return SettingsSaved(
        changes=[SettingChangeView(**c) for c in result.changes],
        fingerprint=result.fingerprint,
        needs_restart=bool(result.changes) and worker.needs_restart(),
    )
