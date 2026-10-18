"""Supply streams for libraries that inspect them in a windowed executable."""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 -- stands in for the stream all run long
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 -- stands in for the stream all run long
