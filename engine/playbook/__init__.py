"""Playbooks: built-in good practice for a kind of work (design 3.8). The core's covers project support."""

from __future__ import annotations

from pathlib import Path

GUIDANCE = Path(__file__).parent / "guidance"


def guidance(name: str) -> str:
    path = GUIDANCE / f"{name}.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""
