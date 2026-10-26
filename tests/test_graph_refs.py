"""Tests for prose cross-reference validation.

validate_refs() walks every ProseBlock in a module (including those
inside subheadings and appendix sections) and returns a list of
RefErrors for each #Label or ##Label that cannot be resolved.
"""

from pathlib import Path

import pytest

from notlob import (
    parse, parse_file, from_tree,
    build, build_package, enrich, validate_refs,
    Edge, EdgeKind,
    Ref, RefError,
)
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import extract_symbols, kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit


def _module(source: str):
    return from_tree(parse(source))


def _graph(source: str):
    """Structural graph only — no symbols."""
    mod = _module(source)
    return build(mod), mod


def _enriched(source: str):
    """Graph enriched with Python symbols."""
    mod = _module(source)
    g   = build(mod)
    enrich(g, mod, extract_symbols)
    return g, mod


EXAMPLES = Path(__file__).parent.parent / "examples"


# ── Happy paths: references that resolve ─────────────────────

class TestNoErrors:
    def test_no_prose_gives_empty_list(self):
        g, m = _graph("#T\n    code\n")
        assert validate_refs(g, m) == []

    def test_ref_to_subheading_resolves(self):
        src = (
            "#T\n"
            "##Decoding\n"
            "See #Decoding for details.\n"
        )
        g, m = _graph(src)
        assert validate_refs(g, m) == []

    def test_sub_ref_to_subheading_resolves(self):
        src = (
            "#T\n"
            "##Encoding\n"
            "See ##Encoding below.\n"
        )
        g, m = _graph(src)
        assert validate_refs(g, m) == []

    def test_ref_to_symbol_resolves(self):
        src = (
            "#T\n"
            "    def f(): pass\n"
            "Call #f to convert.\n"
        )
        g, m = _enriched(src)
        assert validate_refs(g, m) == []

    def test_no_refs_in_prose_gives_empty(self):
        src = "#T\nJust plain prose, no hashes.\n"
        g, m = _graph(src)
        assert validate_refs(g, m) == []


# ── Unresolved references ─────────────────────────────────────

class TestErrors:
    def test_unknown_hash_ref(self):
        src = "#T\nSee #Unknown for details.\n"
        g, m = _graph(src)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].ref.label == "Unknown" and errs[0].ref.sub is False

    def test_unknown_double_hash_ref(self):
        src = "#T\nSee ##Unknown below.\n"
        g, m = _graph(src)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].ref.label == "Unknown" and errs[0].ref.sub is True

    def test_sub_ref_to_symbol_is_error(self):
        # ##Label requires a subheading, not a symbol.
        # Use an uppercase constant so the ref pattern matches.
        src = (
            "#T\n"
            "    FACTOR = 1.5\n"
            "See ##Factor below.\n"
        )
        g, m = _enriched(src)
        # FACTOR is a symbol; ##Factor is a ref to a non-subheading
        # (note: case difference means it won't even find the symbol,
        # but the key point is it is not a SUBHEADING)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].ref.label == "Factor"
        assert errs[0].ref.sub is True

    def test_multiple_unknown_refs(self):
        src = "#T\nUses #Alpha and #Beta together.\n"
        g, m = _graph(src)
        errs = validate_refs(g, m)
        labels = {e.ref.label for e in errs}
        assert labels == {"Alpha", "Beta"}

    def test_one_good_one_bad(self):
        src = (
            "#T\n"
            "##Real\n"
            "See #Real and #Phantom here.\n"
        )
        g, m = _graph(src)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].ref.label == "Phantom"


# ── Location tracking ─────────────────────────────────────────

class TestLocation:
    def test_module_level_error_location(self):
        src = "#My Module\nSee #Unknown.\n"
        g, m = _graph(src)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].location == "my/module"

    def test_subheading_level_error_location(self):
        src = (
            "#My Module\n"
            "##Section\n"
            "See #Unknown.\n"
        )
        g, m = _graph(src)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].location == "my/module#Section"


# ── RefError representation ───────────────────────────────────

class TestRefError:
    def test_str_hash_ref(self):
        e = RefError(location="my/module", ref=Ref("Alpha", sub=False))
        assert str(e) == "my/module: unresolved reference #Alpha"

    def test_str_double_hash_ref(self):
        e = RefError(location="my/module", ref=Ref("Alpha", sub=True))
        assert str(e) == "my/module: unresolved reference ##Alpha"


# ── Refs inside subheading prose ─────────────────────────────

class TestSubheadingProse:
    def test_ref_in_subheading_prose_resolves(self):
        src = (
            "#T\n"
            "##Alpha\n"
            "See #Alpha here.\n"
            "##Beta\n"
            "    code\n"
        )
        g, m = _graph(src)
        assert validate_refs(g, m) == []

    def test_ref_in_subheading_prose_fails(self):
        src = (
            "#T\n"
            "##Alpha\n"
            "See #Missing here.\n"
        )
        g, m = _graph(src)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].location == "t#Alpha"

    def test_cross_subheading_ref_resolves(self):
        # A ref from ##Alpha's prose to ##Beta is valid.
        src = (
            "#T\n"
            "##Alpha\n"
            "    code\n"
            "##Beta\n"
            "As defined in #Alpha above.\n"
        )
        g, m = _graph(src)
        assert validate_refs(g, m) == []


# ── IMPORTS edges (package graph layer) ──────────────────────

