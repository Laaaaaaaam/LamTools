from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
SPEC_FILE = PROJECT_ROOT / "lamartist.spec"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"


def check_python_version():
    if sys.version_info < (3, 14):
        print("Error: Python 3.14+ is required.")
        sys.exit(1)
    print(f"Python version: {sys.version}")


def check_dependencies():
    required = {
        "PyInstaller": "pyinstaller",
        "webview": "pywebview",
        "pystray": "pystray",
        "filelock": "filelock",
    }
    missing = []
    for import_name, pip_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"Error: Missing dependencies: {', '.join(missing)}")
        print(f"Install with: pip install {' '.join(missing)}")
        sys.exit(1)
    print("All desktop dependencies installed.")


def build_frontend():
    if FRONTEND_DIST.exists():
        print(f"Frontend build already exists: {FRONTEND_DIST}")
        return

    if not (FRONTEND_DIR / "package.json").exists():
        print("Error: frontend/package.json not found.")
        sys.exit(1)

    print("Building frontend...")
    system = platform.system()

    npm_candidates = []
    node_paths = os.environ.get("PATH", "").split(os.pathsep)
    if system == "Windows":
        npm_candidates = ["npm.cmd", "npm"]
        default_node = os.environ.get("ProgramFiles", "C:\\Program Files") + "\\nodejs"
        if default_node not in node_paths:
            os.environ["PATH"] = default_node + os.pathsep + os.environ.get("PATH", "")
    else:
        npm_candidates = ["npm"]

    npm_cmd = None
    for candidate in npm_candidates:
        if shutil.which(candidate):
            npm_cmd = candidate
            break

    if npm_cmd is None:
        print("Error: npm not found. Install Node.js first.")
        sys.exit(1)

    try:
        subprocess.run(
            [npm_cmd, "run", "build"],
            cwd=str(FRONTEND_DIR),
            check=True,
            capture_output=True,
            text=True,
        )
        print("Frontend build complete.")
    except subprocess.CalledProcessError as e:
        last_lines = e.stderr.strip().split('\n')[-5:]
        print(f"vue-tsc failed, retrying with vite build directly...")
        npx_cmd = "npx.cmd" if system == "Windows" else "npx"
        try:
            subprocess.run(
                [npx_cmd, "vite", "build"],
                cwd=str(FRONTEND_DIR),
                check=True,
                capture_output=True,
                text=True,
            )
            print("Frontend build complete (vite only).")
        except subprocess.CalledProcessError as e2:
            print(f"Error: Frontend build failed.\n{e2.stderr[-500:]}")
            sys.exit(1)


def clean_build():
    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"Cleaned: {d}")


def run_pyinstaller():
    if not SPEC_FILE.exists():
        print(f"Error: Spec file not found: {SPEC_FILE}")
        sys.exit(1)

    print("Running PyInstaller...")
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm"]
    try:
        subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
        print("PyInstaller build complete.")
    except subprocess.CalledProcessError as e:
        print(f"Error: PyInstaller build failed.")
        sys.exit(1)


def print_result():
    output_dir = DIST_DIR / "lamartist"
    if output_dir.exists():
        total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
        size_mb = total_size / (1024 * 1024)
        print(f"\nBuild output: {output_dir}")
        print(f"Total size: {size_mb:.1f} MB")

        exe_name = "lamartist.exe" if platform.system() == "Windows" else "lamartist"
        exe_path = output_dir / exe_name
        if exe_path.exists():
            print(f"Executable: {exe_path}")
    else:
        print("Warning: Build output directory not found.")


def main():
    parser = argparse.ArgumentParser(description="Build lamartist desktop app")
    parser.add_argument(
        "--platform",
        choices=["windows", "macos", "linux"],
        default=platform.system().lower().replace("darwin", "macos"),
        help="Target platform (default: current)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build cache before building",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend build step",
    )
    args = parser.parse_args()

    print(f"Building lamartist for {args.platform}...")
    print(f"Project root: {PROJECT_ROOT}\n")

    check_python_version()
    check_dependencies()

    if args.clean:
        clean_build()

    if not args.skip_frontend:
        build_frontend()
    else:
        if not FRONTEND_DIST.exists():
            print("Error: --skip-frontend but frontend/dist/ does not exist.")
            sys.exit(1)
        print("Skipping frontend build.")

    run_pyinstaller()
    print_result()


if __name__ == "__main__":
    main()
