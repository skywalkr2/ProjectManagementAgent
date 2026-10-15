"""Tiny files with made-up text, built in memory: what each reader checks itself on at startup, and what tests read.

Each builder takes the body text it should hold and makes the smallest file of its kind that has a title, a body, a
table or cells, a comment or a note, so a reader that has stopped working on any of them shows.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from xml.sax.saxutils import escape

from engine.extract import DOCUMENT, PDF, PRESENTATION, SPREADSHEET

AUTHOR = "Reviewer"
TITLE = "Harbor lantern plan"
BODY = "The lanterns are hung on the second quay before the evening tide."
CELL = "Mooring fee"
COMMENT = "Check the tide table before hanging them."
NOTE = "Mention the volunteer rota here."

_NS = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/></Types>'
)


WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def empty_document() -> bytes:
    """A document with one paragraph and nothing in it."""
    return _zip({"word/document.xml": f'<w:document xmlns:w="{WORD}"><w:body><w:p/></w:body></w:document>'})


def zipped(parts: dict[str, str]) -> bytes:
    """Any parts of text in a zip, with no checks on them, for files that are wrong on purpose."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in parts.items():
            archive.writestr(_entry(name), body)
    return buffer.getvalue()


def _zip(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_entry("[Content_Types].xml"), _TYPES)
        for name, body in parts.items():
            archive.writestr(_entry(name), '<?xml version="1.0" encoding="UTF-8"?>' + body)
    return buffer.getvalue()


def _entry(name: str) -> zipfile.ZipInfo:
    """An entry with a fixed time, so the same parts always make the same bytes."""
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _rels(*entries: tuple[str, str, str]) -> str:
    inner = "".join(f'<Relationship Id="{i}" Type="{_REL}/{kind}" Target="{target}"/>' for i, kind, target in entries)
    return f"<Relationships {_NS}>{inner}</Relationships>"


def document(title: str = TITLE, body: str = BODY, comment: str = COMMENT) -> bytes:
    w = f'xmlns:w="{WORD}"'
    paragraphs = f"<w:p><w:r><w:t>{escape(title)}</w:t></w:r></w:p><w:p><w:r><w:t>{escape(body)}</w:t></w:r></w:p>"
    table = (
        f"<w:tbl><w:tr><w:tc><w:p><w:r><w:t>{escape(CELL)}</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>12</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    comments = (
        f'<w:comments {w}><w:comment w:id="0" w:author="{AUTHOR}">'
        f"<w:p><w:r><w:t>{escape(comment)}</w:t></w:r></w:p></w:comment></w:comments>"
    )
    return _zip(
        {
            "word/document.xml": f"<w:document {w}><w:body>{paragraphs}{table}</w:body></w:document>",
            "word/comments.xml": comments,
        }
    )


def spreadsheet(title: str = TITLE, comment: str = COMMENT) -> bytes:
    s = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    r = f'xmlns:r="{_REL}"'
    return _zip(
        {
            "xl/workbook.xml": (
                f'<workbook {s} {r}><sheets><sheet name="Costs" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": _rels(("rId1", "worksheet", "worksheets/sheet1.xml")),
            "xl/sharedStrings.xml": f"<sst {s}><si><t>{escape(title)}</t></si><si><t>{escape(CELL)}</t></si></sst>",
            "xl/worksheets/sheet1.xml": (
                f'<worksheet {s}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row>'
                '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>12</v></c></row></sheetData></worksheet>'
            ),
            "xl/worksheets/_rels/sheet1.xml.rels": _rels(("rId1", "comments", "../comments1.xml")),
            "xl/comments1.xml": (
                f"<comments {s}><authors><author>{AUTHOR}</author></authors><commentList>"
                f'<comment ref="B2" authorId="0"><text><r><t>{escape(comment)}</t></r></text></comment>'
                "</commentList></comments>"
            ),
        }
    )


def presentation(title: str = TITLE, body: str = BODY, note: str = NOTE) -> bytes:
    a = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    p = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    r = f'xmlns:r="{_REL}"'

    def paragraph(text: str) -> str:
        return f"<a:p><a:r><a:t>{escape(text)}</a:t></a:r></a:p>"

    slide = (
        f"<p:sld {a} {p}><p:cSld><p:spTree><p:sp><p:txBody>{paragraph(title)}{paragraph(body)}</p:txBody></p:sp>"
        f"<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody>{paragraph(CELL)}</a:txBody></a:tc>"
        f"<a:tc><a:txBody>{paragraph('12')}</a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
        "</p:spTree></p:cSld></p:sld>"
    )
    notes = (
        f"<p:notes {a} {p}><p:cSld><p:spTree><p:sp><p:txBody>"
        '<a:p><a:fld type="slidenum"><a:t>1</a:t></a:fld></a:p>'
        f"{paragraph(note)}</p:txBody></p:sp></p:spTree></p:cSld></p:notes>"
    )
    return _zip(
        {
            "ppt/presentation.xml": (
                f'<p:presentation {p} {r}><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'
            ),
            "ppt/_rels/presentation.xml.rels": _rels(("rId1", "slide", "slides/slide1.xml")),
            "ppt/slides/slide1.xml": slide,
            "ppt/slides/_rels/slide1.xml.rels": _rels(("rId1", "notesSlide", "../notesSlides/notesSlide1.xml")),
            "ppt/notesSlides/notesSlide1.xml": notes,
        }
    )


def pdf(text: str = TITLE) -> bytes:
    """A one-page PDF whose page shows `text` in a standard font."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return bytes(out)


def text() -> bytes:
    return f"{TITLE}\n{BODY}\n".encode()


#: Each reader's own check: the kind, the file's media type, how to build it and the words that must come back.
CHECKS: dict[str, tuple[str, Callable[[], bytes], tuple[str, ...]]] = {
    "document": (DOCUMENT, document, (TITLE, BODY, CELL, COMMENT)),
    "spreadsheet": (SPREADSHEET, spreadsheet, (TITLE, CELL, COMMENT)),
    "presentation": (PRESENTATION, presentation, (TITLE, BODY, CELL, NOTE)),
    "pdf": (PDF, pdf, (TITLE,)),
    "text": ("text/plain", text, (TITLE, BODY)),
}
