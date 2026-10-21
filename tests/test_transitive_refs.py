"""A module's code runs with everything it depends on, transitively.

kamtrinia's report (2026-10-19): `Top` lists only `Middle`; `Middle` lists
`Base` and uses it at module level. `notlob test` on `Middle` passed (Base
is its direct dependency), but on `Top` Middle's own code failed with a
NameError, because the Python and Haskell runners inlined only a module's
direct references. Listing Base in Top made it run but made `[imports]`
call the import unused: no way to satisfy both.

Loading and visibility are different questions. Loading must be
transitive: a module that works on its own must work when something else
uses it. Visibility is the module's own business: it should use only what
it lists, which Python lint enforces (F821) and which this change leaves
alone. TypeScript already loaded transitively; Python and Haskell now do,
through one shared function (`project.load_dependency_modules`).

meta/bugs/2026-10-21-transitive-lob-refs/bug.md
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from notlob import from_tree, parse_file
from notlob.bindings import Status
from notlob.bindings.python import build_python, extract_calls, extract_symbols
from notlob.bindings.python.lint import lint_python
from notlob.bindings.python.runner import (
    run_examples, run_properties, run_tests,
)
from notlob.check import check_imports
from notlob.commands import cmd_test
from notlob.project import build_package

_PYTHON = "#B\n\n---\n\n#Binding\n    ~language python\n"
_HASKELL = "#B\n\n---\n\n#Binding\n    ~language haskell\n"

_BASE = (
    "#Base\n\nThe bottom of the chain.\n\n"
    "    def base_value() -> int:\n        return 1\n\n"
    "~example\n    base_value() == 1\n"
)
# Uses Base at module level: it cannot even be loaded without it.
_MIDDLE = (
    "#Middle\n\nThe middle uses #Base when it is loaded.\n\n"
    "    MIDDLE_VALUE = base_value() + 1\n\n"
    "~example\n    MIDDLE_VALUE == 2\n\n"
    "---\n\n#References\n    #Base\n"
)
# Lists only Middle and never names anything from Base.
_TOP = (
    "#Top\n\nThe top uses only #Middle.\n\n"
    "    TOP_VALUE = MIDDLE_VALUE + 1\n\n"
    "~example\n    TOP_VALUE == 3\n\n"
    "~property\n"
    "    @given(n=st.integers(min_value=0, max_value=3))\n"
    "    def _(n):\n        assert TOP_VALUE == 3\n\n"
    "---\n\n#Tests\n    TOP_VALUE == 3\n\n"
    "#References\n    #Middle\n"
)
# Lists both, deepest last: the order that used to fail.
_SUMMIT = (
    "#Summit\n\nUses both #Middle and #Base.\n\n"
    "    SUMMIT_VALUE = MIDDLE_VALUE + base_value()\n\n"
    "~example\n    SUMMIT_VALUE == 3\n\n"
    "---\n\n#References\n    #Middle\n    #Base\n"
)
# Lists only Middle but uses a name that only Base defines.
_UNDECLARED = (
    "#Undeclared\n\nCalls into #Base without listing it.\n\n"
    "    UNDECLARED = base_value()\n\n"
    "~example\n    UNDECLARED == 1\n\n"
    "---\n\n#References\n    #Middle\n"
)


def _project(tmp_path: Path, files: dict[str, str], binding=_PYTHON) -> Path:
    (tmp_path / "binding.lob").write_text(binding, encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


@pytest.fixture
def chain(tmp_path):
    return _project(tmp_path, {
        "base.lob": _BASE, "middle.lob": _MIDDLE, "top.lob": _TOP,
        "summit.lob": _SUMMIT, "undeclared.lob": _UNDECLARED,
    })


def _module(root: Path, name: str):
    return from_tree(parse_file(root / name))


def _statuses(results):
    return [r.status for r in results]


# ── Python: claims ────────────────────────────────────────────

class TestPythonClaimsLoadTransitively:
    def test_middle_alone_passes(self, chain):
        """Control: the direct dependency was always loaded."""
        path = chain / "middle.lob"
        results = run_examples(_module(chain, "middle.lob"), file_path=path)
        assert _statuses(results) == [Status.PASS]

    def test_examples_of_a_module_whose_dependency_has_dependencies(
        self, chain,
    ):
        path = chain / "top.lob"
        results = run_examples(_module(chain, "top.lob"), file_path=path)
        assert [(r.address, r.status) for r in results] == [
            ("top#example#1", Status.PASS)]

    def test_tests_section(self, chain):
        path = chain / "top.lob"
        results = run_tests(_module(chain, "top.lob"), file_path=path)
        assert _statuses(results) == [Status.PASS]

    def test_properties(self, chain):
        path = chain / "top.lob"
        results = run_properties(_module(chain, "top.lob"), file_path=path)
        assert _statuses(results) == [Status.PASS]

    def test_listing_order_does_not_matter(self, chain):
        """`#Middle` listed before `#Base` used to be a NameError."""
        path = chain / "summit.lob"
        results = run_examples(_module(chain, "summit.lob"), file_path=path)
        assert _statuses(results) == [Status.PASS]

    def test_the_whole_command_passes(self, chain, monkeypatch, capsys):
        """`notlob test top.lob`: claims, lint and cross-reference checks
        together, as a user runs it."""
        monkeypatch.chdir(chain)
        assert cmd_test(chain / "top.lob") == 0
        out = capsys.readouterr().out
        assert "ERROR" not in out and "LINT" not in out


# ── Python: build ─────────────────────────────────────────────

class TestPythonBuildLoadsTransitively:
    def _source(self, chain, name):
        return build_python(_module(chain, name), chain / name)

    def test_dependencies_are_in_dependency_order(self, chain):
        src = self._source(chain, "top.lob")
        assert (src.index("def base_value")
                < src.index("MIDDLE_VALUE = ")
                < src.index("TOP_VALUE = "))

    def test_each_module_appears_once(self, chain):
        src = self._source(chain, "summit.lob")      # lists Middle and Base
        assert src.count("def base_value") == 1
        assert src.count("MIDDLE_VALUE = ") == 1

    def test_the_built_artifact_runs(self, chain):
        namespace: dict = {}
        exec(self._source(chain, "top.lob"), namespace)
        assert namespace["TOP_VALUE"] == 3


# ── Python: lint and [imports] ────────────────────────────────

class TestPythonLintAndImports:
    def test_a_module_using_only_what_it_lists_is_clean(self, chain):
        findings = lint_python(_module(chain, "top.lob"), root=chain)
        assert findings == []

    def test_using_an_unlisted_modules_name_is_still_reported(self, chain):
        """Visibility is the module's business, and lint flags the name it
        did not declare: this is how 'each module lists exactly what it
        uses' is enforced. Loading follows use, so `Undeclared`, which
        lists `Middle` but uses nothing `Middle` defines, does not load
        `Middle`, and so not `Base` either: it fails at run time too. (It
        used to run, because everything listed was loaded.)"""
        results = run_examples(
            _module(chain, "undeclared.lob"),
            file_path=chain / "undeclared.lob")
        assert _statuses(results) == [Status.ERROR]
        findings = lint_python(_module(chain, "undeclared.lob"), root=chain)
        assert [(f.code, f.message) for f in findings] == [
            ("F821", "Undefined name `base_value`")]

    def test_imports_check_needs_no_workaround(self, chain):
        """Top lists only Middle, uses it, and is not flagged; the
        catch-22 (list Base to run, flagged for listing Base) is gone."""
        graph = build_package(chain, extract_symbols,
                              call_extractor=extract_calls)
        flagged = [f for f in check_imports(graph)
                   if "Top" in f.message]
        assert flagged == []


# ── Haskell ───────────────────────────────────────────────────

_HAS_HASKELL = (shutil.which("runghc") is not None
                or shutil.which("stack") is not None)


@pytest.mark.skipif(not _HAS_HASKELL, reason="runghc or stack not found")
class TestHaskellClaimsLoadTransitively:
    def test_examples_of_a_module_whose_dependency_has_dependencies(
        self, tmp_path,
    ):
        from notlob.bindings.haskell.runner import run_examples as run_hs
        root = _project(tmp_path, {
            "base.lob": "#Base\n\n    baseValue :: Int\n    baseValue = 1\n",
            "middle.lob": (
                "#Middle\n\n    middleValue :: Int\n"
                "    middleValue = baseValue + 1\n\n"
                "---\n\n#References\n    #Base\n"),
            "top.lob": (
                "#Top\n\n    topValue :: Int\n"
                "    topValue = middleValue + 1\n\n"
                "~example\n    topValue == 3\n\n"
                "---\n\n#References\n    #Middle\n"),
        }, binding=_HASKELL)
        results = run_hs(_module(root, "top.lob"),
                         file_path=root / "top.lob")
        assert _statuses(results) == [Status.PASS], results


# ── TypeScript (already transitive; the regression) ───────────

class TestTypeScriptSourceLoadsTransitively:
    def test_dependencies_are_in_dependency_order_once_each(self, tmp_path):
        from notlob.bindings.typescript.runner import _build_module_source
        root = _project(tmp_path, {
            "base.lob": "#Base\n\n    const baseValue = 1;\n",
            "middle.lob": (
                "#Middle\n\n    const middleValue = baseValue + 1;\n\n"
                "---\n\n#References\n    #Base\n"),
            "top.lob": (
                "#Top\n\n    const topValue = middleValue + 1;\n\n"
                "---\n\n#References\n    #Middle\n    #Base\n"),
        }, binding="#B\n\n---\n\n#Binding\n    ~language typescript\n")
        src = _build_module_source(_module(root, "top.lob"), root)
        assert (src.index("const baseValue")
                < src.index("const middleValue")
                < src.index("const topValue"))
        assert src.count("const baseValue") == 1
