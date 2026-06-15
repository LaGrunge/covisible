"""Tests for the gcov JSON parser (file/dir dispatch, entries, branches)."""

from __future__ import annotations

import json
from pathlib import Path

from covisible.parsers.gcov_json import parse_gcov_json, parse_gcov_json_string

SIMPLE = {
    "files": [
        {
            "file": "/path/to/test.cpp",
            "functions": [
                {
                    "name": "_Z9test_funci",
                    "demangled_name": "test_func(int)",
                    "start_line": 10,
                    "end_line": 20,
                    "execution_count": 5,
                    "blocks_executed": 3,
                    "blocks": 4,
                }
            ],
            "lines": [
                {"line_number": 10, "count": 5, "function_name": "test_func"},
                {"line_number": 11, "count": 5},
                {"line_number": 12, "count": 0, "unexecuted_block": True},
            ],
        }
    ]
}


def test_parse_files_array_line_totals():
    cov = parse_gcov_json_string(json.dumps(SIMPLE))
    assert cov.total_files == 1
    assert cov.total_lines == 3
    assert cov.covered_lines == 2
    assert cov.uncovered_lines == 1


def test_parse_functions():
    cov = parse_gcov_json_string(json.dumps(SIMPLE))
    func = next(iter(cov.files.values())).functions[0]
    assert func.name == "_Z9test_funci"
    assert func.demangled_name == "test_func(int)"
    assert func.start_line == 10
    assert func.end_line == 20
    assert func.execution_count == 5
    assert func.blocks_executed == 3
    assert func.blocks_total == 4
    assert func.is_covered


def test_parse_line_metadata():
    cov = parse_gcov_json_string(json.dumps(SIMPLE))
    file_cov = next(iter(cov.files.values()))
    assert file_cov.lines[10].function_name == "test_func"
    assert file_cov.lines[12].has_unexecuted_block is True


def test_parse_branches():
    content = {
        "files": [
            {
                "file": "/p/test.cpp",
                "lines": [
                    {
                        "line_number": 10,
                        "count": 5,
                        "branches": [
                            {"count": 3, "throw": False, "fallthrough": True},
                            {"count": 0, "throw": True, "fallthrough": False},
                        ],
                    }
                ],
            }
        ]
    }
    cov = parse_gcov_json_string(json.dumps(content))
    line = next(iter(cov.files.values())).lines[10]
    assert len(line.branches) == 2
    assert line.branches[0].is_covered
    assert line.branches[0].is_fallthrough
    assert not line.branches[1].is_covered
    assert line.branches[1].is_throw


def test_single_file_key_without_files_array():
    # gcov also emits a top-level "file" object (no "files" array).
    content = {"file": "/p/solo.cpp", "lines": [{"line_number": 1, "count": 1}]}
    cov = parse_gcov_json_string(json.dumps(content))
    assert cov.total_files == 1
    assert cov.covered_lines == 1


def test_unknown_payload_is_ignored():
    # Neither "files" nor "file" -> no files, no crash.
    assert parse_gcov_json_string("{}").total_files == 0


def test_empty_files_array():
    cov = parse_gcov_json_string('{"files": []}')
    assert cov.total_files == 0
    assert cov.total_lines == 0


def test_repeated_file_and_line_counts_are_summed():
    # The same file/line spread across entries must accumulate, not overwrite.
    content = {
        "files": [
            {"file": "a.cpp", "lines": [{"line_number": 1, "count": 2}]},
            {"file": "a.cpp", "lines": [{"line_number": 1, "count": 3}]},
        ]
    }
    cov = parse_gcov_json_string(json.dumps(content))
    assert cov.total_files == 1
    assert next(iter(cov.files.values())).lines[1].count == 5


def test_parse_gcov_json_single_path(tmp_path):
    f = tmp_path / "x.gcov.json"
    f.write_text(json.dumps(SIMPLE))
    cov = parse_gcov_json(f)
    assert cov.total_files == 1
    assert cov.total_lines == 3


def test_parse_gcov_json_directory_globs_recursively(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "one.gcov.json").write_text(
        json.dumps({"file": "one.cpp", "lines": [{"line_number": 1, "count": 1}]})
    )
    (tmp_path / "nested" / "two.gcov.json").write_text(
        json.dumps({"file": "two.cpp", "lines": [{"line_number": 1, "count": 0}]})
    )
    # A non-matching file must be skipped by the *.gcov.json glob.
    (tmp_path / "ignore.json").write_text("{}")

    cov = parse_gcov_json(tmp_path)
    assert cov.total_files == 2
    assert {p.name for p in cov.files} == {"one.cpp", "two.cpp"}
    assert cov.covered_lines == 1


def test_parse_gcov_json_accepts_str_path(tmp_path):
    f = tmp_path / "x.gcov.json"
    f.write_text(json.dumps(SIMPLE))
    cov = parse_gcov_json(str(f))
    assert cov.total_files == 1
    assert isinstance(next(iter(cov.files)), Path)


def test_parse_gcov_json_file_with_unknown_payload(tmp_path):
    f = tmp_path / "x.gcov.json"
    f.write_text("{}")
    assert parse_gcov_json(f).total_files == 0


def test_file_entry_without_lines_still_registers():
    content = {
        "file": "a.cpp",
        "functions": [{"name": "f", "execution_count": 1}],
    }
    cov = parse_gcov_json_string(json.dumps(content))
    file_cov = next(iter(cov.files.values()))
    assert cov.total_files == 1
    assert file_cov.total_lines == 0
    assert file_cov.functions[0].name == "f"
    assert file_cov.functions[0].demangled_name is None
