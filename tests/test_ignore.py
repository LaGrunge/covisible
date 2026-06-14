"""Tests for the ignore/exclude module (file patterns + line markers)."""

from pathlib import Path

from covisible.core.ignore import IgnoreConfig, IgnoreFilter
from covisible.core.models import CoverageData, FileCoverage, FunctionCoverage, LineCoverage


class TestIgnoreConfig:
    """Tests for IgnoreConfig construction."""

    def test_defaults(self):
        config = IgnoreConfig()
        assert config.exclude_patterns == []
        assert config.include_patterns == []
        assert "# pragma: no cover" in config.line_markers
        assert ("// LCOV_EXCL_START", "// LCOV_EXCL_STOP") in config.block_markers

    def test_from_dict(self):
        config = IgnoreConfig.from_dict(
            {
                "exclude": ["*_test.cpp"],
                "include": ["src/*"],
                "line_markers": ["// SKIP"],
                "block_markers": [["// OFF", "// ON"]],
            }
        )
        assert config.exclude_patterns == ["*_test.cpp"]
        assert config.include_patterns == ["src/*"]
        assert config.line_markers == ["// SKIP"]
        assert config.block_markers == [("// OFF", "// ON")]

    def test_from_dict_empty_block_markers_fall_back_to_defaults(self):
        # Empty block_markers should not wipe out the sensible defaults.
        config = IgnoreConfig.from_dict({"exclude": ["x"]})
        assert config.block_markers  # non-empty defaults


class TestShouldIncludeFile:
    """Tests for file-level include/exclude matching."""

    def test_exclude_pattern(self):
        f = IgnoreFilter(IgnoreConfig(exclude_patterns=["*_test.cpp"]))
        assert f.should_include_file("src/foo.cpp") is True
        assert f.should_include_file("src/foo_test.cpp") is False

    def test_include_pattern_restricts(self):
        f = IgnoreFilter(IgnoreConfig(include_patterns=["src/*"]))
        assert f.should_include_file("src/foo.cpp") is True
        assert f.should_include_file("other/foo.cpp") is False

    def test_exclude_takes_precedence_over_include(self):
        f = IgnoreFilter(
            IgnoreConfig(include_patterns=["src/*"], exclude_patterns=["*_test.cpp"])
        )
        assert f.should_include_file("src/foo_test.cpp") is False


class TestGetIgnoredLines:
    """Tests for line-marker resolution against real file content."""

    def test_single_line_marker(self, tmp_path: Path):
        src = tmp_path / "a.py"
        src.write_text("a = 1\nb = 2  # pragma: no cover\nc = 3\n")
        f = IgnoreFilter()
        assert f.get_ignored_lines(src) == {2}

    def test_block_marker(self, tmp_path: Path):
        src = tmp_path / "a.cpp"
        src.write_text(
            "int a;\n"
            "// LCOV_EXCL_START\n"
            "int b;\n"
            "int c;\n"
            "// LCOV_EXCL_STOP\n"
            "int d;\n"
        )
        f = IgnoreFilter()
        # Start, body, and stop lines (2..5) are all ignored.
        assert f.get_ignored_lines(src) == {2, 3, 4, 5}

    def test_missing_file_returns_empty(self, tmp_path: Path):
        f = IgnoreFilter()
        assert f.get_ignored_lines(tmp_path / "nope.py") == set()


class TestFilterCoverageData:
    """Regression tests for filter_coverage_data (was broken against the model)."""

    def _make_coverage(self, path: Path) -> CoverageData:
        lines = {n: LineCoverage(line_number=n, count=(n % 2)) for n in range(1, 5)}
        func = FunctionCoverage(
            name="f", demangled_name=None, start_line=2, end_line=4, execution_count=1
        )
        file_cov = FileCoverage(path=path, lines=lines, functions=[func])
        return CoverageData(files={path: file_cov})

    def test_drops_ignored_lines_and_their_functions(self, tmp_path: Path):
        src = tmp_path / "a.py"
        src.write_text("l1\nl2  # pragma: no cover\nl3\nl4\n")
        coverage = self._make_coverage(src)

        filtered = IgnoreFilter().filter_coverage_data(coverage)

        result = filtered.files[src]
        # Line 2 is ignored and removed; the rest survive.
        assert set(result.lines.keys()) == {1, 3, 4}
        # The function starts on the ignored line 2, so it is dropped.
        assert result.functions == []

    def test_excluded_file_is_removed_entirely(self, tmp_path: Path):
        src = tmp_path / "a_test.py"
        src.write_text("l1\nl2\n")
        coverage = self._make_coverage(src)

        config = IgnoreConfig(exclude_patterns=["*_test.py"])
        filtered = IgnoreFilter(config).filter_coverage_data(coverage)

        assert filtered.files == {}

    def test_file_without_ignored_lines_is_passed_through(self, tmp_path: Path):
        src = tmp_path / "a.py"
        src.write_text("l1\nl2\nl3\nl4\n")
        coverage = self._make_coverage(src)

        filtered = IgnoreFilter().filter_coverage_data(coverage)

        # Unchanged: same object, all four lines kept.
        assert filtered.files[src] is coverage.files[src]
        assert set(filtered.files[src].lines.keys()) == {1, 2, 3, 4}
