"""Self-update: swap in a new printify/ package from a zip and restart the process."""

import logging
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path, PurePosixPath

log = logging.getLogger("printify")

MAX_UPDATE_BYTES = 20 * 1024 * 1024
PACKAGE = "printify"
BUILD_FILE = Path(__file__).parent / "_build.txt"


class UpdateError(Exception):
    pass


def current_build() -> str:
    try:
        return BUILD_FILE.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def _check_entries(zf: zipfile.ZipFile) -> None:
    total = 0
    for info in zf.infolist():
        name = info.filename
        parts = PurePosixPath(name).parts
        if name.startswith(("/", "\\")) or ":" in name or ".." in parts or "\\" in name:
            raise UpdateError(f"Unsafe path in update: {name}")
        if not (parts and (parts[0] == PACKAGE or name == "requirements.txt")):
            raise UpdateError(f"Unexpected file in update: {name}")
        total += info.file_size
        if total > MAX_UPDATE_BYTES:
            raise UpdateError("Update is too large.")
    names = set(zf.namelist())
    for required in (f"{PACKAGE}/__init__.py", f"{PACKAGE}/main.py"):
        if required not in names:
            raise UpdateError(f"Update is missing {required}.")


def apply_update(zip_path: Path, base_dir: Path) -> dict:
    """Install the package in zip_path into base_dir. Returns {"build", "pip"}."""
    staging = base_dir / "update_staging"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            _check_entries(zf)
            zf.extractall(staging)
    except zipfile.BadZipFile as e:
        raise UpdateError("Not a valid zip file.") from e

    target, old = base_dir / PACKAGE, base_dir / f"{PACKAGE}.old"
    shutil.rmtree(old, ignore_errors=True)
    try:
        if target.exists():
            target.rename(old)
        (staging / PACKAGE).rename(target)
    except OSError as e:
        # A file inside is held open; fall back to copying over the existing package.
        log.warning("Package swap by rename failed (%s); copying instead", e)
        if not target.exists() and old.exists():
            old.rename(target)
        shutil.copytree(staging / PACKAGE, target, dirs_exist_ok=True)

    pip = ""
    new_req, req = staging / "requirements.txt", base_dir / "requirements.txt"
    if new_req.is_file() and (not req.is_file() or new_req.read_bytes() != req.read_bytes()):
        shutil.copyfile(new_req, req)
        result = subprocess.run(
            [_console_python(), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req)],
            capture_output=True, text=True, timeout=600, cwd=base_dir,
        )
        pip = (result.stdout + result.stderr).strip()[-4000:]
        if result.returncode != 0:
            raise UpdateError(f"pip install failed: {pip}")

    shutil.rmtree(staging, ignore_errors=True)
    build = (target / "_build.txt").read_text(encoding="utf-8").strip() if (target / "_build.txt").is_file() else "dev"
    return {"build": build, "pip": pip}


def _console_python() -> str:
    # pythonw.exe can't run pip reliably (no console); use python.exe next to it.
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.is_file():
            return str(console)
    return str(exe)


def restart(base_dir: Path, delay: float = 1.0) -> None:
    """Start a fresh process and exit this one after the response has gone out."""
    env = {**os.environ, "PRINTIFY_RESTART": "1"}
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [sys.executable, "-m", PACKAGE], cwd=base_dir, env=env, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs,
    )
    log.info("Restarting Printify")
    threading.Timer(delay, os._exit, args=(0,)).start()
