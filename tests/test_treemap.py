"""Tests for treemap hierarchy building and directory aggregation."""

from __future__ import annotations

from pathlib import Path

from covisible.analysis.treemap import (
    TreemapBuilder,
    TreemapNode,
    build_treemap_data,
    get_directory_coverage,
)
from covisible.core.models import CoverageData, FileCoverage, LineCoverage


def _f(path: str, total: int, covered: int) -> FileCoverage:
    fc = FileCoverage(path=Path(path))
    for i in range(1, total + 1):
        fc.lines[i] = LineCoverage(line_number=i, count=1 if i <= covered else 0)
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
