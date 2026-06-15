"""Tests for CoverageData.merge (lcov ``-a`` semantics)."""

from pathlib import Path

from covisible.core.models import (
    BranchCoverage,
    CoverageData,
    FileCoverage,
    FunctionCoverage,
    LineCoverage,
)


def _file(path: str, lines: dict[int, int]) -> FileCoverage:
    fc = FileCoverage(path=Path(path))
    for ln, count in lines.items():
        fc.lines[ln] = LineCoverage(line_number=ln, count=count)
    return fc


def test_merge_sums_line_counts_and_unions_lines():
    a = CoverageData(files={Path("x"): _file("x", {1: 1, 2: 0})})
    b = CoverageData(files={Path("x"): _file("x", {2: 3, 3: 1})})
    a.merge(b)
    fc = a.files[Path("x")]
    assert fc.lines[1].count == 1
    assert fc.lines[2].count == 3  # 0 + 3 -> now covered
    assert fc.lines[3].count == 1  # line unique to b is added
    assert fc.total_lines == 3
    assert fc.covered_lines == 3


def test_merge_adds_files_unique_to_other():
    a = CoverageData(files={Path("x"): _file("x", {1: 1})})
    b = CoverageData(files={Path("y"): _file("y", {1: 0})})
    a.merge(b)
    assert set(a.files) == {Path("x"), Path("y")}


def test_merge_sums_branch_counts_by_id():
    la = LineCoverage(
        line_number=10,
        count=1,
        branches=[BranchCoverage(10, 0, 1), BranchCoverage(10, 1, 0)],
    )
    lb = LineCoverage(
        line_number=10,
        count=1,
        branches=[
            BranchCoverage(10, 0, 0),
            BranchCoverage(10, 1, 2),
            BranchCoverage(10, 2, 1),
        ],
    )
    a = CoverageData(files={Path("x"): FileCoverage(path=Path("x"), lines={10: la})})
    b = CoverageData(files={Path("x"): FileCoverage(path=Path("x"), lines={10: lb})})
    a.merge(b)
    branches = {br.branch_id: br.count for br in a.files[Path("x")].lines[10].branches}
    assert branches == {0: 1, 1: 2, 2: 1}  # 1+0, 0+2, and the new branch id 2
    fc = a.files[Path("x")]
    assert fc.total_branches == 3
    assert fc.covered_branches == 3


def test_merge_sums_function_counts_by_name():
    fa = FileCoverage(path=Path("x"), functions=[FunctionCoverage("foo", None, 1, 5, 0)])
    fb = FileCoverage(
        path=Path("x"),
        functions=[
            FunctionCoverage("foo", None, 1, 5, 2),
            FunctionCoverage("bar", None, 6, 9, 1),
        ],
    )
    a = CoverageData(files={Path("x"): fa})
    b = CoverageData(files={Path("x"): fb})
    a.merge(b)
    funcs = {f.name: f.execution_count for f in a.files[Path("x")].functions}
    assert funcs == {"foo": 2, "bar": 1}  # foo 0+2 -> covered, bar added
    assert a.files[Path("x")].covered_functions == 2
