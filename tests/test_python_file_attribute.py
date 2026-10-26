"""A Python module's `__file__` is the `.lob` file it was written in.

examples/gutenberg/gutenberg/hamlet.lob finds its data with
`Path(__file__).parent.parent / "data"`. The original in-process loader
(`ModuleCache`) set `__file__` to the `.lob` path; the subprocess harness
that replaced it runs a temp script, so `__file__` was the temp script and
the example's data file was "missing". The example was not covered by any
test, so nobody noticed (found by tests/test_example_projects.py).

Claims (`~example`, `#Tests`, `~property`) run with the module's own
`__file__` set to its `.lob` path. A built artifact does not: it is
portable and must not carry the source tree's absolute path.
"""

from __future__ import annotations

import pytest

from kitcalls import building, in_project
from notlob import from_tree, parse_file
from notlob.bindings import Status
from notlob.bindings.python import build_python as _build_python, kit
from notlob.bindings.python.runner import (
    run_examples as _run_examples, run_properties as _run_properties,
    run_tests as _run_tests,
)

run_examples = in_project(_run_examples, kit, "EXAMPLE")
run_properties = in_project(_run_properties, kit, "PROPERTY")
run_tests = in_project(_run_tests, kit, "TEST")
build_python = building(_build_python, kit)

_SOURCE = (
    "#Where\n\n"
    "Finds its data relative to the file it is written in.\n\n"
    "    HERE = Path(__file__).name\n"
    "    DATA = (Path(__file__).parent.parent / 'data' / 'x.txt').read_text()\n\n"
    "~example\n    HERE == 'where.lob'\n    DATA == 'hi'\n\n"
    "~property\n"
    "    @given(n=st.integers(min_value=0, max_value=2))\n"
    "    def _(n):\n        assert HERE == 'where.lob'\n\n"
    "---\n\n#Tests\n    HERE == 'where.lob'\n    DATA == 'hi'\n\n"
    "#References\n    from pathlib import Path\n"
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "binding.lob").write_text(
        "#P\n\n---\n\n#Binding\n    ~language python\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    path = tmp_path / "pkg" / "where.lob"
    path.write_text(_SOURCE, encoding="utf-8")
    return path


def _statuses(results):
    return [r.status for r in results]


class TestFileAttribute:
    def test_examples_see_the_lob_file(self, project):
        module = from_tree(parse_file(project))
        results = run_examples(module, file_path=project)
        assert _statuses(results) == [Status.PASS, Status.PASS], results

    def test_tests_section_sees_the_lob_file(self, project):
        module = from_tree(parse_file(project))
        results = run_tests(module, file_path=project)
        assert _statuses(results) == [Status.PASS, Status.PASS], results

    def test_properties_see_the_lob_file(self, project):
        module = from_tree(parse_file(project))
        results = run_properties(module, file_path=project)
        assert _statuses(results) == [Status.PASS], results

    def test_a_built_artifact_carries_no_source_path(self, project):
        """Portable: the artifact must not bake in this machine's path."""
        module = from_tree(parse_file(project))
        source = build_python(module, project)
        assert str(project.resolve()) not in source
        assert str(project.parent) not in source
