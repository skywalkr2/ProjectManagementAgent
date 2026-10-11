"""API routes for the Add-ons screen (design 3.11): the packs catalog feeds list, with what each adds, reaches and
keeps and what its AI work costs here, and the plugins this install has."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter

from api.schemas import InstalledPackView, PackFeedView, PackSummary, PacksView, PackView
from engine import packs
from engine.config import Config
from engine.plugin_api import PLUGIN_API_VERSION
from engine.plugin_manifest import declared_plugins
from engine.shipped import product
from engine.storage import Store
from engine.workspace import Workspace


def build_pack_router(ws: Workspace, cfg: Config, store: Store) -> APIRouter:
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
        settings = cfg.workspace.plugins.catalog
        feeds = packs.read_feeds(
            packs.feed_urls(cfg, product()), ws.private_dir, settings.refresh_hours, refresh=refresh
        )
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

    @r.get("/packs")
    def listed() -> PacksView:
        return view(refresh=False)

    @r.post("/packs/refresh")
    def refreshed() -> PacksView:
        return view(refresh=True)

    return r
