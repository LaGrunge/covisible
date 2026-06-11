"""Parser for LCOV info format."""

from __future__ import annotations

import re
from pathlib import Path

from covisible.core.models import (
    BranchCoverage,
    CoverageData,
    FileCoverage,
    FunctionCoverage,
    LineCoverage,
)


def parse_lcov(path: Path | str) -> CoverageData:
    """Parse LCOV info format file.

    Args:
        path: Path to lcov.info file

    Returns:
        CoverageData with parsed coverage information
    """
    path = Path(path)
    with open(path) as f:
        return parse_lcov_string(f.read())


def parse_lcov_string(content: str) -> CoverageData:
    """Parse LCOV info format from string.

    LCOV format records:
    - TN: test name
    - SF: source file path
    - FN: function line,name
    - FNDA: execution_count,function_name
    - FNF: functions found
    - FNH: functions hit
    - DA: line_number,execution_count[,checksum]
    - LF: lines found
    - LH: lines hit
    - BRDA: line,block,branch,taken
    - BRF: branches found
    - BRH: branches hit
    - end_of_record

    Args:
        content: LCOV info file content

    Returns:
        CoverageData with parsed coverage information
    """
    coverage = CoverageData()
    current_file: FileCoverage | None = None
    function_lines: dict[str, int] = {}

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("TN:"):
            continue

        elif line.startswith("SF:"):
            file_path = Path(line[3:])
            current_file = FileCoverage(path=file_path)
            coverage.files[file_path] = current_file
            function_lines = {}

        elif line.startswith("FN:"):
            match = re.match(r"FN:(\d+),(.+)", line)
            if match and current_file:
                line_num = int(match.group(1))
                func_name = match.group(2)
                function_lines[func_name] = line_num

        elif line.startswith("FNDA:"):
            match = re.match(r"FNDA:(\d+),(.+)", line)
            if match and current_file:
                exec_count = int(match.group(1))
                func_name = match.group(2)
                start_line = function_lines.get(func_name, 0)
                func = FunctionCoverage(
                    name=func_name,
                    demangled_name=None,
                    start_line=start_line,
                    end_line=0,
                    execution_count=exec_count,
                )
                current_file.functions.append(func)

        elif line.startswith("DA:"):
            match = re.match(r"DA:(\d+),(\d+)", line)
            if match and current_file:
                line_num = int(match.group(1))
                count = int(match.group(2))
                if line_num in current_file.lines:
                    current_file.lines[line_num].count += count
                else:
                    current_file.lines[line_num] = LineCoverage(
                        line_number=line_num,
                        count=count,
                    )

        elif line.startswith("BRDA:"):
            # Block ids may carry an "e" prefix (lcov v2 marks exception
            # branches as e.g. "BRDA:59,e0,1,-"); dropping those records
            # makes branch totals disagree with `lcov --summary`.
            match = re.match(r"BRDA:(\d+),(e?\d+),(\d+),(-|\d+)", line)
            if match and current_file:
                line_num = int(match.group(1))
                block_id = match.group(2)
                branch_id = int(match.group(3))
                taken_str = match.group(4)
                taken = 0 if taken_str == "-" else int(taken_str)

                branch = BranchCoverage(
                    line_number=line_num,
                    branch_id=branch_id,
                    count=taken,
                    is_throw=block_id.startswith("e"),
                )

                if line_num in current_file.lines:
                    current_file.lines[line_num].branches.append(branch)
                else:
                    current_file.lines[line_num] = LineCoverage(
                        line_number=line_num,
                        count=0,
                        branches=[branch],
                    )

        elif line == "end_of_record":
            current_file = None
            function_lines = {}

    return coverage
