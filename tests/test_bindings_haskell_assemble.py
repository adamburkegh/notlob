"""Tests for the Haskell assembler.

All tests are pure Python — no GHC or stack required.

The assembler maps a Module to a standalone Haskell source string.
Key invariants:
  • The output starts with ``module <Name> where``.
  • Haskell import statements from #References appear before code.
  • Lob-ref lines (#Title) are dropped from #References.
  • Code blocks are dedented and separated by blank lines.
  • Location comments (``-- address``) precede each group.
  • assemble() returns '' for a module with no code and no imports.
"""

import textwrap


from notlob.bindings.haskell.assemble import (
    _module_name,
    _haskell_imports,
    assemble,
)
from notlob.model import (
    AppendixSection,
    CodeBlock,
    Module,
    PostText,
    ProseBlock,
    ReferencesSection,
    Subheading,
)


# ── helpers ───────────────────────────────────────────────────

def _module(title, body=None, refs=None):
    """Build a minimal Module for tests."""
    body = body or []
    post = None
    if refs is not None:
        post = PostText(sections=[
            ReferencesSection(lines=refs)
        ])
    return Module(title=title, body=body, post_text=post)


def _code(text):
    """Build a CodeBlock from an unindented text string."""
    lines = ["    " + line for line in text.splitlines()]
    return CodeBlock(lines=lines)


# ── _module_name ──────────────────────────────────────────────

class TestModuleName:
    def test_two_words(self):
        assert _module_name("Roman Numerals") == "RomanNumerals"

    def test_single_word(self):
        assert _module_name("Primes") == "Primes"

    def test_three_words(self):
        assert _module_name("Pricing Discounts Tax") == "PricingDiscountsTax"

    def test_hyphen_separator(self):
        assert _module_name("my-module") == "MyModule"

    def test_already_camel(self):
        # Capitalise-each-word still works: "FooBar" → "Foobar"
        # (title-casing, not camel-preserving)
        assert _module_name("FooBar") == "Foobar"

    def test_lowercase_title(self):
        assert _module_name("hello world") == "HelloWorld"

    def test_multiple_spaces(self):
        assert _module_name("a  b") == "AB"

    def test_numbers_preserved(self):
        assert _module_name("Chapter 2") == "Chapter2"

    def test_leading_trailing_spaces(self):
        # Splitting on non-alnum removes leading/trailing
        assert _module_name("  Roman  ") == "Roman"


# ── _haskell_imports ──────────────────────────────────────────

class TestHaskellImports:
    def test_drops_lob_refs(self):
        lines = ["    #Roman Numerals", "    import Data.List (sort)"]
        assert _haskell_imports(lines) == ["import Data.List (sort)"]

    def test_drops_blank_lines(self):
        lines = ["    import Data.List (sort)", "", "    import Data.Char"]
        assert _haskell_imports(lines) == [
            "import Data.List (sort)",
            "import Data.Char",
        ]

    def test_strips_indent(self):
        lines = ["        import Data.Map.Strict (Map)"]
        assert _haskell_imports(lines) == ["import Data.Map.Strict (Map)"]

    def test_empty_input(self):
        assert _haskell_imports([]) == []

    def test_only_lob_refs(self):
        assert _haskell_imports(["    #Foo", "    #Bar"]) == []

    def test_mixed(self):
        lines = [
            "    #Roman Numerals",
            "    import Data.List (sort)",
            "",
            "    #Pricing",
            "    import Data.Map (Map)",
        ]
        assert _haskell_imports(lines) == [
            "import Data.List (sort)",
            "import Data.Map (Map)",
        ]


# ── assemble — module header ──────────────────────────────────

class TestModuleHeader:
    def test_header_present(self):
        m = _module("Roman Numerals", body=[_code("f x = x")])
        src = assemble(m)
        assert src.startswith("module RomanNumerals where")

    def test_empty_module_returns_empty(self):
        m = _module("Roman Numerals")
        assert assemble(m) == ""

    def test_module_with_only_prose_returns_empty(self):
        m = _module("Roman Numerals", body=[ProseBlock(spans=["some text"])])
        assert assemble(m) == ""


# ── assemble — imports ────────────────────────────────────────

class TestAssembleImports:
    def test_imports_present_when_refs_exist(self):
        m = _module(
            "Numerals",
            body=[_code("f x = x")],
            refs=["    import Data.List (sort)"],
        )
        src = assemble(m)
        assert "import Data.List (sort)" in src

    def test_imports_before_code(self):
        m = _module(
            "Numerals",
            body=[_code("answer = 42")],
            refs=["    import Data.List (sort)"],
        )
        src = assemble(m)
        import_pos = src.index("import Data.List")
        code_pos   = src.index("answer = 42")
        assert import_pos < code_pos

    def test_lob_refs_excluded(self):
        m = _module(
            "Numerals",
            body=[_code("f x = x")],
            refs=["    #Roman Numerals", "    import Data.Char (toLower)"],
        )
        src = assemble(m)
        assert "#Roman Numerals" not in src
        assert "import Data.Char (toLower)" in src

    def test_no_refs_section(self):
        m = _module("Numerals", body=[_code("f x = x")])
        src = assemble(m)
        assert "import" not in src

    def test_module_with_only_imports(self):
        # No code blocks, but imports present — still generates header
        m = _module("Numerals", refs=["    import Data.List (sort)"])
        src = assemble(m)
        assert src.startswith("module Numerals where")
        assert "import Data.List (sort)" in src


