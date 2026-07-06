#!/usr/bin/env python3
"""Markdown 知识库整理工具 (KBTool)

提供 scan 和 report 两个子命令，用于扫描 Markdown 文件、提取元数据、检测坏链并生成索引。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Note:
    """单条笔记的元数据。"""
    path: Path
    title: str = ""
    tags: list[str] = field(default_factory=list)
    wiki_links: list[str] = field(default_factory=list)
    md_links: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------

# 正则表达式（编译一次，复用多次）
_WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_TAG_RE = re.compile(r"#([A-Za-z0-9_\u4e00-\u9fff]+)")
_TODO_RE = re.compile(r"^\s*- \[ \] (.+)$", re.MULTILINE)
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _extract_front_matter(content: str) -> tuple[dict[str, str], str]:
    """提取 YAML front matter，返回 (键值对, 剩余内容)。"""
    match = _FRONT_MATTER_RE.match(content)
    if not match:
        return {}, content
    fm_text = match.group(1)
    rest = content[match.end():]
    data: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            data[key.strip()] = val.strip()
    return data, rest


def _extract_title(content: str) -> str:
    """从内容中提取第一个 H1 标题。"""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _extract_tags(content: str) -> list[str]:
    """提取内容中的标签（#tag 形式，排除代码块和 URL 中的 hash）。"""
    tags: set[str] = set()
    # 简单过滤：排除代码块内的内容
    cleaned_lines = []
    in_code = False
    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    for match in _TAG_RE.finditer(cleaned):
        tag = match.group(1)
        # 排除纯数字标签（可能是颜色值）
        if not tag.isdigit():
            tags.add(tag)
    return sorted(tags)


def parse_note(file_path: Path) -> Note:
    """解析单个 Markdown 文件，返回 Note 对象。"""
    content = file_path.read_text(encoding="utf-8")
    fm, body = _extract_front_matter(content)

    title = _extract_title(body)
    if not title:
        # 如果正文没有 H1，尝试从文件名推断
        title = file_path.stem

    tags = _extract_tags(body)
    # 也支持 front matter 中的 tags 字段
    if "tags" in fm:
        fm_tags = [t.strip() for t in fm["tags"].split(",") if t.strip()]
        tags = sorted(set(tags) | set(fm_tags))

    wiki_links = _WIKI_LINK_RE.findall(body)
    md_links = [link for _, link in _MD_LINK_RE.findall(body)]
    todos = _TODO_RE.findall(body)

    return Note(
        path=file_path,
        title=title,
        tags=tags,
        wiki_links=wiki_links,
        md_links=md_links,
        todos=todos,
    )


# ---------------------------------------------------------------------------
# 扫描器
# ---------------------------------------------------------------------------

def scan_directory(directory: Path) -> list[Note]:
    """递归扫描目录下的所有 .md 文件，返回 Note 列表。"""
    notes: list[Note] = []
    for md_file in directory.rglob("*.md"):
        if md_file.name.lower() == "index.md":
            continue
        try:
            note = parse_note(md_file)
            notes.append(note)
        except Exception as exc:
            print(f"警告: 解析 {md_file} 失败: {exc}", file=sys.stderr)
    return notes


# ---------------------------------------------------------------------------
# 坏链检测
# ---------------------------------------------------------------------------

def find_broken_links(notes: list[Note], base_dir: Path) -> dict[str, list[str]]:
    """检测坏链，返回 {文件路径: [坏链列表]}。"""
    # 构建存在的文件名和路径集合
    existing_names = set()
    existing_paths: set[Path] = set()
    for note in notes:
        existing_names.add(note.path.name)
        existing_names.add(note.path.stem)
        existing_paths.add(note.path.resolve())

    broken: dict[str, list[str]] = {}
    for note in notes:
        bad: list[str] = []
        for link in note.wiki_links:
            # [[目标]] 可以指向同名文件或带 .md 的文件
            target_name = link.strip()
            if target_name not in existing_names and target_name + ".md" not in existing_names:
                bad.append(f"[[{target_name}]]")
        for link in note.md_links:
            # Markdown 链接可能是相对路径
            link_path = (note.path.parent / link).resolve()
            if link_path not in existing_paths and link_path.name not in existing_names:
                # 也检查不带 .md 后缀的情况
                link_path_md = link_path.with_suffix(".md")
                if link_path_md not in existing_paths:
                    bad.append(f"[{link}]({link})")
        if bad:
            broken[str(note.path)] = bad
    return broken


