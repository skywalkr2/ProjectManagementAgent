"""Settling a divergence between two computers from the screen: the situation described in counts and times, the line
Today shows, the choice noted and carried out at the next start through the same `keep` the command uses (so its lease
check holds), and a held start that writes nothing to the folder."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from tests.test_handover import change, projects, two, write  # noqa: F401  (two is a fixture)

TOKEN = "test-token-value"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def diverge(two):  # noqa: F811
    """Computer A and B each change while they can't sync; B wrote the folder last and closed."""
    from engine.handover import open_workspace, release

    a, cfg_a, b, cfg_b, folder = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    release(a, cfg_a)
    open_workspace(b, cfg_b)
    release(b, cfg_b)
    change(a, cfg_a, "Made on A")
    change(a, cfg_a, "Also on A")
    change(b, cfg_b, "Made on B")
    write(b, cfg_b)
    release(b, cfg_b)
    return a, cfg_a, b, cfg_b, folder


def test_the_situation_counts_what_each_side_has_that_the_other_lacks(two):  # noqa: F811
    import socket

    from engine.handover import situation

    a, cfg_a, _, _, _ = diverge(two)
    found = situation(a, cfg_a)
    assert found.kind == "diverged"
    assert found.here.computer == socket.gethostname() and found.here.changes > found.folder.changes > 0
    assert found.here.latest and found.folder.latest
    assert projects(a, cfg_a).count("Made on A") == 1  # describing changes nothing


def test_nothing_is_described_when_the_copies_agree(two):  # noqa: F811
    from engine.handover import open_workspace, situation

    a, cfg_a, _, _, _ = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    assert situation(a, cfg_a) is None


def test_a_fresh_lease_elsewhere_is_its_own_situation_with_the_wait(two):  # noqa: F811
    from engine.handover import open_workspace, situation, take

    a, cfg_a, b, cfg_b, _ = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    take(b, cfg_b, ledger=0)
    found = situation(a, cfg_a)
    assert found.kind == "elsewhere" and found.computer and 1 <= found.minutes_left <= 10
    later = datetime.now(UTC) + timedelta(minutes=11)
    assert situation(a, cfg_a, later) is None or situation(a, cfg_a, later).kind != "elsewhere"


def test_a_choice_is_noted_only_when_the_copies_diverged_and_the_other_computer_is_closed(two):  # noqa: F811
    from engine.handover import Refused, choose, chosen, clear_choice, take

    a, cfg_a, b, cfg_b, _ = diverge(two)
    with pytest.raises(ValueError):
        choose(a, cfg_a, "both")
    choose(a, cfg_a, "here")
    assert chosen(a) == "here"
    clear_choice(a)
    assert chosen(a) is None
    take(b, cfg_b, ledger=0)  # the other computer opened it
    with pytest.raises(Refused, match="open on the other computer"):
        choose(a, cfg_a, "folder")
    assert chosen(a) is None


def test_nothing_is_noted_when_there_is_nothing_to_choose_between(two):  # noqa: F811
    from engine.handover import Refused, choose, chosen, open_workspace

    a, cfg_a, _, _, _ = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    with pytest.raises(Refused, match="nothing to choose"):
        choose(a, cfg_a, "here")
    assert chosen(a) is None


def test_starting_on_diverged_copies_holds_the_sync_and_changes_nothing(two):  # noqa: F811
    from engine.handover import open_or_hold, read_lease

    a, cfg_a, b, cfg_b, folder = diverge(two)
    before = read_lease(folder)
    opened = open_or_hold(a, cfg_a)
    assert opened.action == "held" and opened.message
    assert read_lease(folder) == before  # the lease was not taken
    assert "Made on B" not in projects(a, cfg_a) and "Made on A" in projects(a, cfg_a)


def test_a_held_worker_writes_nothing_and_leaves_the_lease_alone(two):  # noqa: F811
    from engine.handover import read_lease
    from engine.storage import Store
    from engine.worker import Events, Worker

    a, cfg_a, _, _, folder = diverge(two)
    before = (folder / ".cockpit" / "export" / "ledger.jsonl").read_bytes(), read_lease(folder)
    store = Store(a.db_path, cfg=cfg_a)
    try:
        worker = Worker(a, store, cfg_a, Events())
        worker.hold_sync()
        assert worker.handover_state() == ("diverged", read_lease(folder).computer)
        assert not worker.sync_if_changed()
        worker.release_folder()
        assert (folder / ".cockpit" / "export" / "ledger.jsonl").read_bytes() == before[0]
        assert read_lease(folder) == before[1]
    finally:
        store.close()


