"""API routes for settings and the first-run setup (design 4.0, 7.8, 7.9)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    AiAccountAdd,
    AiTestResult,
    BackupFolderAdd,
    EndpointView,
    FingerprintIn,
    FolderCheckView,
    FolderListView,
    MeIn,
    MeView,
    Ok,
    SettingChangeView,
    SettingItem,
    SettingsSave,
    SettingsSaved,
    SettingsView,
    SetupStepView,
    SetupView,
    TemplateApplied,
    TemplateApply,
    TemplateView,
)
from engine import settings as config_screens
from engine import setup, templates
from engine.config import Config, ConfigError, load_config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace

#: Settings an add-on's setup step may never suggest: where keys come from and which accounts get the work.
NEVER_SUGGESTED = ("ai.providers", "ai.tiers", "workspace.plugins.secrets", "workspace.plugins.enabled", "server.")
#: Keys the guided steps write that no form shows: an AI account, the tiers it does, the backup folders.
GUIDED = ("ai.providers.", "ai.tiers.", "storage.backups.targets")


def build_setup_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")
    local = cfg.server.mode == "local"

    def current() -> Config:
        """The settings as the files hold them now; the running app may have started with older ones."""
        try:
            return load_config(ws.config_dir, env=dict(os.environ))
        except ConfigError:
            return cfg

    def saved(result: config_screens.Saved) -> SettingsSaved:
        events.changed()
        return SettingsSaved(
            changes=[SettingChangeView(**c) for c in result.changes],
            fingerprint=result.fingerprint,
            restarts=bool(result.changes) and worker.needs_restart(),
        )

    def save(changes: dict[str, Any], reset: list[str], fingerprint: str, allow: tuple[str, ...] = ()) -> Any:
        try:
            return config_screens.save(
                ws,
                cfg,
                store,
                changes=changes,
                reset=reset,
                read_fingerprint=fingerprint,
                env=dict(os.environ),
                allow=allow,
            )
        except config_screens.SettingsConflict as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        except StoreError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    # ---- settings ------------------------------------------------------------------------------------------------

    @r.get("/settings")
    def settings_view() -> SettingsView:
        return SettingsView(
            fingerprint=config_screens.fingerprint(ws.config_dir),
            items=[SettingItem(**vars(s)) for s in config_screens.describe(current())],
        )

    @r.post("/settings")
    def settings_save(body: SettingsSave) -> SettingsSaved:
        # The keys the guided steps write are accepted here too, so their Undo (the values from before) works.
        return saved(save(body.changes, body.reset, body.fingerprint, allow=GUIDED))

    # ---- the person the app is for --------------------------------------------------------------------------------

    def me_now() -> MeView:
        pid = current().workspace.user.person
        person = store.read().get("person", pid) if pid else None
        return MeView(person=person.id if person else None, full_name=person.data["full_name"] if person else "")

    @r.get("/me")
    def me() -> MeView:
        return me_now()

    @r.post("/me")
    def me_save(body: MeIn) -> MeView:
        """Name the person the app is for: renames their person record, or makes one and links it in the settings."""
        from engine.storage import WriteContext

        name = " ".join(body.full_name.split())
        found = me_now()
        clash = [
            p
            for p in store.read().list("person")
            if p.id != found.person and p.data["full_name"].lower() == name.lower()
        ]
        if clash:
            raise HTTPException(status_code=409, detail=f"{name} is already someone else in People.")
        ctx = WriteContext(actor="pm", trust="trusted", op="person.edit" if found.person else "person.add")
        with store.transaction() as tx:
            if found.person:
                current_person = tx.get("person", found.person)
                tx.update("person", found.person, {"full_name": name}, ctx, read_version=current_person.version)
                pid = found.person
            else:
                pid = tx.create("person", {"full_name": name}, ctx).id
        events.changed()
        if not found.person:
            save(
                {"workspace.user.person": pid},
                [],
                config_screens.fingerprint(ws.config_dir),
                allow=("workspace.user.",),
            )
            worker.needs_restart()
        return MeView(person=pid, full_name=name)

    # ---- setup steps ---------------------------------------------------------------------------------------------

    @r.get("/setup")
    def setup_view() -> SetupView:
        steps = setup.steps(ws, current(), store)
        return SetupView(
            steps=[SetupStepView(**vars(s)) for s in steps],
            finished=all(s.done or s.skipped for s in steps),
            local=local,
        )

    @r.post("/setup/{step:path}/apply-settings")
    def setup_apply_settings(step: str, body: FingerprintIn) -> SettingsSaved:
        found = next((s for s in setup.steps(ws, current(), store) if s.id == step), None)
        if found is None or not found.settings:
            raise HTTPException(status_code=404, detail="That step suggests no settings.")
        barred = [k for k in found.settings if k.startswith(NEVER_SUGGESTED)]
        if barred:
            raise HTTPException(status_code=400, detail=f"An add-on can't suggest {', '.join(barred)}.")
        return saved(save(dict(found.settings), [], body.fingerprint, allow=("",)))

    @r.post("/setup/{step:path}/skip")
    def setup_skip(step: str) -> Ok:
        setup.skip(ws, step)
        events.changed()
        return Ok(ok=step)

    @r.post("/setup/{step:path}/reopen")
    def setup_reopen(step: str) -> Ok:
        setup.skip(ws, step, skipped=False)
        events.changed()
        return Ok(ok=step)

    # ---- templates -----------------------------------------------------------------------------------------------

    @r.get("/templates")
    def template_list() -> list[TemplateView]:
        return [TemplateView(id=t["id"], name=t["name"], description=t["description"]) for t in templates.shipped()]

    @r.post("/templates/apply")
    def template_apply(body: TemplateApply) -> TemplateApplied:
        if body.id not in {t["id"] for t in templates.shipped()}:
            raise HTTPException(status_code=404, detail=f"there is no template {body.id}")
        try:
            plugins = templates.apply(ws, body.id)
        except (templates.TemplateError, ConfigError) as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        setup.template_applied(ws, body.id)
        events.changed()
        return TemplateApplied(plugins=plugins, restarts=worker.needs_restart())

    # ---- folders -------------------------------------------------------------------------------------------------

    @r.get("/setup/folder-check")
    def folder_check(path: str) -> FolderCheckView:
        return FolderCheckView(**vars(setup.check_backup_folder(ws, path)))

    @r.get("/setup/folders")
    def folders(path: str | None = None) -> FolderListView:
        if not local:
            raise HTTPException(status_code=403, detail="Folders on the server can't be browsed; type the path.")
        try:
            return FolderListView(**vars(setup.list_folders(path)))
        except StoreError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    @r.post("/setup/backup-folder")
    def backup_folder(body: BackupFolderAdd) -> SettingsSaved:
        check = setup.check_backup_folder(ws, body.path)
        if not check.ok:
            raise HTTPException(status_code=400, detail=check.problem)
        targets = [t.model_dump() for t in current().storage.backups.targets]
        if any(os.path.realpath(os.path.expanduser(t["path"])) == check.path for t in targets):
            raise HTTPException(status_code=409, detail="Backups already go to that folder.")
        targets.append({"path": check.path, "label": body.label.strip()})
        return saved(save({"storage.backups.targets": targets}, [], body.fingerprint, allow=("storage.backups.",)))

    # ---- AI accounts ---------------------------------------------------------------------------------------------

    @r.get("/ai/endpoints")
    def endpoints() -> list[EndpointView]:
        return [EndpointView(**e) for e in setup.known_endpoints()]

    @r.post("/ai/accounts")
    def ai_account_add(body: AiAccountAdd) -> SettingsSaved:
        from engine.ai.adapters import ADAPTERS

        if body.adapter not in ADAPTERS or body.adapter == "stub":
            raise HTTPException(status_code=400, detail=f"There is no kind of account called {body.adapter}.")
        if body.name in current().ai.providers:
            raise HTTPException(status_code=409, detail=f"There is already an account called {body.name}.")
        if not body.models:
            raise HTTPException(status_code=400, detail="Name at least one model the account uses.")
        if body.key and body.key_ref:
            raise HTTPException(status_code=400, detail="Paste a key or give where it is, not both.")
        if body.key and not local:
            raise HTTPException(
                status_code=400, detail="On a hosted app, keys come from the environment: give env:NAME instead."
            )
        provider: dict[str, Any] = {
            "adapter": body.adapter,
            "models": body.models,
            "allowed_data": list(body.allowed_data),
        }
        if body.base_url:
            provider["base_url"] = body.base_url.strip()
        if body.agent is not None:
            provider["agent"] = body.agent
        kept = None
        if body.key:
            try:
                kept = setup.keep_key(ws, body.name, body.key)
            except StoreError as err:
                raise HTTPException(status_code=400, detail=str(err)) from None
            provider["auth"] = kept
        elif body.key_ref:
            provider["auth"] = body.key_ref.strip()
        first = next(iter(body.models))
        changes: dict[str, Any] = {f"ai.providers.{body.name}": provider}
        for tier in body.use_for:
            changes[f"ai.tiers.{tier}.use"] = f"{body.name}/{first}"
        try:
            result = save(changes, [], body.fingerprint, allow=("ai.providers.", "ai.tiers."))
        except HTTPException:
            if kept is not None:
                (ws.private_dir / "keys" / body.name).unlink(missing_ok=True)
            raise
        return saved(result)

    @r.post("/ai/test")
    def ai_test() -> list[AiTestResult]:
        from engine.ai.smoke import record, smoke_test

        try:
            current = load_config(ws.config_dir)
        except ConfigError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        results = smoke_test(current, os.environ)
        record(ws, results)
        events.changed()
        return [AiTestResult(tier=x.tier, account=x.account, main=x.main, ok=x.ok, detail=x.detail) for x in results]

    return r
