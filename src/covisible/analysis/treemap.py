"""Treemap data generation for directory-based coverage visualization."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from covisible.core.models import CoverageData


@dataclass
class TreemapNode:
    """A node in the treemap hierarchy."""

    name: str
    path: str
    full_path: str = ""
    total_lines: int = 0
    covered_lines: int = 0
    children: dict[str, TreemapNode] = field(default_factory=dict)
    is_file: bool = False

    @property
    def uncovered_lines(self) -> int:
        return self.total_lines - self.covered_lines

    @property
    def coverage_percent(self) -> float:
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "full_path": self.full_path,
            "total_lines": self.total_lines,
            "covered_lines": self.covered_lines,
            "uncovered_lines": self.uncovered_lines,
            "coverage_percent": round(self.coverage_percent, 2),
            "is_file": self.is_file,
        }
        if self.children:
            result["children"] = [child.to_dict() for child in self.children.values()]
        return result


class TreemapBuilder:
    """Builds treemap data from coverage information."""

    def __init__(self, coverage: CoverageData, base_path: Path | str | None = None):
        self.coverage = coverage
        self.base_path = Path(base_path) if base_path else None
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
            self._add_file(file_path, file_cov.total_lines, file_cov.covered_lines)

        self._propagate_totals(self.root)
        return self.root

    def _add_file(self, file_path: Path, total_lines: int, covered_lines: int) -> None:
        """Add a file to the treemap."""
        base_path = self.base_path or self._find_common_prefix()

        if base_path:
            try:
                rel_path = file_path.relative_to(base_path)
            except ValueError:
                rel_path = file_path
        else:
            rel_path = file_path

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
                current.total_lines = total_lines
                current.covered_lines = covered_lines
                current.full_path = str(file_path)

    def _propagate_totals(self, node: TreemapNode) -> tuple[int, int]:
        """Propagate totals up the tree."""
        if node.is_file or not node.children:
            return node.total_lines, node.covered_lines

        total = 0
        covered = 0
        for child in node.children.values():
            child_total, child_covered = self._propagate_totals(child)
            total += child_total
            covered += child_covered

        node.total_lines = total
        node.covered_lines = covered
        return total, covered

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
    coverage: CoverageData, base_path: Path | str | None = None
) -> dict[str, Any]:
    """Build treemap data from coverage.

    Args:
        coverage: Coverage data
        base_path: Base path to make paths relative to

    Returns:
        Dictionary with treemap hierarchy
    """
    builder = TreemapBuilder(coverage, base_path)
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
