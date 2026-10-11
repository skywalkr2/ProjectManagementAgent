"""Projects inside projects (a book in its series): the language work on a record is written in, and what AI work on a
project and everything in it has cost against the budget the person set."""

from __future__ import annotations

from typing import Any


def chain(view: Any, project_id: str | None) -> list[Any]:
    """The project and the projects above it, nearest first; stops at a loop or a missing parent."""
    found, seen = [], set()
    current = view.get("project", project_id) if project_id else None
    while current is not None and current.id not in seen:
        found.append(current)
        seen.add(current.id)
        up = current.data.get("parent")
        current = view.get("project", up) if isinstance(up, str) else None
    return found


def project_of(record: Any) -> str | None:
    """The project a record is in: itself for a project, else its `project` field."""
    if record is None:
        return None
    if record.kind == "project":
        return record.id
    value = record.data.get("project")
    return value if isinstance(value, str) else None


def language_for(view: Any, default: str, record: Any) -> str:
    """The language tag work on a record is written in: its project's, else the nearest parent's, else the
    workspace's."""
    for project in chain(view, project_of(record)):
        if project.data.get("language"):
            return project.data["language"]
    return default


def spent_on(store: Any, project_id: str) -> float:
    """USD spent on AI work about this project, records in it and projects inside it."""
    from engine.packet import target_of

    view = store.read()
    total = 0.0
    requests: dict[str, bool] = {}
    for run in view.list("run"):
        request_id = run.data.get("request")
        if request_id not in requests:
            request = view.get("request", request_id) if request_id else None
            about = target_of(store, request.data) if request else None
            record = view.get(*about) if about else None
            requests[request_id] = any(p.id == project_id for p in chain(view, project_of(record)))
        if requests[request_id]:
            total += run.data.get("cost_usd") or 0.0
    return total


def budget_problem(store: Any, request: dict, estimate: float | None) -> str | None:
    """Why a run would go over the budget of the project it is about (or one above it), or None."""
    from engine.packet import target_of

    view = store.read()
    about = target_of(store, request)
    record = view.get(*about) if about else None
    for project in chain(view, project_of(record)):
        budget = project.data.get("budget_usd")
        if budget is None:
            continue
        spent = spent_on(store, project.id)
        cost = estimate or 0.0
        if spent + cost > budget:
            name = project.data["name"]
            about_cost = f" and this would cost about ${cost:.2f}" if cost else ""
            return (
                f"{name} has a budget of ${budget:.2f}; ${spent:.2f} is spent{about_cost}. "
                "Raise the budget on the project, or set this aside."
            )
    return None