# ---------------------------------------------------------------------------
# 索引生成
# ---------------------------------------------------------------------------

def generate_index(notes: list[Note], output_path: Path) -> None:
    """生成 index.md，按标签和文件标题组织索引。"""
    lines: list[str] = []
    lines.append("# 知识库索引\n")
    lines.append(f"\n> 自动生成，共 {len(notes)} 篇笔记。\n")

    # 按标签组织
    tag_to_notes: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        if note.tags:
            for tag in note.tags:
                tag_to_notes[tag].append(note)
        else:
            tag_to_notes["未分类"].append(note)

    lines.append("\n## 按标签分类\n")
    for tag in sorted(tag_to_notes.keys()):
        lines.append(f"\n### {tag}\n")
        for note in sorted(tag_to_notes[tag], key=lambda n: n.title or n.path.name):
            rel = note.path.name
            lines.append(f"- [{note.title or rel}]({rel})")

    # 按文件名列表
    lines.append("\n\n## 全部文件\n")
    for note in sorted(notes, key=lambda n: n.path.name):
        rel = note.path.name
        lines.append(f"- [{note.title or rel}]({rel})")

    output_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def generate_report(notes: list[Note], base_dir: Path) -> str:
    """生成 report 文本。"""
    total_files = len(notes)
    all_tags: set[str] = set()
    total_todos = 0
    for note in notes:
        all_tags.update(note.tags)
        total_todos += len(note.todos)

    broken = find_broken_links(notes, base_dir)
    total_broken = sum(len(v) for v in broken.values())

    lines: list[str] = []
    lines.append("=" * 50)
    lines.append("         Markdown 知识库报告")
    lines.append("=" * 50)
    lines.append(f"扫描目录 : {base_dir.resolve()}")
    lines.append(f"文件数量 : {total_files}")
    lines.append(f"标签数量 : {len(all_tags)}")
    lines.append(f"待办数量 : {total_todos}")
    lines.append(f"坏链数量 : {total_broken}")
    lines.append("-" * 50)

    if broken:
        lines.append("\n坏链列表:")
        for file_path, links in broken.items():
            lines.append(f"\n  {file_path}")
            for link in links:
                lines.append(f"    - {link}")
    else:
        lines.append("\n未发现坏链。")

    if all_tags:
        lines.append(f"\n标签列表: {', '.join(sorted(all_tags))}")
    else:
        lines.append("\n未发现标签。")

    lines.append("-" * 50)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _scan_cmd(args: argparse.Namespace) -> None:
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"错误: {directory} 不是有效目录", file=sys.stderr)
        sys.exit(1)
    notes = scan_directory(directory)
    index_path = directory / "index.md"
    generate_index(notes, index_path)
    print(f"已扫描 {len(notes)} 个文件，索引已生成: {index_path}")


def _report_cmd(args: argparse.Namespace) -> None:
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"错误: {directory} 不是有效目录", file=sys.stderr)
        sys.exit(1)
    notes = scan_directory(directory)
    report = generate_report(notes, directory)
    print(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kbtool",
        description="Markdown 知识库整理工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="扫描目录并生成 index.md")
    scan_parser.add_argument("directory", help="要扫描的目录路径")
    scan_parser.set_defaults(func=_scan_cmd)

    report_parser = subparsers.add_parser("report", help="生成知识库报告")
    report_parser.add_argument("directory", help="要报告的目录路径")
    report_parser.set_defaults(func=_report_cmd)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
