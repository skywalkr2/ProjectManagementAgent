"""API routes for the Add-ons screen (design 3.11): the packs catalog feeds list, with what each adds, reaches and
keeps and what its AI work costs here, and the plugins this install has."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException

from api.schemas import InstalledPackView, PackFeedView, PackInstalled, PackSummary, PacksView, PackView
from engine import packs
from engine.config import Config, ConfigError, load_config
from engine.plugin_api import PLUGIN_API_VERSION
from engine.plugin_manifest import declared_plugins
from engine.shipped import product
from engine.storage import Store
from engine.worker import Worker
from engine.workspace import Workspace


def _sentence(text: str) -> str:
    """A refusal as a sentence: capitalized, with its full stop."""
    text = text.strip()
    return (text[:1].upper() + text[1:]).rstrip(".") + "."


def _saved(ws: Workspace, cfg: Config) -> Config:
    """The settings as the files hold them now: an add-on turned off since the start is off here, though it runs until
    the restart."""
    try:
        return load_config(ws.config_dir, env=dict(os.environ))
    except ConfigError:
        return cfg


def build_pack_router(ws: Workspace, cfg: Config, store: Store, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")
    host = store.plugins

    def costs(entry: packs.Entry) -> list[dict]:
        from engine.ai.router import Router

        router = Router(cfg, store, env=os.environ)
        found = []
        for job in entry.ai_jobs:
            try:
                found.append(packs.job_cost(cfg, router, job))
            except Exception:  # noqa: BLE001 - a price that can't be looked up shows the job's size alone
                found.append(
                    {"label": job.label, "tokens": job.input_tokens + job.output_tokens, "usd": None, "account": True}
                )
        return found

    def view(refresh: bool) -> PacksView:
        from importlib.metadata import entry_points

        from engine import pack_install

        # Which add-ons the app installed from this screen (and so can take away again), by the name they run under.
        mine = {
            ep.name
            for ep in entry_points(group="pm_cockpit.plugins")
            if ep.dist is not None and pack_install.installed_here(ep.dist.name)
        }
        settings = cfg.workspace.plugins.catalog
        feeds = packs.read_feeds(
            packs.feed_urls(cfg, product()), ws.private_dir, settings.refresh_hours, refresh=refresh
        )
        # As saved now: an add-on just turned on shows as on (it starts after the restart the person chooses).
        try:
            enabled = set(load_config(ws.config_dir, env=dict(os.environ)).workspace.plugins.enabled)
        except ConfigError:
            enabled = set(cfg.workspace.plugins.enabled)
        on_disk = {m.name: m for m in declared_plugins(ws.config_dir, None)}
        available = []
        for feed in feeds:
            for entry in feed.entries:
                manifest = host.manifests.get(entry.id) or on_disk.get(entry.id)
                available.append(
                    PackView(
                        id=entry.id,
                        name=entry.name,
                        summary=entry.summary,
                        publisher=entry.publisher,
                        maintainers=entry.maintainers,
                        updated=entry.updated,
                        version=entry.version,
                        price=entry.price.model_dump(),
                        homepage=entry.homepage,
                        homepage_domain=urlsplit(entry.homepage).hostname if entry.homepage else None,
                        install=entry.install,
                        demo=entry.demo,
                        compatible=packs.compatible(entry, PLUGIN_API_VERSION),
                        installed_version=manifest.version if manifest else None,
                        enabled=entry.id in enabled,
                        what=PackSummary(**packs.summary(entry.provides, entry.requires)),
                        installable=entry.release is not None and cfg.server.mode == "local",
                        removable=entry.id in mine,
                        costs=costs(entry),
                        feed=urlsplit(feed.url).hostname or "",
                    )
                )
        installed = [
            InstalledPackView(
                name=name,
                version=manifest.version,
                description=manifest.description,
                enabled=name in enabled,
                state=host.status[name].state if name in host.status else "off",
                reason=host.status[name].reason if name in host.status else None,
                what=PackSummary(**packs.manifest_summary(manifest)),
                removable=name in mine,
            )
            for name, manifest in sorted({**on_disk, **host.manifests}.items())
        ]
        return PacksView(
            enabled=settings.enabled,
            feeds=[
                PackFeedView(
                    domain=urlsplit(f.url).hostname or "",
                    error=f.error,
                    notes=f.notes,
                    read_at=datetime.fromtimestamp(f.read_at, UTC).isoformat() if f.read_at else None,
                )
                for f in feeds
            ],
            available=available,
            installed=installed,
        )

    def entry_for(pack_id: str) -> packs.Entry:
        settings = cfg.workspace.plugins.catalog
        feeds = packs.read_feeds(packs.feed_urls(cfg, product()), ws.private_dir, settings.refresh_hours)
        for feed in feeds:
            for entry in feed.entries:
                if entry.id == pack_id:
                    return entry
        raise HTTPException(status_code=404, detail=f"No catalog lists an add-on called {pack_id}.")

    @r.post("/packs/{pack_id}/install")
    def install(pack_id: str) -> PackInstalled:
        """Install (or update) an add-on from the release file its catalog entry names, checked against the entry's
        checksum. It isn't turned on; it is used after the restart the person chooses."""
        from engine import pack_install
        from engine.secrets import SecretError, resolve_secret

        if cfg.server.mode != "local":
            raise HTTPException(status_code=400, detail="A hosted app's add-ons are installed with its deployment.")
        entry = entry_for(pack_id)
        if entry.release is None:
            raise HTTPException(
                status_code=409, detail=f"{entry.name} has no release the app can install: {entry.install}"
            )
        host_name = urlsplit(entry.release.url).hostname or ""
        ref = cfg.workspace.plugins.catalog.release_tokens.get(host_name)
        try:
            token = resolve_secret(ref) if ref else None
            data = pack_install.download(entry.release.url, entry.release.sha256, token)
            done = pack_install.install(data)
        except SecretError:
            raise HTTPException(
                status_code=409,
                detail=f"The read token for {host_name} isn't available, so the release file can't be read.",
            ) from None
        except pack_install.InstallError as err:
            raise HTTPException(status_code=409, detail=_sentence(str(err))) from None
        if host.active(pack_id):
            # A running add-on was updated: work waits for the restart rather than mix old and new files.
            worker.add_ons_changed()
        return PackInstalled(name=done.name, version=done.version, needs_restart=True)

    @r.post("/packs/{pack_id}/uninstall")
    def uninstall(pack_id: str) -> PackInstalled:
        """Remove an add-on installed from this screen. Its records and settings stay; turn it off first."""
        from importlib.metadata import entry_points

        from engine import pack_install

        if pack_id in set(_saved(ws, cfg).workspace.plugins.enabled):
            raise HTTPException(status_code=409, detail="Turn it off first, then remove it.")
        # Turned off but still running until the restart: its files go now, so work waits for that restart.
        running = host.active(pack_id)
        found = next((ep for ep in entry_points(group="pm_cockpit.plugins") if ep.name == pack_id), None)
        if found is None or found.dist is None:
            raise HTTPException(status_code=404, detail=f"{pack_id} isn't installed as a package.")
        # Read before the files go: the package's metadata is among them.
        name, version = found.dist.name, found.dist.version
        try:
            pack_install.remove(name)
        except pack_install.InstallError as err:
            raise HTTPException(status_code=409, detail=_sentence(str(err))) from None
        if running:
            worker.add_ons_changed()
        return PackInstalled(name=name, version=version, needs_restart=True)

    @r.get("/packs")
    def listed() -> PacksView:
        return view(refresh=False)

    @r.post("/packs/refresh")
    def refreshed() -> PacksView:
        return view(refresh=True)

    return r
