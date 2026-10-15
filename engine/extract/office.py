"""Readers for documents, spreadsheets and presentations: each is a zip of XML parts, read with the standard library.

Each reader takes the file's bytes and the most characters to keep, and returns the text it found, in reading order,
with a mark when it stopped at the limit. A file that can't be read raises `ExtractError` with the reason in words.
Markup that declares entities or a document type is refused, so a crafted file can't expand into more than it is.
Elements are matched by their local names, so a file written with another version of the format's namespaces reads the
same.
"""

from __future__ import annotations

import io
import posixpath
import xml.etree.ElementTree as ET
import zipfile

from engine.extract.core import Extracted, ExtractError, Text

#: The largest single part of a file read into memory, after unzipping.
MAX_PART_BYTES = 64 * 1024 * 1024

WRONG_KIND = "the file is damaged, or it isn't the kind of file its name says"


def _name(el: ET.Element) -> str:
    """An element's name without its namespace."""
    return el.tag.rsplit("}", 1)[-1]


def _kids(el: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in el if _name(child) == name]


def _kid(el: ET.Element | None, name: str) -> ET.Element | None:
    found = _kids(el, name) if el is not None else []
    return found[0] if found else None


def _all(el: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in el.iter() if _name(child) == name]


def _attribute(el: ET.Element, name: str) -> str | None:
    """An attribute by its local name, whatever namespace it is in."""
    for key, value in el.attrib.items():
        if key.rsplit("}", 1)[-1] == name:
            return value
    return None


def _relation_id(el: ET.Element) -> str | None:
    """The id of the relationship an element points to: its attribute named `id` that has a namespace (an element
    may also have a plain `id` of its own)."""
    for key, value in el.attrib.items():
        if key.startswith("{") and key.rsplit("}", 1)[-1] == "id":
            return value
    return None


def _open(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        raise ExtractError(WRONG_KIND) from None


def _part(archive: zipfile.ZipFile, name: str, *, required: bool = True) -> ET.Element | None:
    """One XML part of the archive, parsed; None when it isn't there and isn't required."""
    try:
        with archive.open(name) as handle:
            raw = handle.read(MAX_PART_BYTES + 1)
    except KeyError:
        if required:
            raise ExtractError(WRONG_KIND) from None
        return None
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
        raise ExtractError(
            "a part of the file can't be unpacked; it may be damaged or locked with a password"
        ) from None
    if len(raw) > MAX_PART_BYTES:
        raise ExtractError("a part of the file is too large to read")
    if b"<!ENTITY" in raw or b"<!DOCTYPE" in raw:
        raise ExtractError("the file holds markup that isn't safe to read")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise ExtractError("a part of the file is damaged") from None


def _relations(archive: zipfile.ZipFile, owner: str) -> dict[str, tuple[str, str]]:
    """The relationships of a part: id -> (type, the target's path in the archive)."""
    folder, name = posixpath.split(owner)
    root = _part(archive, posixpath.join(folder, "_rels", name + ".rels"), required=False)
    found: dict[str, tuple[str, str]] = {}
    for rel in root if root is not None else []:
        target = rel.get("Target") or ""
        path = target[1:] if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        found[rel.get("Id") or ""] = (rel.get("Type") or "", path)
    return found


def _related(archive: zipfile.ZipFile, owner: str, kind: str) -> list[str]:
    """The paths of the parts of one relationship kind (the last word of its type) that a part points to."""
    return [path for type_, path in _relations(archive, owner).values() if type_.rsplit("/", 1)[-1] == kind]


def _row(cells: list[str], out: Text) -> None:
    if any(cell.strip() for cell in cells):
        out.line(" | ".join(cells))


# ---- documents -------------------------------------------------------------------------------------------------------


def _paragraph(p: ET.Element) -> str:
    out = []
    for el in p.iter():
        name = _name(el)
        if name == "t":
            out.append(el.text or "")
        elif name == "tab":
            out.append("\t")
        elif name in ("br", "cr"):
            out.append("\n")
    return "".join(out)


def _cell(tc: ET.Element) -> str:
    return " ".join(t for p in _all(tc, "p") if (t := _paragraph(p).strip()))


def _blocks(parent: ET.Element, out: Text) -> None:
    for el in parent:
        if out.full:
            return
        name = _name(el)
        if name == "p":
            out.line(_paragraph(el))
        elif name == "tbl":
            for tr in _kids(el, "tr"):
                _row([_cell(tc) for tc in _kids(tr, "tc")], out)
        elif name == "sdt":
            content = _kid(el, "sdtContent")
            if content is not None:
                _blocks(content, out)
        elif name in ("ins", "customXml", "smartTag"):
            _blocks(el, out)


def read_document(data: bytes, limit: int) -> Extracted:
    """A word-processing document: its paragraphs and tables in order, then its comments."""
    archive = _open(data)
    body = _part(archive, "word/document.xml")
    out = Text(limit)
    holder = _kid(body, "body")
    if holder is not None:
        _blocks(holder, out)
    comments = _part(archive, "word/comments.xml", required=False)
    for comment in _all(comments, "comment") if comments is not None else []:
        author = (_attribute(comment, "author") or "").strip()
        said = _cell(comment)
        if said:
            out.line(f"Comment by {author}: {said}" if author else f"Comment: {said}")
    return out.result()


# ---- spreadsheets ----------------------------------------------------------------------------------------------------


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = _part(archive, "xl/sharedStrings.xml", required=False)
    found = []
    for si in _kids(root, "si") if root is not None else []:
        runs = [t.text or "" for t in _kids(si, "t")] + [t.text or "" for r in _kids(si, "r") for t in _kids(r, "t")]
        found.append("".join(runs))
    return found


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in _all(cell, "t"))
    raw = _kid(cell, "v")
    value = (raw.text or "") if raw is not None else ""
    if kind == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            return ""
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def _sheet_comments(archive: zipfile.ZipFile, sheet: str, out: Text) -> None:
    for path in _related(archive, sheet, "comments"):
        root = _part(archive, path, required=False)
        if root is None:
            continue
        authors = [(a.text or "").strip() for a in _all(root, "author")]
        for comment in _all(root, "comment"):
            index = comment.get("authorId")
            author = authors[int(index)] if index and index.isdigit() and int(index) < len(authors) else ""
            said = "".join(t.text or "" for t in _all(comment, "t")).strip()
            if said:
                out.line(f"Comment on {comment.get('ref')}" + (f" by {author}" if author else "") + f": {said}")