# ── assemble — code blocks ────────────────────────────────────

class TestAssembleCode:
    def test_single_block(self):
        m = _module("Numerals", body=[_code("answer = 42")])
        src = assemble(m)
        assert "answer = 42" in src

    def test_block_is_dedented(self):
        # Code block has 4-space indent (lob format); should be stripped
        m = _module("Numerals", body=[_code("f x = x + 1")])
        src = assemble(m)
        assert "    f x = x + 1" not in src  # not double-indented
        assert "f x = x + 1" in src

    def test_location_comment_present(self):
        m = _module("Roman Numerals", body=[_code("f x = x")])
        src = assemble(m)
        assert "-- roman/numerals" in src

    def test_two_blocks_separated_by_blank(self):
        body = [_code("f x = x"), _code("g x = x")]
        m = _module("Numerals", body=body)
        src = assemble(m)
        assert "\n\n" in src

    def test_multiline_block(self):
        code = "toRoman :: Int -> String\ntoRoman 0 = \"\"\ntoRoman n = \"I\""
        m = _module("Numerals", body=[_code(code)])
        src = assemble(m)
        assert "toRoman :: Int -> String" in src
        assert 'toRoman 0 = ""' in src

    def test_prose_blocks_ignored(self):
        body = [ProseBlock(spans=["some text"]), _code("f x = x")]
        m = _module("Numerals", body=body)
        src = assemble(m)
        assert "some text" not in src
        assert "f x = x" in src


# ── assemble — subheadings ────────────────────────────────────

class TestAssembleSubheadings:
    def test_subheading_code_included(self):
        sub = Subheading(title="Helpers", body=[_code("helper x = x + 1")])
        m = _module("Numerals", body=[sub])
        src = assemble(m)
        assert "helper x = x + 1" in src

    def test_subheading_location_comment(self):
        sub = Subheading(title="Helpers", body=[_code("helper x = x + 1")])
        m = _module("Numerals", body=[sub])
        src = assemble(m)
        assert "-- numerals#Helpers" in src

    def test_module_then_subheading_order(self):
        body = [
            _code("topLevel = 1"),
            Subheading(title="Sub", body=[_code("sub = 2")]),
        ]
        m = _module("Numerals", body=body)
        src = assemble(m)
        top_pos = src.index("topLevel = 1")
        sub_pos = src.index("sub = 2")
        assert top_pos < sub_pos

    def test_empty_subheading_not_included(self):
        sub = Subheading(title="Empty", body=[])
        body = [_code("f x = x"), sub]
        m = _module("Numerals", body=body)
        src = assemble(m)
        assert "Empty" not in src


# ── #Appendix code ───────────────────────────────────────────

class TestAppendixCode:
    def test_appendix_code_included(self):
        m = Module(
            title="Numerals",
            body=[_code("f x = x")],
            post_text=PostText(sections=[
                AppendixSection(title="#Appendix", body=[
                    _code("fixtureHelper = 42"),
                ]),
            ]),
        )
        src = assemble(m)
        assert "fixtureHelper = 42" in src

    def test_appendix_location_comment(self):
        m = Module(
            title="Numerals",
            body=[_code("f x = x")],
            post_text=PostText(sections=[
                AppendixSection(title="#Appendix", body=[_code("y = 2")]),
            ]),
        )
        src = assemble(m)
        assert "-- numerals#Appendix" in src

    def test_appendix_subheading_uses_module_level_address(self):
        sub = Subheading(title="Glossary", body=[_code("y = 2")])
        m = Module(
            title="Numerals",
            body=[_code("f x = x")],
            post_text=PostText(sections=[
                AppendixSection(title="#Appendix", body=[sub]),
            ]),
        )
        src = assemble(m)
        assert "-- numerals#Glossary" in src

    def test_no_appendix_no_change(self):
        m = _module("Numerals", body=[_code("f x = x")])
        assert assemble(m) == "module Numerals where\n\n-- numerals\nf x = x"


# ── assemble — full example ───────────────────────────────────

class TestAssembleFullExample:
    def test_roman_numerals_shape(self):
        """Integration: a realistic module assembles correctly."""
        refs = [
            "    #Roman Numerals",
            "    import Data.List (sortBy)",
        ]
        code = textwrap.dedent("""\
            numerals :: [(Int, String)]
            numerals = [(1000, "M"), (500, "D"), (100, "C")]

            toRoman :: Int -> String
            toRoman 0 = ""
            toRoman n = snd h ++ toRoman (n - fst h)
              where h = head $ filter ((<=n).fst) numerals
        """).strip()

        m = _module(
            "Roman Numerals",
            body=[_code(code)],
            refs=refs,
        )
        src = assemble(m)

        assert src.startswith("module RomanNumerals where")
        assert "import Data.List (sortBy)" in src
        assert "#Roman Numerals" not in src
        assert "numerals :: [(Int, String)]" in src
        assert "toRoman :: Int -> String" in src
        assert "-- roman/numerals" in src
