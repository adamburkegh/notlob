"""Two modules may list each other in `#References`.

The Gutenberg example is where `#Name` cross-references between modules
started: `corpus` is the general machinery and says, in prose, that a second
text would be "a module of the same shape as" `hamlet`. `hamlet` lists
`corpus` because its code needs it. For `corpus` to refer to `hamlet`
the way the language says a module refers to another, it must list it too,
and that was a cycle nothing could run: listing a module made `corpus`'s
code load `hamlet`'s first, and `hamlet`'s code needs `corpus`'s.

Listing in `#References` says "this argument cites that module". Whether
the code of the cited module is needed is a separate fact, and the code
itself says which way it goes: a module's code needs what it uses. A
reference nothing in the code uses is a citation only, so it adds
nothing to what has to be loaded. A cycle in which each side's code does
use the other is a different matter and is an error, not a silent
NameError.

meta/bugs/2026-10-22-mutual-references/bug.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob import from_tree, parse_file
from notlob.bindings import Status
from notlob.bindings.python import build_python, kit
from notlob.bindings.python.runner import run_examples
from notlob.commands import cmd_test
from notlob.graph import EdgeKind
from notlob.project import build_package, load_dependency_modules

_BINDING = "#B\n\n---\n\n#Binding\n    ~language python\n"

# The general module. Its code uses nothing from Demo; its prose cites it.
_CORE = (
    "#Core\n\n"
    "The machinery. A second use would be a module of the same shape as\n"
    "#Demo, which lists this one.\n\n"
    "    def double(n: int) -> int:\n        return n * 2\n\n"
    "~example\n    double(2) == 4\n\n"
    "---\n\n#References\n    #Demo\n"
)
# The specific module. Its code uses Core's.
_DEMO = (
    "#Demo\n\n"
    "Applies #Core to a value.\n\n"
    "    VALUE = double(21)\n\n"
    "~example\n    VALUE == 42\n\n"
    "---\n\n#References\n    #Core\n"
)
# The same shape, but each side's code uses the other: a real cycle.
_PING = (
    "#Ping\n\nCalls #Pong at load.\n\n"
    "    PING = pong_value() + 1\n\n"
    "    def ping_value() -> int:\n        return 1\n\n"
    "~example\n    PING == 3\n\n"
    "---\n\n#References\n    #Pong\n"
)
_PONG = (
    "#Pong\n\nCalls #Ping at load.\n\n"
    "    PONG = ping_value() + 1\n\n"
    "    def pong_value() -> int:\n        return 2\n\n"
    "~example\n    PONG == 2\n\n"
    "---\n\n#References\n    #Ping\n"
)


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "binding.lob").write_text(_BINDING, encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def _module(root: Path, name: str):
    return from_tree(parse_file(root / name))


@pytest.fixture
def pair(tmp_path):
    return _project(tmp_path, {"core.lob": _CORE, "demo.lob": _DEMO})


@pytest.fixture
def cycle(tmp_path):
    return _project(tmp_path, {"ping.lob": _PING, "pong.lob": _PONG})


class TestMutualReferencesRun:
    def test_the_general_module_runs_with_its_citation_listed(self, pair):
        """Core cites Demo; running Core must not load Demo's code first."""
        results = run_examples(
            _module(pair, "core.lob"), file_path=pair / "core.lob")
        assert [r.status for r in results] == [Status.PASS]

    def test_the_specific_module_still_runs(self, pair):
        results = run_examples(
            _module(pair, "demo.lob"), file_path=pair / "demo.lob")
        assert [r.status for r in results] == [Status.PASS]

    def test_each_command_passes(self, pair, monkeypatch, capsys):
        monkeypatch.chdir(pair)
        assert cmd_test(pair / "core.lob") == 0
        assert cmd_test(pair / "demo.lob") == 0
        out = capsys.readouterr()
        assert "ERROR" not in out.out + out.err

    def test_the_whole_project_passes(self, pair, monkeypatch, capsys):
        monkeypatch.chdir(pair)
        assert cmd_test(None) == 0

    def test_the_citation_is_not_loaded_as_code(self, pair):
        loaded = load_dependency_modules(
            _module(pair, "core.lob"), pair, kit)
        assert loaded == []

    def test_the_use_is_loaded_as_code(self, pair):
        loaded = load_dependency_modules(
            _module(pair, "demo.lob"), pair, kit)
        assert [m.title for m in loaded] == ["Core"]

    def test_a_listing_the_code_does_not_use_loads_nothing(self, tmp_path):
        """Property 4. Not only in a cycle: a citation is never loaded."""
        root = _project(tmp_path, {
            "lib.lob": "#Lib\n\n    def f() -> int:\n        return 1\n",
            "user.lob": ("#User\n\nOnly cites #Lib.\n\n"
                         "    X = 2\n\n---\n\n#References\n    #Lib\n"),
        })
        loaded = load_dependency_modules(
            _module(root, "user.lob"), root, kit)
        assert loaded == []

    def test_a_claim_that_uses_the_name_is_a_use(self, tmp_path):
        root = _project(tmp_path, {
            "lib.lob": "#Lib\n\n    def f() -> int:\n        return 1\n",
            "user.lob": ("#User\n\nChecks #Lib.\n\n"
                         "~example\n    f() == 1\n\n"
                         "---\n\n#References\n    #Lib\n"),
        })
        loaded = load_dependency_modules(
            _module(root, "user.lob"), root, kit)
        assert [m.title for m in loaded] == ["Lib"]

    def test_a_tests_section_assertion_is_a_use(self, tmp_path):
        """More than one line, which used to leave the node's code
        unparseable (and so empty of references)."""
        root = _project(tmp_path, {
            "lib.lob": "#Lib\n\n    def f() -> int:\n        return 1\n",
            "user.lob": ("#User\n\nChecks #Lib.\n\n"
                         "---\n\n#Tests\n    f() == 1\n    f() + 1 == 2\n\n"
                         "#References\n    #Lib\n"),
        })
        loaded = load_dependency_modules(
            _module(root, "user.lob"), root, kit)
        assert [m.title for m in loaded] == ["Lib"]

    def test_a_name_in_a_string_or_comment_is_not_a_use(self, tmp_path):
        root = _project(tmp_path, {
            "lib.lob": "#Lib\n\n    def f() -> int:\n        return 1\n",
            "user.lob": ("#User\n\nMentions #Lib.\n\n"
                         "    X = 'f'  # f() is in Lib\n\n"
                         "---\n\n#References\n    #Lib\n"),
        })
        loaded = load_dependency_modules(
            _module(root, "user.lob"), root, kit)
        assert loaded == []

    def test_a_name_the_module_defines_itself_is_not_a_use(self, tmp_path):
        """Property 6."""
        root = _project(tmp_path, {
            "lib.lob": "#Lib\n\n    def f() -> int:\n        return 1\n",
            "user.lob": ("#User\n\nHas its own f, cites #Lib.\n\n"
                         "    def f() -> int:\n        return 2\n\n"
                         "    Y = f()\n\n---\n\n#References\n    #Lib\n"),
        })
        loaded = load_dependency_modules(
            _module(root, "user.lob"), root, kit)
        assert loaded == []

    def test_a_built_artifact_has_the_code_it_uses_and_no_more(self, pair):
        core = build_python(_module(pair, "core.lob"), pair / "core.lob")
        demo = build_python(_module(pair, "demo.lob"), pair / "demo.lob")
        assert "VALUE" not in core
        assert core.index("def double") < demo.index("VALUE")


