"""API routes for settings and the first-run setup (design 4.0, 7.8, 7.9)."""

from __future__ import annotations

import copy
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException

from api.pack_routes import entry_in
from api.schemas import (
    AiAccountAdd,
    AiAccountChange,
    AiAccountRemove,
    AiAccountSkills,
    AiAccountView,
    AiBorrowAnswer,
    AiBorrowed,
    AiCheckSize,
    AiMeasureEstimate,
    AiMeasureIn,
    AiMeasureStarted,
    AiModelsAsk,
    AiModelSkills,
    AiModelsView,
    AiModelView,
    AiSkillsView,
    AiSkillView,
    AiSwitched,
    AiSwitchEstimate,
    AiTestResult,
    BackupFolderAdd,
    CatalogAddress,
    ConfirmDone,
    ConfirmIn,
    DataLevelAllowed,
    DomainOffer,
    EndpointView,
    FingerprintIn,
    FolderCheckView,
    FolderListView,
    LocalServerView,
    MeIn,
    MeView,
    Ok,
    PackTokenIn,
    RestartAsked,
    SettingChangeView,
    SettingItem,
    SettingsSave,
    SettingsSaved,
    SettingsView,
    SetupStepView,
    SetupView,
    SortingRuleIn,
    TemplateApplied,
    TemplateApply,
    TemplateView,
    WalkthroughIn,
    WalkthroughView,
    WatchKindView,
    WatchSourceChange,
    WatchSourceIn,
)
from engine import audit, setup, templates
from engine import set_aside as set_aside_mail
from engine import settings as config_screens
from engine import sorting_rules as sorting
from engine.config import Config, ConfigError, load_config
from engine.config.schema import WatchSource
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace

log = logging.getLogger(__name__)

#: What a hosted app says to a pasted key: keys stay in the app's own environment, given by their reference.
HOSTED_KEY = "On a hosted app, a key can't be pasted: keep it in the app's environment and give where it is instead."

#: Why a measuring failed, in words.
MEASURE_WHY = {
    "no-answer": "The account didn't take any of the cases (it asked to slow down or its plan was used up), so nothing "
    "was measured.",
    "unfinished": "Measuring couldn't finish; nothing was added.",
}

#: Settings an add-on's setup step may never suggest: where keys come from and which accounts get the work.
#: How many confirmed senders on one domain make the screen offer a rule for the whole domain.
DOMAIN_OFFER_AT = 3
NEVER_SUGGESTED = ("ai.providers", "ai.tiers", "workspace.plugins.secrets", "workspace.plugins.enabled", "server.")
#: Keys the guided steps write that no form shows: an AI account, the tiers it does, the backup folders.
#: The keys the guided routes write (an AI account, a backup folder, the sources, sorting rules, add-ons on or off, a
#: release's read token, the person's own name). The general save accepts them too, because a screen's Undo saves the
#: values from before there.
GUIDED = (
    "ai.providers.",
    "ai.tiers.",
    "storage.backups.",
    "watch.sources",
    "watch.triage",
    "workspace.plugins.enabled",
    "workspace.plugins.catalog.release_tokens",
    "workspace.user.",
)


#: How the first read of a source added from the screen goes: the source setting's own default, which the add route
#: leaves untouched.
NEW_SOURCE_FIRST_RUN = WatchSource.model_fields["first_run"].get_default()


def _defaults(model: Any) -> dict[str, Any]:
    """A settings model's defaults where every field has one; empty where a field must be filled in."""
    values = {}
    for key, info in model.model_fields.items():
        if not info.is_required():
            default = info.get_default(call_default_factory=True)
            values[key] = default.model_dump(mode="json") if hasattr(default, "model_dump") else default
    return values


def asked_reference(typed: str) -> str:
    """A place a secret is kept, as the person typed it: a bare name is the name of an environment variable."""
    text = typed.strip()
    return text if ":" in text else f"env:{text}"


def _nested(values: dict[str, Any], dotted: str) -> Any:
    """The value at a dotted name in nested settings, or None where there is none or it is empty."""
    at: Any = values
    for part in dotted.split("."):
        if not isinstance(at, dict) or part not in at:
            return None
        at = at[part]
    return at or None


