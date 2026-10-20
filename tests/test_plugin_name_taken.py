"""A plugin loaded under its own name finds its own symbols even when another load of the same name, in the same
process, put a different module there meanwhile (the app and a settings check loading at once)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from engine.plugin_host import PluginHost

BUNDLED = Path(__file__).resolve().parents[1] / "plugins"


def test_a_plugins_symbols_come_from_its_own_load_whatever_holds_its_name_now():
    loader = PluginHost.__new__(PluginHost)
    loader._modules = []
    saved = {n: m for n, m in sys.modules.items() if n == "kit" or n.startswith("kit.")}
    try:
        for name in saved:
            sys.modules.pop(name)
        symbol = loader._importer(BUNDLED / "kit", "kit")
        sys.modules["kit"] = types.ModuleType("kit")  # another load's module, not yet run
        assert callable(symbol("kit:register"))
        assert isinstance(symbol("kit:Config"), type)
    finally:
        for name in [m for m in sys.modules if any(m == n or m.startswith(n + ".") for n in loader._modules)]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)
