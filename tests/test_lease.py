import logging
import os
import subprocess
import sys

import pytest

from engine.storage.lease import Lease, LeaseHeld


def test_a_second_copy_is_refused_while_the_first_is_alive(store):
    first = Lease(store, holder="first")
    first.acquire()
    with pytest.raises(LeaseHeld, match="already open"):
        Lease(store, holder="second").acquire()


def test_an_expired_lease_can_be_taken(store):
    Lease(store, holder="first", ttl_seconds=-1).acquire()
    Lease(store, holder="second").acquire()
    assert Lease(store).current().holder == "second"


def test_takeover_with_force_and_the_old_holder_notices(store):
    first = Lease(store, holder="first")
    first.acquire()
    Lease(store, holder="second").acquire(force=True)
    assert first.heartbeat() is False


def test_release_frees_the_workspace(store):
    lease = Lease(store, holder="first")
    lease.acquire()
    lease.release()
    assert lease.current() is None


def _holder_of(pid: int) -> str:
    return f"{pid}-{'0' * 32}"


def _finished_process_id() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_a_new_lease_names_this_process_in_its_holder_id(store):
    assert Lease(store).holder.startswith(f"{os.getpid()}-")


def test_a_lease_left_by_a_stopped_copy_on_this_computer_is_taken_without_force(store, caplog):
    Lease(store, holder=_holder_of(_finished_process_id())).acquire()
    second = Lease(store)
    with caplog.at_level(logging.INFO, logger="engine.storage.lease"):
        second.acquire()
    assert second.current().holder == second.holder
    assert [r.getMessage() for r in caplog.records if "no longer running" in r.getMessage()]


def test_a_lease_whose_process_is_running_is_refused_and_says_it_is_open_here(store):
    Lease(store, holder=_holder_of(os.getpid())).acquire()
    with pytest.raises(LeaseHeld, match="already open in another window on this computer") as refused:
        Lease(store).acquire()
    assert "takeover" not in str(refused.value)
    assert Lease(store).current().holder == _holder_of(os.getpid())


def test_a_lease_from_another_computer_is_refused_and_names_it(store):
    other = "another-computer"
    stopped = Lease(store, holder=_holder_of(_finished_process_id()))
    stopped.host = other
    stopped.acquire()
    with pytest.raises(LeaseHeld, match=other) as refused:
        Lease(store).acquire()
    assert "takeover" in str(refused.value)


def test_a_holder_id_without_a_process_is_refused_as_before(store):
    Lease(store, holder="a1b2c3").acquire()
    with pytest.raises(LeaseHeld, match="already open") as refused:
        Lease(store).acquire()
    assert "takeover" in str(refused.value)
    assert Lease(store).current().holder == "a1b2c3"
