"""API routes for watched sources (design 6.4): what the assistant keeps reading, how the last read went, and
reading one now."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    AutoClosedView,
    Created,
    ReadVersion,
    SetAsideDone,
    SetAsideFolder,
    SetAsideIn,
    SetAsideView,
    UnconfirmIn,
    WatchRunView,
    WatchSourceView,
)
from engine import set_aside, watch
from engine.config import Config
from engine.connectors import declared_reads, reads
from engine.storage import Store, StoreError, WriteContext
from engine.worker import Events, Worker
from engine.workspace import Workspace

LISTED = 50


def build_watch_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def view(source: object) -> WatchSourceView:
        known = watch.connectors(store)
        connector = known.get(source.connector)
        last = watch.last_run(store, source.id)
        read = watch.last_read(store, source.id)
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
            reads=reads(source.connector, declared_reads(known)),
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
            read_at=str(read.data["started_at"]) if read else None,
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
        _show_again(request_id)
        events.changed()
        worker.poke()
        return Created(id=request_id)

    def _show_again(request_id: str) -> None:
        """A mail item handed in after all shows in Today's list of what came in again."""
        with store.transaction() as tx:
            request = tx.get("request", request_id)
            source = tx.get("source", request.data["source"]) if request and request.data.get("source") else None
            watched = (source.data.get("watched") if source else None) or {}
            for snap in tx.find("snapshot", {"source": watched.get("source", ""), "key": watched.get("key", "")}):
                if snap.data.get("closed_by"):
                    tx.update(
                        "snapshot",
                        snap.id,
                        {"closed_by": None},
                        WriteContext("pm", "trusted", "triage.closer_look"),
                        read_version=snap.version,
                    )

    # ---- mail set aside as not work ---------------------------------------------------------------------------

    def folder_view() -> SetAsideFolder:
        set_aside.purge_due(ws, store, cfg)
        return SetAsideFolder(
            items=[SetAsideView(**row) for row in set_aside.folder(ws, store, cfg)],
            deleted=set_aside.deleted_count(store),
        )

    @r.get("/set-aside")
    def set_aside_folder() -> SetAsideFolder:
        """The Set aside folder: mail kept away from the assistant, in two sections, newest first."""
        return folder_view()

    def mail_snapshot(snapshot_id: str):
        found = store.read().get("snapshot", snapshot_id)
        if found is None or not found.data.get("message") or found.data.get("deleted"):
            raise HTTPException(status_code=404, detail="That isn't a message the app is holding.")
        return found

    def done(snapshot_id: str, section: str) -> SetAsideDone:
        snap = store.read().get("snapshot", snapshot_id)
        address = set_aside.address_of(snap, ws)
        return SetAsideDone(
            id=snapshot_id,
            version=snap.version,
            section=section,
            address=address,
            domain=set_aside.domain_of(address),
        )

    @r.post("/mail/{snapshot_id}/set-aside")
    def set_aside_mail(snapshot_id: str, body: SetAsideIn) -> SetAsideDone:
        """Move a mail item to the Set aside folder, as personal or sales mail, and close its request if one is
        waiting for the assistant."""
        from engine.dispatcher import signal

        mail_snapshot(snapshot_id)
        try:
            closed = set_aside.set_aside_item(store, snapshot_id, body.section)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        result = done(snapshot_id, body.section)
        note = body.section + (", with a sorting rule offered for the sender" if result.address else "")
        signal(store, "set_aside", closed or [snapshot_id], note)
        events.changed()
        return result

    @r.post("/set-aside/{snapshot_id}/work")
    def set_aside_is_work(snapshot_id: str, body: ReadVersion) -> SetAsideDone:
        """This is work: hand the message in after all, as Take a closer look does, and keep the correction."""
        from engine.dispatcher import signal

        snap = mail_snapshot(snapshot_id)
        mark = snap.data.get("set_aside")
        if not mark:
            raise HTTPException(status_code=404, detail="That isn't set aside.")
        if snap.version != body.read_version:
            raise HTTPException(status_code=409, detail="That message changed. Look at the folder again.")
        try:
            waiting = set_aside.put_back(ws, store, cfg, snapshot_id, hand_in=True)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        signal(store, "pulled_back", [waiting or snapshot_id], f"Set aside: {mark['reason']}")
        events.changed()
        worker.poke()
        return done(snapshot_id, mark["section"])

    @r.post("/set-aside/{snapshot_id}/put-back")
    def set_aside_put_back(snapshot_id: str, body: ReadVersion) -> SetAsideDone:
        """Undo a set-aside the person made by hand: the message and its request go back as they were."""
        snap = mail_snapshot(snapshot_id)
        if snap.version != body.read_version:
            raise HTTPException(status_code=409, detail="That message changed. Look at it again.")
        mark = snap.data.get("set_aside") or {}
        try:
            set_aside.put_back(ws, store, cfg, snapshot_id, hand_in=False)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        worker.poke()
        return done(snapshot_id, mark.get("section", "sales"))

    @r.post("/set-aside/unconfirm")
    def set_aside_unconfirm(body: UnconfirmIn) -> Created:
        """Undo a confirmation within its undo time: the messages are back in the folder."""
        try:
            set_aside.unconfirm_items(store, body.ids)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        return Created(id=body.ids[0])

    return r
