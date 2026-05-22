"""Tests for cross-file import support in the Python claim runner.

Verifies that run_examples, run_properties, and run_tests correctly
use the ModuleCache to make imported module namespaces available when
evaluating claims.
"""

from pathlib import Path

import pytest

from notlob import from_tree, parse
from notlob.bindings.python.loader import ModuleCache
from notlob.bindings.python.runner import Status, run_examples, run_properties, run_tests


# ── Helpers ───────────────────────────────────────────────────

_BINDING = "#Proj\n\n---\n\n#Binding\n    ~language python\n    ~property-testing hypothesis\n    ~unit-testing pytest\n"
_BINDING_DECLS = {"property-testing": "hypothesis", "unit-testing": "pytest"}


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _setup(tmp_path: Path) -> ModuleCache:
    _write(tmp_path, "binding.lob", _BINDING)
    return ModuleCache(tmp_path)


def _module(src: str):
    return from_tree(parse(src))


# ── run_examples with cache ───────────────────────────────────

class TestRunExamplesWithCache:
    def test_example_uses_imported_name(self, tmp_path):
        _write(tmp_path, "math/utils.lob", (
            "#Math Utils\n\n"
            "    def triple(n):\n"
            "        return n * 3\n"
        ))
        cache = _setup(tmp_path)
        src = (
            "#App\n\n"
            "~example\n"
            "    triple(7) == 21\n\n"
            "---\n\n"
            "#References\n"
            "    #Math Utils\n"
        )
        results = run_examples(_module(src), cache=cache)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_example_fails_without_cache(self, tmp_path):
        # Same module but no cache — name not found → ERROR
        src = (
            "#App\n\n"
            "~example\n"
            "    triple(7) == 21\n\n"
            "---\n\n"
            "#References\n"
            "    #Math Utils\n"
        )
        results = run_examples(_module(src))
        assert results[0].status == Status.ERROR

    def test_example_with_mixed_references(self, tmp_path):
        _write(tmp_path, "base.lob", "#Base\n\n    BASE = 10\n")
        cache = _setup(tmp_path)
        src = (
            "#Consumer\n\n"
            "~example\n"
            "    BASE + added == 15\n\n"
            "---\n\n"
            "#References\n"
            "    #Base\n"
            "    added = 5\n"
        )
        results = run_examples(_module(src), cache=cache)
        assert results[0].status == Status.PASS


# ── run_tests with cache ──────────────────────────────────────

class TestRunTestsWithCache:
    def test_tests_section_uses_imported_name(self, tmp_path):
        _write(tmp_path, "utils.lob", (
            "#Utils\n\n"
            "    def square(n):\n"
            "        return n * n\n"
        ))
        cache = _setup(tmp_path)
        src = (
            "#Checker\n\n"
            "---\n\n"
            "#Tests\n"
            "    square(4) == 16\n"
            "    square(0) == 0\n\n"
            "#References\n"
            "    #Utils\n"
        )
        results = run_tests(_module(src), cache=cache)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)


# ── run_properties with cache ─────────────────────────────────

class TestRunPropertiesWithCache:
    def test_property_uses_imported_name(self, tmp_path):
        _write(tmp_path, "utils.lob", (
            "#Utils\n\n"
            "    def double(n):\n"
            "        return n * 2\n"
        ))
        cache = _setup(tmp_path)
        src = (
            "#Props\n\n"
            "~property\n"
            "    @given(n=st.integers(min_value=0, max_value=100))\n"
            "    def _(n):\n"
            "        assert double(n) == n + n\n\n"
            "---\n\n"
            "#References\n"
            "    #Utils\n"
        )
        results = run_properties(
            _module(src),
            binding=_BINDING_DECLS,
            cache=cache,
        )
        assert len(results) == 1
        assert results[0].status == Status.PASS


# ── cache=None is backward compatible ─────────────────────────

class TestCacheNoneBackcompat:
    def test_run_examples_no_cache(self):
        src = "#T\n\n    x = 1\n\n~example\n    x == 1\n"
        results = run_examples(_module(src))
        assert results[0].status == Status.PASS

    def test_run_tests_no_cache(self):
        src = "#T\n\n    x = 1\n\n---\n\n#Tests\n    x == 1\n"
        results = run_tests(_module(src))
        assert results[0].status == Status.PASS
