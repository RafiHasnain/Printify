"""Load settings from config.toml next to the app (C:\\Printify\\config.toml when installed)."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    host: str = "0.0.0.0"
    port: int = 8631
    printer: str = ""
    max_upload_mb: int = 50
    sumatra_path: str = ""
    update_token: str = ""  # empty = remote updates disabled

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def sumatra(self) -> Path:
        return Path(self.sumatra_path) if self.sumatra_path else BASE_DIR / "bin" / "SumatraPDF.exe"

    @property
    def tmp_dir(self) -> Path:
        return BASE_DIR / "tmp"

    @property
    def log_file(self) -> Path:
        return BASE_DIR / "printify.log"


def load_config(path: Path | None = None) -> Config:
    path = path or Path(os.environ.get("PRINTIFY_CONFIG", BASE_DIR / "config.toml"))
    if not path.is_file():
        return Config()
    with path.open("rb") as f:
        data = tomllib.load(f)
    known = {k: v for k, v in data.items() if k in Config.__dataclass_fields__}
    return Config(**known)
