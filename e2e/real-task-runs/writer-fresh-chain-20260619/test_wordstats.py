import pytest
import json
from io import StringIO

from wordstats import extract_words, count_words, sort_word_counts, analyze_file, main


class TestExtractWords:
    def test_basic_words(self):
        text = "Hello world hello"
        assert extract_words(text) == ["hello", "world", "hello"]

    def test_case_insensitive(self):
        text = "Hello HELLO hello"
        result = extract_words(text)
        assert all(w == "hello" for w in result)
        assert len(result) == 3

    def test_punctuation(self):
        text = "Hello, world! How are you?"
        assert extract_words(text) == ["hello", "world", "how", "are", "you"]

    def test_numbers_ignored(self):
        text = "I have 2 cats and 3 dogs"
        assert extract_words(text) == ["i", "have", "cats", "and", "dogs"]

    def test_contractions(self):
        text = "Don't worry, it's fine"
        assert extract_words(text) == ["don't", "worry", "it's", "fine"]

    def test_empty_string(self):
        assert extract_words("") == []


class TestCountWords:
    def test_count_basic(self):
        text = "the cat and the dog"
        result = count_words(text)
        assert result == {"the": 2, "cat": 1, "and": 1, "dog": 1}

    def test_count_empty(self):
        assert count_words("") == {}

    def test_single_word(self):
        assert count_words("hello") == {"hello": 1}


class TestSortWordCounts:
    def test_sort_by_frequency_then_alpha(self):
        counts = {"apple": 2, "zebra": 3, "banana": 2, "cat": 1}
        result = sort_word_counts(counts)
        expected = {"zebra": 3, "apple": 2, "banana": 2, "cat": 1}
        assert result == expected


class TestAnalyzeFile:
    def test_analyze_sample_txt(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world hello")
        result = analyze_file(str(test_file))
        assert result == {"hello": 2, "world": 1}

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            analyze_file("nonexistent_file_xyz.txt")


class TestCLI:
    def test_cli_with_file(self, tmp_path, monkeypatch, capsys):
        test_file = tmp_path / "input.txt"
        test_file.write_text("foo bar foo")

        monkeypatch.setattr("sys.argv", ["wordstats.py", str(test_file)])
        main()

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"foo": 2, "bar": 1}

    def test_cli_no_args(self, monkeypatch, capsys):
        import sys
        monkeypatch.setattr("sys.argv", ["wordstats.py"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage" in captured.err

    def test_cli_file_not_found(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["wordstats.py", "nonexistent.txt"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "File not found" in captured.err
