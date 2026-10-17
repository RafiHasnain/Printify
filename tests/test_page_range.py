import pytest

from printify.pdfcheck import PdfError, page_count, parse_page_range


@pytest.mark.parametrize("text, expected", [
    ("", ""),
    ("  ", ""),
    ("1", "1"),
    ("1-3", "1-3"),
    ("1-3, 5", "1-3,5"),
    ("2-2", "2"),
    (" 1 - 2 ,4", "1-2,4"),
])
def test_valid_ranges(text, expected):
    assert parse_page_range(text, 5) == expected


@pytest.mark.parametrize("text", ["0", "3-1", "1-6", "6", "a", "1-", "1,,2", "-2", "1-2-3"])
def test_invalid_ranges(text):
    with pytest.raises(PdfError):
        parse_page_range(text, 5)


def test_page_count(tmp_path, pdf_bytes):
    f = tmp_path / "a.pdf"
    f.write_bytes(pdf_bytes)
    assert page_count(f) == 3


def test_not_a_pdf(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"hello world")
    with pytest.raises(PdfError, match="not a PDF"):
        page_count(f)


def test_broken_pdf(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4\ngarbage")
    with pytest.raises(PdfError):
        page_count(f)
