"""Tests for file grouping by module/directory."""

from pathlib import Path

import pytest

from covisible.analysis.grouping import (
    ModuleGroup,
    ModuleGrouper,
    group_coverage_by_directory,
    group_coverage_by_pattern,
)
from covisible.core.models import CoverageData, FileCoverage, LineCoverage


class TestModuleGroup:
    """Tests for ModuleGroup dataclass."""

    def test_empty_group(self):
        group = ModuleGroup(name="test", path="test/path")
        assert group.total_lines == 0
        assert group.covered_lines == 0
        assert group.uncovered_lines == 0
        assert group.coverage_percent == 100.0
        assert group.total_functions == 0
        assert group.covered_functions == 0
        assert group.file_count == 0

    def test_group_with_files(self):
        group = ModuleGroup(name="src", path="src")

        # Create file coverage with lines
        file1 = FileCoverage(path=Path("src/file1.py"))
        file1.lines = {
            1: LineCoverage(line_number=1, count=5),
            2: LineCoverage(line_number=2, count=0),
            3: LineCoverage(line_number=3, count=3),
        }

        file2 = FileCoverage(path=Path("src/file2.py"))
        file2.lines = {
            1: LineCoverage(line_number=1, count=1),
            2: LineCoverage(line_number=2, count=0),
        }

        group.files = [file1, file2]

        assert group.total_lines == 5
        assert group.covered_lines == 3
        assert group.uncovered_lines == 2
        assert group.coverage_percent == pytest.approx(60.0)
        assert group.file_count == 2

    def test_to_dict(self):
        group = ModuleGroup(name="module", path="src/module")
        file_cov = FileCoverage(path=Path("src/module/file.py"))
        file_cov.lines = {
            1: LineCoverage(line_number=1, count=1),
            2: LineCoverage(line_number=2, count=0),
        }
        group.files = [file_cov]

        result = group.to_dict()

        assert result["name"] == "module"
        assert result["path"] == "src/module"
        assert result["file_count"] == 1
        assert result["total_lines"] == 2
        assert result["covered_lines"] == 1
        assert result["uncovered_lines"] == 1
        assert result["coverage_percent"] == 50.0


