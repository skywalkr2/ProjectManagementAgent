"""Moving data to its one place when an older workspace opens (one source of truth, decisions 2026-10-11).

The PM's name and other names used to be settings (`workspace.user.full_name`, `aliases`) as well as their person
record. They now live on the record only: at start, values still in the settings file go to the record (the
settings file's name wins, since the setup screen used to edit only that), and the keys leave the file.
"""

from __future__ import annotations

from typing import Any

from engine.config.yaml_edit import remove_key, set_key
from engine.storage import WriteContext

_MIGRATE = WriteContext(actor="engine", trust="trusted", op="migrate.identity")


def move_identity(ws: Any, store: Any, cfg: Any) -> str | None:
    """Move the PM's name and aliases from the settings to their person record. Returns the person id, if any."""
    full_name = cfg.moved.get("workspace.user.full_name")
    aliases = cfg.moved.get("workspace.user.aliases") or []
    if full_name is None and not aliases:
        return None
    pid = cfg.workspace.user.person
    name = " ".join(str(full_name or "").split())
    with store.transaction() as tx:
        person = tx.get("person", pid) if pid else None
        if person is None and name:
            person = tx.create("person", {"full_name": name, "name_verified": True}, _MIGRATE)
            pid = person.id
        if person is not None:
            known = {a.lower() for a in person.data.get("aliases", [])} | {person.data["full_name"].lower()}
            extra = [a for a in (str(a).strip() for a in aliases) if a and a.lower() not in known | {"me"}]
            changes = {}
            if name and name != person.data["full_name"]:
                changes["full_name"] = name
            if extra:
                changes["aliases"] = [*person.data.get("aliases", []), *extra]
            if changes:
                tx.update("person", person.id, changes, _MIGRATE, read_version=person.version)
    path = ws.config_dir / "workspace.yaml"
    text = path.read_text(encoding="utf-8")
    for key in ("full_name", "aliases"):
        text = remove_key(text, ["user", key])
    if pid and pid != cfg.workspace.user.person:
        text = set_key(text, ["user", "person"], pid)
    path.write_text(text, encoding="utf-8")
    return pid