class TestMutualReferencesAreInTheGraph:
    def test_both_imports_edges_exist(self, pair):
        graph = build_package(pair)
        assert [n.address for n in graph.children("core", EdgeKind.IMPORTS)
                ] == ["demo"]
        assert [n.address for n in graph.children("demo", EdgeKind.IMPORTS)
                ] == ["core"]

    def test_the_prose_reference_resolves_and_is_an_edge(self, pair):
        graph = build_package(pair)
        assert "demo" in [
            n.address for n in graph.children("core", EdgeKind.REFERENCES)]


_SHOP = (
    "#Shop\n\n"
    "The shop is two parts: #Shop Prices says what things cost and\n"
    "#Shop Tax adds the tax to a price. This module has no code.\n\n"
    "---\n\n#References\n    #Shop Prices\n    #Shop Tax\n"
)
_PRICES = (
    "#Shop Prices\n\nPart of #Shop.\n\n"
    "    def price() -> int:\n        return 100\n\n"
    "~example\n    price() == 100\n\n"
    "---\n\n#References\n    #Shop\n"
)
_TAX = (
    "#Shop Tax\n\nPart of #Shop; taxes what #Shop Prices says.\n\n"
    "    def with_tax() -> int:\n        return price() + price() // 10\n\n"
    "~example\n    with_tax() == 110\n\n"
    "---\n\n#References\n    #Shop\n    #Shop Prices\n"
)


@pytest.fixture
def shop(tmp_path):
    root = _project(tmp_path, {"shop.lob": _SHOP})
    (root / "shop").mkdir()
    (root / "shop" / "prices.lob").write_text(_PRICES, encoding="utf-8")
    (root / "shop" / "tax.lob").write_text(_TAX, encoding="utf-8")
    return root


