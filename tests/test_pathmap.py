"""Tests for coverage path rewriting (substitute / prefix / strip)."""

from pathlib import Path

import pytest

from covisible.core.models import CoverageData, FileCoverage, LineCoverage
from covisible.core.pathmap import apply_path_transforms, parse_substitution


def _cov(*paths: str) -> CoverageData:
    files = {
        Path(p): FileCoverage(path=Path(p), lines={1: LineCoverage(1, 1)}) for p in paths
    }
    return CoverageData(files=files)


def test_parse_substitution_basic_delimiter_and_flag():
    pat, repl = parse_substitution("s/foo/bar/")
    assert pat.sub(repl, "foo/x") == "bar/x"
    pat, repl = parse_substitution("s#/build/##")  # alternate delimiter
    assert pat.sub(repl, "/build/src/a.c") == "src/a.c"
    pat, repl = parse_substitution("s/ABC/x/i")  # case-insensitive flag
    assert pat.sub(repl, "abc") == "x"


def test_parse_substitution_rejects_garbage():
    for bad in ["nope", "s/onlyone/", "s/a/b", "x/a/b/"]:
        with pytest.raises(ValueError):
            parse_substitution(bad)


def test_substitute_rewrites_paths():
    out = apply_path_transforms(_cov("/build/src/a.cpp"), [parse_substitution("s#/build/##")])
    assert set(out.files) == {Path("src/a.cpp")}


def test_prefix_removes_leading_path():
    out = apply_path_transforms(_cov("/build/src/a.cpp"), prefix="/build")
    assert set(out.files) == {Path("src/a.cpp")}


def test_strip_levels_keeps_filename():
    out = apply_path_transforms(_cov("/a/b/c/d.cpp"), strip=2)
    assert set(out.files) == {Path("c/d.cpp")}
    # Over-stripping still keeps at least the filename.
    out2 = apply_path_transforms(_cov("/a/b/d.cpp"), strip=10)
    assert set(out2.files) == {Path("d.cpp")}


def test_collisions_after_rewrite_are_merged():
    a = FileCoverage(
        path=Path("/x/a.cpp"),
        lines={1: LineCoverage(1, 1), 2: LineCoverage(2, 0)},
    )
    b = FileCoverage(
        path=Path("/y/a.cpp"),
        lines={2: LineCoverage(2, 5), 3: LineCoverage(3, 1)},
    )
    cov = CoverageData(files={a.path: a, b.path: b})
    out = apply_path_transforms(cov, strip=1)  # both collapse to "a.cpp"
    assert set(out.files) == {Path("a.cpp")}
    fc = out.files[Path("a.cpp")]
    assert fc.total_lines == 3
    assert fc.lines[2].count == 5  # 0 + 5 merged
    assert fc.covered_lines == 3


def test_noop_when_no_transforms():
    cov = _cov("/build/src/a.cpp")
    assert apply_path_transforms(cov) is cov
