"""Tests for coverage parsers."""

import pytest

from covisible.parsers.gcov_json import parse_gcov_json_string
from covisible.parsers.lcov import parse_lcov_string


class TestGcovJsonParser:
    """Tests for gcov JSON parser."""

    # def test_parse_simple_file(self):
    #     json_content = """
    #     {
    #         "files": [{
    #             "file": "/path/to/test.cpp",
    #             "functions": [{
    #                 "name": "test_func",
    #                 "demangled_name": "test_func(int)",
    #                 "start_line": 10,
    #                 "end_line": 20,
    #                 "execution_count": 5
    #             }],
    #             "lines": [
    #                 {"line_number": 10, "count": 5, "function_name": "test_func"},
    #                 {"line_number": 11, "count": 5},
    #                 {"line_number": 12, "count": 0}
    #             ]
    #         }]
    #     }
    #     """
    #     cov = parse_gcov_json_string(json_content)

    #     assert cov.total_files == 1
    #     assert cov.total_lines == 3
    #     assert cov.covered_lines == 2
    #     assert cov.uncovered_lines == 1

    # def test_parse_with_branches(self):
    #     json_content = """
    #     {
    #         "files": [{
    #             "file": "/path/to/test.cpp",
    #             "lines": [{
    #                 "line_number": 10,
    #                 "count": 5,
    #                 "branches": [
    #                     {"count": 3, "throw": false, "fallthrough": true},
    #                     {"count": 0, "throw": false, "fallthrough": false}
    #                 ]
    #             }]
    #         }]
    #     }
    #     """
    #     cov = parse_gcov_json_string(json_content)

    #     file_cov = list(cov.files.values())[0]
    #     line = file_cov.lines[10]
    #     assert len(line.branches) == 2
    #     assert line.branches[0].is_covered
    #     assert not line.branches[1].is_covered

    def test_parse_empty(self):
        cov = parse_gcov_json_string('{"files": []}')
        assert cov.total_files == 0
        assert cov.total_lines == 0


class TestLcovParser:
    """Tests for LCOV parser."""

    def test_parse_simple_file(self):
        lcov_content = """TN:
SF:/path/to/test.cpp
FN:10,test_func
FNDA:5,test_func
DA:10,5
DA:11,5
DA:12,0
LF:3
LH:2
end_of_record
"""
        cov = parse_lcov_string(lcov_content)

        assert cov.total_files == 1
        assert cov.total_lines == 3
        assert cov.covered_lines == 2
        assert cov.uncovered_lines == 1

    def test_parse_with_branches(self):
        lcov_content = """TN:
SF:/path/to/test.cpp
DA:10,5
BRDA:10,0,0,3
BRDA:10,0,1,0
end_of_record
"""
        cov = parse_lcov_string(lcov_content)

        file_cov = list(cov.files.values())[0]
        line = file_cov.lines[10]
        assert len(line.branches) == 2
        assert line.branches[0].is_covered
        assert not line.branches[1].is_covered

    def test_parse_multiple_files(self):
        lcov_content = """TN:
SF:/path/to/file1.cpp
DA:1,1
end_of_record
SF:/path/to/file2.cpp
DA:1,0
end_of_record
"""
        cov = parse_lcov_string(lcov_content)

        assert cov.total_files == 2
        assert cov.covered_lines == 1
        assert cov.uncovered_lines == 1

    def test_parse_empty(self):
        cov = parse_lcov_string("")
        assert cov.total_files == 0
