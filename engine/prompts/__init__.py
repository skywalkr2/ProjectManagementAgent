"""Default prompt templates. A workspace's prompts/ folder overrides any of them by file name."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

DEFAULTS = Path(__file__).parent


def render(name: str, values: Mapping[str, str], workspace_root: Path | None = None) -> str:
    override = workspace_root / "prompts" / f"{name}.md" if workspace_root else None
    path = override if override and override.exists() else DEFAULTS / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: values.get(m.group(1), m.group(0)), text).strip()
