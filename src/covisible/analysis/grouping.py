"""File grouping by module/directory for coverage analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from covisible.core.models import CoverageData, FileCoverage


@dataclass
class ModuleGroup:
    """A group of files representing a module or directory."""

    name: str
    path: str
    files: list[FileCoverage] = field(default_factory=list)

    @property
    def total_lines(self) -> int:
        return sum(f.total_lines for f in self.files)

    @property
    def covered_lines(self) -> int:
        return sum(f.covered_lines for f in self.files)

    @property
    def uncovered_lines(self) -> int:
        return self.total_lines - self.covered_lines

    @property
    def coverage_percent(self) -> float:
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    @property
    def total_functions(self) -> int:
        return sum(f.total_functions for f in self.files)

    @property
    def covered_functions(self) -> int:
        return sum(f.covered_functions for f in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "file_count": self.file_count,
            "total_lines": self.total_lines,
            "covered_lines": self.covered_lines,
            "uncovered_lines": self.uncovered_lines,
            "coverage_percent": round(self.coverage_percent, 2),
            "total_functions": self.total_functions,
            "covered_functions": self.covered_functions,
        }


class ModuleGrouper:
    """Groups files by module/directory."""

    def __init__(
        self,
        coverage: CoverageData,
        base_path: Path | str | None = None,
        depth: int = 1,
    ):
        """Initialize grouper.

        Args:
            coverage: Coverage data
            base_path: Base path to make paths relative to
            depth: Directory depth for grouping (1 = top-level dirs)
        """
        self.coverage = coverage
        self.base_path = Path(base_path) if base_path else None
        self.depth = depth

    def _find_common_prefix(self) -> Path | None:
        """Find common path prefix for all files."""
        paths = [p for p in self.coverage.files.keys()]
        if not paths:
            return None

        # Get all parent directories
        first_parts = paths[0].parts
        common_parts: list[str] = []

        for i, part in enumerate(first_parts[:-1]):  # Exclude filename
            if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                common_parts.append(part)
            else:
                break

        if common_parts:
            return Path(*common_parts)
        return None

    def group_by_directory(self) -> list[ModuleGroup]:
        """Group files by directory at specified depth.

        Returns:
            List of ModuleGroup sorted by uncovered lines descending
        """
        groups: dict[str, ModuleGroup] = {}

        # Auto-detect base path if not provided
        base_path = self.base_path or self._find_common_prefix()

        for file_path, file_cov in self.coverage.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parts = rel_path.parts
            if len(parts) > self.depth:
                group_path = str(Path(*parts[: self.depth]))
                group_name = parts[self.depth - 1]
            else:
                # File is in root or shallow directory
                if len(parts) > 0:
                    group_path = parts[0] if len(parts) > 1 else "."
                    group_name = parts[0] if len(parts) > 1 else rel_path.name
                else:
                    group_path = "."
                    group_name = "root"

            if group_path not in groups:
                groups[group_path] = ModuleGroup(name=group_name, path=group_path)

            groups[group_path].files.append(file_cov)

        return sorted(
            groups.values(),
            key=lambda g: g.uncovered_lines,
            reverse=True,
        )

    def group_by_pattern(self, patterns: dict[str, str]) -> list[ModuleGroup]:
        """Group files by custom patterns.

        Args:
            patterns: Dictionary mapping group names to glob patterns

        Returns:
            List of ModuleGroup
        """
        import fnmatch

        groups: dict[str, ModuleGroup] = {}
        unmatched = ModuleGroup(name="Other", path="other")

        for name, pattern in patterns.items():
            groups[name] = ModuleGroup(name=name, path=pattern)

        for file_path, file_cov in self.coverage.files.items():
            matched = False
            for name, pattern in patterns.items():
                if fnmatch.fnmatch(str(file_path), pattern):
                    groups[name].files.append(file_cov)
                    matched = True
                    break

            if not matched:
                unmatched.files.append(file_cov)

        result = list(groups.values())
        if unmatched.files:
            result.append(unmatched)

        return sorted(result, key=lambda g: g.uncovered_lines, reverse=True)


def group_coverage_by_directory(
    coverage: CoverageData,
    base_path: Path | str | None = None,
    depth: int = 1,
) -> list[dict[str, Any]]:
    """Group coverage data by directory.

    Args:
        coverage: Coverage data
        base_path: Base path to make paths relative to
        depth: Directory depth for grouping

    Returns:
        List of module group dictionaries
    """
    grouper = ModuleGrouper(coverage, base_path, depth)
    groups = grouper.group_by_directory()
    return [g.to_dict() for g in groups]


def group_coverage_by_pattern(
    coverage: CoverageData,
    patterns: dict[str, str],
) -> list[dict[str, Any]]:
    """Group coverage data by custom patterns.

    Args:
        coverage: Coverage data
        patterns: Dictionary mapping group names to glob patterns

    Returns:
        List of module group dictionaries
    """
    grouper = ModuleGrouper(coverage)
    groups = grouper.group_by_pattern(patterns)
    return [g.to_dict() for g in groups]
