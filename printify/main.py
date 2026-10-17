"""FastAPI app: serves the web page and the print API."""

import logging
import re
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Config, load_config
from .pdfcheck import PdfError, page_count, parse_page_range
from .printer import make_backend
from .sumatra import PrintOptions

log = logging.getLogger("printify")
STATIC_DIR = Path(__file__).parent / "static"


def safe_filename(name: str) -> str:
    """Keep a readable name (it shows in the Windows queue) without path tricks."""
    # Browsers may send a full Windows path; strip directories for both separator styles.
    name = (name or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^\w.\- ()]", "_", name).strip(" .") or "document"
    stem = Path(name).stem[:100] or "document"
    return f"{stem}.pdf"


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def create_app(config: Config | None = None, backend=None) -> FastAPI:
    config = config or load_config()
    backend = backend or make_backend(config)
    print_lock = threading.Lock()

    shutil.rmtree(config.tmp_dir, ignore_errors=True)
    config.tmp_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Printify", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def limit_upload_size(request: Request, call_next):
        if request.url.path == "/api/print":
            length = request.headers.get("content-length")
            # Allow a little room for the multipart form fields around the file.
            if length and int(length) > config.max_upload_bytes + 64 * 1024:
                return error(413, f"File is too large (max {config.max_upload_mb} MB).")
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/printer")
    def printer_info():
        try:
            return {"ok": True, **backend.info(), "max_upload_mb": config.max_upload_mb}
        except Exception as e:
            log.exception("Printer info failed")
            return error(503, f"Printer not available: {e}")

    @app.get("/api/jobs")
    def jobs():
        try:
            return {"ok": True, "jobs": backend.jobs()}
        except Exception as e:
            log.exception("Listing jobs failed")
            return error(503, f"Could not read the print queue: {e}")

    @app.post("/api/print")
    def print_file(
        request: Request,
        file: UploadFile = File(...),
        copies: int = Form(1),
        pages: str = Form(""),
        duplex: str = Form("off"),
        color: str = Form("color"),
        paper: str = Form(""),
        scale: str = Form("fit"),
    ):
        client = request.client.host if request.client else "?"
        job_dir = config.tmp_dir / uuid.uuid4().hex
        job_dir.mkdir()
        pdf = job_dir / safe_filename(file.filename)
        try:
            with pdf.open("wb") as out:
                shutil.copyfileobj(file.file, out)
            if pdf.stat().st_size > config.max_upload_bytes:
                raise PdfError(f"File is too large (max {config.max_upload_mb} MB).")

            n = page_count(pdf)
            opts = PrintOptions(
                copies=copies,
                pages=parse_page_range(pages, n),
                duplex=duplex,
                color=color,
                paper=paper.lower(),
                scale=scale,
            )
            with print_lock:
                backend.print_pdf(pdf, opts)
        except (PdfError, ValueError) as e:
            log.info("REJECTED ip=%s file=%r: %s", client, pdf.name, e)
            return error(400, str(e))
        except Exception as e:
            log.exception("FAILED ip=%s file=%r", client, pdf.name)
            return error(502, str(e))
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

        log.info("PRINTED ip=%s file=%r pages=%d opts=%s", client, pdf.name, n, opts)
        return {"ok": True, "message": f"Sent {pdf.name} to {backend.name}.", "pages": n}

    return app
