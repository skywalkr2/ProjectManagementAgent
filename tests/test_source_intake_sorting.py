"""The assistant's sorting of mail is part of a new source's intake (design 6.5, 6.32): it is priced into the one
total, it waits for the intake's go with the rest, and when the go is given it runs first, so mail it sets aside
never starts."""

import json

from engine import source_intake
from engine.ai.adapters.stub import set_responder
from engine.today_queue import queue
from tests.test_mail_sorting import CLUB, NOW, mail, make, rows_of, sort_runs, unplaced


def test_the_intakes_go_sorts_its_mail_first_so_what_is_set_aside_never_starts(tmp_path):
    seen = []

    def account(task):
        seen.append(task.kind)
        rows = [{"id": r["id"], "answer": "sales" if r["subject"] == "Newsletter" else "work"} for r in rows_of(task)]
        return json.dumps({"answers": rows})

    set_responder(account)
    items = [unplaced(0), mail("news", f"deals@{CLUB}", subject="Newsletter"), unplaced(2)]
    ws, cfg, store = make(tmp_path, items, first_run="intake")
    cfg.ai.budgets.confirm_unpriced = True  # unpriced runs wait for a go, so the intake does
    try:
        from engine.watch import refresh

        result = refresh(ws, store, cfg, "m", NOW)
        assert len(result.taken_in) == 3 and result.new == []
        # No price is known, so the three wait for the go; nothing was sorted or spent before it.
        assert seen == [] and not store.read().has("run")
        (line,) = [x for x in queue(ws, store, cfg, NOW) if x.kind == "intake_go"]
        assert line.count == 3 and line.unpriced >= 3
        assert source_intake.grant_go(ws, store, cfg, "m", now=NOW) == 2
        assert seen == ["sort-mail"] and len(sort_runs(store)) == 1
        snaps = {s.data["key"]: s.data for s in store.read().list("snapshot")}
        assert snaps["news"]["set_aside"]["section"] == "sales"
        aside = [r for r in store.read().list("request") if r.data.get("set_aside")]
        assert len(aside) == 1 and aside[0].data["state"] == "done" and aside[0].data["intake"] == "m"
        queued = [r for r in store.read().list("request") if r.data["state"] == "queued"]
        assert len(queued) == 2 and all(r.data["approval"] == "granted" for r in queued)
    finally:
        store.close()
        set_responder(None)
