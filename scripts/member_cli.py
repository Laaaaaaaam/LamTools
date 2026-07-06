from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = ["py", "-3.14"]  # Windows Python launcher — prefer newest Python 3


def _ports() -> dict:
    ports_file = ROOT / "scripts" / "ports.json"
    return json.loads(ports_file.read_text(encoding="utf-8-sig"))


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _run(command: list[str], cwd: Path) -> int:
    return subprocess.run(command, cwd=str(cwd), env=_env()).returncode


def _health(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            print(response.read().decode("utf-8", errors="replace"))
            return 0 if 200 <= response.status < 300 else 1
    except urllib.error.URLError as exc:
        print(f"health check failed: {exc}", file=sys.stderr)
        return 1


def _member_health(member_id: str) -> int:
    ports = _ports()
    member_ports = ports.get(member_id, {})
    backend_port = member_ports.get("backend", 6173)
    return _health(f"http://127.0.0.1:{backend_port}/api/health")


def _writer(args: list[str]) -> int:
    cwd = ROOT / "members" / "writer" / "backend"
    if not args or args[0] in {"-h", "--help", "help"}:
        return _run(PY + ["-m", "writer_cli", "--help"], cwd)

    command = args[0]
    rest = args[1:]
    if command == "health":
        return _member_health("writer")
    if command == "session":
        if not rest or rest[0] in {"-h", "--help", "help"}:
            return _run(PY + ["-m", "writer_cli", "--help"], cwd)
        if not rest or rest[0] in {"list", "ls"}:
            return _run(PY + ["-m", "writer_cli", "list", *rest[1:]], cwd)
        return _run(PY + ["-m", "writer_cli", *rest], cwd)

    return _run(PY + ["-m", "writer_cli", *args], cwd)


def _artist(args: list[str]) -> int:
    cwd = ROOT / "members" / "artist" / "backend"
    artist_cli = ["-m", "app.cli"]
    if not args or args[0] in {"-h", "--help", "help"}:
        return _run(PY + artist_cli + ["--help"], cwd)

    command = args[0]
    rest = args[1:]
    if command == "run":
        if not rest:
            print("usage: artist run <task...>", file=sys.stderr)
            return 2
        return _run(PY + artist_cli + rest, cwd)
    if command == "resume":
        if len(rest) < 2:
            print("usage: artist resume <session-id> <message...>", file=sys.stderr)
            return 2
        return _run(PY + artist_cli + ["session", rest[0], *rest[1:]], cwd)
    if command == "image":
        if not rest:
            print("usage: artist image <prompt...>", file=sys.stderr)
            return 2
        return _run(PY + artist_cli + ["image", *rest], cwd)
    if command == "session":
        if not rest or rest[0] in {"-h", "--help", "help"}:
            return _run(PY + artist_cli + ["--help"], cwd)
        if not rest or rest[0] in {"list", "ls"}:
            return _run(PY + artist_cli + ["session", "ls", *rest[1:]], cwd)
        if rest[0] in {"new", "copy", "rename"}:
            return _run(PY + artist_cli + ["session", *rest], cwd)
        return _run(PY + artist_cli + ["session", *rest], cwd)
    if command == "health":
        return _member_health("artist")

    print("usage: artist <run|resume|image|session|health> [args...]", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    invoked = Path(sys.argv[0]).stem.lower()

    if invoked in {"writer", "artist"}:
        member = invoked
        args = argv
    else:
        if not argv:
            print("usage: member_cli.py <writer|artist> <command> ...", file=sys.stderr)
            return 2
        member = argv[0].lower()
        args = argv[1:]

    if member == "writer":
        return _writer(args)
    if member == "artist":
        return _artist(args)

    print(f"unknown member: {member}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
