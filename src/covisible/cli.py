"""Command-line interface for Covisible."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from covisible.analysis.diff import DiffAnalyzer
from covisible.analysis.pr_coverage import PRCoverageAnalyzer, PRCoverageSummary
from covisible.core.models import CoverageData
from covisible.parsers.gcov_json import parse_gcov_json
from covisible.parsers.lcov import parse_lcov
from covisible.report.generator import ReportGenerator

console = Console()


def detect_and_parse(path: Path) -> CoverageData:
    """Auto-detect coverage format and parse."""
    if path.suffix == ".json" or path.name.endswith(".gcov.json"):
        return parse_gcov_json(path)
    else:
        return parse_lcov(path)


@click.group()
@click.version_option()
def main() -> None:
    """Covisible — PR-first code coverage reports.

    Turn an LCOV or gcov-JSON coverage file into a browsable HTML report that
    highlights what your change did to coverage, not just the global percentage.

    \b
    Common commands:
      report    build the HTML/JSON report (start here)
      diff      print a CodeCov-style coverage diff in the terminal
      files     list files by coverage
      summary   show totals for one coverage file

    Run 'covisible COMMAND --help' for details on any command.
    """
    pass


@main.command()
@click.option(
    "--current",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    metavar="FILE",
    help="Coverage to report on. Format auto-detected: *.json / *.gcov.json is "
    "read as gcov JSON, anything else as LCOV .info.",
)
@click.option(
    "--baseline",
    "-b",
    type=click.Path(exists=True, path_type=Path),
    metavar="FILE",
    help="Earlier coverage to compare against (e.g. master before your PR). "
    "Enables coverage deltas in the report and summary.",
)
@click.option(
    "--git-diff",
    "git_diff_range",
    type=str,
    metavar="RANGE",
    help="Turn on PR-first mode: report only on lines changed in this git range. "
    "Runs 'git diff -U0 RANGE' inside --repo. Example: main..HEAD",
)
@click.option(
    "--diff-file",
    type=click.Path(exists=True, path_type=Path),
    metavar="FILE",
    help="PR-first mode from a saved unified diff instead of running git. "
    "Mutually exclusive with --git-diff.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("coverage-report"),
    metavar="DIR",
    show_default=True,
    help="Directory to write the report into (created if missing).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["html", "json", "both"]),
    default="html",
    show_default=True,
    help="What to emit: a browsable HTML site, machine-readable JSON, or both.",
)
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    metavar="DIR",
    help="Git repository root. Where --git-diff runs, the default for "
    "--source-root, and the source of the auto title.",
)
@click.option(
    "--source-root",
    "source_root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    metavar="DIR",
    help="Where the source files actually live on disk, used to render code. "
    "Resolves relative coverage paths and matches absolute build paths "
    "(e.g. /home/ci/build/...) by their longest existing suffix. "
    "Defaults to --repo.",
)
@click.option(
    "--title",
    type=str,
    default=None,
    metavar="TEXT",
    help="Heading shown in the report  [default: 'Covisible: <project>'].",
)
@click.option(
    "--blame/--no-blame",
    default=False,
    show_default=True,
    help="Annotate uncovered lines with git blame (who last touched them).",
)
@click.option(
    "--exclude",
    "exclude_patterns",
    multiple=True,
    metavar="GLOB",
    help="Drop files matching this glob from the report. Repeatable, "
    "e.g. --exclude '*_test.cpp' --exclude 'third_party/*'.",
)
@click.option(
    "--ignore-config",
    type=click.Path(exists=True, path_type=Path),
    metavar="FILE",
    help="YAML/JSON file with exclude/include globs and line_markers to ignore "
    "(an alternative to repeating --exclude).",
)
def report(
    current: Path,
    baseline: Path | None,
    git_diff_range: str | None,
    diff_file: Path | None,
    output: Path,
    output_format: str,
    repo: Path | None,
    source_root: Path | None,
    title: str,
    blame: bool,
    exclude_patterns: tuple[str, ...],
    ignore_config: Path | None,
) -> None:
    """Generate an HTML/JSON coverage report.

    Reads a coverage file (LCOV .info or gcov JSON, auto-detected) and writes a
    browsable report to --output. It runs in one of two modes:

    \b
    - Whole-project (default): coverage for every file in the data.
    - PR-first (with --git-diff or --diff-file): focuses on the lines your
      change touched, e.g. "-1.3% coverage, 3 new uncovered lines".

    Add --baseline to show deltas against an earlier run. Source code is read
    from disk via --source-root (defaulting to --repo); files that cannot be
    found are shown with coverage but no code, and the count is reported.

    \b
    Examples:
      # whole-project HTML report
      covisible report -c coverage.info -o report/

    \b
      # PR-first report vs. main, with deltas and code from this checkout
      covisible report -c new.info -b old.info \\
          --git-diff main..HEAD --source-root . -o report/

    \b
      # from a saved diff, emitting both HTML and JSON
      covisible report -c coverage.json --diff-file pr.diff --format both
    """
    console.print("[bold blue]Covisible[/] — Generating coverage report...\n")

    # Source files default to living under the repo root when not given explicitly.
    effective_source_root = source_root or repo

    # Auto-generate title if not provided
    if title is None:
        if repo:
            project_name = repo.resolve().name
        else:
            # Try to get project name from coverage file path or cwd
            project_name = current.resolve().parent.name
            if project_name in ("coverage", "build", "out", "output", "."):
                project_name = Path.cwd().name
        title = f"Covisible: {project_name}"

    current_cov = detect_and_parse(current)
    console.print(f"✓ Loaded current coverage: [green]{current}[/]")
    console.print(f"  {current_cov.total_files} files, {current_cov.total_lines} lines")

    baseline_cov = None
    if baseline:
        baseline_cov = detect_and_parse(baseline)
        console.print(f"✓ Loaded baseline coverage: [green]{baseline}[/]")

    # Apply ignore/exclude rules (file patterns + line markers) if requested.
    if exclude_patterns or ignore_config:
        from covisible.core.ignore import IgnoreFilter, load_ignore_config

        ignore_filter = IgnoreFilter(
            load_ignore_config(ignore_config, list(exclude_patterns) or None)
        )
        before = current_cov.total_files
        current_cov = ignore_filter.filter_coverage_data(current_cov)
        if baseline_cov:
            baseline_cov = ignore_filter.filter_coverage_data(baseline_cov)
        console.print(
            f"✓ Applied ignore rules: [green]{before} → {current_cov.total_files}[/] files kept"
        )

    diff = None
    if git_diff_range:
        diff = DiffAnalyzer.from_git_diff(git_diff_range, repo)
        console.print(f"✓ Parsed git diff: [green]{git_diff_range}[/]")
        console.print(f"  {len(diff.files)} files changed")
    elif diff_file:
        diff = DiffAnalyzer.from_diff_file(diff_file)
        console.print(f"✓ Parsed diff file: [green]{diff_file}[/]")
        console.print(f"  {len(diff.files)} files changed")

    if diff:
        analyzer = PRCoverageAnalyzer(
            current=current_cov,
            diff=diff,
            baseline=baseline_cov,
        )
        summary = analyzer.analyze()

        console.print("\n[bold]PR Coverage Summary:[/]")
        _print_summary(summary)

        generator = ReportGenerator(
            analyzer=analyzer,
            output_dir=output,
            title=title,
            base_path=repo,
            source_root=effective_source_root,
            enable_blame=blame,
        )
    else:
        generator = ReportGenerator(
            coverage=current_cov,
            baseline=baseline_cov,
            output_dir=output,
            title=title,
            base_path=repo,
            source_root=effective_source_root,
            enable_blame=blame,
        )

        # Print coverage diff summary if baseline provided
        if baseline_cov:
            _print_coverage_diff(current_cov, baseline_cov, limit=10)

    if output_format in ("html", "both"):
        generator.generate_html()
        console.print(f"\n✓ HTML report generated: [green]{output}/index.html[/]")

        resolved, missing = generator.source_stats
        if missing:
            console.print(
                f"[yellow]⚠ {missing} source file(s) not found "
                f"([green]{resolved}[/] resolved); rendered coverage without code.[/]"
            )
            missing_paths = generator.missing_sources
            preview = missing_paths[:10]
            for path in preview:
                console.print(f"    [dim]{path}[/]")
            if len(missing_paths) > len(preview):
                console.print(f"    [dim]... and {len(missing_paths) - len(preview)} more[/]")
            if not effective_source_root:
                console.print(
                    "  [dim]Hint: pass --source-root to point covisible at your sources.[/]"
                )
        elif resolved:
            console.print(f"  Resolved [green]{resolved}[/] source files")

    if output_format in ("json", "both"):
        generator.generate_json()
        console.print(f"✓ JSON report generated: [green]{output}/coverage.json[/]")


def _print_summary(summary: PRCoverageSummary) -> None:
    """Print PR coverage summary to console."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    delta_style = "green" if summary.coverage_delta >= 0 else "red"
    delta_sign = "+" if summary.coverage_delta >= 0 else ""

    table.add_row(
        "New/modified lines",
        f"{summary.total_new_lines}",
    )
    table.add_row(
        "Covered new lines",
        f"[green]{summary.covered_new_lines}[/] ({summary.new_lines_coverage_percent:.1f}%)",
    )
    table.add_row(
        "Uncovered new lines",
        f"[red]{summary.uncovered_new_lines}[/]",
    )
    table.add_row(
        "Coverage delta",
        f"[{delta_style}]{delta_sign}{summary.coverage_delta:.2f}%[/]",
    )
    table.add_row(
        "Files with uncovered code",
        f"{summary.files_with_uncovered_new_lines}",
    )

    console.print(table)


