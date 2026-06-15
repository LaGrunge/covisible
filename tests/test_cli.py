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


_LCOV_BRANCHES = """\
SF:/proj/src/a.cpp
DA:10,5
BRDA:10,0,0,3
BRDA:10,0,1,0
end_of_record
"""


def test_report_branches_flag_toggles_columns(tmp_path):
    cov = tmp_path / "coverage.info"
    cov.write_text(_LCOV_BRANCHES)
    out = tmp_path / "report"

    # Default: branch coverage columns are hidden.
    result = CliRunner().invoke(main, ["report", "-c", str(cov), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "Branch Coverage" not in (out / "index.html").read_text()

    # --branches reveals them (the data has BRDA records).
    result = CliRunner().invoke(
        main, ["report", "-c", str(cov), "-o", str(out), "--branches"]
    )
    assert result.exit_code == 0, result.output
    assert "Branch Coverage" in (out / "index.html").read_text()


def test_report_range_flag_sets_thresholds(tmp_path):
    cov = _write_lcov(tmp_path)
    out = tmp_path / "report"

    # Default thresholds are 50,80.
    result = CliRunner().invoke(main, ["report", "-c", str(cov), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "const covHigh = 80" in (out / "index.html").read_text()

    # --range overrides the green cutoff everywhere it is used.
    result = CliRunner().invoke(
        main, ["report", "-c", str(cov), "-o", str(out), "--range", "50,75"]
    )
    assert result.exit_code == 0, result.output
    html = (out / "index.html").read_text()
    assert "const covLow = 50" in html
    assert "const covHigh = 75" in html
    assert "const covHigh = 80" not in html


def test_report_range_rejects_invalid(tmp_path):
    cov = _write_lcov(tmp_path)
    out = tmp_path / "report"
    for bad in ["80,50", "50", "foo,bar", "50,150"]:
        result = CliRunner().invoke(
            main, ["report", "-c", str(cov), "-o", str(out), "--range", bad]
        )
        assert result.exit_code != 0, f"expected failure for --range {bad}"


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


# Baseline vs current where three files each change coverage -> all impacted.
_BASE_DIFF = """\
SF:a.c
DA:1,1
DA:2,1
end_of_record
SF:b.c
DA:1,1
DA:2,1
end_of_record
SF:c.c
DA:1,1
DA:2,1
end_of_record
"""
_CURR_DIFF = """\
SF:a.c
DA:1,1
DA:2,0
end_of_record
SF:b.c
DA:1,0
DA:2,0
end_of_record
SF:c.c
DA:1,1
DA:2,0
end_of_record
"""


def test_diff_limit_caps_output(tmp_path):
    base = tmp_path / "base.lcov"
    curr = tmp_path / "curr.lcov"
    base.write_text(_BASE_DIFF)
    curr.write_text(_CURR_DIFF)
    result = CliRunner().invoke(main, ["diff", str(curr), "-b", str(base), "-n", "1"])
    assert result.exit_code == 0, result.output
    assert "more files with changes" in result.output


def test_diff_limit_zero_shows_all(tmp_path):
    base = tmp_path / "base.lcov"
    curr = tmp_path / "curr.lcov"
    base.write_text(_BASE_DIFF)
    curr.write_text(_CURR_DIFF)
    result = CliRunner().invoke(main, ["diff", str(curr), "-b", str(base), "-n", "0"])
    assert result.exit_code == 0, result.output
    assert "more files with changes" not in result.output
