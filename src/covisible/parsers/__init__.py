"""Coverage data parsers."""

from covisible.parsers.gcov_json import parse_gcov_json
from covisible.parsers.lcov import parse_lcov

__all__ = ["parse_gcov_json", "parse_lcov"]
