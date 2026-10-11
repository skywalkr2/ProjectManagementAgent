"""API routes for watched sources (design 6.4): what the assistant keeps reading, how the last read went, and
reading one now."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import WatchRunView, WatchSourceView
from engine import watch
from engine.config import Config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_watch_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def view(source: object) -> WatchSourceView:
        connector = watch.connectors(store).get(source.connector)
        last = watch.last_run(store, source.id)
        failures = watch.failures_in_a_row(store, source.id)
        items = [s for s in store.read().find("snapshot", {"source": source.id}) if not s.data["gone"]]
        problem = None
        if last is not None and last.data["outcome"] == "failed":
            kind = last.data.get("error_kind") or ""
            problem = f"{last.data.get('error') or kind}. {watch.WHAT_TO_DO.get(kind, '')}".strip()
        return WatchSourceView(
            id=source.id,
            label=source.label or source.id,
            connector=source.connector,
            connector_label=connector.label if connector else "",
            enabled=source.enabled,
            every_minutes=source.every_minutes,
            items=len(items),
            last=WatchRunView(
                **{k: last.data.get(k) for k in ("outcome", "error_kind", "error", "new", "changed", "removed")},
                started_at=str(last.data["started_at"]),
            )
            if last
            else None,
            failures=failures,
            problem=problem,
        )

    @r.get("/watch")
    def sources() -> list[WatchSourceView]:
        return [view(source) for source in cfg.watch.sources]

    @r.post("/watch/{source_id}/read")
    def read_now(source_id: str) -> WatchSourceView:
        source = next((s for s in cfg.watch.sources if s.id == source_id), None)
        if source is None:
            raise HTTPException(status_code=404, detail=f"there is no source {source_id}")
        try:
            result = watch.refresh(ws, store, cfg, source_id)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        if result.new or result.changed or result.removed:
            worker.poke()
        return view(source)

    return r
