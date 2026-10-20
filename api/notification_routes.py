"""API routes for notices that something needs the person (design 7.19): what they are set to, what the open screen
shows a browser notice for, and "Send me a test". A notice goes to the person only and carries a count; the address
for it is saved by the secret routes, which keep it as a reference."""

from __future__ import annotations

import os

from fastapi import APIRouter

from api.schemas import NotificationsView, NotifyTestIn, NotifyTestResult, NotifyWaiting, NotifyWebhookView
from engine import notifications, setup
from engine.config import Config, ConfigError, load_config
from engine.storage import Store
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_notification_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def current() -> Config:
        """The settings as the files hold them now; the running app may have started with older ones."""
        try:
            return load_config(ws.config_dir, env=dict(os.environ))
        except ConfigError:
            return cfg

    @r.get("/notifications")
    def notifications_view() -> NotificationsView:
        """What the notices are set to now, and why the last note to the address didn't arrive when it didn't."""
        now = current()
        n = now.ui.notifications
        where, name = setup.secret_where(ws, n.webhook)
        return NotificationsView(
            enabled=n.enabled,
            browser=n.browser,
            webhook=NotifyWebhookView(where=where, name=name),
            quiet_now=notifications.quiet_now(now, worker.now()),
            mail_ready=False,
            problem=notifications.last_problem(ws),
        )

    @r.get("/notifications/waiting")
    def notifications_waiting() -> NotifyWaiting:
        """What the open screen shows a browser notice for. Empty while notices or the browser target are off."""
        now = current()
        n = now.ui.notifications
        if not (n.enabled and n.browser):
            return NotifyWaiting(browser=False, keys=[], message="")
        found = notifications.waiting(ws, store, now, worker.now(), handover=worker.handover_state())
        return NotifyWaiting(
            browser=not notifications.quiet_now(now, worker.now()), keys=found.keys, message=found.message
        )

    @r.post("/notifications/test")
    def notifications_test(body: NotifyTestIn) -> NotifyTestResult:
        """ "Send me a test": the webhook gets the test note now (even with notices off, so it can be checked first);
        for the browser the answer carries the words, which the open screen shows itself."""
        now = current()
        words = notifications.test_message(now)
        if body.target == "browser":
            return NotifyTestResult(ok=True, message=words)
        sent = notifications.send_test(ws, now, env=dict(os.environ))
        return NotifyTestResult(ok=sent.ok, message=words, problem=sent.problem)

    return r
