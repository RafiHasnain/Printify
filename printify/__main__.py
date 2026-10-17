"""Entry point: python -m printify (pythonw -m printify at Windows startup)."""

import logging
import os
import socket
import sys
from logging.handlers import RotatingFileHandler

import uvicorn

from .config import load_config
from .main import create_app


def setup_logging(log_file) -> None:
    # pythonw has no console: stdout/stderr are None, and anything writing there would crash.
    if sys.stdout is None or sys.stderr is None:
        sys.stdout = sys.stderr = open(os.devnull, "w")

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console)


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


def main() -> None:
    config = load_config()
    setup_logging(config.log_file)
    log = logging.getLogger("printify")

    if port_in_use(config.host, config.port):
        log.info("Port %d is already in use (Printify already running?). Exiting.", config.port)
        return

    log.info("Starting Printify on http://%s:%d", config.host, config.port)
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_config=None)


if __name__ == "__main__":
    main()
