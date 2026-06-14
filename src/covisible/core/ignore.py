"""Ignore patterns for excluding files and lines from coverage reports."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from covisible.core.models import CoverageData

_DEFAULT_LINE_MARKERS = [
    "# pragma: no cover",
    "// LCOV_EXCL_LINE",
    "/* LCOV_EXCL_LINE */",
    "// NOLINT",
    "// NOLINTNEXTLINE",
]

_DEFAULT_BLOCK_MARKERS = [
    ("# pragma: no cover start", "# pragma: no cover end"),
    ("// LCOV_EXCL_START", "// LCOV_EXCL_STOP"),
    ("/* LCOV_EXCL_START */", "/* LCOV_EXCL_STOP */"),
]


@dataclass
class IgnoreConfig:
    """Configuration for ignoring files and lines."""

    # File patterns to exclude (glob patterns)
    exclude_patterns: list[str] = field(default_factory=list)

    # File patterns to include (if specified, only these are included)
    include_patterns: list[str] = field(default_factory=list)

    # Line markers to ignore (e.g., "# pragma: no cover", "LCOV_EXCL_LINE")
    line_markers: list[str] = field(default_factory=lambda: list(_DEFAULT_LINE_MARKERS))

    # Block markers (start/end pairs)
    block_markers: list[tuple[str, str]] = field(
        default_factory=lambda: list(_DEFAULT_BLOCK_MARKERS)
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IgnoreConfig:
        """Create config from dictionary."""
        return cls(
            exclude_patterns=data.get("exclude", []),
            include_patterns=data.get("include", []),
            line_markers=data.get("line_markers", list(_DEFAULT_LINE_MARKERS)),
            block_markers=[tuple(pair) for pair in data.get("block_markers", [])]
            or list(_DEFAULT_BLOCK_MARKERS),
        )

    @classmethod
    def from_file(cls, config_path: Path | str) -> IgnoreConfig:
        """Load config from YAML or JSON file."""
        import json

        path = Path(config_path)
        if not path.exists():
            return cls()

        content = path.read_text()

        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore[import-untyped]

                data = yaml.safe_load(content) or {}
            except ImportError:
                return cls()
        else:
            data = json.loads(content)

        ignore_config = data.get("ignore", data)
        return cls.from_dict(ignore_config)


class IgnoreFilter:
    """Filters files and lines based on ignore configuration."""

    def __init__(self, config: IgnoreConfig | None = None):
        self.config = config or IgnoreConfig()
        self._compiled_excludes: list[re.Pattern[str]] = []
        self._compiled_includes: list[re.Pattern[str]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile glob patterns to regex."""
        for pattern in self.config.exclude_patterns:
            regex = fnmatch.translate(pattern)
            self._compiled_excludes.append(re.compile(regex))

        for pattern in self.config.include_patterns:
            regex = fnmatch.translate(pattern)
            self._compiled_includes.append(re.compile(regex))

    def should_include_file(self, file_path: Path | str) -> bool:
        """Check if a file should be included in the report.

        Args:
            file_path: Path to the file

        Returns:
            True if the file should be included
        """
        path_str = str(file_path)

        # Check exclude patterns first
        for pattern in self._compiled_excludes:
            if pattern.match(path_str):
                return False

        # If include patterns are specified, file must match at least one
        if self._compiled_includes:
            return any(pattern.match(path_str) for pattern in self._compiled_includes)

        return True

    def get_ignored_lines(self, file_path: Path | str) -> set[int]:
        """Get line numbers that should be ignored in a file.

        Args:
            file_path: Path to the file

        Returns:
            Set of line numbers to ignore (1-indexed)
        """
        path = Path(file_path)
        if not path.exists():
            return set()

        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError):
            return set()

        lines = content.split("\n")
        ignored: set[int] = set()

        # Track block ignores
        in_block = False
        block_end_marker = ""

        for i, line in enumerate(lines, 1):
            # Check for block start
            if not in_block:
                for start, end in self.config.block_markers:
                    if start in line:
                        in_block = True
                        block_end_marker = end
                        ignored.add(i)
                        break

            # If in block, add line and check for end
            if in_block:
                ignored.add(i)
                if block_end_marker in line:
                    in_block = False
                    block_end_marker = ""
                continue

            # Check for single-line markers
            for marker in self.config.line_markers:
                if marker in line:
                    ignored.add(i)
                    break

        return ignored

    def filter_coverage_data(self, coverage_data: CoverageData) -> CoverageData:
        """Filter coverage data based on ignore configuration.

        Files not matching the include/exclude rules are dropped entirely;
        for the remaining files any line matched by a line/block marker is
        removed (which also drops the branches attached to that line).

        Args:
            coverage_data: CoverageData object

        Returns:
            Filtered CoverageData object
        """
        from covisible.core.models import CoverageData, FileCoverage

        filtered_files: dict[Path, FileCoverage] = {}

        for file_path, file_cov in coverage_data.files.items():
            # Check if file should be included
            if not self.should_include_file(file_path):
                continue

            # Get ignored lines for this file
            ignored_lines = self.get_ignored_lines(file_path)

            if not ignored_lines:
                filtered_files[file_path] = file_cov
                continue

            # Drop ignored lines (their branches go with them) and any
            # function whose declaration line is ignored.
            filtered_lines = {
                ln: line for ln, line in file_cov.lines.items() if ln not in ignored_lines
            }
            filtered_functions = [
                func for func in file_cov.functions if func.start_line not in ignored_lines
            ]

            filtered_files[file_path] = FileCoverage(
                path=file_cov.path,
                lines=filtered_lines,
                functions=filtered_functions,
            )

        return CoverageData(files=filtered_files)


def load_ignore_config(
    config_path: Path | str | None = None,
    exclude_patterns: list[str] | None = None,
) -> IgnoreConfig:
    """Load ignore configuration from file or create from patterns.

    Args:
        config_path: Path to config file (YAML or JSON)
        exclude_patterns: List of glob patterns to exclude

    Returns:
        IgnoreConfig object
    """
    config = IgnoreConfig.from_file(config_path) if config_path else IgnoreConfig()

    if exclude_patterns:
        config.exclude_patterns.extend(exclude_patterns)

    return config
