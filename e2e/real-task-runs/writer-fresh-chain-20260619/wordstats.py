#!/usr/bin/env python3
"""
Word Frequency Statistics CLI Tool

Usage:
    python wordstats.py <file_path>

Output:
    JSON object with word counts, sorted by frequency (descending), then alphabetically.
"""

import sys
import json
import re
from collections import Counter


def extract_words(text: str) -> list[str]:
    """Extract words from text, converting to lowercase."""
    # Match sequences of letters (supporting Unicode letters)
    words = re.findall(r"[\w']+", text.lower())
    # Filter out standalone numbers and clean up
    cleaned = []
    for word in words:
        # Remove leading/trailing apostrophes
        word = word.strip("'")
        if word and not word.isdigit():
            cleaned.append(word)
    return cleaned


def count_words(text: str) -> dict[str, int]:
    """Count word frequencies in the given text."""
    words = extract_words(text)
    return dict(Counter(words))


def sort_word_counts(word_counts: dict[str, int]) -> dict[str, int]:
    """Sort word counts by frequency (descending), then alphabetically (ascending)."""
    return dict(sorted(word_counts.items(), key=lambda item: (-item[1], item[0])))


def analyze_file(file_path: str) -> dict[str, int]:
    """Read a file and return sorted word frequency counts."""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    word_counts = count_words(text)
    return sort_word_counts(word_counts)


def main():
    if len(sys.argv) < 2:
        print("Usage: python wordstats.py <file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    try:
        result = analyze_file(file_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
