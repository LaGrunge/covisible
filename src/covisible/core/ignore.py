"""Ignore patterns for excluding files and lines from coverage reports."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IgnoreConfig:
    """Configuration for ignoring files and lines."""
    
    # File patterns to exclude (glob patterns)
    exclude_patterns: list[str] = field(default_factory=list)
    
    # File patterns to include (if specified, only these are included)
    include_patterns: list[str] = field(default_factory=list)
    
    # Line markers to ignore (e.g., "# pragma: no cover", "LCOV_EXCL_LINE")
    line_markers: list[str] = field(default_factory=lambda: [
        "# pragma: no cover",
        "// LCOV_EXCL_LINE",
        "/* LCOV_EXCL_LINE */",
        "// NOLINT",
        "// NOLINTNEXTLINE",
    ])
    
    # Block markers (start/end pairs)
    block_markers: list[tuple[str, str]] = field(default_factory=lambda: [
        ("# pragma: no cover start", "# pragma: no cover end"),
        ("// LCOV_EXCL_START", "// LCOV_EXCL_STOP"),
        ("/* LCOV_EXCL_START */", "/* LCOV_EXCL_STOP */"),
    ])
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IgnoreConfig:
        """Create config from dictionary."""
        return cls(
            exclude_patterns=data.get("exclude", []),
            include_patterns=data.get("include", []),
            line_markers=data.get("line_markers", cls.__dataclass_fields__["line_markers"].default_factory()),
            block_markers=[
                tuple(pair) for pair in data.get("block_markers", [])
            ] or cls.__dataclass_fields__["block_markers"].default_factory(),
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
                import yaml
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
        self._compiled_excludes: list[re.Pattern] = []
        self._compiled_includes: list[re.Pattern] = []
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
            for pattern in self._compiled_includes:
                if pattern.match(path_str):
                    return True
            return False
        
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
        except (IOError, UnicodeDecodeError):
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
    
    def filter_coverage_data(self, coverage_data: Any) -> Any:
        """Filter coverage data based on ignore configuration.
        
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
            
            # Filter line coverage
            filtered_line_cov = {
                ln: count for ln, count in file_cov.line_coverage.items()
                if ln not in ignored_lines
            }
            
            # Filter function coverage
            filtered_func_cov = {
                name: count for name, count in file_cov.function_coverage.items()
            }
            
            # Filter branch coverage
            filtered_branch_cov = {
                ln: branches for ln, branches in file_cov.branch_coverage.items()
                if ln not in ignored_lines
            }
            
            # Create new FileCoverage with filtered data
            filtered_file = FileCoverage(
                path=file_cov.path,
                line_coverage=filtered_line_cov,
                function_coverage=filtered_func_cov,
                branch_coverage=filtered_branch_cov,
            )
            
            filtered_files[file_path] = filtered_file
        
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
    if config_path:
        config = IgnoreConfig.from_file(config_path)
    else:
        config = IgnoreConfig()
    
    if exclude_patterns:
        config.exclude_patterns.extend(exclude_patterns)
    
    return config