@main.command()
@click.argument("coverage_file", type=click.Path(exists=True, path_type=Path))
def summary(coverage_file: Path) -> None:
    """Print line/function/branch totals for one coverage file.

    Format (LCOV .info or gcov JSON) is auto-detected from the filename.
    """
    cov = detect_and_parse(coverage_file)

    console.print(f"[bold blue]Coverage Summary:[/] {coverage_file}\n")

    table = Table(show_header=True)
    table.add_column("Metric", style="dim")
    table.add_column("Covered", justify="right", style="green")
    table.add_column("Total", justify="right")
    table.add_column("Percent", justify="right", style="bold")

    table.add_row(
        "Lines",
        str(cov.covered_lines),
        str(cov.total_lines),
        f"{cov.line_coverage_percent:.1f}%",
    )
    table.add_row(
        "Functions",
        str(cov.covered_functions),
        str(cov.total_functions),
        f"{cov.function_coverage_percent:.1f}%",
    )
    table.add_row(
        "Branches",
        str(cov.covered_branches),
        str(cov.total_branches),
        f"{cov.branch_coverage_percent:.1f}%",
    )

    console.print(table)
    console.print(f"\n[dim]Files:[/] {cov.total_files}")


@main.command()
@click.argument("coverage_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--limit", "-n", type=int, default=20, show_default=True,
    help="Max files to show; 0 means no limit (show all).",
)
@click.option(
    "--sort",
    type=click.Choice(["coverage", "uncovered", "name"]),
    default="uncovered",
    show_default=True,
    help="Order by: lowest coverage %, most uncovered lines, or path.",
)
def files(coverage_file: Path, limit: int, sort: str) -> None:
    """List files in a coverage file, ranked by the chosen order.

    Format (LCOV .info or gcov JSON) is auto-detected from the filename.
    Use -n 0 to list every file without a limit.
    """
    cov = detect_and_parse(coverage_file)

    file_list = list(cov.files.values())

    if sort == "coverage":
        file_list.sort(key=lambda f: f.line_coverage_percent)
    elif sort == "uncovered":
        file_list.sort(key=lambda f: f.uncovered_lines, reverse=True)
    else:
        file_list.sort(key=lambda f: str(f.path))

    # -n 0 (or negative) disables the cap and shows every file.
    shown = file_list if limit <= 0 else file_list[:limit]

    table = Table(show_header=True)
    table.add_column("File", style="dim", max_width=60)
    table.add_column("Coverage", justify="right")
    table.add_column("Covered", justify="right", style="green")
    table.add_column("Uncovered", justify="right", style="red")

    for file_cov in shown:
        pct = file_cov.line_coverage_percent
        pct_style = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"
        table.add_row(
            str(file_cov.path),
            f"[{pct_style}]{pct:.1f}%[/]",
            str(file_cov.covered_lines),
            str(file_cov.uncovered_lines),
        )

    console.print(table)

    if len(shown) < len(file_list):
        console.print(f"\n[dim]... and {len(file_list) - len(shown)} more files[/]")


