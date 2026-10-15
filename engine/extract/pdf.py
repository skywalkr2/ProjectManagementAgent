"""The PDF reader: the text layer of each page, in page order, read with a pure-Python library."""

from __future__ import annotations

import io

from engine.extract.core import Extracted, ExtractError, Text

DAMAGED = "the PDF is damaged or can't be read"


def read_pdf(data: bytes, limit: int) -> Extracted:
    from pypdf import PdfReader

    out = Text(limit)
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractError("the PDF is locked with a password")
        for number, page in enumerate(reader.pages, 1):
            if out.full:
                break
            text = (page.extract_text() or "").strip()
            if text:
                out.line(f"Page {number}:")
                out.line(text)
    except ExtractError:
        raise
    except Exception:  # the library raises many kinds of error for a malformed file
        raise ExtractError(DAMAGED) from None
    return out.result()
