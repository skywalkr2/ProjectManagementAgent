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