@main.command()
@click.argument("current", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--baseline", "-b",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    metavar="FILE",
    help="Coverage to compare CURRENT against (the 'base').",
)
@click.option(
    "--limit", "-n", type=int, default=10, show_default=True,
    help="Max impacted files to list; 0 means no limit (show all).",
)
@click.option(
    "--markdown",
    "markdown_out",
    type=click.Path(path_type=Path),
    metavar="FILE",
    help="Also write a compact markdown brief (for pasting into CI PR comments).",
)
@click.option(
    "--base-label", type=str, default="Master", show_default=True,
    help="Column header for the baseline in the --markdown brief.",
)
@click.option(
    "--current-label", type=str, default="PR", show_default=True,
    help="Column header for CURRENT in the --markdown brief.",
)
def diff(
    current: Path,
    baseline: Path,
    limit: int,
    markdown_out: Path | None,
    base_label: str,
    current_label: str,
) -> None:
    """Show coverage diff between current and baseline (CodeCov style).

    Example: covisible diff coverage_new.lcov -b coverage.lcov

    Use -n 0 to list every impacted file without a limit.
    """
    current_cov = detect_and_parse(current)
    baseline_cov = detect_and_parse(baseline)

    _print_coverage_diff(current_cov, baseline_cov, limit)

    if markdown_out:
        from covisible.report.markdown import render_diff_markdown

        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text(
            render_diff_markdown(
                current_cov,
                baseline_cov,
                base_label=base_label,
                current_label=current_label,
            )
        )
        console.print(f"✓ Markdown brief written: [green]{markdown_out}[/]")


