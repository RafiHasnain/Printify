import subprocess
from pathlib import Path

import pytest

from printify import sumatra
from printify.sumatra import PrintOptions, build_command, build_print_settings


def test_defaults():
    assert build_print_settings(PrintOptions()) == "fit,simplex,color"


def test_all_options():
    opts = PrintOptions(copies=2, pages="1-3,5", duplex="long", color="mono", paper="a4", scale="actual")
    assert build_print_settings(opts) == "1-3,5,noscale,duplexlong,monochrome,paper=A4,2x"


def test_short_edge_letter():
    opts = PrintOptions(duplex="short", paper="letter")
    assert build_print_settings(opts) == "fit,duplexshort,color,paper=Letter"


@pytest.mark.parametrize("kwargs", [
    {"copies": 0}, {"copies": 100}, {"duplex": "both"}, {"color": "red"},
    {"paper": "a0"}, {"scale": "zoom"},
])
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        PrintOptions(**kwargs)


def test_command_is_argument_list():
    cmd = build_command(Path("S.exe"), "HP LaserJet", Path("a b.pdf"), PrintOptions())
    assert cmd == ["S.exe", "-print-to", "HP LaserJet", "-print-settings", "fit,simplex,color", "-silent", "a b.pdf"]


def _fake_run(stdout="", stderr=""):
    def fake(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout=stdout, stderr=stderr)
    return fake


def test_run_hides_parseflags_noise(monkeypatch):
    noise = "ParseFlags: argName: '-print-to', arg: 33\nParseFlags: argName: '-silent', arg: 1\n"
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=noise))
    with pytest.raises(RuntimeError) as e:
        sumatra.run(["SumatraPDF.exe"])
    assert "ParseFlags" not in str(e.value)
    assert "Check the printer name" in str(e.value)


def test_run_keeps_real_error(monkeypatch):
    out = "ParseFlags: argName: '-silent', arg: 1\nCouldn't open file\n"
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=out))
    with pytest.raises(RuntimeError, match="Couldn't open file"):
        sumatra.run(["SumatraPDF.exe"])
