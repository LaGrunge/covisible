"""Markdown rendering of coverage diffs for CI comments."""

from __future__ import annotations

from covisible.core.models import CoverageData


def _delta_cell(delta: float) -> str:
    """Render a percentage-point delta with a traffic-light marker.

    Mirrors the benchmark PR-comment convention: 🟢 better, 🔴 worse,
    ⚪ unchanged.
    """
    if abs(delta) < 0.005:
        return "⚪ `0.00%`"
    marker = "🟢" if delta > 0 else "🔴"
    return f"{marker} `{delta:+.2f}%`"


def _metric_row(
    name: str,
    base_covered: int,
    base_total: int,
    cur_covered: int,
    cur_total: int,
) -> str:
    base_pct = (base_covered / base_total * 100) if base_total else 0.0
    cur_pct = (cur_covered / cur_total * 100) if cur_total else 0.0
    return (
        f"| {name} "
        f"| {base_pct:.2f}% ({base_covered}/{base_total}) "
        f"| {cur_pct:.2f}% ({cur_covered}/{cur_total}) "
        f"| {_delta_cell(cur_pct - base_pct)} |"
    )


def render_diff_markdown(
    current: CoverageData,
    baseline: CoverageData,
    base_label: str = "Master",
    current_label: str = "PR",
) -> str:
    """Render a compact coverage-vs-baseline brief as a GitHub markdown table."""
    lines = [
        f"| Coverage | {base_label} | {current_label} | Δ |",
        "|:---|---:|---:|:--|",
        _metric_row(
            "Lines",
            baseline.covered_lines,
            baseline.total_lines,
            current.covered_lines,
            current.total_lines,
        ),
        _metric_row(
            "Functions",
            baseline.covered_functions,
            baseline.total_functions,
            current.covered_functions,
            current.total_functions,
        ),
    ]
    if baseline.total_branches or current.total_branches:
        lines.append(
            _metric_row(
                "Branches",
                baseline.covered_branches,
                baseline.total_branches,
                current.covered_branches,
                current.total_branches,
            )
        )
    return "\n".join(lines) + "\n"