def read_spreadsheet(data: bytes, limit: int) -> Extracted:
    """A spreadsheet: for each sheet its name, then each row's filled cells as `A1: value`, then its comments."""
    archive = _open(data)
    workbook = _part(archive, "xl/workbook.xml")
    relations = _relations(archive, "xl/workbook.xml")
    shared = _shared_strings(archive)
    out = Text(limit)
    sheets = _kid(workbook, "sheets")
    for sheet in sheets if sheets is not None else []:
        if out.full:
            break
        target = relations.get(_relation_id(sheet) or "")
        if target is None:
            continue
        out.line(f"Sheet: {sheet.get('name') or ''}")
        root = _part(archive, target[1], required=False)
        for row in _all(root, "row") if root is not None else []:
            if out.full:
                break
            cells = [f"{c.get('r')}: {text}" for c in _kids(row, "c") if (text := _cell_text(c, shared).strip())]
            if cells:
                out.line(" | ".join(cells))
        _sheet_comments(archive, target[1], out)
    return out.result()


# ---- presentations ---------------------------------------------------------------------------------------------------


def _drawn_paragraph(p: ET.Element) -> str:
    out = []
    for el in p:
        name = _name(el)
        if name == "r":
            out.append("".join(t.text or "" for t in _kids(el, "t")))
        elif name == "br":
            out.append("\n")
        elif name == "fld" and not (el.get("type") or "").startswith("slidenum"):
            out.append("".join(t.text or "" for t in _kids(el, "t")))
    return "".join(out)


def _drawn_cell(tc: ET.Element) -> str:
    return " ".join(t for p in _all(tc, "p") if (t := _drawn_paragraph(p).strip()))


def _shapes(el: ET.Element, out: Text) -> None:
    for child in el:
        if out.full:
            return
        name = _name(child)
        if name == "tbl":
            for tr in _kids(child, "tr"):
                _row([_drawn_cell(tc) for tc in _kids(tr, "tc")], out)
        elif name == "p":
            out.line(_drawn_paragraph(child))
        else:
            _shapes(child, out)


def read_presentation(data: bytes, limit: int) -> Extracted:
    """A presentation: for each slide in order its text and tables, then its speaker notes."""
    archive = _open(data)
    presentation = _part(archive, "ppt/presentation.xml")
    relations = _relations(archive, "ppt/presentation.xml")
    listed = _kid(presentation, "sldIdLst")
    slides = [
        relations[rid][1] for s in (listed if listed is not None else []) if (rid := _relation_id(s)) in relations
    ]
    out = Text(limit)
    for number, path in enumerate(slides, 1):
        if out.full:
            break
        out.line(f"Slide {number}:")
        root = _part(archive, path, required=False)
        if root is not None:
            _shapes(root, out)
        for notes_path in _related(archive, path, "notesSlide"):
            notes = _part(archive, notes_path, required=False)
            held = Text(max(0, limit - out.size))
            if notes is not None:
                _shapes(notes, held)
            if held.parts:
                out.line("Speaker notes:")
                for line in held.parts:
                    out.line(line)
    return out.result()
