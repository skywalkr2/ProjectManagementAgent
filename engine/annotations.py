"""Read a class's own annotations the same way on every supported interpreter.

From Python 3.14 annotations are evaluated lazily and no longer sit in the class namespace, so reading
`vars(cls)["__annotations__"]` finds nothing. This helper returns only what the class itself annotates, never what it
inherits, whichever interpreter runs.
"""

from __future__ import annotations

import inspect
from typing import Any

try:  # Python 3.14 and later
    import annotationlib
except ImportError:  # pragma: no cover - depends on the interpreter
    annotationlib = None


def local_annotations(cls: type) -> dict[str, Any]:
    """The annotations written in the class body itself. A name that can't be resolved yet stays a forward reference."""
    if annotationlib is not None:
        return annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
    return inspect.get_annotations(cls)
