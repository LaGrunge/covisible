"""Tests for source-file resolution against --source-root.

Covers the three resolution branches in ReportGenerator._resolve_source_path:
the recorded path as-is, a relative path joined under source_root, and an
absolute build path matched by its longest existing suffix under source_root.
"""

from pathlib import Path

from covisible.report.generator import ReportGenerator


def _gen(tmp_path: Path, source_root: Path | None) -> ReportGenerator:
    return ReportGenerator(output_dir=tmp_path / "out", source_root=source_root)


def test_resolves_existing_path_as_is(tmp_path: Path) -> None:
    """A path that already exists is used directly, no source_root needed."""
    src = tmp_path / "foo.c"
    src.write_text("int main() {}\n")
    gen = _gen(tmp_path, source_root=None)
    assert gen._resolve_source_path(src) == src


def test_resolves_relative_path_under_source_root(tmp_path: Path) -> None:
    """A relative coverage path is joined onto source_root."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "foo.c").write_text("x\n")
    gen = _gen(tmp_path, source_root=root)
    assert gen._resolve_source_path(Path("src/foo.c")) == root / "src" / "foo.c"


def test_resolves_absolute_build_path_by_suffix(tmp_path: Path) -> None:
    """An absolute path with a foreign build prefix matches by suffix."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    target = root / "src" / "foo.c"
    target.write_text("x\n")
    gen = _gen(tmp_path, source_root=root)
    recorded = Path("/home/ci/build/proj/src/foo.c")
    assert gen._resolve_source_path(recorded) == target


def test_prefers_longest_suffix_match(tmp_path: Path) -> None:
    """When multiple suffixes exist, the most specific (longest) one wins."""
    root = tmp_path / "repo"
    (root / "a" / "src").mkdir(parents=True)
    (root / "src").mkdir()
    specific = root / "a" / "src" / "foo.c"
    specific.write_text("specific\n")
    (root / "src" / "foo.c").write_text("shallow\n")
    gen = _gen(tmp_path, source_root=root)
    recorded = Path("/build/x/a/src/foo.c")
    assert gen._resolve_source_path(recorded) == specific


def test_missing_source_returns_none(tmp_path: Path) -> None:
    """No candidate anywhere yields None."""
    gen = _gen(tmp_path, source_root=tmp_path / "repo")
    assert gen._resolve_source_path(Path("/nope/missing.c")) is None


def test_no_source_root_only_matches_existing(tmp_path: Path) -> None:
    """Without source_root, only an existing recorded path resolves."""
    gen = _gen(tmp_path, source_root=None)
    assert gen._resolve_source_path(Path("/home/ci/build/foo.c")) is None


def test_read_source_file_tracks_stats(tmp_path: Path) -> None:
    """_read_source_file populates resolved/missing stats and returns lines."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "foo.c").write_text("line1\nline2\n")
    gen = _gen(tmp_path, source_root=root)

    assert gen._read_source_file(Path("/ci/src/foo.c")) == ["line1", "line2"]
    assert gen._read_source_file(Path("/ci/src/missing.c")) == []

    resolved, missing = gen.source_stats
    assert (resolved, missing) == (1, 1)
