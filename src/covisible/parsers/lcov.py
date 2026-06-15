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
    # func_name -> (start_line, end_line); end_line is 0 when unknown (lcov v1).
    function_lines: dict[str, tuple[int, int]] = {}

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
            # lcov v2/v3 emits "FN:start,end,name"; the older v1 form is
            # "FN:line,name". Mangled symbol names never contain commas, so
            # the leading numeric fields disambiguate the two cleanly.
            match_v2 = re.match(r"FN:(\d+),(\d+),(.+)", line)
            if match_v2 and current_file:
                function_lines[match_v2.group(3)] = (
                    int(match_v2.group(1)),
                    int(match_v2.group(2)),
                )
            else:
                match = re.match(r"FN:(\d+),(.+)", line)
                if match and current_file:
                    function_lines[match.group(2)] = (int(match.group(1)), 0)

        elif line.startswith("FNDA:"):
            match = re.match(r"FNDA:(\d+),(.+)", line)
            if match and current_file:
                exec_count = int(match.group(1))
                func_name = match.group(2)
                start_line, end_line = function_lines.get(func_name, (0, 0))
                func = FunctionCoverage(
                    name=func_name,
                    demangled_name=None,
                    start_line=start_line,
                    end_line=end_line,
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
            # BRDA:<line>,<block>,<branch>,<taken>. Parse positionally so every
            # producer is handled: gcov uses numeric branch ids, lcov v2 marks
            # exception blocks with an "e" prefix (taken may be "-"), and
            # coverage.py emits a *textual* branch descriptor
            # ("jump to line 63") instead of a number. The branch field is
            # everything between the block id and the trailing taken count, and
            # gets a synthetic per-line id when it is not numeric — otherwise
            # those records were silently dropped and branch totals read 0.
            parts = line[5:].split(",")
            taken_str = parts[-1] if parts else ""
            if (
                len(parts) >= 4
                and current_file
                and parts[0].isdigit()
                and (taken_str == "-" or taken_str.isdigit())
            ):
                line_num = int(parts[0])
                block_id = parts[1]
                branch_field = ",".join(parts[2:-1])
                taken = 0 if taken_str == "-" else int(taken_str)

                line_cov = current_file.lines.get(line_num)
                if line_cov is None:
                    line_cov = LineCoverage(line_number=line_num, count=0)
                    current_file.lines[line_num] = line_cov

                try:
                    branch_id = int(branch_field)
                except ValueError:
                    branch_id = len(line_cov.branches)

                line_cov.branches.append(
                    BranchCoverage(
                        line_number=line_num,
                        branch_id=branch_id,
                        count=taken,
                        is_throw=block_id.startswith("e"),
                    )
                )

        elif line == "end_of_record":
            current_file = None
            function_lines = {}

    return coverage
