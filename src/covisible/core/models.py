"""Core data models for coverage information."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Self


class LineStatus(Enum):
    """Coverage status for a line."""

    COVERED = "covered"
    NOT_COVERED = "not_covered"
    NOT_EXECUTABLE = "not_executable"


@dataclass
class BranchCoverage:
    """Branch coverage information."""

    line_number: int
    branch_id: int
    count: int
    is_throw: bool = False
    is_fallthrough: bool = False

    @property
    def is_covered(self) -> bool:
        return self.count > 0


@dataclass
class LineCoverage:
    """Coverage information for a single line."""

    line_number: int
    count: int
    function_name: str | None = None
    has_unexecuted_block: bool = False
    branches: list[BranchCoverage] = field(default_factory=list)

    @property
    def status(self) -> LineStatus:
        if self.count > 0:
            return LineStatus.COVERED
        return LineStatus.NOT_COVERED

    @property
    def is_covered(self) -> bool:
        return self.count > 0

    @property
    def branch_coverage(self) -> tuple[int, int]:
        """Returns (covered_branches, total_branches)."""
        if not self.branches:
            return (0, 0)
        covered = sum(1 for b in self.branches if b.is_covered)
        return (covered, len(self.branches))


@dataclass
class FunctionCoverage:
    """Coverage information for a function."""

    name: str
    demangled_name: str | None
    start_line: int
    end_line: int
    execution_count: int
    blocks_executed: int = 0
    blocks_total: int = 0

    @property
    def is_covered(self) -> bool:
        return self.execution_count > 0


@dataclass
class FileCoverage:
    """Coverage information for a single file."""

    path: Path
    lines: dict[int, LineCoverage] = field(default_factory=dict)
    functions: list[FunctionCoverage] = field(default_factory=list)

    @property
    def total_lines(self) -> int:
        return len(self.lines)

    @property
    def covered_lines(self) -> int:
        return sum(1 for line in self.lines.values() if line.is_covered)

    @property
    def uncovered_lines(self) -> int:
        return self.total_lines - self.covered_lines

    @property
    def line_coverage_percent(self) -> float:
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    @property
    def total_functions(self) -> int:
        return len(self.functions)

    @property
    def covered_functions(self) -> int:
        return sum(1 for f in self.functions if f.is_covered)

    @property
    def function_coverage_percent(self) -> float:
        if self.total_functions == 0:
            return 100.0
        return (self.covered_functions / self.total_functions) * 100

    @property
    def total_branches(self) -> int:
        return sum(len(line.branches) for line in self.lines.values())

    @property
    def covered_branches(self) -> int:
        return sum(
            sum(1 for b in line.branches if b.is_covered) for line in self.lines.values()
        )

    @property
    def branch_coverage_percent(self) -> float:
        if self.total_branches == 0:
            return 100.0
        return (self.covered_branches / self.total_branches) * 100

    def get_uncovered_line_numbers(self) -> list[int]:
        """Get sorted list of uncovered line numbers."""
        return sorted(ln for ln, line in self.lines.items() if not line.is_covered)

    def get_function_at_line(self, line_number: int) -> FunctionCoverage | None:
        """Find the function containing a given line."""
        for func in self.functions:
            if func.start_line <= line_number <= func.end_line:
                return func
        return None


@dataclass
class CoverageData:
    """Aggregated coverage data for a project."""

    files: dict[Path, FileCoverage] = field(default_factory=dict)

    @property
    def total_lines(self) -> int:
        return sum(f.total_lines for f in self.files.values())

    @property
    def covered_lines(self) -> int:
        return sum(f.covered_lines for f in self.files.values())

    @property
    def uncovered_lines(self) -> int:
        return self.total_lines - self.covered_lines

    @property
    def line_coverage_percent(self) -> float:
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    @property
    def total_functions(self) -> int:
        return sum(f.total_functions for f in self.files.values())

    @property
    def covered_functions(self) -> int:
        return sum(f.covered_functions for f in self.files.values())

    @property
    def function_coverage_percent(self) -> float:
        if self.total_functions == 0:
            return 100.0
        return (self.covered_functions / self.total_functions) * 100

    @property
    def total_branches(self) -> int:
        return sum(f.total_branches for f in self.files.values())

    @property
    def covered_branches(self) -> int:
        return sum(f.covered_branches for f in self.files.values())

    @property
    def branch_coverage_percent(self) -> float:
        if self.total_branches == 0:
            return 100.0
        return (self.covered_branches / self.total_branches) * 100

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def files_with_coverage(self) -> int:
        return sum(1 for f in self.files.values() if f.covered_lines > 0)

    def get_file(self, path: Path | str) -> FileCoverage | None:
        """Get coverage for a specific file."""
        if isinstance(path, str):
            path = Path(path)
        return self.files.get(path)

    def merge(self, other: Self) -> Self:
        """Merge another CoverageData into this one (lcov ``-a`` semantics).

        Execution counts are summed, so a line, branch, or function counts as
        covered when any input covered it. Lines, branches, files, and functions
        unique to ``other`` are added.
        """
        for path, file_cov in other.files.items():
            existing = self.files.get(path)
            if existing is None:
                self.files[path] = file_cov
                continue
            for ln, line in file_cov.lines.items():
                cur = existing.lines.get(ln)
                if cur is None:
                    existing.lines[ln] = line
                    continue
                cur.count += line.count
                if cur.function_name is None:
                    cur.function_name = line.function_name
                # The block is unexecuted only if it stayed unexecuted in both.
                cur.has_unexecuted_block = (
                    cur.has_unexecuted_block and line.has_unexecuted_block
                )
                _merge_branches(cur, line.branches)
            _merge_functions(existing, file_cov.functions)
        return self


def _merge_branches(line: LineCoverage, incoming: list[BranchCoverage]) -> None:
    """Merge branch hit counts into ``line`` by branch id, summing counts."""
    by_id = {b.branch_id: b for b in line.branches}
    for branch in incoming:
        match = by_id.get(branch.branch_id)
        if match is None:
            line.branches.append(branch)
            by_id[branch.branch_id] = branch
        else:
            match.count += branch.count


def _merge_functions(file_cov: FileCoverage, incoming: list[FunctionCoverage]) -> None:
    """Merge function execution counts into ``file_cov`` by name, summing counts."""
    by_name = {f.name: f for f in file_cov.functions}
    for func in incoming:
        match = by_name.get(func.name)
        if match is None:
            file_cov.functions.append(func)
            by_name[func.name] = func
        else:
            match.execution_count += func.execution_count
            match.blocks_executed = max(match.blocks_executed, func.blocks_executed)
            match.blocks_total = max(match.blocks_total, func.blocks_total)
