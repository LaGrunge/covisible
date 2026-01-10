"""Parser for gcov JSON format output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from covisible.core.models import (
    BranchCoverage,
    CoverageData,
    FileCoverage,
    FunctionCoverage,
    LineCoverage,
)


def parse_gcov_json(path: Path | str) -> CoverageData:
    """Parse gcov JSON format file(s).

    Supports both single JSON file and directory containing multiple .gcov.json files.

    Args:
        path: Path to JSON file or directory containing .gcov.json files

    Returns:
        CoverageData with parsed coverage information
    """
    path = Path(path)
    coverage = CoverageData()

    if path.is_dir():
        for json_file in path.rglob("*.gcov.json"):
            _parse_single_file(json_file, coverage)
    else:
        _parse_single_file(path, coverage)

    return coverage


def _parse_single_file(path: Path, coverage: CoverageData) -> None:
    """Parse a single gcov JSON file into CoverageData."""
    with open(path) as f:
        data = json.load(f)

    if "files" in data:
        for file_data in data["files"]:
            _parse_file_entry(file_data, coverage)
    elif "file" in data:
        _parse_file_entry(data, coverage)


def _parse_file_entry(file_data: dict[str, Any], coverage: CoverageData) -> None:
    """Parse a single file entry from gcov JSON."""
    file_path = Path(file_data["file"])

    if file_path in coverage.files:
        file_cov = coverage.files[file_path]
    else:
        file_cov = FileCoverage(path=file_path)
        coverage.files[file_path] = file_cov

    if "functions" in file_data:
        for func_data in file_data["functions"]:
            func = FunctionCoverage(
                name=func_data["name"],
                demangled_name=func_data.get("demangled_name"),
                start_line=func_data.get("start_line", 0),
                end_line=func_data.get("end_line", 0),
                execution_count=func_data.get("execution_count", 0),
                blocks_executed=func_data.get("blocks_executed", 0),
                blocks_total=func_data.get("blocks", 0),
            )
            file_cov.functions.append(func)

    if "lines" in file_data:
        for line_data in file_data["lines"]:
            line_num = line_data["line_number"]
            branches: list[BranchCoverage] = []

            if "branches" in line_data:
                for i, branch_data in enumerate(line_data["branches"]):
                    branch = BranchCoverage(
                        line_number=line_num,
                        branch_id=i,
                        count=branch_data.get("count", 0),
                        is_throw=branch_data.get("throw", False),
                        is_fallthrough=branch_data.get("fallthrough", False),
                    )
                    branches.append(branch)

            line = LineCoverage(
                line_number=line_num,
                count=line_data.get("count", 0),
                function_name=line_data.get("function_name"),
                has_unexecuted_block=line_data.get("unexecuted_block", False),
                branches=branches,
            )

            if line_num in file_cov.lines:
                file_cov.lines[line_num].count += line.count
            else:
                file_cov.lines[line_num] = line


def parse_gcov_json_string(content: str) -> CoverageData:
    """Parse gcov JSON from string content.

    Args:
        content: JSON string content

    Returns:
        CoverageData with parsed coverage information
    """
    data = json.loads(content)
    coverage = CoverageData()

    if "files" in data:
        for file_data in data["files"]:
            _parse_file_entry(file_data, coverage)
    elif "file" in data:
        _parse_file_entry(data, coverage)

    return coverage
