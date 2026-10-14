"""Write the plugin developer guide from the code, so it can't drift from what the host does.

`python -m engine.plugin_guide` writes docs/plugin-guide.md; the self-check fails when the committed file is stale.
Everything in the guide comes from docstrings, field descriptions, `#:` attribute comments and the host's own tables
(events, settings, core records), so a change to the API changes the guide in the same commit.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import sys
import typing
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

GUIDE_PATH = Path(__file__).resolve().parents[1] / "docs" / "plugin-guide.md"


# ---- rendering helpers -----------------------------------------------------------------------------------------------


def _type(annotation: Any) -> str:
    """A readable type: `list[str]`, `str | None`, `Literal['a', 'b']`."""
    if isinstance(annotation, str):
        text = annotation
    elif isinstance(annotation, type) and not typing.get_args(annotation):
        text = annotation.__name__
    else:
        text = repr(annotation)
    text = re.sub(r"<class '([\w.]+)'>", r"\1", text)
    text = re.sub(r"\b(?:typing|collections\.abc|engine(?:\.\w+)*|pydantic(?:\.\w+)*)\.", "", text)
    text = text.replace("NoneType", "None").replace("Annotated[", "Annotated[")
    return text


def _doc(obj: Any) -> str:
    """The object's own docstring: a class never borrows its base class's."""
    if inspect.isclass(obj):
        own = obj.__dict__.get("__doc__")
        doc = inspect.cleandoc(own) if isinstance(own, str) else ""
    else:
        doc = inspect.getdoc(obj) or ""
    return "" if doc.startswith("!!! abstract") or doc.startswith(getattr(obj, "__name__", "\0") + "(") else doc


def _para(text: str) -> str:
    """A docstring as Markdown: paragraphs kept, wrapped lines joined, indented blocks kept as code."""
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        if lines and all(line.startswith("    ") for line in lines):
            out.append("```\n" + "\n".join(line[4:] for line in lines) + "\n```")
        elif block.strip():
            out.append(" ".join(line.strip() for line in lines))
    return "\n\n".join(out)


def _cell(text: Any) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _default(value: Any) -> str:
    if value is PydanticUndefined or value is dataclasses.MISSING:
        return "required"
    return f"`{value!r}`"


def _table(header: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _attribute_docs(source_of: Any) -> dict[str, str]:
    """`#:` comments above attributes or constants, by name."""
    docs: dict[str, str] = {}
    pending: list[str] = []
    for line in inspect.getsource(source_of).splitlines():
        stripped = line.strip()
        if stripped.startswith("#:"):
            pending.append(stripped[2:].strip())
            continue
        match = re.match(r"(\w+)\s*(?::[^=]+)?(?:=|$)", stripped)
        if pending and match:
            docs[match.group(1)] = " ".join(pending)
        if not stripped.startswith("#"):
            pending = []
    return docs


def _model_rows(model: type[BaseModel], prefix: str = "") -> list[list[str]]:
    """Every field of a pydantic model, nested models flattened into dotted paths."""
    rows = []
    for name, info in model.model_fields.items():
        path = f"{prefix}{info.alias or name}"
        if info.default_factory is not None:
            try:
                default = _default(info.default_factory())
            except TypeError:
                default = "computed"
        else:
            default = _default(info.default)
        nested = _nested_model(info.annotation)
        if nested is not None and nested is not model:
            default = "see below" if default not in ("required", "`[]`") else default
            rows.append([f"`{path}`", _type(info.annotation), default, info.description or ""])
            many = typing.get_origin(info.annotation) is list or "list[" in str(info.annotation)
            rows += _model_rows(nested, f"{path}[]." if many else f"{path}.")
        else:
            rows.append([f"`{path}`", _type(info.annotation), default, info.description or ""])
    return rows


def _nested_model(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in typing.get_args(annotation):
        found = _nested_model(arg)
        if found is not None:
            return found
    return None


def _dataclass_rows(cls: type) -> list[list[str]]:
    rows = []
    for f in dataclasses.fields(cls):
        if f.name.startswith("_"):
            continue
        default = f.default if f.default_factory is dataclasses.MISSING else f.default_factory()
        rows.append([f"`{f.name}`", _type(f.type), _default(default)])
    return rows


def _methods(cls: type, owner: str) -> str:
    out = []
    for name, member in cls.__dict__.items():
        if name.startswith("_") or not callable(member):
            continue
        signature = str(inspect.signature(member)).replace("(self, ", "(").replace("(self)", "()")
        signature = re.sub(r"(: |-> )'([^']*)'", r"\1\2", signature)
        out.append(_join(f"#### `{owner}.{name}{signature}`", _para(_doc(member))))
    return "\n\n".join(out)


def _section(title: str, *parts: str) -> str:
    return _join(f"## {title}", *parts)


def _join(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


# ---- the guide -------------------------------------------------------------------------------------------------------


def build() -> str:
    import engine.plugin_api as api
    import engine.plugin_api.testing as testing
    from engine import actions, pack_check, plugin_host, plugin_manifest, texts, tools, working
    from engine.config.schema import FileLimits, PluginSettings
    from engine.ops import OP_MODELS
    from engine.records import REGISTRY

    constants = _attribute_docs(api)
    parts = [
        "# Plugin developer guide",
        "<!-- Generated by `uv run python -m engine.plugin_guide` from the host's code. Do not edit by hand. -->",
        f"Plugin API **{api.PLUGIN_API_VERSION}**. Declare `plugin_api: '>={_minor(api.PLUGIN_API_VERSION)},<"
        f"{_next_minor(api.PLUGIN_API_VERSION)}'` in the manifest: 0.x minor versions may break, so a manifest for an"
        " earlier minor version is refused. This guide is generated from the code and is the contract; names here are"
        " the names in the code. `docs/plugin-api-0.x.md` says what changed in each version.",
        _para(_doc(api)),
        "Import everything from `engine.plugin_api`: "
        + ", ".join(f"`{n}`" for n in api.__all__)
        + ". Nothing else in the host is an API.",
        _section(
            "The manifest: plugin.yaml",
            _para(_doc(plugin_manifest)),
            _table(["Key", "Type", "Default", "What it is"], _model_rows(plugin_manifest.Manifest)),
            "### Not yet available\n\nA non-empty value for any of these keys turns the plugin off with the reason.\n\n"
            + _table(["Key", "For"], [[f"`{k}`", v] for k, v in plugin_manifest.NOT_YET.items()]),
        ),
        _section(
            "Settings",
            _para(_doc(api.Settings)),
            _table(["Field", "Type", "Default", "What it is"], _model_rows(api.Settings)),
        ),
        _section("Registering", _para(_doc(api.Registrar)), _methods(api.Registrar, "registrar")),
        _section(
            "Record types",
            _para(_doc(api.Record)),
            _table(
                ["Class variable", "Type", "What it is"],
                [
                    [f"`{name}`", _type(ann), doc]
                    for name, ann in api.Record.__annotations__.items()
                    if "ClassVar" in str(ann)
                    for doc in [_attribute_docs(api.Record).get(name, "")]
                ],
            ),
            "### References\n\n" + _para(_doc(api.RefTo)),
        ),
        _section(
            "Ops",
            _para(_doc(api.OpModel)),
            _table(["Field", "Type", "Default", "What it is"], _model_rows(api.OpModel)),
            f"#### `op.describe()`\n\n{_para(_doc(api.OpModel.describe))}",
            f"Tiers: {', '.join(f'`{t}`' for t in typing.get_args(api.Tier))}; plugin ops are `data` or `system`.",
            "### The writer\n\n" + _para(_doc(api.OpWriter)),
            _methods(api.OpWriter, "writer"),
            "### Evidence\n\n" + _para(_doc(api.EvidenceIn)),
            _table(["Field", "Type", "Default", "What it is"], _model_rows(api.EvidenceIn)),
        ),
        _section(
            "Reading records",
            _para(_doc(api.ReadView)),
            _methods(api.ReadView, "view"),
            f"`ANY`: {constants.get('ANY', '')}",
            "### Stored\n\n" + _para(_doc(api.Stored)),
            _table(["Field", "Type", "Default"], _dataclass_rows(api.Stored)),
        ),
        _section(
            "Events",
            "Subscribe in the manifest and register one handler per event with `registrar.subscribe`. A subscription "
            "may name `kinds` only for these events: "
            + ", ".join(f"`{e}`" for e in sorted(plugin_host.EVENTS_WITH_KIND))
            + ".",
            "\n\n".join(
                f"### `{event}`\n\n{meaning}\n\n"
                + _table(["Payload field", "What it is"], [[f"`{k}`", v] for k, v in fields.items()])
                for event, (meaning, fields) in plugin_host.EVENT_SPECS.items()
            ),
            "### The handler's context\n\n" + _para(_doc(api.EventContext)),
            _methods(api.EventContext, "context"),
        ),
        _section(
            "Stages",
            "### StageDefinition\n\n" + _para(_doc(api.StageDefinition)),
            _table(["Field", "Type", "Default", "What it is"], _model_rows(api.StageDefinition)),
            "### StageCheckResult\n\n" + _para(_doc(api.StageCheckResult)),
            _table(["Field", "Type", "Default"], _dataclass_rows(api.StageCheckResult)),
        ),
        _section(
            "Person actions",
            _para(_doc(actions)),
            "### The action's context\n\n" + _para(_doc(api.ActionContext)),
            _methods(api.ActionContext, "context"),
            "\n\n".join(
                _join(f"### {cls.__name__}", _para(_doc(cls)))
                + "\n\n"
                + _table(["Field", "Type", "Default"], _dataclass_rows(cls))
                for cls in (api.Proposal, api.Item, api.Group, api.Choice, api.NewFile, api.Preview)
            ),
            "Previews may be: " + ", ".join(f"`{t}`" for t in sorted(actions.PREVIEW_TYPES)) + ".",
            "Core ops an action may propose: " + ", ".join(f"`{o}`" for o in sorted(actions.ACTION_CORE_OPS)) + ".",
        ),
        _section(
            "AI task kinds",
            "Registered with `registrar.task_kind` (see Registering). A task kind with a `packet` function returns "
            "what each run sees:",
            "\n\n".join(
                _join(f"### {cls.__name__}", _para(_doc(cls)))
                + "\n\n"
                + _table(["Field", "Type", "Default"], _dataclass_rows(cls))
                for cls in (api.PacketParts, api.Part, api.KnowledgeParts)
            ),
            "### PacketContext\n\n" + _para(_doc(api.PacketContext)),
            _methods(api.PacketContext, "view"),
        ),
        _section(
            "Lints",
            "Registered with `registrar.lint` (see Registering).",
            _join("### LintFinding", _para(_doc(api.LintFinding)))
            + "\n\n"
            + _table(["Field", "Type", "Default"], _dataclass_rows(api.LintFinding)),
        ),
        _section(
            "Long text",
            _para(_doc(texts)),
            _join("### LongText", _para(_doc(api.LongText)))
            + "\n\n"
            + _table(["Field", "Type", "Default"], _dataclass_rows(api.LongText)),
            _join("### Unit", _para(_doc(api.Unit)))
            + "\n\n"
            + _table(["Field", "Type", "Default"], _dataclass_rows(api.Unit)),
            "Core formats: " + ", ".join(f"`{f}`" for f in texts.CORE_FORMATS) + ". Read a field with "
            "`view.text(record, field)`, its versions with `view.text_versions(record, field)` and who wrote what "
            "with `view.authorship(record, field)`; write one of your own with `writer.set_text` in an op, or propose "
            "the core ops `text.edit` and `text.propose` from an action. The `text_version` record and the text ops "
            "are under Core records and Core ops.",
        ),
        _section(
            "Working copies",
            _para(_doc(working)),
            "Registered with `registrar.working_copy` (see Registering). The `working_copy` record is under Core "
            "records.",
            _join("### TakeBack", _para(_doc(api.TakeBack)))
            + "\n\n"
            + _table(["Field", "Type", "Default"], _dataclass_rows(api.TakeBack)),
            "### WorkingCopyContext\n\n" + _para(_doc(api.WorkingCopyContext)),
        ),
        _section(
            "Programs",
            _para(_doc(tools)),
            "### `context.tools`\n\n" + _para(_doc(api.ToolBox)),
            _methods(api.ToolBox, "context.tools"),
            "### ToolResult\n\n" + _para(_doc(api.ToolResult)),
            _table(["Field", "Type", "Default"], _dataclass_rows(api.ToolResult)),
        ),
        _section("Publishing a pack", _para(_doc(pack_check))),
        _section(
            "Wording",
            "A plugin's wording files (`provides.wording`) may set these keys for identifiers in its own namespace; "
            "the screens read nothing else from them. The workspace's `ui.wording` overrides any of them.",
            _table(["Key", "What it names"], [[f"`{k}`", v] for k, v in plugin_host.WORDING_KEYS.items()]),
        ),
        _section(
            "Connectors",
            "What `registrar.connector`'s `poll` returns and raises.",
            "### SourceItem\n\n" + _para(_doc(api.SourceItem)),
            _table(["Field", "Type", "Default"], _dataclass_rows(api.SourceItem)),
            "### EventDetails\n\n" + _para(_doc(api.EventDetails)),
            _table(["Field", "Type", "Default"], _dataclass_rows(api.EventDetails)),
            "### MessageDetails\n\n" + _para(_doc(api.MessageDetails)),
            _table(["Field", "Type", "Default"], _dataclass_rows(api.MessageDetails)),
            "### Poll\n\n" + _para(_doc(api.Poll)),
            _table(["Field", "Type", "Default"], _dataclass_rows(api.Poll)),
            "### ConnectorError\n\n" + _para(_doc(api.ConnectorError)),
            "### Testing a connector: `engine.plugin_api.testing`\n\n" + _para(_doc(testing)),
            "\n\n".join(
                _join(f"#### `{name}{inspect.signature(getattr(testing, name))}`", _para(_doc(getattr(testing, name))))
                for name in ("connector_context", "read")
            ),
            "#### Reply and Asked\n\n" + _para(_doc(testing.Reply)) + " " + _para(_doc(testing.Asked)),
            "### Testing everything else: `plugin_workspace`\n\n"
            + _join(
                f"#### `plugin_workspace{inspect.signature(testing.plugin_workspace)}`",
                _para(_doc(testing.plugin_workspace)),
            ),
            _para(_doc(testing.PluginWorkspace)),
            _methods(testing.PluginWorkspace, "ws"),
            "\n\n".join(
                _join(f"#### {cls.__name__}", _para(_doc(cls)))
                for cls in (
                    testing.Outcome,
                    testing.AskResult,
                    testing.ActionResult,
                    testing.PluginState,
                    testing.SavedWorkspace,
                    testing.PluginDidNotStart,
                )
            ),
        ),
        _section(
            "Errors",
            _table(
                ["Error", "Meaning"],
                [
                    [f"`{e.__name__}`", _doc(e)]
                    for e in (api.StoreError, api.NeedsPerson, api.PluginMisuse, api.ToolError)
                ],
            ),
        ),
        _section(
            "Settings that limit plugins",
            "In the workspace's `config/workspace.yaml`; the person can change them.",
            _table(["Key", "Type", "Default", "What it is"], _model_rows(PluginSettings, "workspace.plugins.")),
            "Files, in `config/storage.yaml`. A file kind keeps only the media types listed here; the plugin's status "
            "notes any it loses.",
            _table(["Key", "Type", "Default", "What it is"], _model_rows(FileLimits, "storage.files.")),
        ),
        _section(
            "Core records",
            "Plugins read these and refer to them with `RefTo`; they change only through core ops.",
            "\n\n".join(
                _join(f"### `{kind}` ({model.prefix}-n)", _para(_doc(model)))
                + "\n\n"
                + _table(
                    ["Field", "Type", "Default", "What it is"],
                    [r for r in _model_rows(model) if r[0] not in ("`id`", "`ext`", "`stage`")],
                )
                for kind, model in REGISTRY.items()
            ),
        ),
        _section(
            "Core ops",
            "Fields of each core op, for actions and task kinds that use them.",
            "\n\n".join(
                _join(f"### `{name}`", _para(_doc(model)))
                + "\n\n"
                + _table(["Field", "Type", "Default", "What it is"], [r for r in _model_rows(model) if r[0] != "`op`"])
                for name, model in sorted(OP_MODELS.items())
            ),
        ),
    ]
    return "\n\n".join(p for p in parts if p).rstrip() + "\n"


def _minor(version: str) -> str:
    major, minor, *_ = version.split(".")
    return f"{major}.{minor}"


def _next_minor(version: str) -> str:
    major, minor, *_ = version.split(".")
    return f"{major}.{int(minor) + 1}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else GUIDE_PATH
    target.write_text(build(), encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
