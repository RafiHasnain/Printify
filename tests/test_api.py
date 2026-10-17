import pytest
from fastapi.testclient import TestClient

from printify import config as config_mod
from printify.config import Config
from printify.main import create_app, safe_filename


class FakeBackend:
    name = "Fake Printer"

    def __init__(self):
        self.printed = []
        self.fail = None

    def info(self):
        return {"name": self.name, "status": ["Ready"], "jobs": 0,
                "caps": {"duplex": None, "color": False, "papers": ["a4"]}}

    def jobs(self):
        return [{"id": 1, "document": "x.pdf", "user": "u", "status": "Printing", "pages": 1, "printed": 0}]

    def print_pdf(self, pdf, opts):
        if self.fail:
            raise self.fail
        assert pdf.is_file()
        self.printed.append((pdf.name, opts))


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    return Config(max_upload_mb=1)


@pytest.fixture
def client(cfg, backend):
    return TestClient(create_app(cfg, backend))


def post(client, data: bytes, name="report.pdf", **form):
    return client.post("/api/print", files={"file": (name, data, "application/pdf")}, data=form)


def test_index_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/health").json() == {"ok": True}


def test_printer_info(client):
    body = client.get("/api/printer").json()
    assert body["name"] == "Fake Printer" and body["caps"]["color"] is False


def test_jobs(client):
    assert client.get("/api/jobs").json()["jobs"][0]["status"] == "Printing"


def test_print_ok(client, backend, pdf_bytes):
    r = post(client, pdf_bytes, copies="2", pages="1-2", duplex="long", color="mono", paper="A4", scale="fit")
    assert r.status_code == 200, r.text
    assert r.json()["pages"] == 3
    name, opts = backend.printed[0]
    assert name == "report.pdf"
    assert (opts.copies, opts.pages, opts.duplex, opts.color, opts.paper) == (2, "1-2", "long", "mono", "a4")


def test_temp_files_removed(client, cfg, pdf_bytes):
    post(client, pdf_bytes)
    assert list(cfg.tmp_dir.iterdir()) == []


def test_reject_non_pdf(client, backend):
    r = post(client, b"not a pdf", name="evil.pdf")
    assert r.status_code == 400 and "not a PDF" in r.json()["error"]
    assert backend.printed == []


def test_reject_bad_range(client, pdf_bytes):
    r = post(client, pdf_bytes, pages="2-9")
    assert r.status_code == 400 and "beyond the last page" in r.json()["error"]


def test_reject_bad_copies(client, pdf_bytes):
    assert post(client, pdf_bytes, copies="500").status_code == 400


def test_too_large(client):
    r = post(client, b"%PDF" + b"0" * (2 * 1024 * 1024))
    assert r.status_code == 413


def test_print_failure(client, backend, pdf_bytes):
    backend.fail = RuntimeError("SumatraPDF failed (exit 1).")
    r = post(client, pdf_bytes)
    assert r.status_code == 502 and "SumatraPDF failed" in r.json()["error"]


@pytest.mark.parametrize("raw, expected", [
    ("report.pdf", "report.pdf"),
    ("../../windows/system32/x.pdf", "x.pdf"),
    ("C:\\Users\\a\\file.PDF", "file.pdf"),
    ("", "document.pdf"),
    ("a<b>|c.pdf", "a_b__c.pdf"),
])
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected
