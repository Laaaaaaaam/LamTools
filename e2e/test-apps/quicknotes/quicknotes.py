#!/usr/bin/env python3
"""
quicknotes.py — 轻量级 Markdown 笔记管理工具

用法:
    python quicknotes.py new  <标题>        创建一篇 Markdown 笔记
    python quicknotes.py list               列出所有笔记
    python quicknotes.py new <标题> -t tag  创建笔记并添加标签

笔记存储在脚本同目录下的 notes/ 目录中，每篇笔记为一个 .md 文件。
"""

import os
import sys
import argparse
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────
# 笔记目录: 与脚本同级的 notes/ 目录（不再用 home 目录，保证可测试性）
NOTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes")
DATE_FMT  = "%Y-%m-%d %H:%M"


# ── 工具函数 ──────────────────────────────────────────
def _ensure_dir() -> None:
    """确保笔记目录存在"""
    os.makedirs(NOTES_DIR, exist_ok=True)


def _slugify(title: str) -> str:
    """将标题转为安全的文件名（小写、连字符、无特殊字符）"""
    keep = "abcdefghijklmnopqrstuvwxyz0123456789-_ "
    slug = "".join(c if c.lower() in keep else "" for c in title)
    slug = "-".join(slug.lower().split())
    slug = "-".join(p for p in slug.split("-") if p)
    return slug or "untitled"


def _note_path(title: str) -> str:
    """根据标题生成完整文件路径（自动处理重名）"""
    slug = _slugify(title)
    base = os.path.join(NOTES_DIR, slug)
    path = base + ".md"
    counter = 1
    while os.path.exists(path):
        path = f"{base}-{counter}.md"
        counter += 1
    return path


# ── 核心命令 ──────────────────────────────────────────
def cmd_new(title: str, tags: list = None) -> str:
    """
    创建一篇新的 Markdown 笔记，返回文件路径。

    模板结构:
        ---
        title: <标题>
        date:  <创建时间>
        tags:  [<标签列表>]
        ---

        # <标题>
    """
    if tags is None:
        tags = []
    _ensure_dir()
    path = _note_path(title)
    now  = datetime.now().strftime(DATE_FMT)
    tag_str = ", ".join(tags) if tags else ""

    front_matter = (
        "---\n"
        "title: {}\n"
        "date: {}\n"
        "tags: [{}]\n"
        "---\n\n"
    ).format(title, now, tag_str)
    body = "# {}\n\n".format(title)

    with open(path, "w", encoding="utf-8") as f:
        f.write(front_matter)
        f.write(body)

    return path


def cmd_list() -> list:
    """
    列出所有笔记，返回按日期降序排列的字典列表。
    每项包含: filename, title, date, tags, path
    """
    _ensure_dir()
    notes = []

    for fname in sorted(os.listdir(NOTES_DIR)):
        if not fname.endswith(".md"):
            continue
        full = os.path.join(NOTES_DIR, fname)
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 front matter
        title = ""
        date = ""
        tags = []
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if line.lower().startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                    elif line.lower().startswith("date:"):
                        date = line.split(":", 1)[1].strip()
                    elif line.lower().startswith("tags:"):
                        raw = line.split(":", 1)[1].strip().strip("[]")
                        tags = [t.strip() for t in raw.split(",") if t.strip()]

        notes.append({
            "filename": fname,
            "title":    title or fname.replace(".md", ""),
            "date":     date,
            "tags":     tags,
            "path":     full,
        })

    # 按日期降序（最新在前）
    notes.sort(key=lambda n: n["date"], reverse=True)
    return notes


# ── 格式化输出 ────────────────────────────────────────
def _print_notes(notes: list) -> None:
    """将笔记列表以表格形式打印到终端"""
    if not notes:
        print("暂无笔记。使用 quicknotes new <标题> 创建第一篇！")
        return

    # 计算列宽
    idx_w   = max(len(str(len(notes))), 3)
    title_w = max(max([len(n["title"]) for n in notes], default=10), 6)
    date_w  = len(DATE_FMT)
    tags_w  = max(max([len(", ".join(n["tags"])) for n in notes], default=0), 4)

    header = (
        " {h:>{idx_w}}  "
        "{t:<{title_w}}  "
        "{d:<{date_w}}  "
        "{tg:<{tags_w}}  "
        "文件名"
    ).format(h="#", t="标题", d="日期", tg="标签",
             idx_w=idx_w, title_w=title_w, date_w=date_w, tags_w=tags_w)

    sep = (
        " {i}  "
        "{s1}  "
        "{s2}  "
        "{s3}  "
        "{s4}"
    ).format(i="-" * idx_w, s1="-" * title_w, s2="-" * date_w,
             s3="-" * tags_w, s4="-" * 20)

    print(header)
    print(sep)

    for i, n in enumerate(notes, 1):
        tag_str = ", ".join(n["tags"]) if n["tags"] else "-"
        line = (
            " {num:>{idx_w}}  "
            "{title:<{title_w}}  "
            "{date:<{date_w}}  "
            "{tags:<{tags_w}}  "
            "{fname}"
        ).format(num=i, title=n["title"], date=n["date"],
                 tags=tag_str, fname=n["filename"],
                 idx_w=idx_w, title_w=title_w,
                 date_w=date_w, tags_w=tags_w)
        print(line)

    print("\n共 {} 篇笔记  目录: {}".format(len(notes), NOTES_DIR))


# ── CLI 入口 ──────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="quicknotes",
        description="轻量级 Markdown 笔记管理工具",
    )
    sub = parser.add_subparsers(dest="command")

    # new 子命令
    p_new = sub.add_parser("new", help="创建一篇 Markdown 笔记")
    p_new.add_argument("title", help="笔记标题")
    p_new.add_argument("-t", "--tags", nargs="*", default=[],
                       help="标签列表，如: -t python cli")

    # list 子命令
    sub.add_parser("list", help="列出所有笔记")

    args = parser.parse_args()

    if args.command == "new":
        path = cmd_new(args.title, args.tags if args.tags else None)
        print("笔记已创建: {}".format(path))

    elif args.command == "list":
        notes = cmd_list()
        _print_notes(notes)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
