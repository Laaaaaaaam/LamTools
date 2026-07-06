"""
Unit tests for kb_core.py and kbtool.py.
"""

import os
import tempfile
import unittest
from pathlib import Path

import kb_core


class TestScanDirectory(unittest.TestCase):
    def test_scan_finds_markdown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("# A")
            (root / "b.txt").write_text("B")
            sub = root / "sub"
            sub.mkdir()
            (sub / "c.md").write_text("# C")
            files = kb_core.scan_directory(tmp)
            self.assertEqual(len(files), 2)
            self.assertTrue(all(f.suffix == ".md" for f in files))

    def test_scan_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = kb_core.scan_directory(tmp)
            self.assertEqual(files, [])

    def test_scan_nonexistent_directory(self):
        files = kb_core.scan_directory("/does/not/exist")
        self.assertEqual(files, [])


class TestExtractTitle(unittest.TestCase):
    def test_first_heading(self):
        self.assertEqual(kb_core.extract_title("# Hello World\n"), "Hello World")

    def test_fallback(self):
        self.assertEqual(kb_core.extract_title("No heading here"), "Untitled")


class TestExtractTags(unittest.TestCase):
    def test_yaml_list_tags(self):
        text = "---\ntags:\n  - foo\n  - bar\n---\n# Title"
        self.assertEqual(kb_core.extract_tags(text), ["bar", "foo"])

    def test_yaml_inline_tags(self):
        text = "---\ntags: [baz, qux]\n---\n# Title"
        self.assertEqual(kb_core.extract_tags(text), ["baz", "qux"])

    def test_inline_hash_tags(self):
        text = "Some text with #tag1 and #tag2 here."
        self.assertEqual(kb_core.extract_tags(text), ["tag1", "tag2"])

    def test_combined_tags(self):
        text = "---\ntags: [alpha]\n---\nAlso #beta"
        self.assertEqual(kb_core.extract_tags(text), ["alpha", "beta"])


class TestExtractLinks(unittest.TestCase):
    def test_wikilinks(self):
        text = "See [[Page One]] and [[Page Two]] for details."
        self.assertEqual(kb_core.extract_wikilinks(text), ["Page One", "Page Two"])

    def test_markdown_links(self):
        text = "[a](a.md) and [b](b.md) and [web](http://example.com)"
        self.assertEqual(kb_core.extract_markdown_links(text), ["a.md", "b.md"])


class TestExtractTodos(unittest.TestCase):
    def test_todos(self):
        text = "- [ ] Task A\n- [x] Task B\n- [X] Task C"
        todos = kb_core.extract_todos(text)
        self.assertEqual(len(todos), 3)
        self.assertEqual(todos[0], ("Task A", False))
        self.assertEqual(todos[1], ("Task B", True))
        self.assertEqual(todos[2], ("Task C", True))


class TestParseFile(unittest.TestCase):
    def test_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md = root / "test.md"
            md.write_text("# Title\n\n#tag1\n\n[Link](other.md)\n\n- [ ] todo1\n")
            data = kb_core.parse_file(md, root)
            self.assertEqual(data["title"], "Title")
            self.assertIn("tag1", data["tags"])
            self.assertIn("other.md", data["md_links"])
            self.assertEqual(len(data["todos"]), 1)
            self.assertEqual(data["todos"][0][0], "todo1")


class TestBrokenLinks(unittest.TestCase):
    def test_broken_markdown_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.md"
            a.write_text("[Missing](missing.md)")
            data = kb_core.parse_file(a, root)
            broken = kb_core.find_broken_links([data], root)
            self.assertEqual(len(broken), 1)
            self.assertIn("missing.md", broken[0][1])

    def test_broken_wikilink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.md"
            a.write_text("[[Missing Page]]")
            data = kb_core.parse_file(a, root)
            broken = kb_core.find_broken_links([data], root)
            self.assertEqual(len(broken), 1)
            self.assertIn("Missing Page", broken[0][1])

    def test_valid_links_not_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.md"
            b = root / "b.md"
            a.write_text("[B](b.md)")
            b.write_text("# B")
            data_a = kb_core.parse_file(a, root)
            data_b = kb_core.parse_file(b, root)
            broken = kb_core.find_broken_links([data_a, data_b], root)
            self.assertEqual(len(broken), 0)


class TestGenerateIndex(unittest.TestCase):
    def test_index_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.md"
            b = root / "b.md"
            a.write_text("# A\n\n#alpha\n")
            b.write_text("# B\n\n#alpha\n#beta\n")
            data_a = kb_core.parse_file(a, root)
            data_b = kb_core.parse_file(b, root)
            index = kb_core.generate_index([data_a, data_b], root)
            self.assertIn("# Knowledge Base Index", index)
            self.assertIn("alpha", index)
            self.assertIn("beta", index)
            self.assertIn("A", index)
            self.assertIn("B", index)


class TestBuildReport(unittest.TestCase):
    def test_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.md"
            b = root / "b.md"
            a.write_text("# A\n\n#tag1\n\n[Missing](missing.md)\n\n- [ ] todo1\n- [x] done1\n")
            b.write_text("# B\n\n#tag1 #tag2\n")
            report = kb_core.build_report(tmp)
            self.assertEqual(report["file_count"], 2)
            self.assertEqual(report["tag_count"], 2)
            self.assertEqual(report["todo_count"], 2)
            self.assertEqual(len(report["broken_links"]), 1)


if __name__ == "__main__":
    unittest.main()
