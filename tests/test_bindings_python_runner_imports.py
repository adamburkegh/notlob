"""Tests for cross-file import support in the Python claim runner.

Verifies that run_examples, run_properties, and run_tests correctly
inline lob-ref dependency source (via _load_dep_modules + file_path,
matching build_python) when evaluating claims. The old mechanism was
an in-process ModuleCache passed as a `cache=` argument -- superseded
because claims now run in a subprocess, which has no access to an
in-memory cache from the parent process. `cache` is still accepted by
all three functions for BindingKit call-site compatibility but is
unused; dependency resolution is entirely file_path-driven now.
"""

from pathlib import Path

from notlob import from_tree, parse
from notlob.bindings.python.runner import Status, run_examples, run_properties, run_tests


# ── Helpers ───────────────────────────────────────────────────

_BINDING = "#Proj\n\n---\n\n#Binding\n    ~language python\n"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _setup(tmp_path: Path) -> None:
    _write(tmp_path, "binding.lob", _BINDING)


def _module(src: str):
    return from_tree(parse(src))


# ── run_examples with file_path ───────────────────────────────

class TestRunExamplesWithFilePath:
    def test_example_uses_imported_name(self, tmp_path):
        _write(tmp_path, "math/utils.lob", (
            "#Math Utils\n\n"
            "    def triple(n):\n"
            "        return n * 3\n"
        ))
        _setup(tmp_path)
        src = (
            "#App\n\n"
            "~example\n"
            "    triple(7) == 21\n\n"
            "---\n\n"
            "#References\n"
            "    #Math Utils\n"
        )
        app_path = _write(tmp_path, "app.lob", src)
        results = run_examples(_module(src), file_path=app_path)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_example_fails_without_project_root(self, tmp_path):
        # Same module but no file_path — no project root to resolve
        # the dependency against → NameError inside the subprocess.
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
        _setup(tmp_path)
        src = (
            "#Consumer\n\n"
            "~example\n"
            "    BASE + added == 15\n\n"
            "---\n\n"
            "#References\n"
            "    #Base\n"
            "    added = 5\n"
        )
        app_path = _write(tmp_path, "consumer.lob", src)
        results = run_examples(_module(src), file_path=app_path)
        assert results[0].status == Status.PASS


# ── run_tests with file_path ──────────────────────────────────

class TestRunTestsWithFilePath:
    def test_tests_section_uses_imported_name(self, tmp_path):
        _write(tmp_path, "utils.lob", (
            "#Utils\n\n"
            "    def square(n):\n"
            "        return n * n\n"
        ))
        _setup(tmp_path)
        src = (
            "#Checker\n\n"
            "---\n\n"
            "#Tests\n"
            "    square(4) == 16\n"
            "    square(0) == 0\n\n"
            "#References\n"
            "    #Utils\n"
        )
        app_path = _write(tmp_path, "checker.lob", src)
        results = run_tests(_module(src), file_path=app_path)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)


# ── run_properties with file_path ─────────────────────────────

class TestRunPropertiesWithFilePath:
    def test_property_uses_imported_name(self, tmp_path):
        _write(tmp_path, "utils.lob", (
            "#Utils\n\n"
            "    def double(n):\n"
            "        return n * 2\n"
        ))
        _setup(tmp_path)
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
        app_path = _write(tmp_path, "props.lob", src)
        results = run_properties(_module(src), file_path=app_path)
        assert len(results) == 1
        assert results[0].status == Status.PASS


# ── no file_path is backward compatible ───────────────────────

class TestNoFilePathBackcompat:
    def test_run_examples_no_file_path(self):
        src = "#T\n\n    x = 1\n\n~example\n    x == 1\n"
        results = run_examples(_module(src))
        assert results[0].status == Status.PASS

    def test_run_tests_no_file_path(self):
        src = "#T\n\n    x = 1\n\n---\n\n#Tests\n    x == 1\n"
        results = run_tests(_module(src))
        assert results[0].status == Status.PASS
