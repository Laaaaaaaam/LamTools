import json
import subprocess
import sys
import os

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "linestats.py")
SAMPLE = os.path.join(os.path.dirname(__file__), "sample.txt")


def test_normal_stats():
    result = subprocess.run(
        [sys.executable, SCRIPT, SAMPLE],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data == {
        "line_count": 3,
        "word_count": 8,
        "char_count": 45,
    }


def test_missing_file_error():
    result = subprocess.run(
        [sys.executable, SCRIPT, "nonexistent_file.txt"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert "error" in data
    assert "nonexistent_file.txt" in data["error"]
