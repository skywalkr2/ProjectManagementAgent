"""API routes for watched sources (design 6.4): what the assistant keeps reading, how the last read went, and
reading one now."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import AutoClosedView, Created, ReadVersion, WatchRunView, WatchSourceView
from engine import watch
from engine.config import Config
from engine.storage import Store, StoreError, WriteContext
from engine.worker import Events, Worker
from engine.workspace import Workspace

LISTED = 50


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
                retry_at=str(last.data["retry_at"]) if last.data.get("retry_at") else None,
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

    @r.get("/auto-closed")
    def auto_closed() -> list[AutoClosedView]:
        view = store.read()
        labels = {s.id: s.label or s.id for s in cfg.watch.sources}
        closed = [q for q in view.list("request") if q.data.get("auto_closed")]
        closed.sort(key=lambda q: str(q.data["created_at"]), reverse=True)
        out = []
        for q in closed[:LISTED]:
            source = view.get("source", q.data["source"]) if q.data.get("source") else None
            watched = (source.data.get("watched") if source else None) or {}
            out.append(
                AutoClosedView(
                    id=q.id,
                    version=q.version,
                    title=source.data["title"] if source else q.id,
                    source=labels.get(watched.get("source", ""), watched.get("source", "")),
                    change=watched.get("change", "new"),
                    rule=q.data["auto_closed"]["rule"],
                    reason=q.data["auto_closed"]["reason"],
                    created_at=str(q.data["created_at"]),
                )
            )
        return out

    @r.post("/watch/{source_id}/recent")
    def recent(source_id: str) -> WatchSourceView:
        """Hand the assistant what the source holds from the recent past or near future that it hasn't seen yet (the
        last day's mail, today's meetings), after a first read that only noted what was there."""
        source = next((s for s in cfg.watch.sources if s.id == source_id), None)
        if source is None:
            raise HTTPException(status_code=404, detail=f"there is no source {source_id}")
        try:
            made = watch.hand_in_recent(ws, store, cfg, source_id)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        if made:
            worker.poke()
        return view(source)

    @r.post("/requests/{request_id}/closer-look")
    def closer_look(request_id: str, body: ReadVersion) -> Created:
        """Hand in a change a triage rule closed after all; the correction is kept so rules can be tuned."""
        from engine.dispatcher import signal

        current = store.read().get("request", request_id)
        if current is None or not current.data.get("auto_closed"):
            raise HTTPException(status_code=404, detail="That isn't something a rule closed.")
        try:
            with store.transaction() as tx:
                tx.update(
                    "request",
                    request_id,
                    {"state": "queued", "waiting": "With the assistant, starting now", "auto_closed": None},
                    WriteContext("pm", "trusted", "triage.closer_look"),
                    read_version=body.read_version,
                )
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        rule = current.data["auto_closed"]["rule"]
        signal(store, "pulled_back", [request_id], f"Closed by {rule}: {current.data['auto_closed']['reason']}")
        events.changed()
        worker.poke()
        return Created(id=request_id)

    return r
