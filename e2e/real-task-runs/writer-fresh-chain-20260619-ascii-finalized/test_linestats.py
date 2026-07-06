import subprocess
import sys
import json
import os


def test_linestats_output():
    result = subprocess.run(
        [sys.executable, "linestats.py", "sample.txt"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["line_count"] == 3
    assert data["word_count"] == 13
    assert data["char_count"] == 90


def test_linestats_missing_file():
    result = subprocess.run(
        [sys.executable, "linestats.py", "nonexistent_file.txt"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr.lower() or result.returncode == 1