@pytest.mark.parametrize("which", ["here", "folder"])
def test_a_choice_is_carried_out_at_the_next_start_and_the_other_side_is_saved(two, which):  # noqa: F811
    from engine.handover import choose, chosen, open_or_hold

    a, cfg_a, _, _, _ = diverge(two)
    choose(a, cfg_a, which)
    opened = open_or_hold(a, cfg_a)
    assert opened.action != "held" and opened.kept[0] == which and opened.kept[1]
    assert chosen(a) is None  # carried out once
    kept = projects(a, cfg_a)
    if which == "here":
        assert "Made on A" in kept and "Made on B" not in kept
    else:
        assert "Made on B" in kept and "Made on A" not in kept
    assert open_or_hold(a, cfg_a).action != "held"


def test_a_choice_still_meets_the_leases_check_when_it_is_carried_out(two):  # noqa: F811
    from engine.handover import Refused, choose, chosen, open_or_hold, take

    a, cfg_a, b, cfg_b, _ = diverge(two)
    choose(a, cfg_a, "folder")
    take(b, cfg_b, ledger=0)  # the other computer opened the workspace after the choice was noted
    with pytest.raises(Refused):
        open_or_hold(a, cfg_a)
    assert chosen(a) is None  # never retried unasked
    assert "Made on A" in projects(a, cfg_a) and "Made on B" not in projects(a, cfg_a)  # nothing was replaced


# ---- the screen's routes ----------------------------------------------------------------------------------


def app_for(ws, cfg, tmp_path, held=True):
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", sync_held=held)
    return TestClient(app, headers=HEADERS), app


def test_today_has_a_line_and_the_page_shows_both_sides(two, tmp_path):  # noqa: F811
    a, cfg_a, _, _, _ = diverge(two)
    with app_for(a, cfg_a, tmp_path)[0] as client:
        [line] = [x for x in client.get("/api/today/queue").json() if x["kind"] == "handover"]
        assert line["state"] == "diverged" and line["group"] == "decide" and line["text"]
        page = client.get("/api/sync/handover").json()
        assert page["state"] == "diverged" and page["chosen"] is None
        assert page["here"]["changes"] > page["folder"]["changes"] > 0
        assert page["here"]["latest"] and page["folder"]["computer"] == line["text"]
        assert client.get("/api/sync").json()["handover"] == "diverged"


def test_choosing_notes_the_choice_and_the_line_waits_for_the_restart(two, tmp_path):  # noqa: F811
    from engine.handover import chosen

    a, cfg_a, _, _, _ = diverge(two)
    with app_for(a, cfg_a, tmp_path)[0] as client:
        done = client.post("/api/sync/handover", json={"which": "folder"})
        assert done.status_code == 200 and done.json()["state"] == "chosen" and done.json()["chosen"] == "folder"
        assert chosen(a) == "folder"
        assert "Made on A" in projects(a, cfg_a)  # nothing changes until the restart
        [line] = [x for x in client.get("/api/today/queue").json() if x["kind"] == "handover"]
        assert line["state"] == "chosen"
        changed_mind = client.delete("/api/sync/handover").json()
        assert changed_mind["state"] == "diverged" and changed_mind["chosen"] is None and chosen(a) is None


def test_the_screen_refuses_a_choice_while_the_other_computer_has_the_workspace_open(two, tmp_path):  # noqa: F811
    from engine.handover import chosen, take

    a, cfg_a, b, cfg_b, _ = diverge(two)
    take(b, cfg_b, ledger=0)
    with app_for(a, cfg_a, tmp_path)[0] as client:
        refused = client.post("/api/sync/handover", json={"which": "here"})
        assert refused.status_code == 409 and "Close it there first" in refused.json()["detail"]
        assert chosen(a) is None


def test_the_screen_offers_no_choice_to_an_app_that_is_not_waiting_for_one(two, tmp_path):  # noqa: F811
    a, cfg_a, _, _, _ = two
    with app_for(a, cfg_a, tmp_path, held=False)[0] as client:
        assert client.post("/api/sync/handover", json={"which": "here"}).status_code == 409
        assert client.get("/api/sync/handover").json()["state"] == "clear"
        assert not [x for x in client.get("/api/today/queue").json() if x["kind"] == "handover"]


def test_a_copy_that_lost_the_workspace_to_the_other_computer_says_so(two, tmp_path):  # noqa: F811
    from engine.handover import open_workspace, take

    a, cfg_a, b, cfg_b, _ = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    client, app = app_for(a, cfg_a, tmp_path, held=False)
    with client:
        take(b, cfg_b, ledger=0)
        app.state.worker.sync_if_changed()
        [line] = [x for x in client.get("/api/today/queue").json() if x["kind"] == "handover"]
        assert line["state"] == "elsewhere" and line["text"]
        page = client.get("/api/sync/handover").json()
        assert page["state"] == "elsewhere" and page["computer"] and page["minutes_left"] >= 1
