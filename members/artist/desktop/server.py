
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import traceback
from pathlib import Path

import uvicorn

_server_logger = logging.getLogger("lamartist.server")


def _setup_logging(log_path: Path) -> None:
    _server_logger.handlers.clear()
    handler = logging.FileHandler(str(log_path), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _server_logger.addHandler(handler)
    _server_logger.setLevel(logging.DEBUG)


def find_available_port(start: int = 8000, end: int = 8100) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available port in range {start}-{end}")


def _resolve_data_dir(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        internal = base / "_internal" / relative_path
        if internal.exists():
            return internal
        return base / relative_path
    return Path(__file__).resolve().parent.parent / relative_path


def _resolve_backend_dir() -> Path:
    return _resolve_data_dir("backend")


class ServerManager:
    def __init__(self):
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0

    def start(self, port: int, data_dir: Path, static_dir: Path | None = None) -> None:
        self._port = port

        if data_dir:
            os.environ["LAMARTIST_DATA_DIR"] = str(data_dir)
        if static_dir:
            os.environ["LAMARTIST_STATIC_DIR"] = str(static_dir)

        err_log_path = data_dir / "server_error.log"
        _setup_logging(err_log_path)

        backend_dir = str(_resolve_backend_dir())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        _server_logger.info("Backend dir: %s", backend_dir)
        _server_logger.info("sys.path[0:3]: %s", sys.path[:3])

        try:
            from app.main import app
            from app.config import settings
            settings.SERVER_PORT = port
            _server_logger.info("app imported OK, routes=%d, port=%d", len(app.routes), port)
        except Exception as e:
            _server_logger.error("app import FAILED: %s\n%s", e, traceback.format_exc())
            raise

        config = uvicorn.Config(
            "app.main:app",
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run_server():
            try:
                _server_logger.info("uvicorn thread starting")
                self._server.run()
            except Exception as e:
                _server_logger.error("uvicorn CRASH: %s\n%s", e, traceback.format_exc())

        self._thread = threading.Thread(target=_run_server, daemon=True)
        self._thread.start()
        _server_logger.info("server thread started")

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def port(self) -> int:
        return self._port

    def is_running(self) -> bool:
        return self._server is not None and not self._server.should_exit
