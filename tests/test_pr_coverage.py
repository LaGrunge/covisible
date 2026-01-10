"""Tests for PR coverage analysis."""

from pathlib import Path

import pytest

from covisible.analysis.diff import DiffAnalyzer
from covisible.analysis.pr_coverage import PRCoverageAnalyzer
from covisible.core.models import CoverageData, FileCoverage, LineCoverage


class TestPRCoverageAnalyzer:
    """Tests for PR coverage analyzer."""

    def test_analyze_new_lines_coverage(self):
        # Create coverage data
        coverage = CoverageData()
        file_cov = FileCoverage(path=Path("file.cpp"))
        file_cov.lines = {
            10: LineCoverage(line_number=10, count=5),
            11: LineCoverage(line_number=11, count=0),
            12: LineCoverage(line_number=12, count=3),
        }
        coverage.files[Path("file.cpp")] = file_cov

        # Create diff
        diff_content = """diff --git a/file.cpp b/file.cpp
--- a/file.cpp
+++ b/file.cpp
@@ -9,0 +10,3 @@
+line 10
+line 11
+line 12
"""
        diff = DiffAnalyzer.from_unified_diff(diff_content)

        # Analyze
        analyzer = PRCoverageAnalyzer(current=coverage, diff=diff)
        summary = analyzer.analyze()

        assert summary.total_new_lines == 3
        assert summary.covered_new_lines == 2
        assert summary.uncovered_new_lines == 1
        assert summary.new_lines_coverage_percent == pytest.approx(66.67, rel=0.01)

    def test_analyze_with_baseline(self):
        # Current coverage: 10 lines, 8 covered (80%)
        current = CoverageData()
        file_cov = FileCoverage(path=Path("file.cpp"))
        file_cov.lines = {i: LineCoverage(line_number=i, count=1) for i in range(1, 9)}
        file_cov.lines[9] = LineCoverage(line_number=9, count=0)
        file_cov.lines[10] = LineCoverage(line_number=10, count=0)
        current.files[Path("file.cpp")] = file_cov

        # Baseline coverage: 8 lines, 6 covered (75%)
        baseline = CoverageData()
        baseline_file = FileCoverage(path=Path("file.cpp"))
        baseline_file.lines = {i: LineCoverage(line_number=i, count=1) for i in range(1, 7)}
        baseline_file.lines[7] = LineCoverage(line_number=7, count=0)
        baseline_file.lines[8] = LineCoverage(line_number=8, count=0)
        baseline.files[Path("file.cpp")] = baseline_file

        # Diff
        diff_content = """diff --git a/file.cpp b/file.cpp
--- a/file.cpp
+++ b/file.cpp
@@ -8,0 +9,2 @@
+line 9
+line 10
"""
        diff = DiffAnalyzer.from_unified_diff(diff_content)

        analyzer = PRCoverageAnalyzer(current=current, diff=diff, baseline=baseline)
        summary = analyzer.analyze()

        # Current has 80% (8/10), baseline has 75% (6/8) -> delta = +5%
        assert summary.coverage_delta > 0
        assert summary.coverage_improved

    def test_get_uncovered_new_lines(self):
        coverage = CoverageData()
        file_cov = FileCoverage(path=Path("file.cpp"))
        file_cov.lines = {
            10: LineCoverage(line_number=10, count=5),
            11: LineCoverage(line_number=11, count=0),
            12: LineCoverage(line_number=12, count=0),
        }
        coverage.files[Path("file.cpp")] = file_cov

        diff_content = """diff --git a/file.cpp b/file.cpp
--- a/file.cpp
+++ b/file.cpp
@@ -9,0 +10,3 @@
+line 10
+line 11
+line 12
"""
        diff = DiffAnalyzer.from_unified_diff(diff_content)

        analyzer = PRCoverageAnalyzer(current=coverage, diff=diff)
        analyzer.analyze()

        uncovered = analyzer.get_uncovered_new_lines()
        assert Path("file.cpp") in uncovered
        assert uncovered[Path("file.cpp")] == [11, 12]

    def test_no_diff_files(self):
        coverage = CoverageData()
        diff = DiffAnalyzer()

        analyzer = PRCoverageAnalyzer(current=coverage, diff=diff)
        summary = analyzer.analyze()

        assert summary.total_new_lines == 0
        assert summary.new_lines_coverage_percent == 100.0
