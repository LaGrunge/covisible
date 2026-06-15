"""Tests for the Cobertura XML exporter."""

from pathlib import Path

from covisible.core.models import (
    BranchCoverage,
    CoverageData,
    FileCoverage,
    FunctionCoverage,
    LineCoverage,
)
from covisible.report.cobertura import build_cobertura_xml


def _sample() -> CoverageData:
    a = FileCoverage(
        path=Path("/proj/src/a.cpp"),
        lines={
            1: LineCoverage(line_number=1, count=3),
            2: LineCoverage(
                line_number=2,
                count=0,
                branches=[BranchCoverage(2, 0, 1), BranchCoverage(2, 1, 0)],
            ),
        },
        functions=[FunctionCoverage("foo", None, 1, 2, 3)],
    )
    b = FileCoverage(
        path=Path("/proj/src/sub/b.cpp"),
        lines={1: LineCoverage(line_number=1, count=1)},
    )
    return CoverageData(files={a.path: a, b.path: b})


def _xml() -> str:
    return build_cobertura_xml(
        _sample(),
        sources=["/proj"],
        relativize=lambda p: p.relative_to("/proj"),
        timestamp=1234567890,
    )


def test_cobertura_has_prolog_and_doctype():
    xml = _xml()
    assert xml.startswith('<?xml version="1.0" ?>')
    assert "<!DOCTYPE coverage SYSTEM" in xml
    assert "<coverage " in xml


def test_cobertura_top_level_totals():
    xml = _xml()
    # 3 lines total (a:2 + b:1), 2 covered (a line1 + b line1) -> 0.6667.
    assert 'lines-valid="3"' in xml
    assert 'lines-covered="2"' in xml
    assert 'line-rate="0.6667"' in xml
    # One branch covered out of two.
    assert 'branches-valid="2"' in xml
    assert 'branches-covered="1"' in xml
    assert 'timestamp="1234567890"' in xml


def test_cobertura_packages_and_classes_use_relative_paths():
    xml = _xml()
    # Files are grouped into packages by directory.
    assert 'name="src"' in xml
    assert 'name="src/sub"' in xml
    assert xml.count("<package ") == 2
    assert xml.count("<class ") == 2
    # Filenames are relativized like the HTML report.
    assert 'filename="src/a.cpp"' in xml
    assert 'filename="src/sub/b.cpp"' in xml


def test_cobertura_lines_branches_and_methods():
    xml = _xml()
    assert 'hits="3"' in xml  # line 1 of a.cpp
    assert 'branch="true"' in xml
    assert 'condition-coverage="50% (1/2)"' in xml
    assert "<condition " in xml
    assert 'name="foo"' in xml  # the method
