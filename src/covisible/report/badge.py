"""Generate a shields-style SVG coverage badge.

The badge mirrors the look CI systems use: a dark label segment carrying the
covisible "eye" logo and the word ``coverage``, plus a colored value segment
showing the integer line-coverage percentage. The value color follows the same
LOW/HIGH thresholds as the rest of the report (CLI ``--range``).
"""

from __future__ import annotations

from xml.sax.saxutils import escape

# Theme palette, matching the report colors / favicon gradient stops.
_RED = "#ef4444"
_AMBER = "#f59e0b"
_GREEN = "#10b981"
_LABEL_BG = "#555"

_HEIGHT = 20
_FONT = "Verdana,Geneva,DejaVu Sans,sans-serif"
_FONT_SIZE = 11
_LOGO_SIZE = 14

# Approximate per-character advance widths for Verdana 11px (in px). Good enough
# to size the segments without shipping a full font-metrics table; the badge
# only ever renders the word "coverage", digits, "%" and ".".
_CHAR_W: dict[str, float] = {
    " ": 3.6,
    "%": 10.5,
    ".": 3.6,
    "0": 6.95,
    "1": 6.95,
    "2": 6.95,
    "3": 6.95,
    "4": 6.95,
    "5": 6.95,
    "6": 6.95,
    "7": 6.95,
    "8": 6.95,
    "9": 6.95,
}
_DEFAULT_CHAR_W = 6.6  # average lowercase Verdana letter


def _text_width(text: str) -> float:
    return sum(_CHAR_W.get(c, _DEFAULT_CHAR_W) for c in text)


def _color_for(percent: float, low: float, high: float) -> str:
    """Pick the tier color the same way the report does: below LOW is red,
    LOW..HIGH amber, at or above HIGH green."""
    if percent >= high:
        return _GREEN
    if percent >= low:
        return _AMBER
    return _RED


def _logo(x: float, y: float, size: int) -> str:
    """The covisible eye, scaled into the badge (references #cov-eye gradient)."""
    scale = size / 32
    return (
        f'<g transform="translate({x:g},{y:g}) scale({scale:.5f})">'
        '<circle cx="16" cy="16" r="14" fill="none" '
        'stroke="url(#cov-eye)" stroke-width="3"/>'
        '<circle cx="16" cy="16" r="8" fill="url(#cov-eye)" opacity="0.9"/>'
        '<circle cx="16" cy="16" r="4" fill="#fff"/>'
        "</g>"
    )


def render_coverage_badge(
    percent: float,
    low: float = 50.0,
    high: float = 80.0,
    label: str = "coverage",
) -> str:
    """Render an SVG coverage badge as a string.

    Args:
        percent: Line-coverage percentage (0-100). Rendered as a rounded int.
        low: Lower threshold; below it the value segment is red.
        high: Upper threshold; at or above it the value segment is green.
        label: Left-segment text.

    Returns:
        A complete, standalone ``<svg>`` document.
    """
    pct = max(0, min(100, round(percent)))
    value = f"{pct}%"
    color = _color_for(percent, low, high)

    label_w = _text_width(label)
    value_w = _text_width(value)

    # Geometry: [pad][logo][gap][label][pad] | [pad][value][pad].
    pad = 6
    logo_x = 5
    gap = 4
    label_x0 = logo_x + _LOGO_SIZE + gap
    left_w = round(label_x0 + label_w + pad)
    right_w = round(pad + value_w + pad)
    total_w = left_w + right_w

    label_cx = label_x0 + label_w / 2
    value_cx = left_w + right_w / 2
    text_y = 14
    shadow_y = text_y + 1
    logo_y = (_HEIGHT - _LOGO_SIZE) / 2

    label_e = escape(label)
    aria = f"{label_e}: {value}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" \
height="{_HEIGHT}" role="img" aria-label="{aria}">
  <title>{aria}</title>
  <defs>
    <linearGradient id="cov-eye" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{_RED}"/>
      <stop offset="50%" stop-color="{_AMBER}"/>
      <stop offset="100%" stop-color="{_GREEN}"/>
    </linearGradient>
    <linearGradient id="cov-gloss" x2="0" y2="100%">
      <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
      <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <clipPath id="cov-round">
      <rect width="{total_w}" height="{_HEIGHT}" rx="3" fill="#fff"/>
    </clipPath>
  </defs>
  <g clip-path="url(#cov-round)">
    <rect width="{left_w}" height="{_HEIGHT}" fill="{_LABEL_BG}"/>
    <rect x="{left_w}" width="{right_w}" height="{_HEIGHT}" fill="{color}"/>
    <rect width="{total_w}" height="{_HEIGHT}" fill="url(#cov-gloss)"/>
  </g>
  {_logo(logo_x, logo_y, _LOGO_SIZE)}
  <g fill="#fff" text-anchor="middle" font-family="{_FONT}" font-size="{_FONT_SIZE}">
    <text x="{label_cx:.1f}" y="{shadow_y}" fill="#010101" fill-opacity=".3">{label_e}</text>
    <text x="{label_cx:.1f}" y="{text_y}">{label_e}</text>
    <text x="{value_cx:.1f}" y="{shadow_y}" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{value_cx:.1f}" y="{text_y}">{value}</text>
  </g>
</svg>
"""
