from __future__ import annotations

import os
import platform
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import webview

from desktop import __version__
from desktop.server import ServerManager, find_available_port
from desktop.tray import TrayManager
from desktop.updater import UpdateChecker

_log_file: Path | None = None


def _log(msg: str) -> None:
    global _log_file
    if _log_file is None:
        return
    try:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(_log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _init_log(data_dir: Path) -> None:
    global _log_file
    data_dir.mkdir(parents=True, exist_ok=True)
    _log_file = data_dir / "startup.log"
    _log(f"=== lamartist v{__version__} startup ===")
    _log(f"frozen={getattr(sys, 'frozen', False)}")
    _log(f"sys._MEIPASS={getattr(sys, '_MEIPASS', 'N/A')}")
    _log(f"sys.path[0]={sys.path[0]}")
    _log(f"platform={platform.system()} {platform.release()}")
    _log(f"data_dir={data_dir}")


def get_platform_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "lamartist"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "lamartist"
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(base) / "lamartist"


def _get_window_size() -> tuple[int, int, int]:
    try:
        if platform.system() == "Windows":
            import ctypes
            user32 = ctypes.windll.user32
            sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        elif platform.system() == "Darwin":
            import subprocess
            out = subprocess.check_output(
                "system_profiler SPDisplaysDataType | grep Resolution",
                shell=True, text=True
            )
            nums = [int(s) for s in out.split() if s.isdigit()]
            sw, sh = nums[0], nums[1] if len(nums) >= 2 else 1440
        else:
            sw, sh = 1920, 1080
    except Exception:
        sw, sh = 1920, 1080

    w = max(1280, int(sw * 0.7))
    h = max(800, int(sh * 0.75))
    minw = max(900, int(w * 0.55))
    return w, h, minw


def get_static_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        internal = base / "_internal" / "frontend" / "dist"
        if internal.exists():
            return internal
        return base / "frontend" / "dist"
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def acquire_lock(data_dir: Path):
    from filelock import FileLock, Timeout

    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / ".lock"
    lock = FileLock(str(lock_path), timeout=0)
    try:
        lock.acquire()
        _log("lock acquired")
        return lock
    except Timeout:
        # Lock file exists — check if stale (no other process running on same port)
        _log("lock contention, checking staleness...")
        import socket
        for port in range(8000, 8100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    # Port is free — lock is stale, clean up
                    lock_path.unlink(missing_ok=True)
                    lock.acquire()
                    _log(f"stale lock removed, re-acquired (port={port})")
                    return lock
                except OSError:
                    continue
        # All ports in use — another instance is genuinely running
        _log("another instance appears to be running, exiting")
        return None
    except Exception as e:
        _log(f"lock FAILED: {e}")
        return None


def wait_for_health(port: int, timeout: int = 10) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            url = f"http://127.0.0.1:{port}/api/health"
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    _log("health OK")
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    _log("health TIMEOUT")
    return False


def main():
    data_dir = get_platform_data_dir()
    _init_log(data_dir)

    static_dir = get_static_dir()
    _log(f"static_dir={static_dir} exists={static_dir.exists()}")

    lock = acquire_lock(data_dir)
    if lock is None:
        _log("already running, exiting")
        sys.exit(0)

    try:
        port = find_available_port(8000, 8100)
        _log(f"port={port}")
    except RuntimeError as e:
        _log(f"port FAILED: {e}")
        sys.exit(1)

    try:
        _log("starting server...")
        server = ServerManager()
        server.start(port, data_dir, static_dir)
    except Exception as e:
        _log(f"server start CRASH: {e}\n{traceback.format_exc()}")
        sys.exit(1)

    if not wait_for_health(port, timeout=15):
        _log("backend failed to start, exiting")
        server.stop()
        sys.exit(1)

    _quitting = threading.Event()

    def on_show():
        if webview.windows:
            webview.windows[0].show()

    def on_assistant():
        if webview.windows:
            webview.windows[0].evaluate_js(
                "window.toggleAssistant && window.toggleAssistant()"
            )
            webview.windows[0].show()

    def on_settings():
        if webview.windows:
            webview.windows[0].evaluate_js(
                'window.navigateTo && window.navigateTo("/settings")'
            )
            webview.windows[0].show()

    def on_quit():
        _quitting.set()
        server.stop()
        tray.stop()
        if webview.windows:
            webview.windows[0].destroy()

    try:
        _log("starting tray...")
        tray = TrayManager(
            on_show=on_show,
            on_assistant=on_assistant,
            on_settings=on_settings,
            on_quit=on_quit,
        )
        tray.start()
        _log("tray started")
    except Exception as e:
        _log(f"tray start CRASH: {e}\n{traceback.format_exc()}")
        server.stop()
        sys.exit(1)

    def check_update():
        try:
            checker = UpdateChecker("lamartist/lamartist", __version__)
            info = checker.check()
            if info:
                tray.notify("lamartist Update", f"New version {info.version} available")
        except Exception:
            pass

    threading.Thread(target=check_update, daemon=True).start()

    def on_close():
        if not _quitting.is_set():
            webview.windows[0].hide()
            return True

    url = f"http://127.0.0.1:{port}"
    win_w, win_h, min_w = _get_window_size()
    _log(f"creating webview window: {url} ({win_w}x{win_h})")

    try:
        window = webview.create_window(
            "lamartist",
            url,
            width=win_w,
            height=win_h,
            min_size=(min_w, 600),
            confirm_close=False,
            text_select=True,
        )
        window.events.closing += on_close
        _log("webview window created, starting event loop...")
        webview.start()
        _log("webview event loop ended")
    except Exception as e:
        _log(f"webview CRASH: {e}\n{traceback.format_exc()}")
        server.stop()
        tray.stop()
        try:
            lock.release()
        except Exception:
            pass
        sys.exit(1)

    if not _quitting.is_set():
        server.stop()
        tray.stop()

    try:
        lock.release()
    except Exception:
        pass

    _log("clean exit")


if __name__ == "__main__":
    main()
