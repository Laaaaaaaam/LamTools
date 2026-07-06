"""CLI tool to output line, word, and character stats for a text file as JSON."""

import json
import sys


def get_stats(path):
    """Return a dict with line_count, word_count, and char_count for the file at *path*."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    words = text.split()

    return {
        "line_count": len(lines),
        "word_count": len(words),
        "char_count": len(text),
    }


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <file>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    try:
        stats = get_stats(path)
    except FileNotFoundError:
        print(json.dumps({"error": f"File not found: {path}"}))
        sys.exit(1)

    print(json.dumps(stats))


if __name__ == "__main__":
    main()