class TestOverviewShape:
    """Property 9: an overview that lists the parts it explains, and
    parts that list it, are ordinary."""

    def test_the_whole_project_passes(self, shop, monkeypatch, capsys):
        monkeypatch.chdir(shop)
        assert cmd_test(None) == 0
        out = capsys.readouterr()
        assert "ERROR" not in out.out + out.err

    def test_the_parts_load_what_they_use_and_not_the_overview(self, shop):
        tax = load_dependency_modules(
            _module(shop, "shop/tax.lob"), shop, kit)
        assert [m.title for m in tax] == ["Shop Prices"]
        overview = load_dependency_modules(
            _module(shop, "shop.lob"), shop, kit)
        assert overview == []

    def test_every_listing_is_in_the_graph(self, shop):
        graph = build_package(shop)
        assert sorted(n.address for n in
                      graph.children("shop", EdgeKind.IMPORTS)
                      ) == ["shop/prices", "shop/tax"]
        assert [n.address for n in
                graph.children("shop/prices", EdgeKind.IMPORTS)] == ["shop"]


class TestWhenUseCannotBeDetermined:
    """Rule 6. TypeScript's and Haskell's reference extraction is not
    complete (calls only; lowercase names only), so their kits do not
    claim it, and the address tree decides: a listing of a descendant is
    a citation and any other listing is loaded."""

    def test_the_kits_say_which_they_are(self):
        from notlob.bindings.haskell import kit as haskell
        from notlob.bindings.typescript import kit as typescript
        assert kit.complete_references
        assert not typescript.complete_references
        assert not haskell.complete_references

    def test_a_listing_of_a_descendant_is_a_citation(self, shop):
        from notlob.bindings.typescript import kit as typescript
        overview = load_dependency_modules(
            _module(shop, "shop.lob"), shop, typescript)
        assert overview == []

    def test_a_listing_of_an_ancestor_or_a_sibling_is_loaded(self, shop):
        from notlob.bindings.typescript import kit as typescript
        tax = load_dependency_modules(
            _module(shop, "shop/tax.lob"), shop, typescript)
        assert [m.title for m in tax] == ["Shop", "Shop Prices"]


class TestTestsSectionUsesAreSeen:
    """Found with this bug: a multi-line `#Tests` group's node code was not
    parseable, so it contributed no `USES` edges, and a module used only
    from there looked unused."""

    def test_a_multi_line_group_makes_uses_edges(self, tmp_path):
        root = _project(tmp_path, {
            "lib.lob": "#Lib\n\n    def f() -> int:\n        return 1\n",
            "user.lob": ("#User\n\nChecks #Lib.\n\n"
                         "---\n\n#Tests\n\n##checks\n"
                         "    f() == 1\n    f() + 1 == 2\n\n"
                         "#References\n    #Lib\n"),
        })
        graph = build_package(
            root, kit.extract_symbols, call_extractor=kit.extract_calls)
        assert any(
            e.kind == EdgeKind.USES and e.source == "user#Tests#checks"
            and e.target == "lib#f"
            for e in graph._edges
        )

    def test_the_import_is_not_reported_unused(self, tmp_path):
        from notlob.check import check_imports
        root = _project(tmp_path, {
            "lib.lob": "#Lib\n\n    def f() -> int:\n        return 1\n",
            "user.lob": ("#User\n\n    X = 1\n\n"
                         "---\n\n#Tests\n\n##checks\n"
                         "    f() == 1\n    f() + 1 == 2\n\n"
                         "#References\n    #Lib\n"),
        })
        graph = build_package(
            root, kit.extract_symbols, call_extractor=kit.extract_calls)
        assert [f for f in check_imports(graph)
                if "User" in f.message] == []


class TestARealCycleIsAnError:
    def test_the_same_listings_with_one_side_a_citation_are_fine(
        self, cycle,
    ):
        """Control: Ping lists Pong and uses it; Pong lists Ping but only
        cites it."""
        (cycle / "pong.lob").write_text(
            "#Pong\n\nCites #Ping.\n\n"
            "    def pong_value() -> int:\n        return 2\n\n"
            "---\n\n#References\n    #Ping\n", encoding="utf-8")
        loaded = load_dependency_modules(
            _module(cycle, "ping.lob"), cycle, kit)
        assert [m.title for m in loaded] == ["Pong"]

    def test_it_is_reported_by_name_not_as_a_name_error(
        self, cycle, monkeypatch, capsys,
    ):
        monkeypatch.chdir(cycle)
        assert cmd_test(cycle / "ping.lob") != 0
        err = capsys.readouterr().err
        assert "circular" in err.lower()
        assert "ping" in err and "pong" in err
        assert "NameError" not in err
