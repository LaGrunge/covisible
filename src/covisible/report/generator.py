"""HTML and JSON report generation."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from covisible.analysis.blame import get_uncovered_blame_summary
from covisible.analysis.grouping import group_coverage_by_directory
from covisible.analysis.history import CoverageHistory
from covisible.analysis.pr_coverage import PRCoverageAnalyzer
from covisible.analysis.treemap import build_treemap_data
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
        base_path: Path | str | None = None,
        enable_blame: bool = False,
        history_file: Path | str | None = None,
        commit: str | None = None,
        branch: str | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.title = title
        self.analyzer = analyzer
        self.coverage = coverage or (analyzer.current if analyzer else CoverageData())
        self.baseline = baseline or (analyzer.baseline if analyzer else None)
        self.base_path = Path(base_path) if base_path else None
        self.enable_blame = enable_blame
        self.history = CoverageHistory(history_file) if history_file else None
        self.commit = commit
        self.branch = branch

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

        # Generate directory tree pages
        self._generate_directory_pages()

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
                    # PR-diff mode has its own delta semantics (new lines, not
                    # whole-file). Templates iterating files still reference
                    # coverage_delta — provide it explicitly so Jinja sees
                    # `is not none` False instead of crashing on abs(Undefined).
                    "coverage_delta": None,
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
            context["files"] = self._build_files_with_delta()
        
        # Build baseline lookup for JS
        if self.baseline:
            context["baseline_tree_data"] = self._build_baseline_tree_for_spa()
            context["impacted_modules"] = self._build_impacted_modules()
            context["impacted_files"] = self._build_impacted_files()

        # Add treemap data
        context["treemap_data"] = build_treemap_data(self.coverage, self.base_path)

        # Add blame data if enabled
        if self.enable_blame:
            uncovered_by_file = {
                path: file_cov.get_uncovered_line_numbers()
                for path, file_cov in self.coverage.files.items()
                if file_cov.uncovered_lines > 0
            }
            context["blame_authors"] = get_uncovered_blame_summary(
                uncovered_by_file, self.base_path, limit=10
            )
        else:
            context["blame_authors"] = []

        # Add full tree data for SPA navigation
        context["full_tree_data"] = self._build_full_tree_for_spa()

        # Add trend data if history is available
        if self.history:
            # Add current entry to history
            self.history.add_entry(
                line_coverage_percent=self.coverage.line_coverage_percent,
                function_coverage_percent=self.coverage.function_coverage_percent,
                total_lines=self.coverage.total_lines,
                covered_lines=self.coverage.covered_lines,
                total_functions=self.coverage.total_functions,
                covered_functions=self.coverage.covered_functions,
                total_files=self.coverage.total_files,
                commit=self.commit,
                branch=self.branch,
            )
            self.history.save()
            context["trend_data"] = self.history.get_trend_data()
            context["coverage_delta"] = self.history.get_delta()
        else:
            context["trend_data"] = []
            context["coverage_delta"] = None

        return context

    def _build_full_tree_for_spa(self) -> dict[str, Any]:
        """Build complete tree structure for SPA navigation."""
        from collections import defaultdict

        # Find common prefix
        paths = list(self.coverage.files.keys())
        if not paths:
            return {}

        first_parts = paths[0].parts
        common_parts: list[str] = []
        for i, part in enumerate(first_parts[:-1]):
            if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                common_parts.append(part)
            else:
                break
        base_path = Path(*common_parts) if common_parts else None

        # Build tree structure
        tree: dict[str, dict[str, Any]] = {}

        for file_path, file_cov in self.coverage.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parts = rel_path.parts

            # Create/update all parent directories
            for i in range(len(parts)):
                if i == len(parts) - 1:
                    # File - add to parent's files list
                    parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
                    if parent_path not in tree:
                        tree[parent_path] = {
                            "name": parts[-2] if len(parts) > 1 else "root",
                            "files": [],
                            "subdirs": [],
                            "stats": {"total_lines": 0, "covered_lines": 0, "total_functions": 0, "covered_functions": 0}
                        }
                    tree[parent_path]["files"].append({
                        "name": parts[-1],
                        "full_path": str(file_path),
                        "total_lines": file_cov.total_lines,
                        "covered_lines": file_cov.covered_lines,
                        "uncovered_lines": file_cov.uncovered_lines,
                        "line_coverage_percent": file_cov.line_coverage_percent,
                        "total_functions": file_cov.total_functions,
                        "covered_functions": file_cov.covered_functions,
                        "function_coverage_percent": file_cov.function_coverage_percent,
                    })
                else:
                    # Directory
                    dir_path = "/".join(parts[:i+1])
                    parent_path = "/".join(parts[:i]) if i > 0 else ""

                    if dir_path not in tree:
                        tree[dir_path] = {
                            "name": parts[i],
                            "files": [],
                            "subdirs": [],
                            "stats": {"total_lines": 0, "covered_lines": 0, "total_functions": 0, "covered_functions": 0}
                        }

                    # Add to parent's subdirs
                    if parent_path not in tree:
                        tree[parent_path] = {
                            "name": parts[i-1] if i > 0 else "root",
                            "files": [],
                            "subdirs": [],
                            "stats": {"total_lines": 0, "covered_lines": 0, "total_functions": 0, "covered_functions": 0}
                        }
                    if parts[i] not in tree[parent_path]["subdirs"]:
                        tree[parent_path]["subdirs"].append(parts[i])

        # Calculate stats for each directory
        for file_path, file_cov in self.coverage.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parts = rel_path.parts
            for i in range(len(parts)):
                dir_path = "/".join(parts[:i]) if i > 0 else ""
                if dir_path in tree:
                    tree[dir_path]["stats"]["total_lines"] += file_cov.total_lines
                    tree[dir_path]["stats"]["covered_lines"] += file_cov.covered_lines
                    tree[dir_path]["stats"]["total_functions"] += file_cov.total_functions
                    tree[dir_path]["stats"]["covered_functions"] += file_cov.covered_functions

        # Calculate percentages
        for path, node in tree.items():
            stats = node["stats"]
            if stats["total_lines"] > 0:
                stats["line_coverage_percent"] = (stats["covered_lines"] / stats["total_lines"]) * 100
                stats["uncovered_lines"] = stats["total_lines"] - stats["covered_lines"]
            else:
                stats["line_coverage_percent"] = 100.0
                stats["uncovered_lines"] = 0
            if stats["total_functions"] > 0:
                stats["function_coverage_percent"] = (stats["covered_functions"] / stats["total_functions"]) * 100
            else:
                stats["function_coverage_percent"] = 100.0
            stats["file_count"] = len(node["files"])

        return tree

    def _build_files_with_delta(self) -> list[dict[str, Any]]:
        """Build files list with baseline delta information."""
        files_list = []
        
        # Build baseline lookup by relative path
        baseline_lookup: dict[str, Any] = {}
        if self.baseline:
            for path, file_cov in self.baseline.files.items():
                rel_path = str(self._get_relative_path(path))
                baseline_lookup[rel_path] = file_cov
        
        for path, file_cov in sorted(
            self.coverage.files.items(),
            key=lambda x: x[1].uncovered_lines,
            reverse=True,
        ):
            rel_path = str(self._get_relative_path(path))
            
            file_data = {
                "path": str(path),
                "rel_path": rel_path,
                "name": path.name,
                "total_lines": file_cov.total_lines,
                "covered_lines": file_cov.covered_lines,
                "uncovered_lines": file_cov.uncovered_lines,
                "coverage_percent": file_cov.line_coverage_percent,
                "total_functions": file_cov.total_functions,
                "covered_functions": file_cov.covered_functions,
                "function_coverage_percent": file_cov.function_coverage_percent,
            }
            
            # Add delta if baseline exists
            if rel_path in baseline_lookup:
                baseline_file = baseline_lookup[rel_path]
                file_data["baseline_coverage_percent"] = baseline_file.line_coverage_percent
                file_data["baseline_covered_lines"] = baseline_file.covered_lines
                file_data["baseline_total_lines"] = baseline_file.total_lines
                file_data["coverage_delta"] = file_cov.line_coverage_percent - baseline_file.line_coverage_percent
                file_data["lines_delta"] = file_cov.covered_lines - baseline_file.covered_lines
                file_data["is_new_file"] = False
            elif self.baseline:
                # File exists in current but not in baseline - it's new
                file_data["is_new_file"] = True
                file_data["coverage_delta"] = None
                file_data["lines_delta"] = file_cov.covered_lines
            else:
                file_data["is_new_file"] = False
                file_data["coverage_delta"] = None
                file_data["lines_delta"] = None
            
            files_list.append(file_data)
        
        return files_list

    def _build_impacted_modules(self) -> list[dict[str, Any]]:
        """Build list of modules with coverage changes for comparison tab."""
        if not self.baseline:
            return []
        
        from collections import defaultdict
        
        def get_module(path: Path) -> tuple[str, str]:
            """Extract module name and path from file path."""
            rel_path = self._get_relative_path(path)
            parts = str(rel_path).split("/")
            
            # Find src/ or similar and take next part
            for i, part in enumerate(parts):
                if part in ("src", "lib", "app", "pkg"):
                    if i + 1 < len(parts) - 1:
                        module_path = "/".join(parts[:i+2])
                        return parts[i+1], module_path
            
            # Fallback: first directory
            if len(parts) > 1:
                return parts[0], parts[0]
            return str(rel_path), str(rel_path)
        
        # Aggregate by module
        current_modules: dict[str, dict] = defaultdict(lambda: {"covered": 0, "total": 0})
        baseline_modules: dict[str, dict] = defaultdict(lambda: {"covered": 0, "total": 0})
        module_paths: dict[str, str] = {}
        
        for path, f in self.coverage.files.items():
            name, mod_path = get_module(path)
            current_modules[name]["covered"] += f.covered_lines
            current_modules[name]["total"] += f.total_lines
            module_paths[name] = mod_path
        
        for path, f in self.baseline.files.items():
            name, mod_path = get_module(path)
            baseline_modules[name]["covered"] += f.covered_lines
            baseline_modules[name]["total"] += f.total_lines
            if name not in module_paths:
                module_paths[name] = mod_path
        
        # Calculate deltas
        impacted = []
        all_modules = set(current_modules.keys()) | set(baseline_modules.keys())
        
        for name in all_modules:
            curr = current_modules.get(name, {"covered": 0, "total": 0})
            base = baseline_modules.get(name, {"covered": 0, "total": 0})
            
            curr_pct = (curr["covered"] / curr["total"] * 100) if curr["total"] > 0 else 0
            base_pct = (base["covered"] / base["total"] * 100) if base["total"] > 0 else 0
            
            delta = curr_pct - base_pct
            
            if abs(delta) > 0.01:  # Only show if changed
                impacted.append({
                    "name": name,
                    "path": module_paths.get(name, name),
                    "coverage": curr_pct,
                    "baseline": base_pct,
                    "delta": delta,
                    "is_new": name not in baseline_modules,
                })
        
        # Sort by absolute delta
        impacted.sort(key=lambda x: abs(x["delta"]), reverse=True)
        return impacted

    def _build_impacted_files(self) -> list[dict[str, Any]]:
        """Build list of files with coverage changes for comparison tab."""
        if not self.baseline:
            return []
        
        # Build baseline lookup by relative path
        baseline_lookup: dict[str, Any] = {}
        for path, file_cov in self.baseline.files.items():
            rel_path = str(self._get_relative_path(path))
            baseline_lookup[rel_path] = file_cov
        
        impacted = []
        
        for path, file_cov in self.coverage.files.items():
            rel_path = str(self._get_relative_path(path))
            
            if rel_path in baseline_lookup:
                baseline_file = baseline_lookup[rel_path]
                delta = file_cov.line_coverage_percent - baseline_file.line_coverage_percent
                
                if abs(delta) > 0.01:  # Only show if changed
                    impacted.append({
                        "path": str(path),
                        "rel_path": rel_path,
                        "coverage": file_cov.line_coverage_percent,
                        "baseline": baseline_file.line_coverage_percent,
                        "delta": delta,
                        "is_new": False,
                    })
            else:
                # New file
                impacted.append({
                    "path": str(path),
                    "rel_path": rel_path,
                    "coverage": file_cov.line_coverage_percent,
                    "baseline": None,
                    "delta": None,
                    "is_new": True,
                })
        
        # Sort by absolute delta (new files last)
        impacted.sort(key=lambda x: abs(x["delta"]) if x["delta"] is not None else -1, reverse=True)
        return impacted[:20]  # Limit to top 20

    def _build_baseline_tree_for_spa(self) -> dict[str, Any]:
        """Build baseline tree structure for comparison in SPA."""
        if not self.baseline:
            return {}
        
        # Find common prefix from baseline
        paths = list(self.baseline.files.keys())
        if not paths:
            return {}

        first_parts = paths[0].parts
        common_parts: list[str] = []
        for i, part in enumerate(first_parts[:-1]):
            if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                common_parts.append(part)
            else:
                break
        base_path = Path(*common_parts) if common_parts else None

        # Build tree structure
        tree: dict[str, dict[str, Any]] = {}

        for file_path, file_cov in self.baseline.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parts = rel_path.parts

            # Create/update all parent directories
            for i in range(len(parts)):
                if i == len(parts) - 1:
                    # File - add to parent's files list
                    parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
                    if parent_path not in tree:
                        tree[parent_path] = {
                            "name": parts[-2] if len(parts) > 1 else "root",
                            "files": {},
                            "stats": {"total_lines": 0, "covered_lines": 0, "total_functions": 0, "covered_functions": 0}
                        }
                    tree[parent_path]["files"][parts[-1]] = {
                        "total_lines": file_cov.total_lines,
                        "covered_lines": file_cov.covered_lines,
                        "line_coverage_percent": file_cov.line_coverage_percent,
                        "total_functions": file_cov.total_functions,
                        "covered_functions": file_cov.covered_functions,
                        "function_coverage_percent": file_cov.function_coverage_percent,
                    }
                else:
                    # Directory
                    dir_path = "/".join(parts[:i+1])
                    parent_path = "/".join(parts[:i]) if i > 0 else ""

                    if dir_path not in tree:
                        tree[dir_path] = {
                            "name": parts[i],
                            "files": {},
                            "stats": {"total_lines": 0, "covered_lines": 0, "total_functions": 0, "covered_functions": 0}
                        }

                    if parent_path not in tree:
                        tree[parent_path] = {
                            "name": parts[i-1] if i > 0 else "root",
                            "files": {},
                            "stats": {"total_lines": 0, "covered_lines": 0, "total_functions": 0, "covered_functions": 0}
                        }

        # Calculate stats for each directory
        for file_path, file_cov in self.baseline.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parts = rel_path.parts
            for i in range(len(parts)):
                dir_path = "/".join(parts[:i]) if i > 0 else ""
                if dir_path in tree:
                    tree[dir_path]["stats"]["total_lines"] += file_cov.total_lines
                    tree[dir_path]["stats"]["covered_lines"] += file_cov.covered_lines
                    tree[dir_path]["stats"]["total_functions"] += file_cov.total_functions
                    tree[dir_path]["stats"]["covered_functions"] += file_cov.covered_functions

        # Calculate percentages
        for path, node in tree.items():
            stats = node["stats"]
            if stats["total_lines"] > 0:
                stats["line_coverage_percent"] = (stats["covered_lines"] / stats["total_lines"]) * 100
            else:
                stats["line_coverage_percent"] = 100.0
            if stats["total_functions"] > 0:
                stats["function_coverage_percent"] = (stats["covered_functions"] / stats["total_functions"]) * 100
            else:
                stats["function_coverage_percent"] = 100.0

        return tree

    def _build_directory_tree_for_template(self) -> list[dict[str, Any]]:
        """Build directory tree data for lcov-style template."""
        from collections import defaultdict

        # Find common prefix
        paths = list(self.coverage.files.keys())
        if not paths:
            return []

        first_parts = paths[0].parts
        common_parts: list[str] = []
        for i, part in enumerate(first_parts[:-1]):
            if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                common_parts.append(part)
            else:
                break
        base_path = Path(*common_parts) if common_parts else None

        # Group files by top-level directory
        dir_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "total_lines": 0,
                "covered_lines": 0,
                "total_functions": 0,
                "covered_functions": 0,
            }
        )

        for file_path, file_cov in self.coverage.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parts = rel_path.parts
            if len(parts) > 1:
                top_dir = parts[0]
            else:
                top_dir = "."

            dir_stats[top_dir]["total_lines"] += file_cov.total_lines
            dir_stats[top_dir]["covered_lines"] += file_cov.covered_lines
            dir_stats[top_dir]["total_functions"] += file_cov.total_functions
            dir_stats[top_dir]["covered_functions"] += file_cov.covered_functions

        # Convert to list
        result = []
        for name, stats in sorted(dir_stats.items()):
            total_lines = stats["total_lines"]
            covered_lines = stats["covered_lines"]
            total_funcs = stats["total_functions"]
            covered_funcs = stats["covered_functions"]

            result.append({
                "name": name,
                "path": name,
                "total_lines": total_lines,
                "covered_lines": covered_lines,
                "uncovered_lines": total_lines - covered_lines,
                "line_coverage_percent": (covered_lines / total_lines * 100) if total_lines > 0 else 100.0,
                "total_functions": total_funcs,
                "covered_functions": covered_funcs,
                "function_coverage_percent": (covered_funcs / total_funcs * 100) if total_funcs > 0 else 100.0,
            })

        # Sort by uncovered lines descending
        result.sort(key=lambda x: x["uncovered_lines"], reverse=True)
        return result

    def _generate_file_page(self, path: Path, pr_cov) -> None:
        """Generate individual file page with PR diff view."""
        template = self.env.get_template("file.html")

        safe_name = str(path).replace("/", "_").replace("\\", "_")
        output_path = self.output_dir / "files" / f"{safe_name}.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        source_lines = self._read_source_file(path)

        # Demangle C++ function names
        coverage_with_demangled = self._demangle_functions(pr_cov.coverage)

        context = {
            "title": f"{path.name} — {self.title}",
            "file_path": str(path),
            "file_name": path.name,
            "pr_coverage": pr_cov,
            "source_lines": source_lines,
            "added_lines": pr_cov.added_lines,
            "coverage": coverage_with_demangled,
            "language": self._detect_language(path),
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

        # Demangle C++ function names
        coverage_with_demangled = self._demangle_functions(file_cov)

        # Compute relative path from project root
        rel_path = self._get_relative_path(path)
        
        # Get baseline coverage for this file if available
        baseline_file_cov = None
        if self.baseline:
            # Try to find matching file in baseline by relative path
            rel_path_str = str(rel_path)
            for baseline_path, baseline_cov in self.baseline.files.items():
                baseline_rel = str(self._get_relative_path(baseline_path))
                if baseline_rel == rel_path_str:
                    baseline_file_cov = baseline_cov
                    break

        context = {
            "title": f"{path.name} — {self.title}",
            "file_path": str(rel_path),
            "file_name": path.name,
            "pr_coverage": None,
            "source_lines": source_lines,
            "added_lines": set(),
            "coverage": coverage_with_demangled,
            "baseline_coverage": baseline_file_cov,
            "language": self._detect_language(path),
        }

        html = template.render(**context)
        output_path.write_text(html)

    def _get_relative_path(self, path: Path) -> Path:
        """Get path relative to project root (base_path or common prefix)."""
        if self.base_path:
            try:
                return path.relative_to(self.base_path)
            except ValueError:
                pass
        
        # Try to find common prefix from all files
        paths = list(self.coverage.files.keys())
        if paths:
            first_parts = paths[0].parts
            common_parts: list[str] = []
            for i, part in enumerate(first_parts[:-1]):
                if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                    common_parts.append(part)
                else:
                    break
            if common_parts:
                base = Path(*common_parts)
                try:
                    return path.relative_to(base)
                except ValueError:
                    pass
        
        return path

    def _read_source_file(self, path: Path) -> list[str]:
        """Read source file lines."""
        try:
            return path.read_text().splitlines()
        except (FileNotFoundError, PermissionError):
            return []

    def _detect_language(self, path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".h": "cpp",
            ".hpp": "cpp",
            ".hxx": "cpp",
            ".go": "go",
            ".rs": "rust",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
        }
        return ext_map.get(path.suffix.lower(), "plaintext")

    def _demangle_functions(self, file_cov):
        """Demangle C++ function names and fix missing start_line."""
        if not file_cov or not file_cov.functions:
            return file_cov

        try:
            from covisible.utils.demangle import demangle_cpp_batch, simplify_cpp_signature

            # Collect all mangled names
            mangled_names = [f.name for f in file_cov.functions]

            # Batch demangle
            demangled = demangle_cpp_batch(mangled_names)

            # Build map of function_name -> first line number from line coverage
            func_to_line: dict[str, int] = {}
            for line_num, line_cov in file_cov.lines.items():
                if line_cov.function_name and line_cov.function_name not in func_to_line:
                    func_to_line[line_cov.function_name] = line_num

            # Update function objects with demangled names and fix start_line
            for func in file_cov.functions:
                if func.name in demangled:
                    raw_demangled = demangled[func.name]
                    func.demangled_name = simplify_cpp_signature(raw_demangled, max_length=100)

                # Fix start_line if it's 0
                if func.start_line == 0 and func.name in func_to_line:
                    func.start_line = func_to_line[func.name]
        except ImportError:
            pass

        return file_cov

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

        # Add module groups for CI
        report["modules"] = group_coverage_by_directory(
            self.coverage, self.base_path, depth=1
        )

        # Add CI-specific fields
        report["ci"] = {
            "passed": self._check_ci_thresholds(),
            "thresholds": {
                "line_coverage_min": 0,
                "new_code_coverage_min": 0,
            },
        }

        return report

    def _check_ci_thresholds(
        self,
        line_coverage_min: float = 0,
        new_code_coverage_min: float = 0,
    ) -> bool:
        """Check if coverage meets CI thresholds."""
        if self.coverage.line_coverage_percent < line_coverage_min:
            return False
        if self.analyzer:
            if self.analyzer.summary.new_lines_coverage_percent < new_code_coverage_min:
                return False
        return True

    def _generate_directory_pages(self) -> None:
        """Generate directory index pages for tree navigation."""
        template = self.env.get_template("directory.html")

        # Build directory tree structure
        tree = self._build_directory_tree()

        # Generate page for each directory
        for dir_path, dir_info in tree.items():
            self._generate_single_directory_page(template, dir_path, dir_info, tree)

    def _build_directory_tree(self) -> dict[str, dict[str, Any]]:
        """Build a tree structure of directories with their stats."""
        tree: dict[str, dict[str, Any]] = {}

        # Find common prefix
        paths = list(self.coverage.files.keys())
        if not paths:
            return tree

        first_parts = paths[0].parts
        common_parts: list[str] = []
        for i, part in enumerate(first_parts[:-1]):
            if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                common_parts.append(part)
            else:
                break
        base_path = Path(*common_parts) if common_parts else None

        # Process each file
        for file_path, file_cov in self.coverage.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            # Add all parent directories
            parts = rel_path.parts
            for i in range(len(parts)):
                if i == len(parts) - 1:
                    # This is the file itself
                    parent_dir = str(Path(*parts[:-1])) if len(parts) > 1 else ""
                    if parent_dir not in tree:
                        tree[parent_dir] = {
                            "name": parts[-2] if len(parts) > 1 else "root",
                            "files": [],
                            "subdirs": set(),
                            "total_lines": 0,
                            "covered_lines": 0,
                        }
                    tree[parent_dir]["files"].append({
                        "name": parts[-1],
                        "path": str(rel_path),
                        "safe_path": str(file_path).replace("/", "_").replace("\\", "_"),
                        "total_lines": file_cov.total_lines,
                        "covered_lines": file_cov.covered_lines,
                        "uncovered_lines": file_cov.uncovered_lines,
                        "coverage_percent": file_cov.line_coverage_percent,
                    })
                else:
                    # This is a directory
                    dir_path_str = str(Path(*parts[:i+1]))
                    parent_dir = str(Path(*parts[:i])) if i > 0 else ""

                    if dir_path_str not in tree:
                        tree[dir_path_str] = {
                            "name": parts[i],
                            "files": [],
                            "subdirs": set(),
                            "total_lines": 0,
                            "covered_lines": 0,
                        }

                    # Add as subdir to parent
                    if parent_dir not in tree:
                        tree[parent_dir] = {
                            "name": parts[i-1] if i > 0 else "root",
                            "files": [],
                            "subdirs": set(),
                            "total_lines": 0,
                            "covered_lines": 0,
                        }
                    tree[parent_dir]["subdirs"].add(parts[i])

        # Calculate stats for each directory (bottom-up)
        for file_path, file_cov in self.coverage.files.items():
            if base_path:
                try:
                    rel_path = file_path.relative_to(base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parts = rel_path.parts
            for i in range(len(parts)):
                dir_path_str = str(Path(*parts[:i])) if i > 0 else ""
                if dir_path_str in tree:
                    tree[dir_path_str]["total_lines"] += file_cov.total_lines
                    tree[dir_path_str]["covered_lines"] += file_cov.covered_lines

        return tree

    def _generate_single_directory_page(
        self,
        template,
        dir_path: str,
        dir_info: dict[str, Any],
        tree: dict[str, dict[str, Any]],
    ) -> None:
        """Generate a single directory index page."""
        # Calculate depth for relative paths
        depth = len(Path(dir_path).parts) if dir_path else 0

        # Build breadcrumbs
        breadcrumbs = []
        if dir_path:
            parts = Path(dir_path).parts
            for i, part in enumerate(parts):
                breadcrumbs.append({
                    "name": part,
                    "path": str(Path(*parts[:i+1])),
                })

        # Get subdirectories with stats
        subdirs = []
        for subdir_name in sorted(dir_info["subdirs"]):
            subdir_path = f"{dir_path}/{subdir_name}" if dir_path else subdir_name
            if subdir_path in tree:
                subdir_info = tree[subdir_path]
                total = subdir_info["total_lines"]
                covered = subdir_info["covered_lines"]
                subdirs.append({
                    "name": subdir_name,
                    "path": subdir_path,
                    "file_count": len(subdir_info["files"]) + sum(
                        len(tree.get(f"{subdir_path}/{s}", {}).get("files", []))
                        for s in subdir_info["subdirs"]
                    ),
                    "total_lines": total,
                    "covered_lines": covered,
                    "uncovered_lines": total - covered,
                    "coverage_percent": (covered / total * 100) if total > 0 else 100.0,
                })

        # Sort files by uncovered lines
        files = sorted(dir_info["files"], key=lambda f: f["uncovered_lines"], reverse=True)

        # Calculate directory stats
        total = dir_info["total_lines"]
        covered = dir_info["covered_lines"]
        stats = {
            "total_lines": total,
            "covered_lines": covered,
            "uncovered_lines": total - covered,
            "coverage_percent": (covered / total * 100) if total > 0 else 100.0,
            "file_count": len(files),
        }

        context = {
            "title": f"{dir_info['name']} — {self.title}",
            "directory_name": dir_info["name"] or "root",
            "directory_path": dir_path,
            "depth": depth,
            "breadcrumbs": breadcrumbs,
            "subdirectories": subdirs,
            "files": files,
            "stats": stats,
        }

        # Create output directory and file
        if dir_path:
            output_dir = self.output_dir / "dirs" / dir_path
        else:
            output_dir = self.output_dir / "dirs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "index.html"

        html = template.render(**context)
        output_path.write_text(html)
