"""A fictional add-on with one screen and nothing else, for the journey tests: a page the add-on writes from the
workspace's records."""

from __future__ import annotations

from engine.plugin_api import Settings

TITLE = "Example overview"
BODY = "This page comes from the example add-on."


class Config(Settings):
    pass


def overview(view, settings, project) -> str:
    return f"{BODY}\n"


def register(registrar) -> None:
    registrar.document("journey-panel/overview", title=TITLE, render=overview)
