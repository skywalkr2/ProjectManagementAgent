"""The change counter that live streams wait on."""

import threading
import time

from engine.worker import Events


def test_wait_returns_when_the_counter_moves() -> None:
    events = Events()
    threading.Timer(0.05, events.changed).start()
    assert events.wait(0, 5.0) == 1


def test_close_releases_waiters_at_once() -> None:
    events = Events()
    threading.Timer(0.05, events.close).start()
    started = time.monotonic()
    assert events.wait(0, 5.0) == 0
    assert time.monotonic() - started < 2.0
    assert events.closed


def test_wait_after_close_does_not_block() -> None:
    events = Events()
    events.close()
    started = time.monotonic()
    events.wait(0, 5.0)
    assert time.monotonic() - started < 1.0
