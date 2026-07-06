#!/usr/bin/env python3
"""kbtool 单元测试"""

import tempfile
from pathlib import Path

import kbtool
from kbtool import (
    Note,
    find_broken_links,
    generate_index,
    generate_report,
    parse_note,
    scan_directory,
)


class TestParseNote:
    def test_extract_title(self):
        content = "# 测试标题\n\n这是正文。"
        path = Path("test.md")
        path.write_text(content, encoding="utf-8")
        try:
            note = parse_note(path)
            assert note.title == "测试标题"
        finally:
            path.unlink()

    def test_extract_tags_inline(self):
        content = "# 文档\n\n这是正文，包含 #python #testing 标签。"
        path = Path("test.md")
        path.write_text(content, encoding="utf-8")
        try:
            note = parse_note(path)
            assert "python" in note.tags
            assert "testing" in note.tags
        finally:
            path.unlink()

    def test_extract_wiki_links(self):
        content = "# 文档\n\n参考 [[其他页面]] 和 [[另一个页面]]。"
        path = Path("test.md")
        path.write_text(content, encoding="utf-8")
        try:
            note = parse_note(path)
            assert "其他页面" in note.wiki_links
            assert "另一个页面" in note.wiki_links
        finally:
            path.unlink()

    def test_extract_md_links(self):
        content = "# 文档\n\n[链接文本](target.md)"
        path = Path("test.md")
        path.write_text(content, encoding="utf-8")
        try:
            note = parse_note(path)
            assert "target.md" in note.md_links
        finally:
            path.unlink()

    def test_extract_todos(self):
        content = "# 文档\n\n- [ ] 任务一\n- [x] 已完成\n- [ ] 任务二"
        path = Path("test.md")
        path.write_text(content, encoding="utf-8")
        try:
            note = parse_note(path)
            assert len(note.todos) == 2
            assert "任务一" in note.todos
            assert "任务二" in note.todos
        finally:
            path.unlink()

    def test_front_matter_tags(self):
        content = "---\ntags: python, testing\n---\n# 文档\n\n正文。"
        path = Path("test.md")
        path.write_text(content, encoding="utf-8")
        try:
            note = parse_note(path)
            assert "python" in note.tags
            assert "testing" in note.tags
        finally:
            path.unlink()

    def test_tags_in_code_block_ignored(self):
        content = "# 文档\n\n```python\n# color = #123456\n```\n\n外部 #real_tag"
        path = Path("test.md")
        path.write_text(content, encoding="utf-8")
        try:
            note = parse_note(path)
            assert "real_tag" in note.tags
            assert "123456" not in note.tags
        finally:
            path.unlink()


class TestScanDirectory:
    def test_scan_finds_md_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A\n", encoding="utf-8")
            (d / "b.md").write_text("# B\n", encoding="utf-8")
            (d / "c.txt").write_text("not markdown", encoding="utf-8")
            notes = scan_directory(d)
            assert len(notes) == 2
            titles = {n.title for n in notes}
            assert "A" in titles
            assert "B" in titles

    def test_scan_skips_index_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "index.md").write_text("# Index\n", encoding="utf-8")
            (d / "note.md").write_text("# Note\n", encoding="utf-8")
            notes = scan_directory(d)
            assert len(notes) == 1
            assert notes[0].title == "Note"

    def test_scan_recursive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            sub = d / "sub"
            sub.mkdir()
            (d / "root.md").write_text("# Root\n", encoding="utf-8")
            (sub / "nested.md").write_text("# Nested\n", encoding="utf-8")
            notes = scan_directory(d)
            assert len(notes) == 2
            titles = {n.title for n in notes}
            assert "Root" in titles
            assert "Nested" in titles


class TestBrokenLinks:
    def test_no_broken_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A\n\n[[b]]", encoding="utf-8")
            (d / "b.md").write_text("# B\n", encoding="utf-8")
            notes = scan_directory(d)
            broken = find_broken_links(notes, d)
            assert len(broken) == 0

    def test_broken_wiki_link(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A\n\n[[不存在的页面]]", encoding="utf-8")
            notes = scan_directory(d)
            broken = find_broken_links(notes, d)
            assert len(broken) == 1
            assert "[[不存在的页面]]" in broken[str(d / "a.md")]

    def test_broken_md_link(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A\n\n[链接](missing.md)", encoding="utf-8")
            notes = scan_directory(d)
            broken = find_broken_links(notes, d)
            assert len(broken) == 1


class TestGenerateIndex:
    def test_index_contains_titles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A 标题\n", encoding="utf-8")
            (d / "b.md").write_text("# B 标题\n", encoding="utf-8")
            notes = scan_directory(d)
            index_path = d / "index.md"
            generate_index(notes, index_path)
            content = index_path.read_text(encoding="utf-8")
            assert "A 标题" in content
            assert "B 标题" in content
            assert "# 知识库索引" in content

    def test_index_grouped_by_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A\n\n#tag1", encoding="utf-8")
            (d / "b.md").write_text("# B\n\n#tag1 #tag2", encoding="utf-8")
            notes = scan_directory(d)
            index_path = d / "index.md"
            generate_index(notes, index_path)
            content = index_path.read_text(encoding="utf-8")
            assert "tag1" in content
            assert "tag2" in content


class TestGenerateReport:
    def test_report_statistics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A\n\n#tag1\n- [ ] 任务", encoding="utf-8")
            (d / "b.md").write_text("# B\n\n#tag2", encoding="utf-8")
            notes = scan_directory(d)
            report = generate_report(notes, d)
            assert "文件数量" in report
            assert "标签数量" in report
            assert "待办数量" in report
            assert "2" in report  # 文件数

    def test_report_broken_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "a.md").write_text("# A\n\n[[missing]]", encoding="utf-8")
            notes = scan_directory(d)
            report = generate_report(notes, d)
            assert "坏链数量" in report
            assert "[[missing]]" in report
