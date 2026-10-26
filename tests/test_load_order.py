"""Which modules a module's code needs, read from the package graph.

A module A needs B when A lists B (an `IMPORTS` edge) and the code of A
uses a name B's own code defines (a `USES` edge into a code block of B),
less the names A defines itself. notlob works that out and hands the
modules to a binding, which loads nothing itself.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import notlob.bindings.haskell as haskell_package
import notlob.bindings.python as python_package
import notlob.bindings.typescript as typescript_package
from notlob import build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.project import LobRefCycleError, load_order

_BINDING = "#B\n\n---\n\n#Binding\n    ~language python\n"

_LIB = "#Lib\n\n    def f() -> int:\n        return 1\n"


def _order(tmp_path: Path, files: dict[str, str], address: str = "user",
           which=kit) -> list[str]:
    (tmp_path / "binding.lob").write_text(_BINDING, encoding="utf-8")
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    graph = build_package(
        tmp_path, kit.extract_symbols, call_extractor=kit.extract_calls)
    return load_order(graph, address, which)


class TestNeedIsReadFromTheGraph:
    def test_a_use_of_the_listed_modules_code_is_a_need(self, tmp_path):
        assert _order(tmp_path, {
            "lib.lob": _LIB,
            "user.lob": ("#User\n\n    X = f()\n\n"
                         "---\n\n#References\n    #Lib\n"),
        }) == ["lib"]

    def test_a_citation_only_is_not(self, tmp_path):
        assert _order(tmp_path, {
            "lib.lob": _LIB,
            "user.lob": ("#User\n\nCites #Lib.\n\n    X = 2\n\n"
                         "---\n\n#References\n    #Lib\n"),
        }) == []

    def test_a_name_both_define_is_the_listing_modules_own(self, tmp_path):
        assert _order(tmp_path, {
            "lib.lob": _LIB,
            "user.lob": ("#User\n\n    def f() -> int:\n        return 2\n\n"
                         "    Y = f()\n\n"
                         "---\n\n#References\n    #Lib\n"),
        }) == []

    def test_a_function_only_a_property_defines_is_not_its_code(
        self, tmp_path,
    ):
        assert _order(tmp_path, {
            "lib.lob": ("#Lib\n\n    X = 1\n\n~property p\n"
                        "    @given()\n    def f():\n        pass\n"),
            "user.lob": ("#User\n\n    Y = f()\n\n"
                         "---\n\n#References\n    #Lib\n"),
        }) == []

    def test_a_use_from_a_claim_is_a_need(self, tmp_path):
        assert _order(tmp_path, {
            "lib.lob": _LIB,
            "user.lob": ("#User\n\n~example\n    f() == 1\n\n"
                         "---\n\n#References\n    #Lib\n"),
        }) == ["lib"]

    def test_a_use_from_tests_is_a_need(self, tmp_path):
        assert _order(tmp_path, {
            "lib.lob": _LIB,
            "user.lob": ("#User\n\n    X = 1\n\n"
                         "---\n\n#Tests\n    f() == 1\n\n"
                         "#References\n    #Lib\n"),
        }) == ["lib"]

    def test_a_use_of_an_unlisted_module_is_not(self, tmp_path):
        assert _order(tmp_path, {
            "lib.lob": _LIB,
            "user.lob": "#User\n\n    X = f()\n",
        }) == []

    def test_what_the_needed_module_needs_comes_first_once(self, tmp_path):
        assert _order(tmp_path, {
            "base.lob": "#Base\n\n    def g() -> int:\n        return 0\n",
            "lib.lob": ("#Lib\n\n    def f() -> int:\n        return g()\n\n"
                        "---\n\n#References\n    #Base\n"),
            "user.lob": ("#User\n\n    X = f() + g()\n\n"
                         "---\n\n#References\n    #Lib\n    #Base\n"),
        }) == ["base", "lib"]

    def test_a_cycle_of_need_is_an_error_naming_it(self, tmp_path):
        with pytest.raises(LobRefCycleError) as caught:
            _order(tmp_path, {
                "ping.lob": ("#Ping\n\n    PING = pong_value()\n\n"
                             "    def ping_value() -> int:\n"
                             "        return 1\n\n"
                             "---\n\n#References\n    #Pong\n"),
                "pong.lob": ("#Pong\n\n    PONG = ping_value()\n\n"
                             "    def pong_value() -> int:\n"
                             "        return 2\n\n"
                             "---\n\n#References\n    #Ping\n"),
            }, address="ping")
        assert caught.value.cycle == ["ping", "pong", "ping"]
        assert "circular code dependency: ping -> pong -> ping" in str(
            caught.value)

    def test_a_cycle_of_citations_is_not(self, tmp_path):
        assert _order(tmp_path, {
            "x.lob": ("#X\n\nCites #Y.\n\n    x = 1\n\n"
                      "---\n\n#References\n    #Y\n"),
            "y.lob": ("#Y\n\nCites #X.\n\n    y = 2\n\n"
                      "---\n\n#References\n    #X\n"),
        }, address="x") == []


class TestWhenUseCannotBeDetermined:
    """A binding whose reference extraction is not complete: the address
    tree decides, and the graph's `USES` edges are not read."""

    CITES = {
        "lib.lob": _LIB,
        "user.lob": ("#User\n\nCites #Lib.\n\n    X = 2\n\n"
                     "---\n\n#References\n    #Lib\n"),
    }

    def test_the_kits_say_which_they_are(self):
        assert kit.complete_references
        assert not typescript_kit.complete_references
        assert not haskell_kit.complete_references

    def test_a_listing_nothing_reads_is_needed(self, tmp_path):
        assert _order(tmp_path, self.CITES, which=typescript_kit) == ["lib"]

    def test_unless_it_is_a_descendant(self, tmp_path):
        assert _order(tmp_path, {
            "shop.lob": ("#Shop\n\nCites #Shop Prices.\n\n"
                         "---\n\n#References\n    #Shop Prices\n"),
            "shop/prices.lob": "#Shop Prices\n\n    P = 1\n",
        }, address="shop", which=typescript_kit) == []

    def test_a_listing_of_an_ancestor_or_a_sibling_is_needed(self, tmp_path):
        assert _order(tmp_path, {
            "shop.lob": "#Shop\n\n    S = 1\n",
            "shop/prices.lob": "#Shop Prices\n\n    P = 1\n",
            "shop/tax.lob": ("#Shop Tax\n\n    T = 1\n\n"
                             "---\n\n#References\n"
                             "    #Shop\n    #Shop Prices\n"),
        }, address="shop/tax", which=typescript_kit) == [
            "shop", "shop/prices"]

    def test_without_a_kit_the_tree_decides_too(self, tmp_path):
        assert _order(tmp_path, self.CITES, which=None) == ["lib"]


@pytest.mark.parametrize("package", [
    python_package, haskell_package, typescript_package,
], ids=["python", "haskell", "typescript"])
class TestABindingLoadsNothingItself:
    GONE = ("module_lob_refs", "resolve_module_path", "transitive_lob_refs",
            "_load_dep_modules", "find_project_root")

    def test_no_runner_or_assembler_reads_the_project(self, package):
        folder = Path(package.__file__).parent
        for name in ("runner.py", "assemble.py", "__init__.py"):
            text = (folder / name).read_text(encoding="utf-8")
            found = [word for word in self.GONE if word in text]
            assert not found, f"{folder.name}/{name}: {found}"

    def test_each_callable_is_handed_deps(self, package):
        for function in (package.kit.run_examples, package.kit.run_tests,
                         package.kit.run_properties, package.kit.build):
            parameter = inspect.signature(function).parameters["deps"]
            assert parameter.default == ()
            assert parameter.kind == inspect.Parameter.KEYWORD_ONLY
