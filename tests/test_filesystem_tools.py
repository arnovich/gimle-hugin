"""Tests for filesystem builtin tools."""

from gimle.hugin.tools.builtins.list_files import list_files
from gimle.hugin.tools.builtins.read_file import read_file
from gimle.hugin.tools.builtins.search_files import search_files


class TestReadFile:
    """Tests for read_file tool."""

    def test_read_existing_file(self, tmp_path):
        """Test reading an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        result = read_file(str(test_file))

        assert not result.is_error
        assert result.content["total_lines"] == 3
        assert result.content["lines_read"] == 3
        assert "line 1" in result.content["content"]
        assert "line 2" in result.content["content"]

    def test_read_file_with_offset(self, tmp_path):
        """Test reading file with start_line offset."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\n")

        result = read_file(str(test_file), start_line=2, max_lines=2)

        assert not result.is_error
        assert result.content["start_line"] == 2
        assert result.content["lines_read"] == 2
        assert "line 2" in result.content["content"]
        assert "line 3" in result.content["content"]
        assert "line 1" not in result.content["content"]

    def test_read_nonexistent_file(self, tmp_path):
        """Test reading a file that doesn't exist."""
        result = read_file(str(tmp_path / "nonexistent.txt"))

        assert result.is_error
        assert "not found" in result.content["error"].lower()

    def test_read_directory_fails(self, tmp_path):
        """Test that reading a directory returns error."""
        result = read_file(str(tmp_path))

        assert result.is_error
        assert "not a file" in result.content["error"].lower()


class TestListFiles:
    """Tests for list_files tool."""

    def test_list_directory(self, tmp_path):
        """Test listing files in a directory."""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.py").write_text("content")
        (tmp_path / "subdir").mkdir()

        result = list_files(str(tmp_path))

        assert not result.is_error
        assert "file1.txt" in result.content["files"]
        assert "file2.py" in result.content["files"]
        assert "subdir/" in result.content["directories"]

    def test_list_with_glob_pattern(self, tmp_path):
        """Test listing files with glob pattern."""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.py").write_text("content")
        (tmp_path / "file3.txt").write_text("content")

        result = list_files(str(tmp_path), pattern="*.txt")

        assert not result.is_error
        assert "file1.txt" in result.content["files"]
        assert "file3.txt" in result.content["files"]
        assert "file2.py" not in result.content["files"]

    def test_list_recursive(self, tmp_path):
        """Test recursive file listing."""
        (tmp_path / "file1.py").write_text("content")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.py").write_text("content")

        result = list_files(str(tmp_path), pattern="*.py", recursive=True)

        assert not result.is_error
        assert result.content["total_files"] == 2

    def test_list_nonexistent_directory(self, tmp_path):
        """Test listing nonexistent directory."""
        result = list_files(str(tmp_path / "nonexistent"))

        assert result.is_error
        assert "not found" in result.content["error"].lower()


class TestSearchFiles:
    """Tests for search_files tool."""

    def test_search_single_file(self, tmp_path):
        """Test searching in a single file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\nfoo bar\nhello again\n")

        result = search_files("hello", str(test_file))

        assert not result.is_error
        assert result.content["total_matches"] == 2
        assert result.content["files_with_matches"] == 1

    def test_search_with_regex(self, tmp_path):
        """Test searching with regex pattern."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello123\nhello456\nworld\n")

        result = search_files(r"hello\d+", str(test_file))

        assert not result.is_error
        assert result.content["total_matches"] == 2

    def test_search_directory(self, tmp_path):
        """Test searching across multiple files in directory."""
        (tmp_path / "file1.txt").write_text("findme here\n")
        (tmp_path / "file2.txt").write_text("nothing\n")
        (tmp_path / "file3.txt").write_text("findme again\n")

        result = search_files("findme", str(tmp_path))

        assert not result.is_error
        assert result.content["total_matches"] == 2
        assert result.content["files_with_matches"] == 2

    def test_search_case_insensitive(self, tmp_path):
        """Test case insensitive search."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello\nHELLO\nhello\n")

        result = search_files("hello", str(test_file), ignore_case=True)

        assert not result.is_error
        assert result.content["total_matches"] == 3

    def test_search_with_file_pattern(self, tmp_path):
        """Test searching with file pattern filter."""
        (tmp_path / "file1.py").write_text("match\n")
        (tmp_path / "file2.txt").write_text("match\n")

        result = search_files("match", str(tmp_path), file_pattern="*.py")

        assert not result.is_error
        assert result.content["total_matches"] == 1

    def test_search_invalid_regex(self, tmp_path):
        """Test searching with invalid regex pattern."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n")

        result = search_files("[invalid", str(test_file))

        assert result.is_error
        assert "invalid regex" in result.content["error"].lower()

    def test_search_max_results(self, tmp_path):
        """Test max_results limit."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("match\n" * 100)

        result = search_files("match", str(test_file), max_results=5)

        assert not result.is_error
        assert result.content["total_matches"] == 5
        assert result.content["truncated"] is True