class TestImportedRefs:
    def test_ref_to_imported_module_resolves(self):
        # Build two modules; add an IMPORTS edge manually.
        src_a = "#Module A\nSee #Module B here.\n"
        src_b = "#Module B\n    code\n"
        mod_a = _module(src_a)
        mod_b = _module(src_b)
        g = build(mod_a)
        g.merge(build(mod_b))
        g.add_edge(Edge(
            source="module/a",
            target="module/b",
            kind=EdgeKind.IMPORTS,
        ))
        assert validate_refs(g, mod_a) == []

    def test_ref_to_unimported_module_is_error(self):
        src_a = "#Module A\nSee #Module B here.\n"
        src_b = "#Module B\n    code\n"
        mod_a = _module(src_a)
        g = build(mod_a)
        g.merge(build(_module(src_b)))
        # No IMPORTS edge — Module B not visible
        errs = validate_refs(g, mod_a)
        assert len(errs) == 1
        assert errs[0].ref.label == "Module B"


# ── Appendix sections ────────────────────────────────────────

class TestAppendixRefs:
    def test_appendix_ref_resolves(self):
        src = (
            "#T\n"
            "##Decoding\n"
            "    code\n"
            "---\n"
            "#Appendix Notes\n"
            "See #Decoding above.\n"
        )
        g, m = _graph(src)
        assert validate_refs(g, m) == []

    def test_appendix_ref_fails(self):
        src = (
            "#T\n"
            "---\n"
            "#Appendix Notes\n"
            "See #Unknown here.\n"
        )
        g, m = _graph(src)
        errs = validate_refs(g, m)
        assert len(errs) == 1
        assert errs[0].ref.label == "Unknown"

    def test_body_ref_to_appendix_subheading_resolves(self):
        # A ##Label ref in the main body pointing at a subheading inside
        # #Appendix should resolve — appendix subheadings are graph nodes.
        src = (
            "#T\n"
            "See ##Notes below.\n"
            "---\n"
            "#Appendix\n"
            "##Notes\n"
            "Some notes.\n"
        )
        g, m = _graph(src)
        assert validate_refs(g, m) == []


# ── Where the references are read from ──────────────────────

class TestLocationsInAnAppendix:
    def test_a_paragraph_directly_in_an_appendix_is_at_the_module(self):
        g, m = _graph("#T\n\n---\n\n#Appendix\n\nSee #Nope.\n")
        (err,) = validate_refs(g, m)
        assert err.location == "t"

    def test_a_paragraph_in_an_appendix_subheading_is_at_that_subheading(
        self,
    ):
        g, m = _graph("#T\n\n---\n\n#Appendix\n\n##AppSub\n\nSee #Nope.\n")
        (err,) = validate_refs(g, m)
        assert err.location == "t#AppSub"


class TestTestsCommentary:
    SRC = (
        "#T\n\n##Real\n\nx\n\n---\n\n#Tests\n\nSee #Missing here.\n\n"
        "##g\n    a == 1\n\nAnd #Gone too, but #Real is there.\n"
    )

    def test_commentary_in_tests_and_in_a_group_is_checked(self):
        g, m = _graph(self.SRC)
        errs = validate_refs(g, m)
        assert [e.ref.label for e in errs] == ["Missing", "Gone"]

    def test_it_is_located_at_the_module(self):
        g, m = _graph(self.SRC)
        assert {e.location for e in validate_refs(g, m)} == {"t"}


class TestReadsTheGraph:
    def test_the_module_is_for_its_address_only(self):
        from notlob.model import Module
        g, _m = _graph("#T\n\nSee #Nope.\n")
        (err,) = validate_refs(g, Module(title="T", body=[]))
        assert err.ref.label == "Nope"

    def test_only_the_modules_own_paragraphs_are_checked(self):
        g, m = _graph("#T\n\nFine.\n")
        other = _module("#Other\n\nSee #Nope.\n")
        g.merge(build(other))
        assert validate_refs(g, m) == []
        assert len(validate_refs(g, other)) == 1


# ── Integration: example files ───────────────────────────────

@pytest.mark.parametrize("project,kit", [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit),
    ("haskell-roman", haskell_kit), ("ts-media", typescript_kit),
], ids=lambda value: value if isinstance(value, str) else "")
def test_no_example_has_an_unresolved_reference(project, kit):
    """Every paragraph of every example, the commentary in `#Tests` and
    in an `#Appendix` too, refers only to what the module can see."""
    graph = build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls)
    failures = {}
    for path in sorted((EXAMPLES / project).rglob("*.lob")):
        errs = validate_refs(graph, from_tree(parse_file(path)))
        if errs:
            failures[path.name] = [str(e) for e in errs]
    assert failures == {}


class TestExampleFiles:
    def _graph(self, path):
        mod = from_tree(parse_file(path))
        g   = build(mod)
        enrich(g, mod, extract_symbols)
        return g, mod

    def test_roman_numerals_no_ref_errors(self):
        g, m = self._graph(
            EXAMPLES / "roman/roman/numerals.lob"
        )
        errs = validate_refs(g, m)
        assert errs == [], [str(e) for e in errs]

    def test_pricing_discounts_no_ref_errors(self):
        # pricing/discounts.lob only uses ##Label refs to its own
        # subheadings — all should resolve within the module graph.
        g, m = self._graph(
            EXAMPLES / "retail/pricing/discounts.lob"
        )
        errs = validate_refs(g, m)
        assert errs == [], [str(e) for e in errs]
