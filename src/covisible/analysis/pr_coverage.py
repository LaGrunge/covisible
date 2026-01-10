"""PR-focused coverage analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from covisible.analysis.diff import DiffAnalyzer, FileDiff
from covisible.core.models import CoverageData, FileCoverage, LineStatus


@dataclass
class LineCoverageInfo:
    """Coverage info for a single line in PR context."""

    line_number: int
    status: LineStatus
    execution_count: int
    is_new: bool
    is_modified: bool
    function_name: str | None = None

    @property
    def is_pr_relevant(self) -> bool:
        """Whether this line is part of the PR changes."""
        return self.is_new or self.is_modified


@dataclass
class FilePRCoverage:
    """PR-focused coverage for a single file."""

    path: Path
    diff: FileDiff | None
    coverage: FileCoverage | None
    lines: dict[int, LineCoverageInfo] = field(default_factory=dict)

    @property
    def is_new_file(self) -> bool:
        return self.diff.is_new_file if self.diff else False

    @property
    def added_lines(self) -> set[int]:
        return self.diff.added_lines if self.diff else set()

    @property
    def total_new_lines(self) -> int:
        """Total number of new/modified lines."""
        return len(self.added_lines)

    @property
    def covered_new_lines(self) -> int:
        """Number of covered new/modified lines."""
        if not self.coverage:
            return 0
        count = 0
        for line_num in self.added_lines:
            if line_num in self.coverage.lines:
                if self.coverage.lines[line_num].is_covered:
                    count += 1
        return count

    @property
    def uncovered_new_lines(self) -> int:
        """Number of uncovered new/modified lines."""
        return self.total_new_lines - self.covered_new_lines

    @property
    def new_lines_coverage_percent(self) -> float:
        """Coverage percentage for new/modified lines only."""
        if self.total_new_lines == 0:
            return 100.0
        return (self.covered_new_lines / self.total_new_lines) * 100

    def get_uncovered_new_line_numbers(self) -> list[int]:
        """Get sorted list of uncovered new line numbers."""
        if not self.coverage:
            return sorted(self.added_lines)
        result = []
        for line_num in self.added_lines:
            if line_num not in self.coverage.lines:
                result.append(line_num)
            elif not self.coverage.lines[line_num].is_covered:
                result.append(line_num)
        return sorted(result)


@dataclass
class PRCoverageSummary:
    """Summary of PR coverage changes."""

    total_new_lines: int = 0
    covered_new_lines: int = 0
    uncovered_new_lines: int = 0
    new_lines_coverage_percent: float = 100.0

    total_lines_current: int = 0
    covered_lines_current: int = 0
    coverage_percent_current: float = 100.0

    total_lines_baseline: int = 0
    covered_lines_baseline: int = 0
    coverage_percent_baseline: float = 100.0

    coverage_delta: float = 0.0
    files_changed: int = 0
    files_with_uncovered_new_lines: int = 0

    @property
    def coverage_improved(self) -> bool:
        return self.coverage_delta > 0

    @property
    def coverage_degraded(self) -> bool:
        return self.coverage_delta < 0


@dataclass
class PRCoverageAnalyzer:
    """Analyzes coverage in the context of a PR."""

    current: CoverageData
    diff: DiffAnalyzer
    baseline: CoverageData | None = None
    files: dict[Path, FilePRCoverage] = field(default_factory=dict)
    summary: PRCoverageSummary = field(default_factory=PRCoverageSummary)

    def analyze(self) -> PRCoverageSummary:
        """Perform PR coverage analysis."""
        self._analyze_files()
        self._compute_summary()
        return self.summary

    def _analyze_files(self) -> None:
        """Analyze coverage for each changed file."""
        for path, file_diff in self.diff.files.items():
            if file_diff.is_deleted_file:
                continue

            file_cov = self._find_file_coverage(path)
            pr_cov = FilePRCoverage(
                path=path,
                diff=file_diff,
                coverage=file_cov,
            )

            if file_cov:
                for line_num in file_diff.added_lines:
                    line_cov = file_cov.lines.get(line_num)
                    if line_cov:
                        info = LineCoverageInfo(
                            line_number=line_num,
                            status=line_cov.status,
                            execution_count=line_cov.count,
                            is_new=file_diff.is_new_file,
                            is_modified=not file_diff.is_new_file,
                            function_name=line_cov.function_name,
                        )
                    else:
                        info = LineCoverageInfo(
                            line_number=line_num,
                            status=LineStatus.NOT_EXECUTABLE,
                            execution_count=0,
                            is_new=file_diff.is_new_file,
                            is_modified=not file_diff.is_new_file,
                        )
                    pr_cov.lines[line_num] = info

            self.files[path] = pr_cov

    def _find_file_coverage(self, path: Path) -> FileCoverage | None:
        """Find coverage data for a file, handling path variations."""
        if path in self.current.files:
            return self.current.files[path]

        for cov_path, cov in self.current.files.items():
            if cov_path.name == path.name:
                return cov
            if str(cov_path).endswith(str(path)):
                return cov
            if str(path).endswith(str(cov_path)):
                return cov

        return None

    def _compute_summary(self) -> None:
        """Compute PR coverage summary."""
        total_new = 0
        covered_new = 0
        files_with_uncovered = 0

        for pr_cov in self.files.values():
            total_new += pr_cov.total_new_lines
            covered_new += pr_cov.covered_new_lines
            if pr_cov.uncovered_new_lines > 0:
                files_with_uncovered += 1

        self.summary = PRCoverageSummary(
            total_new_lines=total_new,
            covered_new_lines=covered_new,
            uncovered_new_lines=total_new - covered_new,
            new_lines_coverage_percent=(covered_new / total_new * 100) if total_new > 0 else 100.0,
            total_lines_current=self.current.total_lines,
            covered_lines_current=self.current.covered_lines,
            coverage_percent_current=self.current.line_coverage_percent,
            total_lines_baseline=self.baseline.total_lines if self.baseline else 0,
            covered_lines_baseline=self.baseline.covered_lines if self.baseline else 0,
            coverage_percent_baseline=(
                self.baseline.line_coverage_percent if self.baseline else 0.0
            ),
            coverage_delta=(
                self.current.line_coverage_percent - self.baseline.line_coverage_percent
                if self.baseline
                else 0.0
            ),
            files_changed=len(self.files),
            files_with_uncovered_new_lines=files_with_uncovered,
        )

    def get_uncovered_new_lines(self) -> dict[Path, list[int]]:
        """Get all uncovered new lines grouped by file."""
        result: dict[Path, list[int]] = {}
        for path, pr_cov in self.files.items():
            uncovered = pr_cov.get_uncovered_new_line_numbers()
            if uncovered:
                result[path] = uncovered
        return result

    def get_critical_uncovered(self) -> list[tuple[Path, int, str | None]]:
        """Get uncovered lines in functions that were modified.

        Returns list of (file_path, line_number, function_name) tuples.
        """
        result: list[tuple[Path, int, str | None]] = []
        for path, pr_cov in self.files.items():
            if not pr_cov.coverage:
                continue
            for line_num in pr_cov.get_uncovered_new_line_numbers():
                func = pr_cov.coverage.get_function_at_line(line_num)
                func_name = func.demangled_name or func.name if func else None
                result.append((path, line_num, func_name))
        return result
