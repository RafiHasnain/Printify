"""Printer access: real Windows backend and a dry-run backend for development on macOS/Linux."""

import logging
import sys
import time
from pathlib import Path

from . import sumatra
from .config import Config
from .sumatra import PAPER_SIZES, PrintOptions

log = logging.getLogger("printify")

# winspool.h status flags (defined here so we don't depend on pywin32 exposing them).
PRINTER_STATUS = {
    0x1: "Paused",
    0x2: "Error",
    0x8: "Paper jam",
    0x10: "Out of paper",
    0x20: "Manual feed needed",
    0x40: "Paper problem",
    0x80: "Offline",
    0x800: "Output bin full",
    0x1000: "Not available",
    0x40000: "Out of toner",
    0x20000: "Toner low",
    0x100000: "Needs attention",
    0x400000: "Door open",
    0x400: "Printing",
    0x200: "Busy",
    0x8000: "Initializing",
    0x10000: "Warming up",
    0x1000000: "Power save",
}
PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x400

JOB_STATUS = {
    0x2: "Error",
    0x20: "Offline",
    0x40: "Out of paper",
    0x400: "Needs attention",
    0x200: "Blocked",
    0x1: "Paused",
    0x4: "Deleting",
    0x10: "Printing",
    0x8: "Spooling",
    0x80: "Printed",
}

DC_DUPLEX = 7
DC_PAPERNAMES = 16
DC_COLORDEVICE = 32


def _flags_to_text(value: int, table: dict[int, str]) -> list[str]:
    return [text for flag, text in table.items() if value & flag]


def match_papers(driver_names: list[str]) -> list[str]:
    """Map driver paper names ("A4 210 x 297 mm", "Letter") to PAPER_SIZES keys, in our order."""
    found = set()
    for name in driver_names:
        words = name.strip().lower().replace("(", " ").split()
        if words and words[0] in PAPER_SIZES:
            found.add(words[0])
    return [key for key in PAPER_SIZES if key in found]


class WindowsBackend:
    def __init__(self, config: Config):
        import win32print  # noqa: F401  (fail fast if pywin32 is missing)

        self.config = config

    @property
    def name(self) -> str:
        import win32print

        return self.config.printer or win32print.GetDefaultPrinter()

    def info(self) -> dict:
        import win32print

        name = self.name
        h = win32print.OpenPrinter(name)
        try:
            p = win32print.GetPrinter(h, 2)
        finally:
            win32print.ClosePrinter(h)
        status = _flags_to_text(p["Status"], PRINTER_STATUS)
        if p["Attributes"] & PRINTER_ATTRIBUTE_WORK_OFFLINE and "Offline" not in status:
            status.insert(0, "Offline")
        return {
            "name": name,
            "status": status or ["Ready"],
            "jobs": p["cJobs"],
            "caps": self._caps(name, p["pPortName"]),
        }

    def _caps(self, name: str, port: str) -> dict:
        """Ask the driver what it supports. None means "unknown", so the UI shows the option anyway."""
        import win32print

        def query(cap):
            try:
                return win32print.DeviceCapabilities(name, port, cap)
            except Exception as e:  # driver-dependent; never fatal
                log.warning("DeviceCapabilities(%s) failed: %s", cap, e)
                return None

        duplex = query(DC_DUPLEX)
        color = query(DC_COLORDEVICE)
        papers = query(DC_PAPERNAMES)
        return {
            "duplex": bool(duplex) if duplex is not None and duplex >= 0 else None,
            "color": bool(color) if color is not None and color >= 0 else None,
            "papers": match_papers(list(papers)) if papers else None,
        }

    def jobs(self) -> list[dict]:
        import win32print

        h = win32print.OpenPrinter(self.name)
        try:
            raw = win32print.EnumJobs(h, 0, 100, 1)
        finally:
            win32print.ClosePrinter(h)
        return [
            {
                "id": j["JobId"],
                "document": j["pDocument"],
                "user": j["pUserName"],
                "status": j["pStatus"] or ", ".join(_flags_to_text(j["Status"], JOB_STATUS)) or "Queued",
                "pages": j["TotalPages"],
                "printed": j["PagesPrinted"],
            }
            for j in raw
        ]

    def _check_printer(self, name: str) -> None:
        """Fail with a clear message instead of Sumatra's silent exit 1."""
        import win32print

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        installed = [p["pPrinterName"] for p in win32print.EnumPrinters(flags, None, 4)]
        if not any(p.lower() == name.lower() for p in installed):
            raise RuntimeError(
                f"Printer {name!r} not found. Installed: {', '.join(installed) or 'none'}. "
                "Fix 'printer' in config.toml."
            )
        status = self.info()["status"]
        blocking = [s for s in status if s in ("Offline", "Not available")]
        if blocking:
            raise RuntimeError(f"Printer {name!r} is {blocking[0].lower()}.")

    def print_pdf(self, pdf: Path, opts: PrintOptions) -> None:
        name = self.name
        self._check_printer(name)
        cmd = sumatra.build_command(self.config.sumatra, name, pdf, opts)
        log.info("Running: %s", cmd)
        sumatra.run(cmd)


class DryRunBackend:
    """Logs what would be printed. Used automatically when not on Windows."""

    def __init__(self, config: Config):
        self.config = config
        self.name = config.printer or "Dry-run printer"
        self._recent: list[dict] = []

    def info(self) -> dict:
        return {
            "name": self.name,
            "status": ["Ready (dry run, nothing is printed)"],
            "jobs": len(self.jobs()),
            "caps": {"duplex": True, "color": True, "papers": ["a4", "letter", "legal"]},
        }

    def jobs(self) -> list[dict]:
        cutoff = time.time() - 15
        self._recent = [j for j in self._recent if j["_t"] > cutoff]
        return [{k: v for k, v in j.items() if k != "_t"} for j in self._recent]

    def print_pdf(self, pdf: Path, opts: PrintOptions) -> None:
        cmd = sumatra.build_command(self.config.sumatra, self.name, pdf, opts)
        log.info("DRY RUN, would run: %s", cmd)
        self._recent.append({
            "id": len(self._recent) + 1, "document": pdf.name, "user": "dry-run",
            "status": "Printed (dry run)", "pages": 0, "printed": 0, "_t": time.time(),
        })


def make_backend(config: Config):
    if sys.platform == "win32":
        return WindowsBackend(config)
    return DryRunBackend(config)
