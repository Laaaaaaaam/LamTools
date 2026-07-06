#!/usr/bin/env python
"""CLI tool to output line/word/char stats for a text file in JSON."""

import json
import sys


def stats(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    line_count = len(lines)
    word_count = len(text.split())
    char_count = len(text)
    return {
        "line_count": line_count,
        "word_count": word_count,
        "char_count": char_count,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python linestats.py <file>", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    try:
        result = stats(path)
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
