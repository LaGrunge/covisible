"""Tests for treemap hierarchy building and directory aggregation."""

from __future__ import annotations

from pathlib import Path

from covisible.analysis.treemap import (
    TreemapBuilder,
    TreemapNode,
    build_treemap_data,
    get_directory_coverage,
)
from covisible.core.models import (
    BranchCoverage,
    CoverageData,
    FileCoverage,
    FunctionCoverage,
    LineCoverage,
)


def _f(path: str, total: int, covered: int) -> FileCoverage:
    fc = FileCoverage(path=Path(path))
    for i in range(1, total + 1):
        fc.lines[i] = LineCoverage(line_number=i, count=1 if i <= covered else 0)
    return fc


def _rich_file(
    path: str, *, lines: list[int], funcs: list[int], branches: list[int]
) -> FileCoverage:
    """Build a file with explicit line/function/branch hit counts (branches on line 1)."""
    fc = FileCoverage(path=Path(path))
    for i, cnt in enumerate(lines, start=1):
        fc.lines[i] = LineCoverage(line_number=i, count=cnt)
    for i, exec_count in enumerate(funcs):
        fc.functions.append(
            FunctionCoverage(
                name=f"f{i}", demangled_name=None, start_line=1, end_line=1,
                execution_count=exec_count,
            )
        )
    if branches:
        line = fc.lines.setdefault(1, LineCoverage(line_number=1, count=0))
        for bid, cnt in enumerate(branches):
            line.branches.append(BranchCoverage(line_number=1, branch_id=bid, count=cnt))
    return fc


def _cov(*files: FileCoverage) -> CoverageData:
    cov = CoverageData()
    for fc in files:
        cov.files[fc.path] = fc
    return cov


def _child(node: dict, name: str) -> dict:
    return next(c for c in node["children"] if c["name"] == name)


# --- TreemapNode ------------------------------------------------------------


def test_node_empty_is_fully_covered():
    assert TreemapNode(name="x", path="x").coverage_percent == 100.0


def test_node_uncovered_and_percent():
    node = TreemapNode(name="x", path="x", total_lines=10, covered_lines=4)
    assert node.uncovered_lines == 6
    assert node.coverage_percent == 40.0


def test_node_to_dict_leaf_has_no_children_key():
    d = TreemapNode(name="a.py", path="a.py", total_lines=2, covered_lines=1).to_dict()
    assert "children" not in d
    assert d["coverage_percent"] == 50.0
    assert d["uncovered_lines"] == 1


def test_node_to_dict_with_children():
    parent = TreemapNode(name="dir", path="dir")
    parent.children["a.py"] = TreemapNode(name="a.py", path="dir/a.py", is_file=True)
    d = parent.to_dict()
    assert isinstance(d["children"], list)
    assert d["children"][0]["name"] == "a.py"


# --- build / propagate ------------------------------------------------------


def test_build_hierarchy_and_propagated_totals():
    cov = _cov(
        _f("/proj/src/pkg/a.py", 10, 5),
        _f("/proj/src/pkg/b.py", 10, 10),
        _f("/proj/src/c.py", 4, 0),
    )
    root = build_treemap_data(cov, base_path="/proj")

    src = _child(root, "src")
    assert src["total_lines"] == 24
    assert src["covered_lines"] == 15
    assert src["uncovered_lines"] == 9

    pkg = _child(src, "pkg")
    assert pkg["total_lines"] == 20
    assert pkg["covered_lines"] == 15
    assert {c["name"] for c in pkg["children"]} == {"a.py", "b.py"}


def test_build_empty_coverage_has_no_children():
    root = build_treemap_data(_cov())
    assert "children" not in root
    assert root["total_lines"] == 0


def test_to_dict_includes_function_and_branch_metrics():
    fc = _rich_file("/p/a.c", lines=[1, 0], funcs=[1, 0], branches=[1, 0])
    root = build_treemap_data(_cov(fc), base_path="/p")
    a = _child(root, "a.c")
    assert a["total_functions"] == 2 and a["covered_functions"] == 1
    assert a["function_coverage_percent"] == 50.0
    assert a["total_branches"] == 2 and a["covered_branches"] == 1
    assert a["branch_coverage_percent"] == 50.0


