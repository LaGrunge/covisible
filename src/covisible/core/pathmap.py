"""Rewrite coverage file paths so they match source on disk.

Coverage tools often record paths that differ from the checkout (absolute build
paths, an extra leading directory, a different root). These helpers rewrite the
paths recorded in :class:`CoverageData` via regex substitution, prefix removal,
and stripping leading directory levels — mirroring ``lcov``/``genhtml``'s
``--substitute`` / ``--prefix`` / ``--strip``.
"""

from __future__ import annotations

import re
from pathlib import Path

from covisible.core.models import CoverageData


def parse_substitution(expr: str) -> tuple[re.Pattern[str], str]:
    """Parse an ``s/PATTERN/REPLACEMENT/[i]`` substitution expression.

    The delimiter is the character right after the leading ``s`` (commonly ``/``
    or ``#``), so a pattern containing ``/`` can pick a different delimiter. A
    trailing ``i`` flag makes the match case-insensitive. PATTERN and
    REPLACEMENT must not contain the delimiter.
    """
    expr = expr.strip()
    if len(expr) < 4 or expr[0] != "s":
        raise ValueError(f"expected s/PATTERN/REPLACEMENT/, got {expr!r}")
    delim = expr[1]
    parts = expr[2:].split(delim)
    if len(parts) < 3:
        raise ValueError(
            f"expected s{delim}PATTERN{delim}REPLACEMENT{delim}[flags], got {expr!r}"
        )
    pattern, replacement, flags_str = parts[0], parts[1], parts[2]
    flags = re.IGNORECASE if "i" in flags_str else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"invalid regex in {expr!r}: {exc}") from None
    return compiled, replacement


def _rewrite(
    path_str: str,
    substitutions: list[tuple[re.Pattern[str], str]],
    prefix: str | None,
    strip: int,
) -> str:
    for pattern, replacement in substitutions:
        path_str = pattern.sub(replacement, path_str)
    if prefix:
        pfx = prefix.rstrip("/")
        if path_str.startswith(pfx + "/"):
            path_str = path_str[len(pfx) + 1 :]
        elif path_str == pfx:
            path_str = ""
    if strip > 0:
        parts = [seg for seg in path_str.split("/") if seg]
        kept = parts[strip:] or parts[-1:]
        path_str = "/".join(kept)
    return path_str


def apply_path_transforms(
    coverage: CoverageData,
    substitutions: list[tuple[re.Pattern[str], str]] | None = None,
    prefix: str | None = None,
    strip: int = 0,
) -> CoverageData:
    """Return coverage with file paths rewritten for source matching.

    Transforms are applied in order: regex substitutions, then prefix removal,
    then stripping ``strip`` leading directory levels. Files that collide after
    rewriting are merged (summing hit counts).
    """
    substitutions = substitutions or []
    if not substitutions and not prefix and not strip:
        return coverage

    result = CoverageData()
    for path, file_cov in coverage.files.items():
        new = _rewrite(Path(path).as_posix(), substitutions, prefix, strip)
        new_path = Path(new)
        file_cov.path = new_path
        result.merge(CoverageData(files={new_path: file_cov}))
    return result