class TestModuleGrouper:
    """Tests for ModuleGrouper class."""

    def _create_coverage_data(self) -> CoverageData:
        """Create sample coverage data for testing."""
        coverage = CoverageData()

        # src/core/file1.py
        file1 = FileCoverage(path=Path("src/core/file1.py"))
        file1.lines = {
            1: LineCoverage(line_number=1, count=5),
            2: LineCoverage(line_number=2, count=0),
        }
        coverage.files[Path("src/core/file1.py")] = file1

        # src/core/file2.py
        file2 = FileCoverage(path=Path("src/core/file2.py"))
        file2.lines = {
            1: LineCoverage(line_number=1, count=1),
        }
        coverage.files[Path("src/core/file2.py")] = file2

        # src/utils/helper.py
        file3 = FileCoverage(path=Path("src/utils/helper.py"))
        file3.lines = {
            1: LineCoverage(line_number=1, count=0),
            2: LineCoverage(line_number=2, count=0),
            3: LineCoverage(line_number=3, count=0),
        }
        coverage.files[Path("src/utils/helper.py")] = file3

        return coverage

    def test_group_by_directory_depth_1(self):
        coverage = self._create_coverage_data()
        grouper = ModuleGrouper(coverage, base_path="src", depth=1)

        groups = grouper.group_by_directory()

        assert len(groups) == 2
        # Sorted by uncovered lines descending
        assert groups[0].name == "utils"  # 3 uncovered
        assert groups[1].name == "core"  # 1 uncovered

    def test_group_by_directory_depth_2(self):
        coverage = CoverageData()

        file1 = FileCoverage(path=Path("src/app/core/file.py"))
        file1.lines = {1: LineCoverage(line_number=1, count=1)}
        coverage.files[Path("src/app/core/file.py")] = file1

        file2 = FileCoverage(path=Path("src/app/utils/file.py"))
        file2.lines = {1: LineCoverage(line_number=1, count=0)}
        coverage.files[Path("src/app/utils/file.py")] = file2

        grouper = ModuleGrouper(coverage, base_path="src", depth=2)
        groups = grouper.group_by_directory()

        assert len(groups) == 2

    def test_group_by_directory_auto_base_path(self):
        coverage = self._create_coverage_data()
        grouper = ModuleGrouper(coverage, depth=1)

        groups = grouper.group_by_directory()

        # Should auto-detect "src" as common prefix
        assert len(groups) == 2

    def test_group_by_directory_empty_coverage(self):
        coverage = CoverageData()
        grouper = ModuleGrouper(coverage, depth=1)

        groups = grouper.group_by_directory()

        assert len(groups) == 0

    def test_find_common_prefix(self):
        coverage = self._create_coverage_data()
        grouper = ModuleGrouper(coverage)

        prefix = grouper._find_common_prefix()

        assert prefix == Path("src")

    def test_find_common_prefix_no_common(self):
        coverage = CoverageData()
        file1 = FileCoverage(path=Path("src/file.py"))
        file1.lines = {1: LineCoverage(line_number=1, count=1)}
        coverage.files[Path("src/file.py")] = file1

        file2 = FileCoverage(path=Path("tests/test.py"))
        file2.lines = {1: LineCoverage(line_number=1, count=1)}
        coverage.files[Path("tests/test.py")] = file2

        grouper = ModuleGrouper(coverage)
        prefix = grouper._find_common_prefix()

        assert prefix is None

    def test_group_by_pattern(self):
        coverage = self._create_coverage_data()
        patterns = {
            "Core": "**/core/*",
            "Utils": "**/utils/*",
        }

        grouper = ModuleGrouper(coverage)
        groups = grouper.group_by_pattern(patterns)

        group_names = {g.name for g in groups}
        assert "Core" in group_names
        assert "Utils" in group_names

    def test_group_by_pattern_with_unmatched(self):
        coverage = CoverageData()

        file1 = FileCoverage(path=Path("src/core/file.py"))
        file1.lines = {1: LineCoverage(line_number=1, count=1)}
        coverage.files[Path("src/core/file.py")] = file1

        file2 = FileCoverage(path=Path("other/random.py"))
        file2.lines = {1: LineCoverage(line_number=1, count=0)}
        coverage.files[Path("other/random.py")] = file2

        patterns = {"Core": "**/core/*"}

        grouper = ModuleGrouper(coverage)
        groups = grouper.group_by_pattern(patterns)

        group_names = {g.name for g in groups}
        assert "Core" in group_names
        assert "Other" in group_names  # Unmatched files go to "Other"

    def test_shallow_file_grouping(self):
        """Test grouping when file is in root or shallow directory."""
        coverage = CoverageData()

        file1 = FileCoverage(path=Path("setup.py"))
        file1.lines = {1: LineCoverage(line_number=1, count=1)}
        coverage.files[Path("setup.py")] = file1

        grouper = ModuleGrouper(coverage, depth=1)
        groups = grouper.group_by_directory()

        assert len(groups) == 1


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_group_coverage_by_directory(self):
        coverage = CoverageData()

        file1 = FileCoverage(path=Path("src/module/file.py"))
        file1.lines = {
            1: LineCoverage(line_number=1, count=1),
            2: LineCoverage(line_number=2, count=0),
        }
        coverage.files[Path("src/module/file.py")] = file1

        result = group_coverage_by_directory(coverage, base_path="src", depth=1)

        assert len(result) == 1
        assert result[0]["name"] == "module"
        assert result[0]["total_lines"] == 2

    def test_group_coverage_by_pattern(self):
        coverage = CoverageData()

        file1 = FileCoverage(path=Path("src/tests/test_file.py"))
        file1.lines = {1: LineCoverage(line_number=1, count=1)}
        coverage.files[Path("src/tests/test_file.py")] = file1

        patterns = {"Tests": "**/tests/*"}
        result = group_coverage_by_pattern(coverage, patterns)

        assert len(result) == 1
        assert result[0]["name"] == "Tests"
