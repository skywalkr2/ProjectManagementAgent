"""Reading YAML text: the compiled parser when this install has it, the pure-Python one otherwise.

Both give the same data. The compiled one is several times faster, which matters because a workspace is many small
files (settings, manifests, records) read at start-up. When the compiled parser refuses a text, the text is parsed
again by the pure-Python one, so a person who mistyped a file gets the longer message that quotes the offending line
and points at the column, and any text only one of the two accepts still loads.
"""

from __future__ import annotations

from typing import Any

import yaml

COMPILED_SAFE_LOADER: type | None = getattr(yaml, "CSafeLoader", None)


def load_with(text: str, compiled: type | None, plain: type) -> Any:
    """Parses `text` with `compiled` when there is one, falling back to `plain` for anything it refuses."""
    if compiled is not None:
        try:
            return yaml.load(text, Loader=compiled)  # noqa: S506 - a SafeLoader subclass
        except yaml.YAMLError:
            pass
    return yaml.load(text, Loader=plain)  # noqa: S506 - a SafeLoader subclass


def load_yaml(text: str) -> Any:
    """What `yaml.safe_load` returns for `text`, sooner when the compiled parser is installed."""
    return load_with(text, COMPILED_SAFE_LOADER, yaml.SafeLoader)
