"""
kb_core.py - Markdown knowledge-base organizer core logic.

Uses only the Python standard library.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple


def scan_directory(directory: str) -> List[Path]:
    """Return a sorted list of all .md files under *directory*."""
    root = Path(directory)
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def extract_title(content: str, fallback: str = "Untitled") -> str:
    """Return the first top-level (#) heading, or *fallback*."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def extract_tags(content: str) -> List[str]:
    """Extract tags from YAML front-matter or inline #tags."""
    tags: Set[str] = set()

    # YAML front-matter tags:  tags:\n  - foo\n  - bar
    fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        front = fm_match.group(1)
        # tags: [foo, bar]
        for m in re.finditer(r"tags:\s*\[([^\]]+)\]", front):
            for t in m.group(1).split(","):
                tags.add(t.strip().lstrip("#"))
        # tags:
        #   - foo
        #   - bar
        tag_section = re.search(r"tags:\s*(.+?)(?:\n\w|$)", front, re.DOTALL)
        if tag_section:
            for line in tag_section.group(1).splitlines():
                line = line.strip().lstrip("- ").strip()
                if line:
                    tags.add(line.lstrip("#"))

    # Inline #tags (avoid hex colors and headings)
    for m in re.finditer(r"(?<![A-Za-z0-9])#([A-Za-z_]\w+)", content):
        tags.add(m.group(1))

    return sorted(tags)


def extract_wikilinks(content: str) -> List[str]:
    """Return all [[WikiLink]] targets."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def extract_markdown_links(content: str) -> List[str]:
    """Return all local Markdown file links from [text](path.md)."""
    links = []
    for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", content):
        href = m.group(2).strip()
        if href.endswith(".md") and not href.startswith(("http:", "https:")):
            links.append(href)
    return links


def extract_todos(content: str) -> List[Tuple[str, bool]]:
    """Return list of (todo_text, done) extracted from - [ ] / - [x] lines."""
    todos = []
    for line in content.splitlines():
        stripped = line.strip()
        m = re.match(r"-\s*\[([ xX])\]\s*(.*)", stripped)
        if m:
            done = m.group(1).lower() == "x"
            text = m.group(2).strip()
            todos.append((text, done))
    return todos


def parse_file(path: Path, base_dir: Path) -> dict:
    """Parse a single Markdown file and return its metadata."""
    content = path.read_text(encoding="utf-8")
    title = extract_title(content, fallback=path.stem.replace("_", " ").title())
    tags = extract_tags(content)
    wikilinks = extract_wikilinks(content)
    md_links = extract_markdown_links(content)
    todos = extract_todos(content)

    # Resolve local markdown links relative to base_dir
    resolved_links = []
    for link in md_links:
        if os.path.isabs(link):
            resolved_links.append(Path(link))
        else:
            resolved_links.append((base_dir / link).resolve())

    return {
        "path": path,
        "relative": path.relative_to(base_dir),
        "title": title,
        "tags": tags,
        "wikilinks": wikilinks,
        "md_links": md_links,
        "resolved_links": resolved_links,
        "todos": todos,
        "content": content,
    }


def find_broken_links(files_data: List[dict], base_dir: Path) -> List[Tuple[Path, str]]:
    """Return list of (file_path, broken_link) for missing targets."""
    existing = {f["path"].resolve() for f in files_data}
    existing_names = {f["path"].stem for f in files_data}
    broken = []

    for fd in files_data:
        # Markdown links
        for raw, resolved in zip(fd["md_links"], fd["resolved_links"]):
            if resolved not in existing:
                broken.append((fd["path"], raw))
        # WikiLinks
        for wl in fd["wikilinks"]:
            if wl not in existing_names:
                broken.append((fd["path"], f"[[{wl}]]"))

    return broken


def generate_index(files_data: List[dict], base_dir: Path) -> str:
    """Generate an index.md string grouped by tags."""
    lines = ["# Knowledge Base Index\n", "\n"]

    # Tag -> files
    tag_map: Dict[str, List[dict]] = {}
    for fd in files_data:
        for tag in fd["tags"]:
            tag_map.setdefault(tag, []).append(fd)

    if tag_map:
        lines.append("## By Tag\n\n")
        for tag in sorted(tag_map):
            lines.append(f"### {tag}\n\n")
            for fd in sorted(tag_map[tag], key=lambda x: x["title"]):
                rel = fd["relative"].as_posix()
                lines.append(f"- [{fd['title']}]({rel})\n")
            lines.append("\n")

    # Also list all files
    lines.append("## All Files\n\n")
    for fd in sorted(files_data, key=lambda x: x["title"]):
        rel = fd["relative"].as_posix()
        tags_str = ", ".join(f"`{t}`" for t in fd["tags"])
        if tags_str:
            lines.append(f"- [{fd['title']}]({rel}) — tags: {tags_str}\n")
        else:
            lines.append(f"- [{fd['title']}]({rel})\n")

    return "".join(lines)


def build_report(directory: str) -> dict:
    """Scan *directory* and return a report dictionary."""
    base = Path(directory).resolve()
    md_files = scan_directory(directory)
    files_data = [parse_file(p, base) for p in md_files]

    broken = find_broken_links(files_data, base)
    all_tags: Set[str] = set()
    todo_count = 0
    for fd in files_data:
        all_tags.update(fd["tags"])
        todo_count += len(fd["todos"])

    return {
        "file_count": len(files_data),
        "tag_count": len(all_tags),
        "broken_links": broken,
        "todo_count": todo_count,
        "files_data": files_data,
        "all_tags": sorted(all_tags),
    }
