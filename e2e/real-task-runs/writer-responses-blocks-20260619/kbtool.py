"""
kbtool.py - CLI entry point for the Markdown knowledge-base organizer.

Usage:
    python kbtool.py scan <directory>
    python kbtool.py report <directory>
"""

import sys
from pathlib import Path

import kb_core


def print_scan(directory: str) -> None:
    base = Path(directory).resolve()
    md_files = kb_core.scan_directory(directory)
    if not md_files:
        print(f"No Markdown files found in '{directory}'.")
        return

    for path in md_files:
        fd = kb_core.parse_file(path, base)
        print(f"File: {fd['relative'].as_posix()}")
        print(f"  Title : {fd['title']}")
        print(f"  Tags  : {', '.join(fd['tags']) or 'None'}")
        print(f"  Links : {', '.join(fd['md_links']) or 'None'}")
        print(f"  Wikis : {', '.join(fd['wikilinks']) or 'None'}")
        print(f"  Todos : {len(fd['todos'])}")
        print()


def print_report(directory: str) -> None:
    report = kb_core.build_report(directory)
    print(f"=== Knowledge Base Report for '{directory}' ===\n")
    print(f"Files scanned : {report['file_count']}")
    print(f"Unique tags   : {report['tag_count']}")
    print(f"Todo items    : {report['todo_count']}")
    print(f"Broken links  : {len(report['broken_links'])}")
    if report["broken_links"]:
        print("\nBroken links:")
        for file_path, link in report["broken_links"]:
            rel = file_path.relative_to(Path(directory).resolve())
            print(f"  - in {rel.as_posix()}: {link}")
    print()


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python kbtool.py <scan|report> <directory>")
        sys.exit(1)

    command = sys.argv[1].lower()
    directory = sys.argv[2]

    if command == "scan":
        print_scan(directory)
    elif command == "report":
        print_report(directory)
    else:
        print(f"Unknown command: {command}")
        print("Usage: python kbtool.py <scan|report> <directory>")
        sys.exit(1)


if __name__ == "__main__":
    main()