def _print_coverage_diff(
    current: CoverageData, baseline: CoverageData, limit: int = 10
) -> None:
    """Print CodeCov-style coverage diff report."""
    # Calculate deltas
    coverage_delta = current.line_coverage_percent - baseline.line_coverage_percent
    lines_delta = current.total_lines - baseline.total_lines
    hits_delta = current.covered_lines - baseline.covered_lines
    misses_delta = current.uncovered_lines - baseline.uncovered_lines

    # Header
    console.print()
    console.print("[bold]@@            Coverage Diff             @@[/]")
    console.print("[dim]##             base      head    +/-   ##[/]")
    console.print("[dim]" + "=" * 44 + "[/]")

    # Coverage line with color
    delta_style = "green" if coverage_delta >= 0 else "red"
    delta_sign = "+" if coverage_delta >= 0 else ""
    prefix = "+" if coverage_delta >= 0 else "-"
    prefix_style = "green" if coverage_delta >= 0 else "red"

    console.print(
        f"[{prefix_style}]{prefix}[/] [bold]Coverage[/]   "
        f"{baseline.line_coverage_percent:>6.2f}%   {current.line_coverage_percent:>6.2f}%   "
        f"[{delta_style}]{delta_sign}{coverage_delta:>5.2f}%[/]"
    )
    console.print("[dim]" + "=" * 44 + "[/]")

    # Files, Lines
    console.print(
        f"  Files        {baseline.total_files:>6}    {current.total_files:>6}   "
        f"{_format_delta(current.total_files - baseline.total_files)}"
    )
    console.print(
        f"  Lines        {baseline.total_lines:>6}    {current.total_lines:>6}   "
        f"{_format_delta(lines_delta)}"
    )

    # Branches if available
    if baseline.total_branches > 0 or current.total_branches > 0:
        branches_delta = current.total_branches - baseline.total_branches
        console.print(
            f"  Branches     {baseline.total_branches:>6}    {current.total_branches:>6}   "
            f"{_format_delta(branches_delta)}"
        )

    console.print("[dim]" + "=" * 44 + "[/]")

    # Hits, Misses, Partials
    console.print(
        f"  Hits         {baseline.covered_lines:>6}    {current.covered_lines:>6}   "
        f"{_format_delta(hits_delta, positive_good=True)}"
    )

    if misses_delta != 0:
        misses_style = "red" if misses_delta > 0 else "green"
        misses_prefix = "-" if misses_delta > 0 else "+"
        misses_lead = f"[{misses_style}]{misses_prefix}[/]"
    else:
        # No empty-style tag: rich raises MarkupError on "[]...[/]".
        misses_lead = " "
    console.print(
        f"{misses_lead} Misses       "
        f"{baseline.uncovered_lines:>6}    {current.uncovered_lines:>6}   "
        f"{_format_delta(misses_delta, positive_good=False)}"
    )

    # Partials (branches not fully covered) if available
    if baseline.total_branches > 0 or current.total_branches > 0:
        baseline_partials = baseline.total_branches - baseline.covered_branches
        current_partials = current.total_branches - current.covered_branches
        partials_delta = current_partials - baseline_partials
        console.print(
            f"  Partials     {baseline_partials:>6}    {current_partials:>6}   "
            f"{_format_delta(partials_delta, positive_good=False)}"
        )

    console.print()

    # Impacted Modules section
    _print_impacted_modules(current, baseline)

    # Impacted Files section
    _print_impacted_files(current, baseline, limit)


