"""Tests for the SVG coverage badge renderer."""

from covisible.report.badge import render_coverage_badge

_RED = "#ef4444"
_AMBER = "#f59e0b"
_GREEN = "#10b981"


def test_badge_is_standalone_svg_with_percent_and_logo():
    svg = render_coverage_badge(67.0)
    assert svg.lstrip().startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert "67%" in svg
    # Standard badge height, and a positive width.
    assert 'height="20"' in svg
    assert 'width="' in svg
    # The covisible eye logo (its gradient) is embedded.
    assert "cov-eye" in svg
    assert 'r="4" fill="#fff"' in svg  # the white pupil


def test_badge_color_follows_thresholds():
    # Default range 50,80.
    assert _RED in render_coverage_badge(49)
    assert _AMBER in render_coverage_badge(50)
    assert _AMBER in render_coverage_badge(79)
    assert _GREEN in render_coverage_badge(80)
    assert _GREEN in render_coverage_badge(100)


def test_badge_color_respects_custom_range():
    # With --range 50,75 the green cutoff moves down.
    assert _AMBER in render_coverage_badge(74, 50, 75)
    assert _GREEN in render_coverage_badge(76, 50, 75)
    # And the red cutoff moves up with a higher low.
    assert _RED in render_coverage_badge(59, 60, 90)
    assert _AMBER in render_coverage_badge(61, 60, 90)


def test_badge_renders_integer_percent():
    assert "67%" in render_coverage_badge(66.7)
    assert "66%" not in render_coverage_badge(66.7)
    assert "99%" in render_coverage_badge(99.4)
    # Clamped to [0, 100].
    assert "100%" in render_coverage_badge(100.0)
    assert "0%" in render_coverage_badge(0.0)


def test_badge_width_grows_with_longer_value():
    # "100%" is wider than "7%", so the badge must be wider too.
    import re

    def width(svg: str) -> int:
        return int(re.search(r'<svg[^>]*\bwidth="(\d+)"', svg).group(1))

    assert width(render_coverage_badge(100)) > width(render_coverage_badge(7))
