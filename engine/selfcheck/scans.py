"""Scans that keep specifics out of the product's code (design 10.2).

Each scan returns findings; an empty list means it passed. Values read from a private workspace are never printed,
only the file and line where they were found, so a scan log can't leak them.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import yaml
from pydantic import BaseModel

from engine.config.schema import FILES

REPO = Path(__file__).resolve().parents[2]
CODE_DIRS = ("engine", "api", "web/src", "web/e2e", "plugins", "tests")
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".yaml", ".yml", ".json", ".md"}
SKIP_PARTS = {"__pycache__", "node_modules", "fixtures", ".pytest_cache"}
ADAPTERS = Path("engine/ai/adapters")
MIN_TERM = 4

URL = re.compile(r"https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DATED_COMMENT = [
    re.compile(r"\b\d{1,2}/\d{1,2}\b"),
    re.compile(r"\b20\d\d-\d\d-\d\d\b"),
    re.compile(r"\bper [A-Z][a-z]+"),
    re.compile(r"\b[A-Z][a-z]+ (said|asked|wants|decided)\b"),
]
NETWORK_MODULES = {"requests", "httpx", "urllib", "socket", "subprocess", "http"}


@dataclass(frozen=True)
class Finding:
    scan: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.scan}: {self.path}:{self.line}: {self.message}"


# ---- file walking ----------------------------------------------------------------------------------------------------


def code_files(root: Path = REPO, *, exclude: Iterable[Path] = ()) -> Iterator[Path]:
    excluded = [root / e for e in exclude]
    for top in CODE_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in CODE_SUFFIXES:
                continue
            if SKIP_PARTS & set(path.relative_to(root).parts):
                continue
            if any(path.is_relative_to(e) for e in excluded):
                continue
            yield path


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


# ---- terms from workspaces -------------------------------------------------------------------------------------------


def workspace_terms(ws_root: Path) -> set[str]:
    """Names and other specifics a workspace holds: these must never appear in code."""
    terms: set[str] = set()

    def add(value: object) -> None:
        if isinstance(value, str):
            text = value.strip()
            if len(text) >= MIN_TERM:
                terms.add(text)
            for host in URL.findall(text):
                terms.add(host.split("://", 1)[1])
        elif isinstance(value, list):
            for item in value:
                add(item)

    cfg_path = ws_root / "config" / "workspace.yaml"
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        add(cfg.get("name"))
        add(cfg.get("assistant_name"))
        user = cfg.get("user") or {}
        add(user.get("full_name"))
        add(user.get("aliases"))
    fields = {
        "person": ("full_name", "aliases", "org"),
        "team": ("name", "aliases"),
        "project": ("name", "group"),
    }
    for kind, keys in fields.items():
        path = ws_root / "data" / f"{kind}.json"
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            for key in keys:
                add(item.get(key))
            for link in item.get("links", []):
                add(link.get("url"))
    for cfg_file in sorted((ws_root / "config").glob("*.yaml")):
        add(URL.findall(cfg_file.read_text(encoding="utf-8")))
    return terms


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE)


# ---- scans -----------------------------------------------------------------------------------------------------------


def scan_specificity(
    fixture_workspaces: list[Path], private_workspace: Path | None = None, root: Path = REPO
) -> list[Finding]:
    public = set().union(*(workspace_terms(ws) for ws in fixture_workspaces)) if fixture_workspaces else set()
    private = workspace_terms(private_workspace) if private_workspace else set()
    patterns = [(t, _term_pattern(t), False) for t in sorted(public)]
    patterns += [(t, _term_pattern(t), True) for t in sorted(private - public)]
    findings = []
    for path in code_files(root):
        for n, line in enumerate(_lines(path), 1):
            for term, pattern, is_private in patterns:
                if pattern.search(line):
                    shown = "a value from your private workspace" if is_private else repr(term)
                    findings.append(Finding("specificity", _rel(path, root), n, f"{shown} belongs in config or data"))
    return findings


def scan_providers(extra_names: Iterable[str] = (), root: Path = REPO) -> list[Finding]:
    data = yaml.safe_load((root / ADAPTERS / "known_vendors.yaml").read_text(encoding="utf-8"))
    names = {n.lower() for n in data.get("vendors", [])} | {n.lower() for n in extra_names if n}
    patterns = [(n, _term_pattern(n)) for n in sorted(names)]
    findings = []
    for path in code_files(root, exclude=[ADAPTERS]):
        for n, line in enumerate(_lines(path), 1):
            for name, pattern in patterns:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            "provider", _rel(path, root), n, f"AI vendor or model name {name!r} outside the adapters"
                        )
                    )
    return findings


def scan_patterns(root: Path = REPO) -> list[Finding]:
    findings = []
    for path in code_files(root):
        rel = _rel(path, root)
        for n, line in enumerate(_lines(path), 1):
            if URL.search(line):
                findings.append(Finding("pattern", rel, n, "a URL in code; URLs belong in config or data"))
        for n, comment in _comments(path):
            for pattern in DATED_COMMENT:
                if pattern.search(comment):
                    message = "a comment that dates or attributes a decision; put the why in decisions.md"
                    findings.append(Finding("pattern", rel, n, message))
                    break
    return findings


def scan_boundary(root: Path = REPO) -> list[Finding]:
    findings = []
    for path in code_files(root):
        if path.suffix != ".py":
            continue
        rel = _rel(path, root)
        top = Path(rel).parts[0]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as err:
            findings.append(Finding("boundary", rel, err.lineno or 0, "file doesn't parse"))
            continue
        for node in ast.walk(tree):
            for module in _imported(node):
                head = module.split(".")[0]
                if top in ("engine", "api") and head == "plugins":
                    findings.append(Finding("boundary", rel, node.lineno, "core code imports from plugins/"))
                if top == "plugins":
                    if head == "engine" and not module.startswith("engine.plugin_api"):
                        findings.append(
                            Finding(
                                "boundary",
                                rel,
                                node.lineno,
                                "plugins may import only engine.plugin_api from the engine",
                            )
                        )
                    if head in NETWORK_MODULES:
                        findings.append(
                            Finding("boundary", rel, node.lineno, f"bundled plugins use the core's clients, not {head}")
                        )
    return findings


def scan_config_coverage() -> list[Finding]:
    findings = []

    def walk(model: type[BaseModel], where: str) -> None:
        for key, info in model.model_fields.items():
            path = f"{where}.{key}"
            if not info.description:
                findings.append(Finding("config", "engine/config/schema.py", 0, f"{path} has no description"))
            if info.is_required():
                findings.append(Finding("config", "engine/config/schema.py", 0, f"{path} has no default"))
            for inner in _models_in(info.annotation):
                walk(inner, path)

    for name, model in FILES.items():
        walk(model, name)
    return findings


def _models_in(annotation: object) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return [m for arg in get_args(annotation) for m in _models_in(arg)]


# ---- helpers ---------------------------------------------------------------------------------------------------------


def _imported(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return [node.module]
    return []


def _comments(path: Path) -> Iterator[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT:
                    yield tok.start[0], tok.string
        except (tokenize.TokenError, IndentationError):
            return
    elif path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        for n, line in enumerate(text.splitlines(), 1):
            if "//" in line:
                yield n, line.split("//", 1)[1]
    elif path.suffix in {".yaml", ".yml"}:
        for n, line in enumerate(text.splitlines(), 1):
            if "#" in line:
                yield n, line.split("#", 1)[1]
