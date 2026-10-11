"""API routes for settings and the first-run setup (design 4.0, 7.8, 7.9)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    AiAccountAdd,
    AiAccountChange,
    AiAccountView,
    AiModelsAsk,
    AiModelsView,
    AiModelView,
    AiTestResult,
    BackupFolderAdd,
    EndpointView,
    FingerprintIn,
    FolderCheckView,
    FolderListView,
    LocalServerView,
    MeIn,
    MeView,
    Ok,
    RestartAsked,
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


def _merged(current: Any, suggested: Any) -> Any:
    """A suggested value laid over the current one: a mapping adds the keys it suggests and keeps every key the
    person already has, with their own values, nested mappings included; anything that isn't a mapping is
    replaced."""
    if isinstance(current, dict) and isinstance(suggested, dict):
        out = dict(current)
        for key, value in suggested.items():
            if key not in current:
                out[key] = value
            elif isinstance(current[key], dict) and isinstance(value, dict):
                out[key] = _merged(current[key], value)
        return out
    return suggested


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
            needs_restart=bool(result.changes) and worker.needs_restart(),
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
            items=[SettingItem(**vars(s)) for s in config_screens.describe(current(), store.plugins, ws.config_dir)],
        )

    @r.post("/restart")
    def restart() -> RestartAsked:
        """Restart now, because the person chose to (never on its own). It starts between pieces of work."""
        if not worker.can_restart:
            raise HTTPException(
                status_code=409, detail="This copy of the app can't restart itself. Close it and start it again."
            )
        worker.request_restart()
        return RestartAsked(restarting=True)

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
        now = current()
        changes = {key: _merged(now.value(key), value) for key, value in found.settings.items()}
        return saved(save(changes, [], body.fingerprint, allow=("",)))

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
        try:
            set_up = templates.in_use(ws, list(current().workspace.plugins.enabled))
        except templates.TemplateError:
            set_up = None
        return [
            TemplateView(
                id=t["id"], name=t["name"], description=t["description"], adds=t["adds"], set_up=t["id"] == set_up
            )
            for t in templates.shipped()
        ]

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
        return TemplateApplied(plugins=plugins, needs_restart=worker.needs_restart())

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
        import shutil

        found = []
        for e in setup.known_endpoints():
            installed = (shutil.which(e["program"]) is not None) if (e["program"] and local) else None
            found.append(EndpointView(**e, installed=installed))
        return found

    # ---- turning add-ons on and off -------------------------------------------------------------------------------

    @r.post("/packs/{name}/on")
    def pack_on(name: str, body: FingerprintIn) -> SettingsSaved:
        """Turn on an add-on installed on this computer: it is added to the add-ons that run, with Undo. Its code
        runs after the restart the person chooses."""
        from engine.plugin_manifest import declared_plugins

        if name not in {m.name for m in declared_plugins(ws.config_dir, None)}:
            raise HTTPException(status_code=404, detail=f"No add-on called {name} is installed on this computer.")
        enabled = list(current().workspace.plugins.enabled)
        if name in enabled:
            raise HTTPException(status_code=409, detail=f"{name} is on already.")
        changes = {"workspace.plugins.enabled": [*enabled, name]}
        return saved(save(changes, [], body.fingerprint, allow=("workspace.plugins.enabled",)))

    @r.post("/packs/{name}/off")
    def pack_off(name: str, body: FingerprintIn) -> SettingsSaved:
        """Turn an add-on off, with Undo: it stops after the restart the person chooses; its records and settings
        stay."""
        enabled = list(current().workspace.plugins.enabled)
        if name not in enabled:
            raise HTTPException(status_code=409, detail=f"{name} is off already.")
        changes = {"workspace.plugins.enabled": [n for n in enabled if n != name]}
        return saved(save(changes, [], body.fingerprint, allow=("workspace.plugins.enabled",)))

    @r.get("/ai/accounts")
    def ai_accounts() -> list[AiAccountView]:
        """The AI accounts in the settings, as they are on disk now; never a key."""
        from engine.secrets import SecretError, describe_secret, resolve_secret

        ai = current().ai

        def key_state(ref: str | None) -> tuple[str, str | None]:
            if not ref:
                return "none", None
            try:
                return ("saved", None) if resolve_secret(ref) else ("missing", describe_secret(ref))
            except SecretError:
                return "missing", describe_secret(ref)

        found = []
        for name, p in ai.providers.items():
            state, where = key_state(p.auth)
            found.append(
                AiAccountView(
                    name=name,
                    kind=p.kind,
                    adapter=p.adapter,
                    base_url=p.base_url,
                    models=dict(p.models),
                    used_for=[t for t, tier in ai.tiers.items() if (tier.use or "").split("/", 1)[0] == name],
                    has_key=bool(p.auth),
                    key_state=state,
                    key_where=where,
                )
            )
        return found

    @r.post("/ai/accounts/{name}/test")
    def ai_account_test(name: str) -> list[AiTestResult]:
        """Test one account on its first model, whether or not any kind of work uses it yet."""
        from engine.ai.smoke import account_test

        try:
            now = load_config(ws.config_dir)
        except ConfigError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        if name not in now.ai.providers:
            raise HTTPException(status_code=404, detail=f"There is no account called {name}.")
        results = account_test(now, os.environ, name)
        line = AiTestResult(tier="account", account=name, main=True, ok=True, detail="answered")
        for x in results:
            if not x.ok and line.ok:
                line.ok, line.detail = False, x.detail
        return [line]

    @r.post("/ai/accounts/{name}")
    def ai_account_change(name: str, body: AiAccountChange) -> SettingsSaved:
        """Give an account a new key, other models or other work, with Undo."""
        provider = current().ai.providers.get(name)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"There is no account called {name}.")
        if body.key and body.key_ref:
            raise HTTPException(status_code=400, detail="Paste a key or give where it is, not both.")
        if body.key and not local:
            raise HTTPException(
                status_code=400, detail="On a hosted app, keys come from the environment: give env:NAME instead."
            )
        changes: dict[str, Any] = {}
        if body.key:
            try:
                changes[f"ai.providers.{name}.auth"] = setup.keep_key(ws, name, body.key)
            except StoreError as err:
                raise HTTPException(status_code=400, detail=str(err)) from None
        elif body.key_ref:
            changes[f"ai.providers.{name}.auth"] = body.key_ref.strip()
        models = body.models if body.models is not None else dict(provider.models)
        if body.models is not None:
            if not body.models:
                raise HTTPException(status_code=400, detail="Name at least one model the account uses.")
            changes[f"ai.providers.{name}.models"] = body.models
        for tier, short in body.use.items():
            if short not in models:
                raise HTTPException(status_code=400, detail=f"{short} isn't one of this account's models.")
            changes[f"ai.tiers.{tier}.use"] = f"{name}/{short}"
        if not changes:
            raise HTTPException(status_code=400, detail="Nothing to change.")
        return saved(save(changes, [], body.fingerprint, allow=("ai.providers.", "ai.tiers.")))

    @r.post("/ai/accounts/{name}/remove")
    def ai_account_remove(name: str, body: FingerprintIn) -> SettingsSaved:
        """Remove an account, with Undo: the work it did goes back to the tier's default account. Its kept key stays
        on this computer, so Undo brings the account back whole."""
        ai = current().ai
        if name not in ai.providers:
            raise HTTPException(status_code=404, detail=f"There is no account called {name}.")
        reset = [f"ai.providers.{name}"]
        changes: dict[str, Any] = {}
        for tier_name, tier in ai.tiers.items():
            if (tier.use or "").split("/", 1)[0] == name:
                reset.append(f"ai.tiers.{tier_name}.use")
            kept = [ref for ref in tier.fallback if ref.split("/", 1)[0] != name]
            if kept != list(tier.fallback):
                changes[f"ai.tiers.{tier_name}.fallback"] = kept
        return saved(save(changes, reset, body.fingerprint, allow=("ai.providers.", "ai.tiers.")))

    @r.post("/ai/accounts")
    def ai_account_add(body: AiAccountAdd) -> SettingsSaved:
        from engine.ai.adapters import ADAPTERS

        if body.adapter not in ADAPTERS or body.adapter == "stub":
            raise HTTPException(status_code=400, detail=f"There is no kind of account called {body.adapter}.")
        if body.name in current().ai.providers:
            raise HTTPException(status_code=409, detail=f"There is already an account called {body.name}.")
        kind = setup.endpoint(body.endpoint) if body.endpoint else None
        if body.endpoint and kind is None:
            raise HTTPException(status_code=400, detail=f"There is no kind of account called {body.endpoint}.")
        models = dict(body.models)
        if not models and kind is not None and kind.get("model_optional"):
            models = {"default": "default"}  # the program picks its own model; the id is passed nowhere
        if not models:
            raise HTTPException(status_code=400, detail="Name at least one model the account uses.")
        if body.key and body.key_ref:
            raise HTTPException(status_code=400, detail="Paste a key or give where it is, not both.")
        if body.key and not local:
            raise HTTPException(
                status_code=400, detail="On a hosted app, keys come from the environment: give env:NAME instead."
            )
        provider: dict[str, Any] = {
            **(kind["settings"] if kind else {}),
            **({"kind": kind["id"]} if kind else {}),
            "adapter": body.adapter,
            "models": models,
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
        first = next(iter(models))
        changes: dict[str, Any] = {f"ai.providers.{body.name}": provider}
        for tier in body.use_for:
            changes[f"ai.tiers.{tier}.use"] = f"{body.name}/{first}"
        for tier, short in body.use.items():
            if short not in models:
                raise HTTPException(status_code=400, detail=f"{short} isn't one of this account's models.")
            changes[f"ai.tiers.{tier}.use"] = f"{body.name}/{short}"
        try:
            result = save(changes, [], body.fingerprint, allow=("ai.providers.", "ai.tiers."))
        except HTTPException:
            if kept is not None:
                (ws.private_dir / "keys" / body.name).unlink(missing_ok=True)
            raise
        return saved(result)

    @r.post("/ai/models")
    def ai_models(body: AiModelsAsk) -> AiModelsView:
        """The models a service offers, read with a key that isn't saved, so the person picks from a list."""
        from engine.secrets import SecretError, resolve_secret

        kind = setup.endpoint(body.endpoint)
        if kind is None:
            raise HTTPException(status_code=400, detail=f"There is no kind of account called {body.endpoint}.")
        base_url = kind["base_url"] or (body.base_url or "").strip()
        if not kind["base_url"] and not local:
            raise HTTPException(status_code=400, detail="On a hosted app, models are listed only for known services.")
        if not base_url:
            return AiModelsView(problem="Enter the service's address first.")
        if body.key and body.key_ref:
            raise HTTPException(status_code=400, detail="Paste a key or give where it is, not both.")
        if body.key and not local:
            raise HTTPException(
                status_code=400, detail="On a hosted app, keys come from the environment: give env:NAME instead."
            )
        try:
            key = body.key.strip() if body.key else resolve_secret(body.key_ref)
        except SecretError as err:
            return AiModelsView(problem=str(err))
        models, problem = setup.list_models(kind, base_url, key)
        return AiModelsView(
            models=[
                AiModelView(
                    id=name,
                    context_tokens=info.context_tokens,
                    input_per_million=info.input_per_million,
                    output_per_million=info.output_per_million,
                )
                for name, info in models
            ],
            problem=problem,
        )

    @r.get("/ai/local")
    def ai_local() -> list[LocalServerView]:
        """Model servers running on this computer now, with their models; none on a hosted app."""
        if not local:
            return []
        found = []
        for kind in setup.known_endpoints():
            if not kind["local"] or not kind["base_url"]:
                continue
            models, problem = setup.list_models(kind, kind["base_url"], None)
            if problem is None and models:
                found.append(LocalServerView(endpoint=kind["id"], name=kind["name"], models=[m for m, _ in models]))
        return found

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
        # One line per kind of work and account, in plain words: the run's own details are for `cockpit ai test`.
        lines: dict[tuple[str, str], AiTestResult] = {}
        for x in results:
            account = x.account.split("/", 1)[0].split(" ", 1)[0]
            line = lines.setdefault(
                (x.tier, account), AiTestResult(tier=x.tier, account=account, main=x.main, ok=True, detail="answered")
            )
            if not x.ok and line.ok:
                line.ok, line.detail = False, x.detail
        return list(lines.values())

    return r