def _print_impacted_modules(current: CoverageData, baseline: CoverageData) -> None:
    """Print impacted modules (directories) with coverage changes."""
    from collections import defaultdict

    def get_module(path: str) -> str:
        """Extract top-level module from path."""
        parts = path.split("/")
        # Find src/ or similar and take next part, or just first directory
        for i, part in enumerate(parts):
            if part in ("src", "lib", "app", "pkg") and i + 1 < len(parts) - 1:
                return "/".join(parts[:i+2])
        # Fallback: first directory
        if len(parts) > 1:
            return parts[0]
        return path

    # Aggregate by module
    current_modules: dict[str, dict[str, int]] = defaultdict(lambda: {"covered": 0, "total": 0})
    baseline_modules: dict[str, dict[str, int]] = defaultdict(lambda: {"covered": 0, "total": 0})

    for path, f in current.files.items():
        module = get_module(str(path))
        current_modules[module]["covered"] += f.covered_lines
        current_modules[module]["total"] += f.total_lines

    for path, f in baseline.files.items():
        module = get_module(str(path))
        baseline_modules[module]["covered"] += f.covered_lines
        baseline_modules[module]["total"] += f.total_lines

    # Calculate deltas
    impacted: list[dict[str, Any]] = []
    all_modules = set(current_modules.keys()) | set(baseline_modules.keys())

    for module in all_modules:
        curr = current_modules.get(module, {"covered": 0, "total": 0})
        base = baseline_modules.get(module, {"covered": 0, "total": 0})

        curr_pct = (curr["covered"] / curr["total"] * 100) if curr["total"] > 0 else 0
        base_pct = (base["covered"] / base["total"] * 100) if base["total"] > 0 else 0

        delta = curr_pct - base_pct

        if abs(delta) > 0.01:  # Only show if changed
            impacted.append({
                "module": module,
                "coverage": curr_pct,
                "baseline": base_pct,
                "delta": delta,
                "is_new": module not in baseline_modules,
            })

    if not impacted:
        return

    # Sort by absolute delta
    impacted.sort(key=lambda x: abs(x["delta"]), reverse=True)

    # Print table
    table = Table(show_header=True, box=None)
    table.add_column("Impacted Modules", style="magenta", max_width=40)
    table.add_column("Coverage Δ", justify="right")

    for item in impacted:
        module = item["module"]
        if len(module) > 40:
            module = "..." + module[-37:]

        if item["is_new"]:
            delta_str = f"{item['coverage']:.2f}% [blue](new)[/]"
        else:
            delta = item["delta"]
            delta_style = "green" if delta >= 0 else "red"
            delta_sign = "+" if delta >= 0 else ""
            delta_str = f"{item['coverage']:.2f}% [{delta_style}]({delta_sign}{delta:.2f}%)[/]"

        table.add_row(module, delta_str)

    console.print(table)
    console.print()


