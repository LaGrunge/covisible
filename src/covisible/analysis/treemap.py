"""Treemap data generation for directory-based coverage visualization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from covisible.core.models import CoverageData, FileCoverage


@dataclass
class TreemapNode:
    """A node in the treemap hierarchy."""

    name: str
    path: str
    full_path: str = ""
    total_lines: int = 0
    covered_lines: int = 0
    total_functions: int = 0
    covered_functions: int = 0
    total_branches: int = 0
    covered_branches: int = 0
    children: dict[str, TreemapNode] = field(default_factory=dict)
    is_file: bool = False

    @property
    def uncovered_lines(self) -> int:
        return self.total_lines - self.covered_lines

    @staticmethod
    def _percent(covered: int, total: int) -> float:
        # Nothing to measure reads as fully covered, matching FileCoverage.
        return (covered / total) * 100 if total > 0 else 100.0

    @property
    def coverage_percent(self) -> float:
        return self._percent(self.covered_lines, self.total_lines)

    @property
    def function_coverage_percent(self) -> float:
        return self._percent(self.covered_functions, self.total_functions)

    @property
    def branch_coverage_percent(self) -> float:
        return self._percent(self.covered_branches, self.total_branches)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Every metric (lines/functions/branches) ships per node so the charts
        can resize and recolor client-side when the user picks a metric.
        """
        result: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "full_path": self.full_path,
            "total_lines": self.total_lines,
            "covered_lines": self.covered_lines,
            "uncovered_lines": self.uncovered_lines,
            "coverage_percent": round(self.coverage_percent, 2),
            "total_functions": self.total_functions,
            "covered_functions": self.covered_functions,
            "function_coverage_percent": round(self.function_coverage_percent, 2),
            "total_branches": self.total_branches,
            "covered_branches": self.covered_branches,
            "branch_coverage_percent": round(self.branch_coverage_percent, 2),
            "is_file": self.is_file,
        }
        if self.children:
            result["children"] = [child.to_dict() for child in self.children.values()]
        return result


class TreemapBuilder:
    """Builds treemap data from coverage information."""

    def __init__(
        self,
        coverage: CoverageData,
        base_path: Path | str | None = None,
        relativize: Callable[[Path], Path] | None = None,
    ):
        self.coverage = coverage
        self.base_path = Path(base_path) if base_path else None
        # Optional canonical relativizer (e.g. ReportGenerator._get_relative_path).
        # When given, it is the single source of truth for path keys so the
        # sunburst hierarchy matches the module table exactly.
        self.relativize = relativize
        self.root = TreemapNode(name="root", path="")

    def _find_common_prefix(self) -> Path | None:
        """Find common path prefix for all files."""
        paths = list(self.coverage.files.keys())
        if not paths:
            return None

        first_parts = paths[0].parts
        common_parts: list[str] = []

        for i, part in enumerate(first_parts[:-1]):
            if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                common_parts.append(part)
            else:
                break

        if common_parts:
            return Path(*common_parts)
        return None

    def build(self) -> TreemapNode:
        """Build the treemap hierarchy."""
        for file_path, file_cov in self.coverage.files.items():
            self._add_file(file_path, file_cov)

        self._propagate_totals(self.root)
        return self.root

    def _relativize(self, file_path: Path) -> Path:
        """Relativize a file path for the tree hierarchy.

        Prefers an injected relativizer so the sunburst shares the report's
        canonical path keys (and stays in sync with the module table). Without
        one, it falls back to base_path, then the common prefix — but unlike a
        bare ``base_path or common_prefix`` it still strips the common prefix
        when base_path is set yet does not actually contain the file.
        """
        if self.relativize is not None:
            return self.relativize(file_path)

        if self.base_path is not None:
            try:
                return file_path.relative_to(self.base_path)
            except ValueError:
                pass

        prefix = self._find_common_prefix()
        if prefix is not None:
            try:
                return file_path.relative_to(prefix)
            except ValueError:
                pass

        return file_path

    def _add_file(self, file_path: Path, file_cov: FileCoverage) -> None:
        """Add a file (with all its metric counts) to the treemap."""
        rel_path = self._relativize(file_path)

        parts = rel_path.parts
        current = self.root

        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            path_so_far = str(Path(*parts[: i + 1]))

            if part not in current.children:
                current.children[part] = TreemapNode(
                    name=part,
                    path=path_so_far,
                    full_path=str(file_path) if is_last else "",
                    is_file=is_last,
                )

            current = current.children[part]

            if is_last:
                current.total_lines = file_cov.total_lines
                current.covered_lines = file_cov.covered_lines
                current.total_functions = file_cov.total_functions
                current.covered_functions = file_cov.covered_functions
                current.total_branches = file_cov.total_branches
                current.covered_branches = file_cov.covered_branches
                current.full_path = str(file_path)

    def _propagate_totals(self, node: TreemapNode) -> tuple[int, int, int, int, int, int]:
        """Propagate line/function/branch totals up the tree."""
        if node.is_file or not node.children:
            return (
                node.total_lines,
                node.covered_lines,
                node.total_functions,
                node.covered_functions,
                node.total_branches,
                node.covered_branches,
            )

        totals = [0, 0, 0, 0, 0, 0]
        for child in node.children.values():
            child_totals = self._propagate_totals(child)
            totals = [a + b for a, b in zip(totals, child_totals, strict=True)]

        (
            node.total_lines,
            node.covered_lines,
            node.total_functions,
            node.covered_functions,
            node.total_branches,
            node.covered_branches,
        ) = totals
        return tuple(totals)  # type: ignore[return-value]

    def get_flat_directories(self, min_lines: int = 0) -> list[dict[str, Any]]:
        """Get flat list of directories with coverage stats."""
        result: list[dict[str, Any]] = []
        self._collect_directories(self.root, result, min_lines)
        return sorted(result, key=lambda x: x["uncovered_lines"], reverse=True)

    def _collect_directories(
        self, node: TreemapNode, result: list[dict[str, Any]], min_lines: int
    ) -> None:
        """Recursively collect directory stats."""
        if (
            not node.is_file
            and node.children
            and node.total_lines >= min_lines
            and node.name != "root"
        ):
            result.append(node.to_dict())

        for child in node.children.values():
            self._collect_directories(child, result, min_lines)


def build_treemap_data(
    coverage: CoverageData,
    base_path: Path | str | None = None,
    relativize: Callable[[Path], Path] | None = None,
) -> dict[str, Any]:
    """Build treemap data from coverage.

    Args:
        coverage: Coverage data
        base_path: Base path to make paths relative to
        relativize: Canonical relativizer shared with the report's module
            table, so the sunburst node paths match the SPA tree keys exactly.

    Returns:
        Dictionary with treemap hierarchy
    """
    builder = TreemapBuilder(coverage, base_path, relativize)
    root = builder.build()
    return root.to_dict()


def get_directory_coverage(
    coverage: CoverageData, base_path: Path | str | None = None, min_lines: int = 10
) -> list[dict[str, Any]]:
    """Get flat list of directories with coverage stats.

    Args:
        coverage: Coverage data
        base_path: Base path to make paths relative to
        min_lines: Minimum lines to include a directory

    Returns:
        List of directory coverage stats, sorted by uncovered lines
    """
    builder = TreemapBuilder(coverage, base_path)
    builder.build()
    return builder.get_flat_directories(min_lines)
