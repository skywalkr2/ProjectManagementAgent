"""Smoke test for the AI setup (design 6.16): one small live call per configured tier and account, with the exact
parameters the work will use, so a setting a model refuses is found before real work fails.

The result is kept with a fingerprint of `ai.yaml`, so the server can say when the settings changed since the last test.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from engine.ai.adapters import make_adapter
from engine.ai.task import AiError, AiTask
from engine.config import Config
from engine.secrets import SecretError, resolve_secret
from engine.workspace import Workspace

STATUS_FILE = "ai-test.json"
_REQUEST = 'Reply with exactly this JSON and nothing else: {"ok": true}'


@dataclass
class SmokeResult:
    tier: str
    account: str
    main: bool
    ok: bool
    detail: str
    seconds: float = 0.0


def _params_for_tier(cfg: Config, tier: str) -> list[tuple[str, float, int]]:
    """(task kind, temperature, max_output) for every task kind that runs on this tier, directly or by escalation."""
    uses = [(k, t.temperature, t.max_output) for k, t in cfg.ai.tasks.items() if t.tier == tier]
    if not uses:
        uses = [
            (k, t.temperature, t.max_output)
            for k, t in cfg.ai.tasks.items()
            if cfg.ai.tiers.get(t.tier) and cfg.ai.tiers[t.tier].escalate_to == tier
        ]
    return uses or [("smoke", 0.0, 256)]


def smoke_test(
    cfg: Config,
    env: Mapping[str, str],
    adapter_factory: Callable[[str, Any, str | None], Any] = make_adapter,
) -> list[SmokeResult]:
    results: list[SmokeResult] = []
    for tier_name, tier in cfg.ai.tiers.items():
        if not tier.use:
            results.append(SmokeResult(tier_name, "", True, False, "no AI account is set up for this tier"))
            continue
        for position, ref in enumerate([tier.use, *tier.fallback]):
            provider_name, _, model_key = ref.partition("/")
            settings = cfg.ai.providers[provider_name]
            model_id = settings.models.get(model_key, model_key)
            for kind, temperature, max_output in _params_for_tier(cfg, tier_name):
                task = AiTask(kind, "This is a connection test.", "", _REQUEST, {}, temperature, max_output)
                start = time.monotonic()
                try:
                    secret = resolve_secret(settings.auth, env)
                    reply = adapter_factory(settings.adapter, settings, secret).run(task, model_id)
                    detail = "answered" if _is_ok(reply.text) else "answered, but not with the requested JSON"
                    ok = True
                except SecretError as err:
                    ok, detail = False, f"key not found: {err}"
                except AiError as err:
                    ok, detail = False, f"{err.kind}: {err.detail}" if err.detail else err.kind
                except ValueError as err:
                    ok, detail = False, str(err)
                label = f"{ref} ({kind}, temperature {temperature}, max output {max_output})"
                results.append(SmokeResult(tier_name, label, position == 0, ok, detail, time.monotonic() - start))
    return results


def _is_ok(text: str) -> bool:
    try:
        return json.loads(text.strip().strip("`").removeprefix("json").strip()) == {"ok": True}
    except ValueError:
        return False


def ai_fingerprint(ws: Workspace) -> str:
    path = ws.config_dir / "ai.yaml"
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def record(ws: Workspace, results: list[SmokeResult]) -> None:
    ws.private_dir.mkdir(parents=True, exist_ok=True)
    passed = all(r.ok for r in results if r.main)
    data = {"fingerprint": ai_fingerprint(ws), "passed": passed, "results": [asdict(r) for r in results]}
    (ws.private_dir / STATUS_FILE).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def untested_since_change(ws: Workspace) -> bool:
    """True when ai.yaml changed since the last passing smoke test (or there never was one)."""
    path = ws.private_dir / STATUS_FILE
    if not path.exists():
        return True
    data = json.loads(path.read_text(encoding="utf-8"))
    return not data.get("passed") or data.get("fingerprint") != ai_fingerprint(ws)
