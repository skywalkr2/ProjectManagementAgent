"""Packs people can add (design 3.11): catalog feeds read on request, and what each listed pack adds, reaches and keeps,
written from its manifest rather than its own description, with its typical AI jobs priced on the workspace's own
accounts.

A feed is one index file (YAML or JSON) at an https address. Everything in it is untrusted: text stays text, links are
https only, and nothing in it becomes a rule, a setting or an instruction. An entry that doesn't fit the format is
left out with a note; the rest of the feed still shows.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from engine.config import Config
from engine.connectors import READS_WORDS, reads
from engine.state_file import write_whole
from engine.yaml_load import load_yaml

#: The largest feed read, in bytes.
MAX_FEED_BYTES = 2_000_000
CACHE_FILE = "pack-catalog.json"
LEVELS = ("open", "internal", "restricted")


class Price(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: Literal["free", "one_time", "subscription", "see_publisher"] = "see_publisher"
    amount: float | None = Field(None, ge=0)
    currency: str = Field("USD", pattern=r"^[A-Z]{3}$")
    period: Literal["month", "year"] | None = None
    note: str = Field("", max_length=200)


class AiJob(BaseModel):
    """One typical piece of AI work the pack does, sized so the app can price it."""

    model_config = ConfigDict(extra="ignore")

    label: str = Field(min_length=1, max_length=80)
    input_tokens: int = Field(ge=0, le=2_000_000)
    output_tokens: int = Field(ge=0, le=200_000)
    role: Literal["write", "check", "research"] = "write"
    data_level: Literal["open", "internal", "restricted"] = "internal"


class Release(BaseModel):
    """Where a pack's release file is, so the app can install it: an https address of a wheel of pure Python, and its
    SHA-256 checksum, which the download must match."""

    model_config = ConfigDict(extra="ignore")

    url: str = Field(max_length=1000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("url")
    @classmethod
    def _https(cls, value: str) -> str:
        if not (value.startswith("https://") and urlsplit(value).hostname):
            raise ValueError("a release is an https address")
        return value


class Entry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,40}$")
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field("", max_length=300)
    publisher: str = Field("", max_length=80)
    maintainers: bool = False
    updated: str = Field("", max_length=40)
    version: str = Field("", max_length=40)
    plugin_api: str = Field("", max_length=40)
    price: Price = Field(default_factory=Price)
    homepage: str | None = Field(None, max_length=500)
    install: str = Field("", max_length=500)
    demo: bool = False
    ai_jobs: list[AiJob] = Field(default_factory=list, max_length=20)
    provides: dict[str, Any] = Field(default_factory=dict)
    requires: dict[str, Any] = Field(default_factory=dict)
    release: Release | None = None

    @field_validator("homepage")
    @classmethod
    def _https(cls, value: str | None) -> str | None:
        if value is not None and not (value.startswith("https://") and urlsplit(value).hostname):
            raise ValueError("a homepage is an https address")
        return value


@dataclass
class Feed:
    url: str
    entries: list[Entry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    read_at: float | None = None


def feed_urls(cfg: Config, product: dict[str, Any]) -> list[str]:
    """The feeds this workspace reads: the one this build came with (unless switched off), then its own."""
    settings = cfg.workspace.plugins.catalog
    if not settings.enabled:
        return []
    shipped = product.get("pack_catalog") if settings.shipped_feed else None
    urls = [shipped] if isinstance(shipped, str) and shipped.startswith("https://") else []
    return [*urls, *(u for u in settings.feeds if u not in urls)]


def parse(url: str, text: str) -> Feed:
    """A feed's entries; entries that don't fit are left out with a note."""
    feed = Feed(url)
    try:
        data = load_yaml(text)
    except yaml.YAMLError:
        feed.error = "it isn't a catalog file"
        return feed
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("packs"), list):
        feed.error = "it isn't a catalog file this version of the app reads"
        return feed
    seen: set[str] = set()
    for i, raw in enumerate(data["packs"][:200]):
        try:
            entry = Entry.model_validate(raw)
        except ValidationError as err:
            feed.notes.append(f"entry {i + 1} was left out: {err.errors()[0]['msg']}")
            continue
        if entry.id in seen:
            feed.notes.append(f"{entry.id} is listed twice; the first is shown")
            continue
        seen.add(entry.id)
        feed.entries.append(entry)
    return feed


def _read_cache(path: Any) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_feeds(
    urls: list[str],
    cache_dir: Any,
    refresh_hours: int,
    *,
    refresh: bool = False,
    web_for: Any = None,
    now: float | None = None,
) -> list[Feed]:
    """Each feed from the kept copy when it is fresh enough, else read again; a feed that can't be read falls back to
    its kept copy, with the reason."""
    from engine.connectors import ConnectorError
    from engine.net import WebClient

    now = time.time() if now is None else now
    path = cache_dir / CACHE_FILE
    kept = _read_cache(path)
    feeds = []
    changed = False
    for url in urls:
        copy = kept.get(url)
        fresh = copy and not refresh and now - float(copy.get("read_at") or 0) < refresh_hours * 3600
        if not fresh:
            client = web_for(url) if web_for else WebClient([urlsplit(url).hostname or ""])
            try:
                response = client.get(url, headers={"Accept": "application/json, application/yaml, text/plain"})
                if len(response.content) > MAX_FEED_BYTES:
                    raise ConnectorError("outage", "the catalog is too large")
                copy = {"text": response.text, "read_at": now}
                kept[url] = copy
                changed = True
            except ConnectorError as err:
                if copy:
                    feed = parse(url, copy["text"])
                    feed.read_at = copy.get("read_at")
                    feed.notes.insert(0, f"couldn't read it just now ({err.kind}); showing the copy kept earlier")
                    feeds.append(feed)
                else:
                    feeds.append(Feed(url, error=f"couldn't read it ({err.kind}): {err.detail}"))
                continue
            finally:
                if web_for is None:
                    client.close()
        feed = parse(url, copy["text"])
        feed.read_at = copy.get("read_at")
        feeds.append(feed)
    if changed:
        write_whole(path, json.dumps({u: kept[u] for u in urls if u in kept}))
    return feeds


# ---- what a pack adds, reaches and keeps -----------------------------------------------------------------------------


def _words(identifier: str) -> str:
    return identifier.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").replace(".", " ")


def _list(value: Any) -> list[str]:
    return [str(v) for v in value if isinstance(v, (str, int))] if isinstance(value, list) else []


def summary(provides: dict[str, Any], requires: dict[str, Any]) -> dict[str, Any]:
    """What a manifest adds, reaches and keeps, in counts and plain names, for the screen to word."""
    tools = requires.get("tools") if isinstance(requires.get("tools"), list) else []
    levels = [lvl for lvl in _list(requires.get("data_levels")) if lvl in LEVELS] or ["open", "internal"]
    declared = provides.get("connector_reads")
    said = {str(k): str(v) for k, v in declared.items()} if isinstance(declared, dict) else {}
    return {
        "adds": {
            "item_types": [_words(k) for k in _list(provides.get("record_types"))],
            "screens": len(_list(provides.get("panels"))),
            "today": len(_list(provides.get("today"))),
            "ai_work": len(_list(provides.get("ai_task_kinds"))),
            "actions": len(_list(provides.get("actions"))),
            "setup_steps": len(_list(provides.get("setup_steps"))),
            "sources": len(_list(provides.get("connectors"))),
        },
        "reaches": {
            "sign_ins": [_words(k) for k in _list(provides.get("sign_ins"))],
            "hosts": _list(requires.get("network")),
            "programs": [str(t.get("name")) for t in tools if isinstance(t, dict) and t.get("name")],
            "keys": len(_list(requires.get("secrets"))),
        },
        "keeps": max(levels, key=LEVELS.index),
        "reads": [
            kind for kind in READS_WORDS if any(kind in reads(c, said) for c in _list(provides.get("connectors")))
        ],
    }


def manifest_summary(manifest: Any) -> dict[str, Any]:
    """The same summary for an installed plugin, from its checked manifest."""
    data = manifest.model_dump(mode="json")
    return summary(data.get("provides") or {}, data.get("requires") or {})


# ---- what its AI work costs here -------------------------------------------------------------------------------------


def job_cost(cfg: Config, router: Any, job: AiJob) -> dict[str, Any]:
    """A pack's typical job on this workspace's accounts: its price in USD when the model's prices are known, else
    only its size; `account` False when no account is set up for the work."""
    from engine.ai.router import NoProvider, choices

    role = getattr(cfg.ai.roles, job.role)
    tier = role.tier or "routine"
    size = {"label": job.label, "tokens": job.input_tokens + job.output_tokens, "usd": None, "account": True}
    try:
        choice = choices(cfg, "", job.data_level, tier=tier)[0]
    except (NoProvider, IndexError):
        return {**size, "account": False}
    info = router.model_info(choice)
    if info.input_per_million is None or info.output_per_million is None:
        return size
    usd = (job.input_tokens * info.input_per_million + job.output_tokens * info.output_per_million) / 1e6
    return {**size, "usd": round(usd, 4)}


def compatible(entry: Entry, version: str) -> bool | None:
    """Whether the pack works with this version of the app; None when the feed doesn't say."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet

    if not entry.plugin_api:
        return None
    try:
        return SpecifierSet(entry.plugin_api).contains(version, prereleases=True)
    except InvalidSpecifier:
        return None
