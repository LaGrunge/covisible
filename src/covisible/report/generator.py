"""HTML and JSON report generation."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from covisible.analysis.pr_coverage import PRCoverageAnalyzer
from covisible.core.models import CoverageData


class ReportGenerator:
    """Generates HTML and JSON coverage reports."""

    def __init__(
        self,
        output_dir: Path,
        title: str = "Coverage Report",
        analyzer: PRCoverageAnalyzer | None = None,
        coverage: CoverageData | None = None,
        baseline: CoverageData | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.title = title
        self.analyzer = analyzer
        self.coverage = coverage or (analyzer.current if analyzer else CoverageData())
        self.baseline = baseline or (analyzer.baseline if analyzer else None)

        self.env = Environment(
            loader=PackageLoader("covisible", "report/templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._register_filters()

    def _register_filters(self) -> None:
        """Register custom Jinja2 filters."""
        self.env.filters["coverage_class"] = self._coverage_class
        self.env.filters["format_percent"] = lambda x: f"{x:.1f}%"
        self.env.filters["format_delta"] = self._format_delta

    @staticmethod
    def _coverage_class(percent: float) -> str:
        """Return CSS class based on coverage percentage."""
        if percent >= 80:
            return "coverage-high"
        elif percent >= 50:
            return "coverage-medium"
        return "coverage-low"

    @staticmethod
    def _format_delta(delta: float) -> str:
        """Format coverage delta with sign."""
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.2f}%"

    def generate_html(self) -> None:
        """Generate HTML report."""
        # Resolve to absolute path to handle cases where cwd was deleted
        self.output_dir = self.output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._copy_assets()

        self._generate_index()

        if self.analyzer:
            for path, pr_cov in self.analyzer.files.items():
                self._generate_file_page(path, pr_cov)
        else:
            for path, file_cov in self.coverage.files.items():
                self._generate_file_page_simple(path, file_cov)

    def _copy_assets(self) -> None:
        """Copy CSS and JS assets to output directory."""
        assets_dir = self.output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        src_assets = Path(__file__).parent.parent / "assets"
        if src_assets.exists():
            for asset_file in src_assets.rglob("*"):
                if asset_file.is_file():
                    rel_path = asset_file.relative_to(src_assets)
                    dest = assets_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(asset_file, dest)

    def _generate_index(self) -> None:
        """Generate main index.html page."""
        template = self.env.get_template("index.html")

        context = self._build_context()
        html = template.render(**context)

        (self.output_dir / "index.html").write_text(html)

    def _build_context(self) -> dict[str, Any]:
        """Build template context."""
        context: dict[str, Any] = {
            "title": self.title,
            "coverage": self.coverage,
            "baseline": self.baseline,
            "has_pr_analysis": self.analyzer is not None,
        }

        if self.analyzer:
            context["summary"] = self.analyzer.summary
            context["files"] = [
                {
                    "path": str(path),
                    "name": path.name,
                    "is_new": pr_cov.is_new_file,
                    "total_new_lines": pr_cov.total_new_lines,
                    "covered_new_lines": pr_cov.covered_new_lines,
                    "uncovered_new_lines": pr_cov.uncovered_new_lines,
                    "new_coverage_percent": pr_cov.new_lines_coverage_percent,
                    "total_lines": pr_cov.coverage.total_lines if pr_cov.coverage else 0,
                    "covered_lines": pr_cov.coverage.covered_lines if pr_cov.coverage else 0,
                    "coverage_percent": (
                        pr_cov.coverage.line_coverage_percent if pr_cov.coverage else 0
                    ),
                }
                for path, pr_cov in sorted(
                    self.analyzer.files.items(),
                    key=lambda x: x[1].uncovered_new_lines,
                    reverse=True,
                )
            ]
            context["uncovered_critical"] = [
                {"file": str(path), "line": line, "function": func}
                for path, line, func in self.analyzer.get_critical_uncovered()[:20]
            ]
        else:
            context["files"] = [
                {
                    "path": str(path),
                    "name": path.name,
                    "total_lines": file_cov.total_lines,
                    "covered_lines": file_cov.covered_lines,
                    "uncovered_lines": file_cov.uncovered_lines,
                    "coverage_percent": file_cov.line_coverage_percent,
                }
                for path, file_cov in sorted(
                    self.coverage.files.items(),
                    key=lambda x: x[1].uncovered_lines,
                    reverse=True,
                )
            ]

        return context

    def _generate_file_page(self, path: Path, pr_cov) -> None:
        """Generate individual file page with PR diff view."""
        template = self.env.get_template("file.html")

        safe_name = str(path).replace("/", "_").replace("\\", "_")
        output_path = self.output_dir / "files" / f"{safe_name}.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        source_lines = self._read_source_file(path)

        context = {
            "title": f"{path.name} — {self.title}",
            "file_path": str(path),
            "file_name": path.name,
            "pr_coverage": pr_cov,
            "source_lines": source_lines,
            "added_lines": pr_cov.added_lines,
            "coverage": pr_cov.coverage,
        }

        html = template.render(**context)
        output_path.write_text(html)

    def _generate_file_page_simple(self, path: Path, file_cov) -> None:
        """Generate individual file page without PR context."""
        template = self.env.get_template("file.html")

        safe_name = str(path).replace("/", "_").replace("\\", "_")
        output_path = self.output_dir / "files" / f"{safe_name}.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        source_lines = self._read_source_file(path)

        context = {
            "title": f"{path.name} — {self.title}",
            "file_path": str(path),
            "file_name": path.name,
            "pr_coverage": None,
            "source_lines": source_lines,
            "added_lines": set(),
            "coverage": file_cov,
        }

        html = template.render(**context)
        output_path.write_text(html)

    def _read_source_file(self, path: Path) -> list[str]:
        """Read source file lines."""
        try:
            return path.read_text().splitlines()
        except (FileNotFoundError, PermissionError):
            return []

    def generate_json(self) -> None:
        """Generate JSON report."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        report_data = self._build_json_report()

        output_path = self.output_dir / "coverage.json"
        with open(output_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)

    def _build_json_report(self) -> dict[str, Any]:
        """Build JSON report data."""
        report: dict[str, Any] = {
            "title": self.title,
            "summary": {
                "total_lines": self.coverage.total_lines,
                "covered_lines": self.coverage.covered_lines,
                "uncovered_lines": self.coverage.uncovered_lines,
                "line_coverage_percent": self.coverage.line_coverage_percent,
                "total_functions": self.coverage.total_functions,
                "covered_functions": self.coverage.covered_functions,
                "function_coverage_percent": self.coverage.function_coverage_percent,
                "total_branches": self.coverage.total_branches,
                "covered_branches": self.coverage.covered_branches,
                "branch_coverage_percent": self.coverage.branch_coverage_percent,
                "total_files": self.coverage.total_files,
            },
            "files": {},
        }

        if self.analyzer:
            report["pr_summary"] = {
                "total_new_lines": self.analyzer.summary.total_new_lines,
                "covered_new_lines": self.analyzer.summary.covered_new_lines,
                "uncovered_new_lines": self.analyzer.summary.uncovered_new_lines,
                "new_lines_coverage_percent": self.analyzer.summary.new_lines_coverage_percent,
                "coverage_delta": self.analyzer.summary.coverage_delta,
                "files_changed": self.analyzer.summary.files_changed,
            }

            for path, pr_cov in self.analyzer.files.items():
                report["files"][str(path)] = {
                    "is_new": pr_cov.is_new_file,
                    "total_new_lines": pr_cov.total_new_lines,
                    "covered_new_lines": pr_cov.covered_new_lines,
                    "uncovered_new_lines": pr_cov.uncovered_new_lines,
                    "uncovered_line_numbers": pr_cov.get_uncovered_new_line_numbers(),
                }
        else:
            for path, file_cov in self.coverage.files.items():
                report["files"][str(path)] = {
                    "total_lines": file_cov.total_lines,
                    "covered_lines": file_cov.covered_lines,
                    "uncovered_lines": file_cov.uncovered_lines,
                    "coverage_percent": file_cov.line_coverage_percent,
                    "uncovered_line_numbers": file_cov.get_uncovered_line_numbers(),
                }

        if self.baseline:
            report["baseline"] = {
                "total_lines": self.baseline.total_lines,
                "covered_lines": self.baseline.covered_lines,
                "line_coverage_percent": self.baseline.line_coverage_percent,
            }

        return report
