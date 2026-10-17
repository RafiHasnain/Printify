"""Translate print options into a SumatraPDF command line."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

# Paper sizes SumatraPDF understands for "paper=...". The key is the lowercase name.
PAPER_SIZES = {
    "a3": "A3",
    "a4": "A4",
    "a5": "A5",
    "letter": "Letter",
    "legal": "Legal",
    "tabloid": "Tabloid",
    "statement": "Statement",
}

DUPLEX = {"off": "simplex", "long": "duplexlong", "short": "duplexshort"}
COLOR = {"color": "color", "mono": "monochrome"}
SCALE = {"fit": "fit", "shrink": "shrink", "actual": "noscale"}

MAX_COPIES = 99


@dataclass(frozen=True)
class PrintOptions:
    copies: int = 1
    pages: str = ""  # normalized range, "" = all
    duplex: str = "off"
    color: str = "color"
    paper: str = ""  # key of PAPER_SIZES, "" = printer default
    scale: str = "fit"

    def __post_init__(self):
        if not 1 <= self.copies <= MAX_COPIES:
            raise ValueError(f"Copies must be between 1 and {MAX_COPIES}.")
        if self.duplex not in DUPLEX:
            raise ValueError(f"Unknown duplex mode: {self.duplex}")
        if self.color not in COLOR:
            raise ValueError(f"Unknown color mode: {self.color}")
        if self.paper and self.paper not in PAPER_SIZES:
            raise ValueError(f"Unsupported paper size: {self.paper}")
        if self.scale not in SCALE:
            raise ValueError(f"Unknown scaling: {self.scale}")


def build_print_settings(opts: PrintOptions) -> str:
    """Build the value for SumatraPDF's -print-settings flag."""
    parts = []
    if opts.pages:
        parts.append(opts.pages)
    parts.append(SCALE[opts.scale])
    parts.append(DUPLEX[opts.duplex])
    parts.append(COLOR[opts.color])
    if opts.paper:
        parts.append(f"paper={PAPER_SIZES[opts.paper]}")
    if opts.copies > 1:
        parts.append(f"{opts.copies}x")
    return ",".join(parts)


def build_command(sumatra: Path, printer: str, pdf: Path, opts: PrintOptions) -> list[str]:
    return [
        str(sumatra),
        "-print-to", printer,
        "-print-settings", build_print_settings(opts),
        "-silent",
        str(pdf),
    ]


def run(cmd: list[str], timeout: int = 180) -> None:
    """Run SumatraPDF; raise RuntimeError on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise RuntimeError(f"SumatraPDF not found at {cmd[0]}. Re-run install.bat.") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Printing timed out. Check the printer.") from e
    if result.returncode != 0:
        raise RuntimeError(f"SumatraPDF failed (exit {result.returncode}). {_error_detail(result)}")


def _error_detail(result: subprocess.CompletedProcess) -> str:
    """Sumatra's output minus its "ParseFlags:" debug lines; a hint if nothing useful is left."""
    lines = [
        line.strip()
        for line in f"{result.stderr or ''}\n{result.stdout or ''}".splitlines()
        if line.strip() and not line.strip().startswith("ParseFlags:")
    ]
    if lines:
        return " ".join(lines)
    return "Check the printer name, that the printer is online, and that the PDF opens in SumatraPDF."