def test_propagates_function_and_branch_totals():
    f1 = _rich_file("/p/pkg/a.c", lines=[1], funcs=[1, 1], branches=[1, 0])
    f2 = _rich_file("/p/pkg/b.c", lines=[0], funcs=[0], branches=[0, 0])
    root = build_treemap_data(_cov(f1, f2), base_path="/p")
    pkg = _child(root, "pkg")
    assert pkg["total_functions"] == 3 and pkg["covered_functions"] == 2
    assert pkg["total_branches"] == 4 and pkg["covered_branches"] == 1
    # Whole-project rollup carries the same metric totals.
    assert root["total_functions"] == 3 and root["total_branches"] == 4


# --- get_directory_coverage -------------------------------------------------


def test_directory_coverage_sorted_by_uncovered_desc():
    cov = _cov(
        _f("/proj/src/pkg/a.py", 10, 5),
        _f("/proj/src/pkg/b.py", 10, 10),
        _f("/proj/src/c.py", 4, 0),
    )
    dirs = get_directory_coverage(cov, base_path="/proj", min_lines=0)
    # Only directories (not files, not root), worst-uncovered first.
    assert [d["name"] for d in dirs] == ["src", "pkg"]
    assert dirs[0]["uncovered_lines"] == 9
    assert dirs[1]["uncovered_lines"] == 5


def test_directory_coverage_min_lines_filter():
    cov = _cov(
        _f("/proj/src/pkg/a.py", 10, 5),
        _f("/proj/src/pkg/b.py", 10, 10),
        _f("/proj/src/c.py", 4, 0),
    )
    dirs = get_directory_coverage(cov, base_path="/proj", min_lines=21)
    assert [d["name"] for d in dirs] == ["src"]


# --- _relativize fallbacks --------------------------------------------------


def test_relativize_prefers_injected_callable():
    builder = TreemapBuilder(
        _cov(_f("/proj/src/a.py", 1, 1)),
        base_path="/proj",
        relativize=lambda p: Path("REL") / p.name,
    )
    assert builder._relativize(Path("/proj/src/a.py")) == Path("REL/a.py")


def test_relativize_uses_base_path():
    builder = TreemapBuilder(_cov(_f("/proj/src/a.py", 1, 1)), base_path="/proj")
    assert builder._relativize(Path("/proj/src/a.py")) == Path("src/a.py")


def test_relativize_falls_back_to_common_prefix_when_base_path_misses():
    cov = _cov(_f("/proj/src/a.py", 1, 1), _f("/proj/src/b.py", 1, 0))
    builder = TreemapBuilder(cov, base_path="/elsewhere")
    # base_path does not contain the file, so it strips the common prefix.
    assert builder._relativize(Path("/proj/src/a.py")) == Path("a.py")


def test_relativize_returns_path_unchanged_without_prefix():
    cov = _cov(_f("a.py", 1, 1), _f("b.py", 1, 0))
    builder = TreemapBuilder(cov)
    assert builder._relativize(Path("a.py")) == Path("a.py")


def test_find_common_prefix_none_for_empty():
    assert TreemapBuilder(_cov())._find_common_prefix() is None


def test_find_common_prefix_stops_where_paths_diverge():
    cov = _cov(_f("/proj/src/a.py", 1, 1), _f("/proj/lib/b.py", 1, 0))
    assert TreemapBuilder(cov)._find_common_prefix() == Path("/proj")


def test_relativize_returns_path_when_outside_common_prefix():
    cov = _cov(_f("/proj/src/a.py", 1, 1), _f("/proj/src/b.py", 1, 0))
    builder = TreemapBuilder(cov, base_path="/elsewhere")
    # Not under base_path nor the files' common prefix -> returned unchanged.
    outside = Path("/totally/different.py")
    assert builder._relativize(outside) == outside