def _put(values: dict[str, Any], dotted: str, value: Any) -> None:
    """Set the value at a dotted name in nested settings, making the objects on the way."""
    *parents, last = dotted.split(".")
    at = values
    for part in parents:
        child = at.get(part)
        if not isinstance(child, dict):
            child = at[part] = {}
        at = child
    at[last] = value


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
        result = saved(save(body.changes, body.reset, body.fingerprint, allow=GUIDED))
        if "workspace.user.person" in body.changes:
            person_named()
        return result

    def person_named() -> None:
        """Work that waited for the workspace to have a person is queued again by itself."""
        from engine.dispatcher import requeue_waiting_for_person

        if requeue_waiting_for_person(store):
            events.changed()
            worker.poke()

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
                tx.update(
                    "person",
                    found.person,
                    {"full_name": name, "name_verified": True},
                    ctx,
                    read_version=current_person.version,
                )
                pid = found.person
            else:
                pid = tx.create("person", {"full_name": name, "name_verified": True}, ctx).id
        events.changed()
        if not found.person:
            save(
                {"workspace.user.person": pid},
                [],
                config_screens.fingerprint(ws.config_dir),
                allow=("workspace.user.",),
            )
            person_named()
        return MeView(person=pid, full_name=name)

    # ---- setup steps ---------------------------------------------------------------------------------------------

    @r.get("/setup")
    def setup_view() -> SetupView:
        now = current()
        steps = setup.steps(ws, now, store)
        return SetupView(
            steps=[SetupStepView(**vars(s)) for s in steps],
            finished=setup.finished(steps),
            local=local,
            walkthrough=WalkthroughView(**vars(setup.walkthrough(ws, now, steps))),
        )

    @r.post("/setup/walkthrough")
    def walkthrough_keep(body: WalkthroughIn) -> WalkthroughView:
        """Keep where the walkthrough stands: its screen, that it was closed, or that it was finished."""
        setup.keep_walkthrough(ws, body.step, body.closed, body.finished)
        events.changed()
        now = current()
        return WalkthroughView(**vars(setup.walkthrough(ws, now, setup.steps(ws, now, store))))

    @r.post("/setup/{step:path}/apply-settings")
    def setup_apply_settings(step: str, body: FingerprintIn) -> SettingsSaved:
        found = next((s for s in setup.steps(ws, current(), store) if s.id == step), None)
        if found is None or not found.settings:
            raise HTTPException(status_code=404, detail="That step suggests no settings.")
        barred = [k for k in found.settings if k.startswith(NEVER_SUGGESTED)]
        if barred:
            log.warning("A setup step suggested settings it may not: %s", ", ".join(barred))
            raise HTTPException(
                status_code=400,
                detail="An add-on can't suggest where keys come from, which accounts get the work, or the server's "
                "own settings.",
            )
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
        before = list(current().workspace.plugins.enabled)
        try:
            plugins = templates.apply(ws, body.id)
        except (templates.TemplateError, ConfigError) as err:
            log.warning("A template couldn't be applied: %s", err)
            raise HTTPException(status_code=400, detail=err.plain) from None
        with store.transaction() as tx:
            audit.plugin_changes(tx, before, list(current().workspace.plugins.enabled))
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
        result = saved(save({"storage.backups.targets": targets}, [], body.fingerprint, allow=("storage.backups.",)))
        # The first backup is made now, in the background, so choosing where doesn't leave a request to back up.
        worker.first_backup_soon()
        return result

    # ---- AI accounts ---------------------------------------------------------------------------------------------

    @r.get("/ai/endpoints")
    def endpoints() -> list[EndpointView]:
        import shutil

        found = []
        for e in setup.known_endpoints():
            installed = (shutil.which(e["program"]) is not None) if (e["program"] and local) else None
            found.append(EndpointView(**e, installed=installed))
        return found

    # ---- watched sources ----------------------------------------------------------------------------------------

    def source_kinds() -> dict[str, Any]:
        from engine import watch

        return watch.connectors(store)

    @r.get("/watch/kinds")
    def watch_kinds() -> list[WatchKindView]:
        """The kinds of source the assistant can keep reading: the core's and running add-ons', each with the form
        its settings take. Kinds made only for tests are left out."""
        found = []
        for name, connector in sorted(source_kinds().items()):
            if connector.test_only:
                continue
            items: list = []
            defaults = _defaults(connector.settings)
            config_screens._walk(connector.settings, ["source"], defaults, defaults, {}, items)
            for item in items:
                item.key = item.key.removeprefix("source.")
                item.group = item.group.removeprefix("source.").removeprefix("source")
                item.source = "default"
            plugin = name.split("/", 1)[0] if "/" in name else None
            found.append(
                WatchKindView(
                    name=name,
                    label=connector.label,
                    plugin=plugin,
                    first_run=NEW_SOURCE_FIRST_RUN,
                    items=[SettingItem(**vars(i)) for i in items],
                )
            )
        return found

    def sources_now() -> list[dict[str, Any]]:
        return [s.model_dump(mode="json") for s in current().watch.sources]

    def checked_source(kind: str, settings: dict[str, Any]) -> dict[str, Any]:
        connector = source_kinds().get(kind)
        if connector is None:
            raise HTTPException(status_code=404, detail=f"There is no kind of source called {kind} running now.")
        try:
            return connector.settings.model_validate(settings).model_dump(mode="json", exclude_defaults=True)
        except ValueError as err:
            first = err.errors()[0] if hasattr(err, "errors") else {"loc": (), "msg": str(err)}
            raise HTTPException(
                status_code=400, detail=f"{'.'.join(map(str, first['loc'])) or 'settings'}: {first['msg']}"
            ) from None

    def checked_author(author: str) -> str:
        view = store.read()
        if view.get("person", author) is None and view.get("team", author) is None:
            raise HTTPException(status_code=400, detail="Choose a person or a team from the list.")
        return author

    def with_secrets(
        kind: str, source_id: str, settings: dict[str, Any], pasted: dict[str, str], supplied: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """The settings with a reference to each pasted secret written in, and what to keep, by file name. `supplied`
        is what the person sent as settings: a field can't be both typed and given as a reference. Nothing is written
        here: a source that fails its checks leaves what was kept before untouched."""
        if not pasted:
            return settings, {}
        if not local:
            raise HTTPException(status_code=400, detail=HOSTED_KEY)
        connector = source_kinds().get(kind)
        if connector is None:
            raise HTTPException(status_code=404, detail=f"There is no kind of source called {kind} running now.")
        allowed = config_screens.secret_fields(connector.settings)
        merged = copy.deepcopy(settings)
        to_keep: dict[str, str] = {}
        for field, value in pasted.items():
            if field not in allowed:
                raise HTTPException(status_code=400, detail="That isn't a setting this kind of source keeps secret.")
            if not value.strip():
                raise HTTPException(status_code=400, detail="Type or paste it, or give where it is kept instead.")
            if _nested(supplied, field):
                raise HTTPException(status_code=400, detail="Type it or give where it is kept, not both.")
            name = setup.unused_secret_name(ws, setup.secret_name("source", source_id, field))
            _put(merged, field, setup.secret_reference(ws, name))
            to_keep[name] = value
        return merged, to_keep

    def keep_all(to_keep: dict[str, str]) -> list[Path]:
        """Keep each pasted secret; returns the files that didn't exist before, to remove if the save is refused."""
        fresh = [setup.secret_path(ws, name) for name in to_keep if not setup.secret_path(ws, name).exists()]
        try:
            for name, value in to_keep.items():
                setup.keep_secret(ws, name, value)
        except StoreError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        return fresh

    @r.post("/watch/sources")
    def watch_add(body: WatchSourceIn) -> SettingsSaved:
        """Start reading a new source, with Undo. Its id comes from its label."""
        sources = sources_now()
        base = re.sub(r"[^a-z0-9]+", "-", (body.label or body.connector).lower()).strip("-")[:40] or "source"
        taken = {s["id"] for s in sources}
        source_id = base
        if base in taken:
            source_id = next(f"{base}-{n}" for n in range(2, 999) if f"{base}-{n}" not in taken)
        given, to_keep = with_secrets(body.connector, source_id, body.settings, body.secrets, body.settings)
        settings = checked_source(body.connector, given)
        new = {
            "id": source_id,
            "connector": body.connector,
            "label": body.label.strip() or source_kinds()[body.connector].label,
            "every_minutes": body.every_minutes,
            "settings": settings,
        }
        if body.project:
            new["project"] = body.project
        if body.author:
            new["author"] = checked_author(body.author)
        fresh = keep_all(to_keep)
        try:
            done = saved(save({"watch.sources": [*sources, new]}, [], body.fingerprint, allow=("watch.sources",)))
        except HTTPException:
            for path in fresh:
                path.unlink(missing_ok=True)
            raise
        worker.read_sources_now()  # its first read happens now, not at the next minute's check
        return done

    @r.post("/watch/sources/{source_id}")
    def watch_change(source_id: str, body: WatchSourceChange) -> SettingsSaved:
        """Change a source's name, how often it is read, whether it is read, or its settings, with Undo."""
        sources = sources_now()
        found = next((s for s in sources if s["id"] == source_id), None)
        if found is None:
            raise HTTPException(status_code=404, detail=f"There is no source {source_id}.")
        base = found["settings"] if body.settings is None else body.settings
        given, to_keep = with_secrets(found["connector"], source_id, base, body.secrets, body.settings or {})
        if body.settings is not None or body.secrets:
            found["settings"] = checked_source(found["connector"], given)
        for key in ("label", "every_minutes", "enabled"):
            value = getattr(body, key)
            if value is not None:
                found[key] = value
        if "author" in body.model_fields_set:
            found["author"] = checked_author(body.author) if body.author else None
        fresh = keep_all(to_keep)
        try:
            return saved(save({"watch.sources": sources}, [], body.fingerprint, allow=("watch.sources",)))
        except HTTPException:
            for path in fresh:
                path.unlink(missing_ok=True)
            raise

    @r.post("/watch/sources/{source_id}/remove")
    def watch_remove(source_id: str, body: FingerprintIn) -> SettingsSaved:
        """Stop reading a source and take it off the list, with Undo; what it already handed in stays."""
        sources = sources_now()
        if not any(s["id"] == source_id for s in sources):
            raise HTTPException(status_code=404, detail=f"There is no source {source_id}.")
        rest = [s for s in sources if s["id"] != source_id]
        return saved(save({"watch.sources": rest}, [], body.fingerprint, allow=("watch.sources",)))

    # ---- sorting mail: the person's own rules, and confirming set-aside mail ----------------------------------

    def triage_now() -> list[dict[str, Any]]:
        return [r.model_dump(mode="json", exclude_defaults=True) for r in current().watch.triage]

    @r.post("/watch/sorting")
    def sorting_rule(body: SortingRuleIn) -> SettingsSaved:
        """Always set aside mail from these senders and domains as personal or sales, or never set it aside, as the
        person's own rule, with Undo. Keeping mail goes first in the list; the rule applies to the next mail."""
        if not body.senders and not body.domains:
            raise HTTPException(status_code=400, detail="Name a sender or a domain.")
        public = next((d for d in body.domains if set_aside_mail.is_public_domain(d, current())), None)
        if public is not None:
            raise HTTPException(
                status_code=400,
                detail=f"{public} is a mail service anyone can have an address at, so a rule for all of it would set "
                "aside mail from people you know. Choose the sender instead.",
            )
        rules = sorting.with_sender_rules(triage_now(), body.choice, body.senders, body.domains)
        return saved(save({"watch.triage": rules}, [], body.fingerprint, allow=("watch.triage",)))

    @r.post("/set-aside/confirm")
    def set_aside_confirm(body: ConfirmIn) -> ConfirmDone:
        """Confirm set-aside mail was rightly set aside: a sender rule is written for each distinct sender, and the
        messages leave the folder and are deleted from the app after their undo time."""
        snaps = [store.read().get("snapshot", i) for i in body.ids]
        if any(sn is None or not sn.data.get("set_aside") or sn.data.get("deleted") for sn in snaps):
            raise HTTPException(status_code=404, detail="One of those isn't set aside.")
        by_section: dict[str, list[str]] = {}
        for sn in snaps:
            address = set_aside_mail.address_of(sn, ws)
            if address and address not in by_section.setdefault(sn.data["set_aside"]["section"], []):
                by_section[sn.data["set_aside"]["section"]].append(address)
        rules = triage_now()
        for section, senders in by_section.items():
            rules = sorting.with_sender_rules(rules, section, senders, [])
        done = saved(
            save(
                {"watch.triage": rules} if any(by_section.values()) else {},
                [],
                body.fingerprint,
                allow=("watch.triage",),
            )
        )
        try:
            confirmed = set_aside_mail.confirm_items(store, body.ids)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        set_aside_mail.purge_due(ws, store, current())
        events.changed()
        sections = {section for section, senders in by_section.items() if senders} or {
            sn.data["set_aside"]["section"] for sn in snaps
        }
        offers = []
        for section, senders in by_section.items():
            domains: dict[str, int] = {}
            for address in senders:
                domain = set_aside_mail.offerable_domain(address, current())
                if domain:
                    domains[domain] = domains.get(domain, 0) + 1
            offers += [
                DomainOffer(domain=d, senders=n, section=section) for d, n in domains.items() if n >= DOMAIN_OFFER_AT
            ]
        return ConfirmDone(
            saved=done,
            confirmed=len(confirmed),
            senders=[a for senders in by_section.values() for a in senders],
            section=next(iter(sections)) if len(sections) == 1 else None,
            domain_offers=offers,
            ids=body.ids,
        )

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
        done = saved(save(changes, [], body.fingerprint, allow=("workspace.plugins.enabled",)))
        setup.decide_addons(ws, [name])
        return done

    @r.post("/packs/{name}/off")
    def pack_off(name: str, body: FingerprintIn) -> SettingsSaved:
        """Turn an add-on off, with Undo: it stops after the restart the person chooses; its records and settings
        stay."""
        enabled = list(current().workspace.plugins.enabled)
        setup.decide_addons(ws, [name])
        if name not in enabled:
            # Off already: leaving it off is the person's choice, so the setup step stops asking about it.
            return SettingsSaved(changes=[], fingerprint=body.fingerprint, needs_restart=False)
        changes = {"workspace.plugins.enabled": [n for n in enabled if n != name]}
        return saved(save(changes, [], body.fingerprint, allow=("workspace.plugins.enabled",)))

    # ---- catalogs and the read tokens for private release files ---------------------------------------------------

    @r.post("/packs/catalogs")
    def catalog_add(body: CatalogAddress) -> SettingsSaved:
        """List another catalog of add-ons, by its address, with Undo. It is read when the screen asks to refresh."""
        address = body.address.strip()
        parts = urlsplit(address)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or " " in address:
            raise HTTPException(
                status_code=400, detail="Give the catalog's address, starting with https:// and no spaces."
            )
        listed = list(current().workspace.plugins.catalog.feeds)
        if address in listed:
            raise HTTPException(status_code=409, detail="That catalog is listed already.")
        key = "workspace.plugins.catalog.feeds"
        return saved(save({key: [*listed, address]}, [], body.fingerprint))

    @r.post("/packs/catalogs/remove")
    def catalog_remove(body: CatalogAddress) -> SettingsSaved:
        """Take a catalog the person listed off the list, with Undo. The add-ons already installed stay."""
        listed = list(current().workspace.plugins.catalog.feeds)
        if body.address not in listed:
            raise HTTPException(status_code=404, detail="That catalog isn't in the list you added.")
        key = "workspace.plugins.catalog.feeds"
        return saved(save({key: [a for a in listed if a != body.address]}, [], body.fingerprint))

    @r.post("/packs/{pack_id}/token")
    def pack_token(pack_id: str, body: PackTokenIn) -> SettingsSaved:
        """Give the read token for the place an add-on's release file is kept, with Undo. A local app keeps a typed
        token in its private folder and the settings hold only where; the token is sent only to that place."""
        if bool(body.token and body.token.strip()) == bool(body.reference and body.reference.strip()):
            raise HTTPException(status_code=400, detail="Type the token, or give where it is kept: one of the two.")
        if body.token and not local:
            raise HTTPException(status_code=400, detail=HOSTED_KEY)
        entry = entry_in(ws, current(), pack_id)
        host = urlsplit(entry.release.url).hostname if entry.release else None
        if not host:
            raise HTTPException(status_code=409, detail=f"{entry.name} has no release file that needs a token.")
        name = setup.unused_secret_name(ws, setup.secret_name("release-token", host))
        fresh = body.token is not None
        try:
            reference = setup.keep_secret(ws, name, body.token) if body.token else asked_reference(body.reference or "")
        except StoreError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        tokens = {**current().workspace.plugins.catalog.release_tokens, host: reference}
        try:
            return saved(
                save(
                    {"workspace.plugins.catalog.release_tokens": tokens},
                    [],
                    body.fingerprint,
                    allow=("workspace.plugins.catalog.release_tokens",),
                )
            )
        except HTTPException:
            if fresh:
                setup.secret_path(ws, name).unlink(missing_ok=True)
            raise

    @r.post("/setup/addons/leave-off")
    def addons_leave_off() -> Ok:
        """Leave every add-on that is off now off: the setup step counts as done until another is installed."""
        setup.decide_addons(ws, setup.addons_off(ws, current()))
        return Ok(ok="addons")

    @r.get("/ai/accounts")
    def ai_accounts() -> list[AiAccountView]:
        """The AI accounts in the settings, as they are on disk now; never a key."""
        from datetime import UTC, datetime

        from engine.ai import check_cost
        from engine.ai.account_state import AccountState, account_states
        from engine.ai.catalog import Catalogs
        from engine.secrets import SecretError, describe_secret, resolve_secret
        from engine.today import zone

        ai = current().ai
        states = account_states(ws, store, current(), datetime.now(UTC))
        catalogs = Catalogs(store.path.parent / ".cockpit" / "ai-catalog.json", ai.catalog_refresh_hours)
        today = datetime.now(zone(current())).date()

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
            now_state = states.get(name, AccountState())
            found.append(
                AiAccountView(
                    name=name,
                    label=p.label,
                    kind=p.kind,
                    adapter=p.adapter,
                    base_url=p.base_url,
                    models=dict(p.models),
                    used_for=[t for t, tier in ai.tiers.items() if (tier.use or "").split("/", 1)[0] == name],
                    backup_for=[
                        t for t, tier in ai.tiers.items() if any(f.split("/", 1)[0] == name for f in tier.fallback)
                    ],
                    has_key=bool(p.auth),
                    key_state=state,
                    key_where=where,
                    credential_expires=p.credential_expires,
                    key_ending=p.credential_expires is not None
                    and (p.credential_expires - today).days <= ai.credential_warn_days,
                    answered_at=now_state.answered_at,
                    spent_today_usd=now_state.spent_today_usd,
                    checked_for=now_state.checked_for,
                    check_failed_for=now_state.check_failed_for,
                    checked_at=now_state.checked_at,
                    paused_until=now_state.paused_until,
                    check_usd=check_cost.cost(current(), name, catalogs),
                )
            )
        return found

    @r.get("/ai/check-size")
    def ai_check_size() -> AiCheckSize:
        """What one account's connection check involves (calls and tokens), so a screen can price it with the price of
        the model the person picks."""
        from engine.ai import check_cost

        found = check_cost.size(current())
        return AiCheckSize(calls=found.calls, input_tokens=found.input_tokens, output_tokens=found.output_tokens)

    @r.get("/ai/skills")
    def ai_skills() -> AiSkillsView:
        """What each account's models can do, from the evaluation runs kept in this workspace: per model and skill the
        pass rate, the runs, the age of the last one, the cost of a passing run and whether it is stale or under the
        minimum score (design 6.16). A skill nobody measured is listed as not measured."""
        from datetime import UTC, datetime

        from engine.ai import matrix, measure
        from engine.ai.adapters import make_adapter
        from engine.shipped import DEMOS, demo

        now = current()
        today = datetime.now(UTC).date()
        asked = measure.read(ws)
        sets: dict[str, dict[str, str]] = {}
        for name in DEMOS:
            sets |= matrix.case_sets(demo(name), ws.root)
        accounts = []
        for name, provider in now.ai.providers.items():
            version = matrix.current_program_version(now, name, make_adapter)
            models = []
            for short, model_id in provider.models.items():
                held = matrix.standing(
                    ws, now, f"{name}/{model_id}", program_version=version, current_sets=sets, today=today
                )
                asked_now = asked.get(f"{name}/{short}") or {}
                models.append(
                    AiModelSkills(
                        model=short,
                        measure=asked_now.get("state"),
                        measure_why=MEASURE_WHY.get(asked_now.get("why") or ""),
                        skills=[
                            AiSkillView(
                                id=s.skill.id,
                                label=s.skill.label,
                                description=s.skill.description,
                                measured=s.measured,
                                runs=s.runs,
                                passes=s.passes,
                                pass_rate=s.pass_rate,
                                age_days=s.age_days(today),
                                cost_per_pass_usd=s.cost_per_pass_usd,
                                stale=s.stale,
                                below_min=s.below_min,
                            )
                            for s in held
                        ],
                    )
                )
            accounts.append(AiAccountSkills(name=name, models=models))
        return AiSkillsView(min_score=now.ai.skills.min_score, stale_days=now.ai.skills.stale_days, accounts=accounts)

    measure_estimates: dict[tuple[Any, ...], Any] = {}

    def measure_plan(name: str, model: str | None) -> tuple[Config, Any]:
        """What measuring an account would run and cost. Pricing builds a few packets, so the answer is kept for as
        long as the accounts file, the account and the number of runs stay."""
        from engine.ai import measure

        now = current()
        key = ((ws.config_dir / "ai.yaml").read_text(encoding="utf-8"), name, model, now.ai.evaluation.runs)
        if key not in measure_estimates:
            try:
                measure_estimates[key] = measure.estimate(now, ws, name, model)
            except measure.MeasureError as err:
                raise HTTPException(status_code=404, detail=str(err)) from None
            if len(measure_estimates) > 50:
                measure_estimates.pop(next(iter(measure_estimates)))
        return now, measure_estimates[key]

    def measure_view(now: Config, plan: Any) -> AiMeasureEstimate:
        from engine.ai import measure

        return AiMeasureEstimate(
            models=plan.models,
            level=plan.level,
            cases=plan.cases,
            skipped=plan.skipped,
            runs=plan.runs,
            usd=plan.usd,
            confirm_above_usd=now.ai.budgets.confirm_above_usd,
            needs_go=measure.needs_go(now, plan),
        )

    @r.post("/ai/skills/{account}/estimate")
    def ai_measure_estimate(account: str, body: AiMeasureIn | None = None) -> AiMeasureEstimate:
        """What measuring this account would cost: its models (or the one named) on the golden cases, the add-ons'
        cases and the learning pairs, only those whose material the account is allowed to see, each as many times as
        the configured number of runs. Nothing is run or spent."""
        now, plan = measure_plan(account, body.model if body else None)
        return measure_view(now, plan)

    @r.post("/ai/skills/{account}/measure")
    def ai_measure(account: str, body: AiMeasureIn | None = None) -> AiMeasureStarted:
        """Measure this account in the background, filling what it can do (`GET /api/ai/skills`). A cost above the
        amount the person asked to be asked about is refused unless `confirmed` is sent; an account that may see none
        of the cases has nothing to measure."""
        from engine.ai import measure

        body = body or AiMeasureIn()
        now, plan = measure_plan(account, body.model)
        if not plan.cases:
            raise HTTPException(
                status_code=409,
                detail="Nothing to measure: this account isn't allowed to see the material of any case.",
            )
        if measure.needs_go(now, plan) and not body.confirmed:
            cost = "its cost can't be estimated" if plan.usd is None else f"it would cost about ${plan.usd:.2f}"
            raise HTTPException(
                status_code=409,
                detail=f"Testing needs your confirmation first: {cost}, and you asked to be asked about that.",
            )
        refs = [f"{account}/{short}" for short in plan.models]
        already = measure.begin(ws, refs)
        worker.measure_soon()
        events.changed()
        return AiMeasureStarted(
            started=[r.partition("/")[2] for r in refs if r not in already],
            already=[r.partition("/")[2] for r in already],
            estimate=measure_view(now, plan),
        )

    @r.post("/ai/accounts/{name}/test")
    def ai_account_test(name: str, tier: str | None = None, model: str | None = None) -> list[AiTestResult]:
        """Test one account, whether or not any kind of work uses it yet: on the model named, else its first. With a
        tier, the test uses that tier's kinds of work and their exact parameters, which is what lets the account be
        added to that tier's fallbacks."""
        from engine.ai.checked import remember
        from engine.ai.smoke import account_test, lift_pauses

        try:
            now = load_config(ws.config_dir)
        except ConfigError as err:
            log.warning("The settings couldn't be loaded: %s", err)
            raise HTTPException(status_code=400, detail=err.plain) from None
        if name not in now.ai.providers:
            raise HTTPException(status_code=404, detail=f"There is no account called {name}.")
        results = account_test(now, os.environ, name, tier=tier, model=model, store=store)
        remember(ws, now, results)
        lift_pauses(ws, results)
        line = AiTestResult(tier="account", account=name, main=True, ok=True, detail="answered")
        for x in results:
            if not x.ok and line.ok:
                line.ok, line.detail = False, x.detail
        return [line]

    switch_estimates: dict[tuple[Any, ...], tuple[float | None, int]] = {}

    def account_plan(name: str, body: AiAccountChange) -> tuple[dict[str, Any], list[str], tuple[str, str] | None]:
        """The settings an account change writes and resets, refusing what can't be done, and the pasted key still
        to keep (its name and value): nothing is written here."""
        provider = current().ai.providers.get(name)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"There is no account called {name}.")
        if body.key and body.key_ref:
            raise HTTPException(status_code=400, detail="Paste a key or give where it is, not both.")
        if body.key and not local:
            raise HTTPException(status_code=400, detail=HOSTED_KEY)
        changes: dict[str, Any] = {}
        pending: tuple[str, str] | None = None
        if body.key:
            try:
                kept_as = setup.key_name(ws, name)
            except StoreError as err:
                raise HTTPException(status_code=400, detail=str(err)) from None
            changes[f"ai.providers.{name}.auth"] = setup.secret_reference(ws, kept_as)
            pending = (kept_as, body.key)
        elif body.key_ref:
            changes[f"ai.providers.{name}.auth"] = body.key_ref.strip()
        reset: list[str] = []
        if body.label is not None:
            if body.label.strip():
                changes[f"ai.providers.{name}.label"] = body.label.strip()
            else:
                reset.append(f"ai.providers.{name}.label")
        if body.credential_expires is not None:
            changes[f"ai.providers.{name}.credential_expires"] = body.credential_expires.isoformat()
        elif body.clear_credential_expires:
            reset.append(f"ai.providers.{name}.credential_expires")
        models = body.models if body.models is not None else dict(provider.models)
        if body.models is not None:
            if not body.models:
                raise HTTPException(status_code=400, detail="Name at least one model the account uses.")
            changes[f"ai.providers.{name}.models"] = body.models
        for tier, short in body.use.items():
            if short not in models:
                raise HTTPException(status_code=400, detail=f"{short} isn't one of this account's models.")
            changes[f"ai.tiers.{tier}.use"] = f"{name}/{short}"
        tiers = current().ai.tiers
        for tier, short in body.backup.items():
            if short not in models:
                raise HTTPException(status_code=400, detail=f"{short} isn't one of this account's models.")
            ref, settings = f"{name}/{short}", tiers.get(tier)
            if settings is None:
                raise HTTPException(status_code=400, detail=f"There is no kind of work called {tier}.")
            if settings.use == ref or ref in settings.fallback:
                raise HTTPException(status_code=400, detail=f"{name} already does that work or stands in for it.")
            chain = list(changes.get(f"ai.tiers.{tier}.fallback", settings.fallback))
            mine = [i for i, other in enumerate(chain) if other.split("/", 1)[0] == name]
            if mine:  # it already stands in with another of its models: that entry moves, keeping its place
                chain[mine[0]] = ref
                chain = [other for i, other in enumerate(chain) if i not in mine[1:]]
            else:
                chain.append(ref)
            changes[f"ai.tiers.{tier}.fallback"] = chain
        if body.stop_backup:
            for tier, settings in tiers.items():
                kept = [other for other in settings.fallback if other.split("/", 1)[0] != name]
                if kept != list(settings.fallback):
                    changes[f"ai.tiers.{tier}.fallback"] = kept
        if not changes and not reset:
            raise HTTPException(status_code=400, detail="Nothing to change.")
        return changes, reset, pending

    def change_account(name: str, body: AiAccountChange, *, check: bool) -> tuple[SettingsSaved, bool]:
        """Save an account change. When it switches a tier's account or model, the switch is kept, with a check to run
        when asked for (and the setting for checks is on); any earlier entry of that tier is superseded. Returns what
        was saved and whether a check was started."""
        from engine.ai import switch_check

        changes, reset, pending = account_plan(name, body)
        before = current()
        if pending is not None:
            setup.keep_secret(ws, *pending)
        try:
            done = save(changes, reset, body.fingerprint, allow=("ai.providers.", "ai.tiers."))
        except HTTPException:
            if pending is not None:
                setup.secret_path(ws, pending[0]).unlink(missing_ok=True)
            raise
        after = current()
        found = switch_check.switches(before, after)
        checking = check and after.dispatch.knowledge.check_on_switch
        if found:
            switch_check.begin(store, found, done.changes, check=checking)
        return saved(done), bool(found) and checking

    @r.post("/ai/accounts/{name}")
    def ai_account_change(name: str, body: AiAccountChange) -> SettingsSaved:
        """Give an account a new key, other models or other work, with Undo. A switch of a tier's account or model
        made this way is made at once, without the check."""
        return change_account(name, body, check=False)[0]

    @r.post("/ai/accounts/{name}/switch-estimate")
    def ai_switch_estimate(name: str, body: AiAccountChange) -> AiSwitchEstimate:
        """What the check that comes with this change would cost, and whether one is offered: only a change that
        switches a tier's account or model, while checks on a switch are on. Nothing is saved."""
        import tempfile
        from pathlib import Path

        from engine.ai import switch_check
        from engine.config.yaml_edit import set_key

        changes, _reset, _pending = account_plan(name, body)
        now = current()
        if not now.dispatch.knowledge.check_on_switch:
            return AiSwitchEstimate(offered=False)
        try:
            after = load_config(ws.config_dir, env=dict(os.environ), flags=dict(changes))
        except ConfigError as err:
            raise HTTPException(status_code=400, detail=err.plain) from None
        found = switch_check.switches(now, after)
        if not found:
            return AiSwitchEstimate(offered=False)
        text = (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")
        for key, value in changes.items():
            if key.startswith("ai."):
                text = set_key(text, key.split(".")[1:], value)
        runs = after.ai.evaluation.runs
        # Pricing builds a few packets, so the answer is kept for as long as the accounts file and the choices stay.
        key = (text, tuple((x.tier, x.after) for x in found), runs)
        if key not in switch_estimates:
            total: float | None = 0.0
            cases = 0
            with tempfile.TemporaryDirectory() as tmp:
                aside = Path(tmp) / "ai.yaml"
                aside.write_text(text, encoding="utf-8")
                for switch in found:
                    usd, cases = switch_check.estimate(after, ws, switch.after, ai_config=aside)
                    total = None if usd is None or total is None else total + usd
            if len(switch_estimates) > 50:
                switch_estimates.clear()
            switch_estimates[key] = (total, cases)
        usd, cases = switch_estimates[key]
        return AiSwitchEstimate(offered=True, usd=usd, cases=cases, runs=runs)

    @r.post("/ai/accounts/{name}/switch-check")
    def ai_switch_check(name: str, body: AiAccountChange) -> AiSwitched:
        """Make the change and check it: when it switches a tier's account or model, the golden cases and the add-ons'
        own cases run on the new choice in the background, and a failure comes to Today with Switch back."""
        done, started = change_account(name, body, check=True)
        if started:
            worker.check_switch_soon()
        return AiSwitched(saved=done, checking=started)

    @r.post("/ai/switch/{tier}/back")
    def ai_switch_back(tier: str, body: FingerprintIn) -> SettingsSaved:
        """Put a tier back as it was before the switch whose check didn't pass, with Undo."""
        from engine.ai import switch_check

        entry = switch_check.failed(store).get(tier)
        if entry is None:
            raise HTTPException(status_code=404, detail="There is no switch to go back on.")
        restore = entry["restore"]
        done = saved(save(restore["changes"], restore["reset"], body.fingerprint, allow=("ai.providers.", "ai.tiers.")))
        switch_check.clear(store, tier)
        events.changed()
        return done

    @r.post("/ai/switch/{tier}/keep")
    def ai_switch_keep(tier: str) -> Ok:
        """Keep a switch whose check didn't pass: the line goes."""
        from engine.ai import switch_check

        if switch_check.failed(store).get(tier) is None:
            raise HTTPException(status_code=404, detail="There is no switch to keep.")
        switch_check.clear(store, tier)
        events.changed()
        return Ok(ok=tier)

    @r.post("/requests/{request_id}/allow-data")
    def request_allow_data(request_id: str) -> DataLevelAllowed:
        """Let the account that would take a stopped request see its material's level, at once and with Undo, then
        queue the request again. Only a request stopped because no account may see its level."""
        from engine.ai.router import LEVELS
        from engine.dispatcher import retry

        req = store.read().get("request", request_id)
        if req is None:
            raise HTTPException(status_code=404, detail="There is no such request.")
        cause = req.data.get("cause") or {}
        if req.data["state"] not in ("needs_you", "failed") or cause.get("kind") != "data_level":
            raise HTTPException(status_code=409, detail="This isn't waiting for an account to be allowed more.")
        level = cause["level"]
        providers = current().ai.providers
        name = next(
            (ref.partition("/")[0] for ref in cause.get("accounts") or [] if ref.partition("/")[0] in providers), None
        )
        if name is None:
            raise HTTPException(status_code=409, detail="The account that would take this isn't set up any more.")
        have = set(providers[name].allowed_data)
        allowed = [lv for lv in LEVELS if lv in have or LEVELS.index(lv) <= LEVELS.index(level)]
        fingerprint = config_screens.fingerprint(ws.config_dir)
        if allowed == sorted(have, key=LEVELS.index):
            done = SettingsSaved(changes=[], fingerprint=fingerprint, needs_restart=False)
        else:
            done = saved(
                save({f"ai.providers.{name}.allowed_data": allowed}, [], fingerprint, allow=("ai.providers.",))
            )
        try:
            retry(store, request_id)
        except (ValueError, StoreError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        worker.poke()
        return DataLevelAllowed(request=request_id, account=name, level=level, saved=done)

    @r.post("/ai/accounts/{name}/remove")
    def ai_account_remove(name: str, body: AiAccountRemove) -> SettingsSaved:
        """Remove an account, with Undo. The work it did goes to the backup named in `take_over` (the backup's own entry
        for that kind of work becomes its main one), or, with none named, has no account until one is chosen. Its kept
        key stays on this computer, so Undo brings the account back whole."""
        ai = current().ai
        if name not in ai.providers:
            raise HTTPException(status_code=404, detail=f"There is no account called {name}.")
        if body.take_over is not None and body.take_over not in ai.providers:
            raise HTTPException(status_code=404, detail=f"There is no account called {body.take_over}.")
        reset = [f"ai.providers.{name}"]
        changes: dict[str, Any] = {}
        for tier_name, tier in ai.tiers.items():
            kept = [ref for ref in tier.fallback if ref.split("/", 1)[0] != name]
            if (tier.use or "").split("/", 1)[0] == name:
                heir = next((ref for ref in kept if ref.split("/", 1)[0] == body.take_over), None)
                if heir is None:
                    reset.append(f"ai.tiers.{tier_name}.use")
                else:
                    changes[f"ai.tiers.{tier_name}.use"] = heir
                    kept = [ref for ref in kept if ref != heir]
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
            raise HTTPException(status_code=400, detail=HOSTED_KEY)
        provider: dict[str, Any] = {
            **(kind["settings"] if kind else {}),
            **({"kind": kind["id"]} if kind else {}),
            "adapter": body.adapter,
            "models": models,
            "allowed_data": list(body.allowed_data),
        }
        if body.label and body.label.strip():
            provider["label"] = body.label.strip()
        if body.base_url:
            provider["base_url"] = body.base_url.strip()
        if body.agent is not None:
            provider["agent"] = body.agent
        kept = None
        if body.key:
            try:
                kept = setup.key_name(ws, body.name)
                provider["auth"] = setup.keep_secret(ws, kept, body.key)
            except StoreError as err:
                raise HTTPException(status_code=400, detail=str(err)) from None
        elif body.key_ref:
            provider["auth"] = body.key_ref.strip()
        if body.credential_expires is not None:
            provider["credential_expires"] = body.credential_expires.isoformat()
        first = next(iter(models))
        changes: dict[str, Any] = {f"ai.providers.{body.name}": provider}
        for tier in body.use_for:
            changes[f"ai.tiers.{tier}.use"] = f"{body.name}/{first}"
        for tier, short in body.use.items():
            if short not in models:
                raise HTTPException(status_code=400, detail=f"{short} isn't one of this account's models.")
            changes[f"ai.tiers.{tier}.use"] = f"{body.name}/{short}"
        # Unless the person said what it is for, a real account takes over every tier still on the stand-in, so the
        # assistant does real work once one is added; tiers on another real account stay where the person put them.
        now = current().ai
        for tier_name, tier in now.tiers.items() if not (body.use_for or body.use) else ():
            key = f"ai.tiers.{tier_name}.use"
            on = now.providers.get(tier.use.split("/", 1)[0])
            if key not in changes and on is not None and on.adapter == "stub":
                changes[key] = f"{body.name}/{first}"
        try:
            result = save(changes, [], body.fingerprint, allow=("ai.providers.", "ai.tiers."))
        except HTTPException:
            if kept is not None:
                setup.secret_path(ws, kept).unlink(missing_ok=True)
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
            raise HTTPException(status_code=400, detail=HOSTED_KEY)
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

    @r.post("/ai/borrow")
    def ai_borrow(body: AiBorrowAnswer) -> AiBorrowed:
        """Answer the question of using another kind of work's account until the paused account's limit resets. A yes
        lets the waiting work run on that account at once and lasts until the reset; a no keeps it waiting."""
        from engine.ai.borrow import BorrowError, answer

        try:
            released = answer(ws, store, current(), body.tier, f"{body.account}/{body.model}", body.use, worker.now())
        except BorrowError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        if released:
            worker.poke()
        events.changed()
        return AiBorrowed(released=released)

    @r.post("/ai/test")
    def ai_test() -> list[AiTestResult]:
        from engine.ai.checked import remember
        from engine.ai.smoke import lift_pauses, record, smoke_test

        try:
            current = load_config(ws.config_dir)
        except ConfigError as err:
            log.warning("The settings couldn't be loaded: %s", err)
            raise HTTPException(status_code=400, detail=err.plain) from None
        results = smoke_test(current, os.environ, store=store)
        record(ws, results)
        remember(ws, current, results)
        lift_pauses(ws, results)
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
