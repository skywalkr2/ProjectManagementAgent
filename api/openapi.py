"""Write the API's OpenAPI schema, which the web client's types are generated from.

`python -m api.openapi` writes web/src/api/openapi.json; the self-check fails when the committed file is out of date.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "web" / "src" / "api" / "openapi.json"


def build() -> str:
    from api.app import create_app
    from engine.workspace import init_workspace

    with tempfile.TemporaryDirectory() as tmp:
        ws = init_workspace(Path(tmp) / "ws", git=False)
        cfg = ws.config(env={}, flags={"server.base_path": "/"})
        app = create_app(ws, cfg, "schema-only")
        try:
            schema = app.openapi()
        finally:
            app.state.store.close()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else SCHEMA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build(), encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
