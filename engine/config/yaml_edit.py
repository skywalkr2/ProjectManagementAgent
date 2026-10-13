"""Changing one key in a config file's text while keeping its comments and layout.

Keys written in block style (`key: value` on its own line, children indented below) are edited in place: a value is
replaced on its line, a missing key is added at the end of its parent, and a removed key takes its children with it.
Anything else (a value inside a one-line `{...}` mapping, say) falls back to rewriting the file from its data, which
keeps the values but not the comments. The result is always checked by reading it back.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import yaml

from engine.yaml_load import load_yaml

_KEY = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_./-]+|\"[^\"]*\"|'[^']*'):(?P<rest>(?: .*)?)$")
_MISSING = object()


class _Fallback(Exception):
    pass


def set_key(text: str, path: list[str], value: Any) -> str:
    """The file's text with the key at `path` set to `value`."""
    data = load_yaml(text) or {}
    expected = copy.deepcopy(data)
    _set(expected, path, value)
    try:
        edited = _set_lines(text.splitlines(), path, value)
        result = "\n".join(edited) + "\n"
        if (load_yaml(result) or {}) == expected:
            return result
    except (_Fallback, yaml.YAMLError):
        pass
    return yaml.safe_dump(expected, sort_keys=False, allow_unicode=True)


def remove_key(text: str, path: list[str]) -> str:
    """The file's text without the key at `path` (so it goes back to its default). A missing key changes nothing."""
    data = load_yaml(text) or {}
    expected = copy.deepcopy(data)
    if not _remove(expected, path):
        return text
    try:
        edited = _remove_lines(text.splitlines(), path)
        result = "\n".join(edited) + "\n"
        if (load_yaml(result) or {}) == expected:
            return result
    except (_Fallback, yaml.YAMLError):
        pass
    return yaml.safe_dump(expected, sort_keys=False, allow_unicode=True)


def get_key(data: Any, path: list[str]) -> Any:
    """The value at `path` in loaded data, or a marker for missing (see `has_key`)."""
    for part in path:
        if not isinstance(data, dict) or part not in data:
            return _MISSING
        data = data[part]
    return data


def has_key(data: Any, path: list[str]) -> bool:
    return get_key(data, path) is not _MISSING


# ---- data ------------------------------------------------------------------------------------------------------------


def _set(data: dict[str, Any], path: list[str], value: Any) -> None:
    for part in path[:-1]:
        child = data.get(part)
        if not isinstance(child, dict):
            child = {}
            data[part] = child
        data = child
    data[path[-1]] = value


def _remove(data: dict[str, Any], path: list[str]) -> bool:
    for part in path[:-1]:
        if not isinstance(data.get(part), dict):
            return False
        data = data[part]
    if path[-1] not in data:
        return False
    del data[path[-1]]
    return True


# ---- lines -----------------------------------------------------------------------------------------------------------


def _significant(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _key_of(line: str) -> tuple[int, str, str] | None:
    match = _KEY.match(line)
    if match is None:
        return None
    key = match["key"]
    if key[0] in "\"'":
        key = key[1:-1]
    return len(match["indent"]), key, match["rest"]


def _block_end(lines: list[str], start: int, indent: int) -> int:
    """The first line after `start` that is significant and indented `indent` or less (the end of start's block). A
    list item at the key's own indent (`key:` then `- item` below it, as many writers lay lists out) is in the block."""
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not _significant(line) or _indent(line) > indent:
            continue
        if _indent(line) == indent and line.lstrip(" ").startswith(("- ", "-\t")) or line.strip() == "-":
            continue
        return i
    return len(lines)


def _content_end(lines: list[str], start: int, end: int) -> int:
    """One past the last significant line in [start, end): blank lines and comments after a block stay put."""
    last = max((i for i in range(start, end) if _significant(lines[i])), default=start - 1)
    return last + 1


def _children(lines: list[str], start: int, end: int) -> tuple[int, int] | None:
    """(first child line, child indent) of the block between start and end, or None when it has none."""
    for i in range(start, end):
        if _significant(lines[i]):
            return i, _indent(lines[i])
    return None


def _find(lines: list[str], start: int, end: int, indent: int, key: str) -> int | None:
    for i in range(start, end):
        if not _significant(lines[i]) or _indent(lines[i]) != indent:
            continue
        parsed = _key_of(lines[i])
        if parsed is not None and parsed[1] == key:
            return i
    return None


def _value_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _comment(rest: str) -> str:
    """A trailing ` # comment` after a plain or quoted scalar, kept when the value changes."""
    quote = None
    for i, ch in enumerate(rest):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and i > 0 and rest[i - 1] == " ":
            return "   " + rest[i:].strip()
    return ""


def _locate_parent(lines: list[str], path: list[str], create: bool) -> tuple[list[str], int, int, int]:
    """The line range of the mapping that holds the last key in `path`, and the indent its keys use; parents that are
    missing are added when `create` is set."""
    start, end, indent = 0, len(lines), 0
    for part in path[:-1]:
        at = _find(lines, start, end, indent, part)
        if at is None:
            if not create:
                raise _Fallback
            lines[end:end] = [" " * indent + f"{_quote(part)}:"]
            at = end
        parsed = _key_of(lines[at])
        assert parsed is not None
        rest = parsed[2].strip()
        if rest and not rest.startswith("#"):
            if rest.split("#", 1)[0].strip() in ("{}", "null", "~") and create:
                lines[at] = " " * indent + f"{_quote(part)}:"
            else:
                raise _Fallback  # the parent's value is written on its own line; edit the data instead
        block_end = _block_end(lines, at, indent)
        child = _children(lines, at + 1, block_end)
        start, end = at + 1, block_end
        indent = child[1] if child else indent + 2
    return lines, start, end, indent


def _quote(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_./-]+", key) else json.dumps(key)


def _set_lines(lines: list[str], path: list[str], value: Any) -> list[str]:
    lines = list(lines)
    lines, start, end, indent = _locate_parent(lines, path, create=True)
    at = _find(lines, start, end, indent, path[-1])
    rendered = " " * indent + f"{_quote(path[-1])}: {_value_text(value)}"
    if at is None:
        # Add it after the last significant line of the parent's block, so trailing comments stay where they are.
        last = max((i for i in range(start, end) if _significant(lines[i])), default=start - 1)
        lines.insert(last + 1, rendered)
        return lines
    parsed = _key_of(lines[at])
    assert parsed is not None
    rest = parsed[2]
    block_end = _block_end(lines, at, indent)
    has_children = any(_significant(lines[i]) for i in range(at + 1, block_end))
    lines[at] = rendered + ("" if has_children else _comment(rest))
    if has_children:
        del lines[at + 1 : _content_end(lines, at + 1, block_end)]
    return lines


def _remove_lines(lines: list[str], path: list[str]) -> list[str]:
    lines = list(lines)
    lines, start, end, indent = _locate_parent(lines, path, create=False)
    at = _find(lines, start, end, indent, path[-1])
    if at is None:
        raise _Fallback
    block_end = _content_end(lines, at, _block_end(lines, at, indent))
    # Comment lines directly above the key describe it, so they go with it.
    first = at
    while first > start and lines[first - 1].strip().startswith("#") and _indent(lines[first - 1]) == indent:
        first -= 1
    del lines[first:block_end]
    if len(path) > 1 and not any(_significant(lines[i]) for i in range(start, end - (block_end - first))):
        parent = start - 1
        parsed = _key_of(lines[parent])
        if parsed is not None:
            lines[parent] = " " * parsed[0] + f"{_quote(parsed[1])}: {{}}"
    return lines
