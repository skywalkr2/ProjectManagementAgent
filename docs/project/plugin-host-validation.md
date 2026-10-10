# Plugin host verification — 2026-10-10

Implementation branch: `codex/plugin-host`, based on `claude/tender-tesla-16a8ob` at
`0d5729ccdce96400b899acf37685ddd96dd929af`. No remote branch has been created or pushed yet.

| Check | Result |
|---|---|
| `uv run ruff check .` | Pass |
| `uv run ruff format --check .` | Pass |
| `uv run pytest` | 269 passed |
| `uv run python -m engine.selfcheck` | Pass, including bundled registrations and both workspaces with/without plugins |
| `npm --prefix web test` | 19 passed |
| `npm --prefix web run build` | Pass |
| `npm --prefix web run e2e` | Blocked before tests: bundled browser absent; installed Chrome aborts with SIGABRT and permission errors in the sandbox |
| `COCKPIT_TEST_CORE_ONLY=1 uv run pytest --ignore=tests/test_plugins.py` | 217 passed |
| `uv lock --check --offline` | Pass |
| `git diff --check` | Pass |

The updated API model was regenerated with `uv run python -m api.openapi`. Browser projects cover both root and nested base
paths. Both server processes now start successfully, but neither browser project can launch its browser in this session.
The request to run the browser check outside the sandbox was rejected by the session's approval policy. No test assertion,
security header or approval gate was weakened to make it pass.

Python checks used an existing dependency environment, `UV_NO_SYNC=1`, and a writable temporary `UV_CACHE_DIR`. Web tests
and build passed with their normal config loader on the final run. The earlier native-loader workaround is no longer needed.

From this checkout in a normal terminal, run the remaining browser check using the installed browser:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
UV_CACHE_DIR=/tmp/plugin-host-uv-cache UV_NO_SYNC=1 npm --prefix web run e2e
```

Resolve any failures and run every required check before pushing only `codex/plugin-host`. The remote is the source
repository; no merge or history rewrite is needed.