def _format_delta(delta: int, positive_good: bool = True) -> str:
    """Format delta value with color."""
    if delta == 0:
        return "      "

    sign = "+" if delta > 0 else ""

    style = ("green" if delta > 0 else "red") if positive_good else "red" if delta > 0 else "green"

    return f"[{style}]{sign}{delta:>5}[/]"


def _print_impacted_files(current: CoverageData, baseline: CoverageData, limit: int) -> None:
    """Print impacted files table."""
    # Build file comparison
    impacted: list[dict[str, Any]] = []

    # Get all file paths from both
    current_files = {str(p): f for p, f in current.files.items()}
    baseline_files = {str(p): f for p, f in baseline.files.items()}

    all_paths = set(current_files.keys()) | set(baseline_files.keys())

    for path in all_paths:
        curr_file = current_files.get(path)
        base_file = baseline_files.get(path)

        if curr_file and base_file:
            # File exists in both - calculate delta
            delta = curr_file.line_coverage_percent - base_file.line_coverage_percent
            if abs(delta) > 0.001:  # Only show if changed
                impacted.append({
                    "path": path,
                    "coverage": curr_file.line_coverage_percent,
                    "delta": delta,
                    "is_new": False,
                })
        elif curr_file:
            # New file
            impacted.append({
                "path": path,
                "coverage": curr_file.line_coverage_percent,
                "delta": None,
                "is_new": True,
            })
        # Deleted files not shown

    # Sort by absolute delta (biggest changes first)
    impacted.sort(key=lambda x: abs(x["delta"]) if x["delta"] is not None else 999, reverse=True)

    if not impacted:
        console.print("[dim]No impacted files.[/]")
        return

    # Print table
    table = Table(show_header=True, box=None)
    table.add_column("Impacted Files", style="cyan", max_width=50)
    table.add_column("Coverage Δ", justify="right")

    # -n 0 (or negative) disables the cap and shows every impacted file.
    shown = impacted if limit <= 0 else impacted[:limit]

    for item in shown:
        path = item["path"]
        # Shorten path if too long
        if len(path) > 50:
            path = "..." + path[-47:]

        if item["is_new"]:
            delta_str = f"{item['coverage']:.2f}% [blue](new)[/]"
        else:
            delta = item["delta"]
            delta_style = "green" if delta >= 0 else "red"
            delta_sign = "+" if delta >= 0 else ""
            delta_str = f"{item['coverage']:.2f}% [{delta_style}]({delta_sign}{delta:.2f}%)[/]"

        table.add_row(path, delta_str)

    console.print(table)

    if len(shown) < len(impacted):
        console.print(
            f"\n[dim]... and {len(impacted) - len(shown)} more files with changes[/]"
        )


if __name__ == "__main__":
    main()
