"""Tests for C++ demangling helpers (subprocess mocked for determinism)."""

from __future__ import annotations

import subprocess

from covisible.utils import demangle
from covisible.utils.demangle import (
    demangle_cpp,
    demangle_cpp_batch,
    simplify_cpp_signature,
)


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def _patch_run(monkeypatch, fn):
    monkeypatch.setattr(demangle.subprocess, "run", fn)


# --- demangle_cpp -----------------------------------------------------------


def test_demangle_cpp_empty_returns_empty():
    assert demangle_cpp("") == ""


def test_demangle_cpp_non_mangled_skips_subprocess(monkeypatch):
    def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("c++filt should not run for non-mangled names")

    _patch_run(monkeypatch, boom)
    assert demangle_cpp("plain_name") == "plain_name"


def test_demangle_cpp_invokes_cppfilt(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc(0, "test_func(int)\n")

    _patch_run(monkeypatch, fake_run)
    assert demangle_cpp("_Z9test_funci") == "test_func(int)"
    assert captured["cmd"][0] == "c++filt"


def test_demangle_cpp_nonzero_returncode_returns_original(monkeypatch):
    _patch_run(monkeypatch, lambda *a, **k: _FakeProc(1, ""))
    assert demangle_cpp("_Z3foov") == "_Z3foov"


def test_demangle_cpp_missing_tool_returns_original(monkeypatch):
    def raise_not_found(*a, **k):
        raise FileNotFoundError

    _patch_run(monkeypatch, raise_not_found)
    assert demangle_cpp("_Z3foov") == "_Z3foov"


def test_demangle_cpp_timeout_returns_original(monkeypatch):
    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="c++filt", timeout=1)

    _patch_run(monkeypatch, raise_timeout)
    assert demangle_cpp("_Z3foov") == "_Z3foov"


# --- demangle_cpp_batch -----------------------------------------------------


def test_batch_empty_list():
    assert demangle_cpp_batch([]) == {}


def test_batch_no_mangled_names_is_identity(monkeypatch):
    def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("c++filt should not run when nothing is mangled")

    _patch_run(monkeypatch, boom)
    assert demangle_cpp_batch(["foo", "bar"]) == {"foo": "foo", "bar": "bar"}


def test_batch_demangles_only_mangled(monkeypatch):
    def fake_run(cmd, **kwargs):
        # Echo back one demangled line per mangled input, in order.
        names = kwargs["input"].split("\n")
        out = "\n".join(f"dem<{n}>" for n in names)
        return _FakeProc(0, out)

    _patch_run(monkeypatch, fake_run)
    result = demangle_cpp_batch(["_Z3foov", "plain", "_Z3barv"])
    assert result == {
        "_Z3foov": "dem<_Z3foov>",
        "plain": "plain",
        "_Z3barv": "dem<_Z3barv>",
    }


def test_batch_missing_tool_returns_identity(monkeypatch):
    def raise_not_found(*a, **k):
        raise FileNotFoundError

    _patch_run(monkeypatch, raise_not_found)
    assert demangle_cpp_batch(["_Z3foov"]) == {"_Z3foov": "_Z3foov"}


def test_batch_nonzero_returncode_returns_identity(monkeypatch):
    _patch_run(monkeypatch, lambda *a, **k: _FakeProc(1, ""))
    assert demangle_cpp_batch(["_Z3foov"]) == {"_Z3foov": "_Z3foov"}


def test_batch_skips_blank_demangled_lines(monkeypatch):
    # A blank line from c++filt must leave that symbol unchanged.
    _patch_run(monkeypatch, lambda *a, **k: _FakeProc(0, "foo()\n\nbar()"))
    result = demangle_cpp_batch(["_Z1", "_Z2", "_Z3"])
    assert result == {"_Z1": "foo()", "_Z2": "_Z2", "_Z3": "bar()"}


# --- simplify_cpp_signature -------------------------------------------------


def test_simplify_empty():
    assert simplify_cpp_signature("") == ""


def test_simplify_strips_std_prefix():
    assert simplify_cpp_signature("std::vector<int>") == "vector<int>"


def test_simplify_collapses_basic_string():
    full = "foo(std::basic_string<char, std::char_traits<char>, std::allocator<char>>)"
    assert simplify_cpp_signature(full) == "foo(string)"


def test_simplify_collapses_basic_string_short_form():
    assert simplify_cpp_signature("f(basic_string<char>)") == "f(string)"


def test_simplify_removes_allocator():
    assert simplify_cpp_signature("vector<int, allocator<int>>") == "vector<int>"


def test_simplify_truncates_long_signatures():
    out = simplify_cpp_signature("a" * 50, max_length=10)
    assert len(out) == 10
    assert out.endswith("...")
