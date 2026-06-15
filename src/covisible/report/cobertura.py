"""Cobertura XML export.

Emits a Cobertura-compatible ``coverage`` document so CI systems that ingest
that format (Jenkins Cobertura plugin, GitLab, Azure DevOps, SonarQube, ...) can
consume covisible's results. Files are grouped into packages by directory; each
file becomes a ``class`` with per-line hits and per-branch conditions.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree as ET

from covisible.core.models import CoverageData, FileCoverage


def _rate(covered: int, total: int) -> float:
    """Coverage rate in [0, 1]; fully covered (1.0) when nothing is measurable."""
    return covered / total if total else 1.0


def build_cobertura_xml(
    coverage: CoverageData,
    sources: list[str] | None = None,
    relativize: Callable[[Path], Path] | None = None,
    timestamp: int | None = None,
) -> str:
    """Build a Cobertura XML report string from coverage data.

    Args:
        coverage: The coverage data to serialize.
        sources: Source roots written into ``<sources>`` (defaults to ``["."]``).
        relativize: Maps an absolute file path to the path recorded in the
            report; keeps Cobertura filenames consistent with the HTML report.
        timestamp: Unix timestamp for the report (defaults to now).
    """
    rel = relativize or (lambda p: p)
    ts = timestamp if timestamp is not None else int(time.time())

    root = ET.Element(
        "coverage",
        {
            "line-rate": f"{_rate(coverage.covered_lines, coverage.total_lines):.4f}",
            "branch-rate": f"{_rate(coverage.covered_branches, coverage.total_branches):.4f}",
            "lines-covered": str(coverage.covered_lines),
            "lines-valid": str(coverage.total_lines),
            "branches-covered": str(coverage.covered_branches),
            "branches-valid": str(coverage.total_branches),
            "complexity": "0",
            "version": "covisible",
            "timestamp": str(ts),
        },
    )

    sources_el = ET.SubElement(root, "sources")
    for src in sources or ["."]:
        ET.SubElement(sources_el, "source").text = src

    packages_el = ET.SubElement(root, "packages")

    # Group files into packages by their relative directory.
    by_pkg: dict[str, list[tuple[str, FileCoverage]]] = {}
    for path, file_cov in coverage.files.items():
        relpath = rel(Path(path)).as_posix()
        parent = Path(relpath).parent.as_posix()
        pkg = "" if parent in (".", "") else parent
        by_pkg.setdefault(pkg, []).append((relpath, file_cov))

    for pkg_name in sorted(by_pkg):
        files = by_pkg[pkg_name]
        pkg_lines = sum(f.total_lines for _, f in files)
        pkg_covered = sum(f.covered_lines for _, f in files)
        pkg_branches = sum(f.total_branches for _, f in files)
        pkg_cov_branches = sum(f.covered_branches for _, f in files)
        package_el = ET.SubElement(
            packages_el,
            "package",
            {
                "name": pkg_name or ".",
                "line-rate": f"{_rate(pkg_covered, pkg_lines):.4f}",
                "branch-rate": f"{_rate(pkg_cov_branches, pkg_branches):.4f}",
                "complexity": "0",
            },
        )
        classes_el = ET.SubElement(package_el, "classes")
        for relpath, file_cov in sorted(files, key=lambda x: x[0]):
            _append_class(classes_el, relpath, file_cov)

    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return (
        '<?xml version="1.0" ?>\n'
        "<!DOCTYPE coverage SYSTEM "
        '"http://cobertura.sourceforge.net/xml/coverage-04.dtd">\n'
        f"{body}\n"
    )


def _append_class(parent: ET.Element, relpath: str, file_cov: FileCoverage) -> None:
    """Append one Cobertura ``<class>`` (a covisible file) under ``parent``."""
    class_el = ET.SubElement(
        parent,
        "class",
        {
            "name": Path(relpath).name,
            "filename": relpath,
            "line-rate": f"{_rate(file_cov.covered_lines, file_cov.total_lines):.4f}",
            "branch-rate": f"{_rate(file_cov.covered_branches, file_cov.total_branches):.4f}",
            "complexity": "0",
        },
    )

    methods_el = ET.SubElement(class_el, "methods")
    for func in file_cov.functions:
        method_el = ET.SubElement(
            methods_el,
            "method",
            {
                "name": func.demangled_name or func.name,
                "signature": "",
                "line-rate": "1.0" if func.is_covered else "0.0",
                "branch-rate": "1.0",
            },
        )
        method_lines = ET.SubElement(method_el, "lines")
        ET.SubElement(
            method_lines,
            "line",
            {"number": str(func.start_line), "hits": str(func.execution_count)},
        )

    lines_el = ET.SubElement(class_el, "lines")
    for ln in sorted(file_cov.lines):
        line = file_cov.lines[ln]
        attrs = {"number": str(ln), "hits": str(line.count)}
        if line.branches:
            covered = sum(1 for b in line.branches if b.is_covered)
            total = len(line.branches)
            pct = round(100 * covered / total) if total else 0
            attrs["branch"] = "true"
            attrs["condition-coverage"] = f"{pct}% ({covered}/{total})"
        else:
            attrs["branch"] = "false"
        line_el = ET.SubElement(lines_el, "line", attrs)
        if line.branches:
            conditions_el = ET.SubElement(line_el, "conditions")
            for branch in line.branches:
                ET.SubElement(
                    conditions_el,
                    "condition",
                    {
                        "number": str(branch.branch_id),
                        "type": "jump",
                        "coverage": "100%" if branch.is_covered else "0%",
                    },
                )
