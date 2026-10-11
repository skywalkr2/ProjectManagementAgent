"""Default prompt templates, the core's here and a plugin's in its own prompts/ folder. A workspace's prompts/ folder
overrides any of them by name: `notes.md` for the core's, `<plugin>/<name>.md` for a plugin's."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

DEFAULTS = Path(__file__).parent


def render(
    name: str, values: Mapping[str, str], workspace_root: Path | None = None, default: Path | None = None
) -> str:
    """The prompt `name` with {{placeholders}} filled: the workspace's override if there is one, else `default` (a
    plugin's own template), else the core's."""
    override = workspace_root / "prompts" / f"{name}.md" if workspace_root else None
    path = override if override and override.exists() else default or DEFAULTS / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: values.get(m.group(1), m.group(0)), text).strip()
