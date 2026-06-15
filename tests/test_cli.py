"""Tests for the command-line interface."""

import json

from click.testing import CliRunner

from covisible.cli import main

_LCOV = """\
SF:/proj/src/a.cpp
FN:1,2,foo
FNDA:1,foo
DA:1,1
DA:2,0
end_of_record
SF:/proj/src/a_test.cpp
DA:1,1
end_of_record
"""


def _write_lcov(tmp_path):
    p = tmp_path / "coverage.info"
    p.write_text(_LCOV)
    return p


def test_report_generates_json(tmp_path):
    cov = _write_lcov(tmp_path)
    out = tmp_path / "report"
    result = CliRunner().invoke(
        main, ["report", "-c", str(cov), "-o", str(out), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "coverage.json").read_text())
    assert data["summary"]["total_lines"] == 3


def test_report_exclude_drops_files(tmp_path):
    cov = _write_lcov(tmp_path)
    out = tmp_path / "report"
    result = CliRunner().invoke(
        main,
        ["report", "-c", str(cov), "-o", str(out), "--format", "json", "--exclude", "*_test.cpp"],
    )
    assert result.exit_code == 0, result.output
    assert "2 → 1 files kept" in result.output
    data = json.loads((out / "coverage.json").read_text())
    # The test file's single line is gone.
    assert data["summary"]["total_lines"] == 2


def test_report_requires_current():
    result = CliRunner().invoke(main, ["report"])
    assert result.exit_code != 0
    assert "current" in result.output.lower()


_LCOV_THREE = """\
SF:a.c
DA:1,1
end_of_record
SF:b.c
DA:1,1
end_of_record
SF:c.c
DA:1,0
end_of_record
"""


def test_files_limit_caps_output(tmp_path):
    cov = tmp_path / "c.lcov"
    cov.write_text(_LCOV_THREE)
    result = CliRunner().invoke(main, ["files", str(cov), "-n", "1"])
    assert result.exit_code == 0, result.output
    assert "and 2 more files" in result.output


def test_files_limit_zero_shows_all(tmp_path):
    cov = tmp_path / "c.lcov"
    cov.write_text(_LCOV_THREE)
    result = CliRunner().invoke(main, ["files", str(cov), "-n", "0"])
    assert result.exit_code == 0, result.output
    # every file present, no truncation notice
    for name in ("a.c", "b.c", "c.c"):
        assert name in result.output
    assert "more files" not in result.output
