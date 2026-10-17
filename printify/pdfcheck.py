"""PDF validation and page-range parsing."""

import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

_RANGE_PART = re.compile(r"^(\d+)(?:-(\d+))?$")


class PdfError(ValueError):
    """User-facing error about the uploaded file or its options."""


def page_count(path: Path) -> int:
    """Return the page count, or raise PdfError if the file isn't a readable PDF."""
    with path.open("rb") as f:
        if b"%PDF" not in f.read(1024):
            raise PdfError("This file is not a PDF.")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfError("This PDF is password-protected.")
        n = len(reader.pages)
    except PdfReadError as e:
        raise PdfError(f"Could not read this PDF ({e}).") from e
    if n == 0:
        raise PdfError("This PDF has no pages.")
    return n


def parse_page_range(text: str, pages: int) -> str:
    """Validate a range like "1-3, 5" against the page count.

    Returns a normalized range ("1-3,5") or "" for all pages.
    """
    text = text.strip().replace(" ", "")
    if not text:
        return ""
    parts = []
    for part in text.split(","):
        m = _RANGE_PART.match(part)
        if not m:
            raise PdfError(f'Invalid page range "{part}". Use a format like 1-3,5.')
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        if start < 1 or end < start:
            raise PdfError(f'Invalid page range "{part}".')
        if end > pages:
            raise PdfError(f'Page range "{part}" is beyond the last page ({pages}).')
        parts.append(f"{start}-{end}" if end != start else str(start))
    return ",".join(parts)
