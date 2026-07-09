"""Tests for the Haskell symbol extractor.

extract_symbols maps a list of indented code lines (as stored in
CodeBlock.lines) to a list of SymbolInfo objects.  Each carries the
top-level defined name and its dedented source text.

Conventions
-----------
Input lines use 4-space indentation throughout (mirroring the .lob
source format).  The extractor dedents before processing, so the
column-0 invariant is established inside the function.
"""

from notlob.bindings.haskell import extract_symbols


def _names(lines):
    """Helper: just the names from extract_symbols output."""
    return [s.name for s in extract_symbols(lines)]


def _syms(lines):
    """Helper: full SymbolInfo list from extract_symbols."""
    return extract_symbols(lines)


# ── Type signatures ──────────────────────────────────────────

class TestTypeSig:
    def test_type_sig_alone(self):
        assert _names(["    f :: Int -> Int"]) == ["f"]

    def test_type_sig_underscore_start(self):
        assert _names(["    _unused :: Bool"]) == ["_unused"]

    def test_type_sig_with_apostrophe(self):
        # f' is a valid Haskell name
        assert _names(["    f' :: a -> a"]) == ["f'"]

    def test_type_sig_multiword(self):
        # Type can span a long line; name is still just the identifier
        assert _names(
            ["    applyDiscount :: Decimal -> Decimal -> Decimal"]
        ) == ["applyDiscount"]


# ── Function definitions ──────────────────────────────────────

class TestFunctionDef:
    def test_simple_def(self):
        assert _names(["    f x = x + 1"]) == ["f"]

    def test_def_no_args(self):
        assert _names(["    answer = 42"]) == ["answer"]

    def test_def_with_pattern(self):
        assert _names(["    f [] = 0"]) == ["f"]

    def test_two_functions(self):
        lines = [
            "    toRoman :: Int -> String",
            "    toRoman 0 = \"\"",
            "",
            "    fromRoman :: String -> Int",
            "    fromRoman [] = 0",
        ]
        assert _names(lines) == ["toRoman", "fromRoman"]

    def test_function_without_type_sig(self):
        assert _names(["    go n = n + 1"]) == ["go"]

    def test_guard_on_same_line(self):
        # Guard with '=' in rest
        assert _names(["    f x | x > 0 = x"]) == ["f"]


# ── Grouping: type sig + equations → one SymbolInfo ──────────

class TestGrouping:
    def test_sig_and_single_equation(self):
        lines = [
            "    toRoman :: Int -> String",
            "    toRoman 0 = \"\"",
        ]
        syms = _syms(lines)
        assert len(syms) == 1
        assert syms[0].name == "toRoman"

    def test_sig_and_multiple_equations(self):
        lines = [
            "    f :: Int -> Int",
            "    f 0 = 1",
            "    f n = n * 2",
        ]
        syms = _syms(lines)
        assert len(syms) == 1
        assert syms[0].name == "f"

    def test_multiple_equations_no_sig(self):
        lines = [
            "    fib 0 = 0",
            "    fib 1 = 1",
            "    fib n = fib (n-1) + fib (n-2)",
        ]
        syms = _syms(lines)
        assert len(syms) == 1
        assert syms[0].name == "fib"

    def test_blank_line_separates_definitions(self):
        lines = [
            "    f :: Int -> Int",
            "    f x = x + 1",
            "",
            "    g :: Int -> Int",
            "    g x = x * 2",
        ]
        syms = _syms(lines)
        assert len(syms) == 2
        assert syms[0].name == "f"
        assert syms[1].name == "g"

    def test_multiple_blanks_between_defs(self):
        lines = [
            "    f x = x",
            "",
            "",
            "    g x = x",
        ]
        assert _names(lines) == ["f", "g"]


# ── Source field content ──────────────────────────────────────

class TestSource:
    def test_type_sig_in_source(self):
        lines = [
            "    toRoman :: Int -> String",
            "    toRoman 0 = \"\"",
            "    toRoman n = n",
        ]
        sym = _syms(lines)[0]
        assert "toRoman :: Int -> String" in sym.source
        assert "toRoman 0" in sym.source
        assert "toRoman n" in sym.source

    def test_source_is_dedented(self):
        # The 4-space indent is stripped; source is flush-left
        lines = ["    answer = 42"]
        sym = _syms(lines)[0]
        assert sym.source == "answer = 42"

    def test_where_clause_in_source(self):
        lines = [
            "    toRoman :: Int -> String",
            "    toRoman n = snd pair",
            "        where pair = head $ filter ((<=n) . fst) nums",
        ]
        sym = _syms(lines)[0]
        assert "where" in sym.source
        assert "pair" in sym.source

    def test_two_functions_separate_sources(self):
        lines = [
            "    f x = x + 1",
            "",
            "    g x = x * 2",
        ]
        syms = _syms(lines)
        assert syms[0].source == "f x = x + 1"
        assert syms[1].source == "g x = x * 2"

    def test_multiline_data_source(self):
        lines = [
            "    data Color",
            "        = Red",
            "        | Green",
            "        | Blue",
        ]
        sym = _syms(lines)[0]
        assert "Red" in sym.source
        assert "Green" in sym.source
        assert "Blue" in sym.source


# ── Data / type declarations ──────────────────────────────────

class TestDataDeclarations:
    def test_data_single_line(self):
        assert _names(["    data Color = Red | Green | Blue"]) == ["Color"]

    def test_data_multiline(self):
        lines = [
            "    data Color",
            "        = Red",
            "        | Green",
        ]
        assert _names(lines) == ["Color"]

    def test_newtype(self):
        assert _names(["    newtype Name = Name String"]) == ["Name"]

    def test_data_with_deriving(self):
        lines = [
            "    data Color = Red | Green",
            "        deriving (Show, Eq)",
        ]
        syms = _syms(lines)
        assert len(syms) == 1
        assert syms[0].name == "Color"
        assert "deriving" in syms[0].source

    def test_type_alias(self):
        assert _names(["    type Name = String"]) == ["Name"]

    def test_type_alias_parameterised(self):
        assert _names(["    type Map k v = [(k, v)]"]) == ["Map"]


# ── Indented continuations ────────────────────────────────────

class TestContinuations:
    def test_where_clause_not_extracted_separately(self):
        # 'helper' is inside a where clause — not a top-level symbol
        lines = [
            "    f x = helper x",
            "        where helper y = y + 1",
        ]
        assert _names(lines) == ["f"]

    def test_multiline_type_sig_attached(self):
        lines = [
            "    f :: Int",
            "     -> Int",
            "     -> Int",
            "    f x y = x + y",
        ]
        syms = _syms(lines)
        assert len(syms) == 1
        assert syms[0].name == "f"

    def test_let_in_where_not_extracted(self):
        lines = [
            "    f x = result",
            "        where",
            "            result = x * 2",
        ]
        assert _names(lines) == ["f"]


# ── Class declarations ────────────────────────────────────────

class TestClassDeclarations:
    def test_simple_class(self):
        lines = [
            "    class Printable a where",
            "        display :: a -> String",
        ]
        assert _names(lines) == ["Printable"]

    def test_class_with_superclass(self):
        assert _names(
            ["    class Eq a => Ord a where"]
        ) == ["Ord"]

    def test_class_with_tuple_constraint(self):
        assert _names(
            ["    class (Eq a, Show a) => Pretty a where"]
        ) == ["Pretty"]

    def test_class_methods_not_extracted(self):
        # Methods are indented — they must not appear as top-level symbols
        lines = [
            "    class Printable a where",
            "        display :: a -> String",
            "        render  :: a -> String",
        ]
        assert _names(lines) == ["Printable"]


# ── Operator definitions ──────────────────────────────────────

class TestOperators:
    def test_operator_type_sig(self):
        assert _names(["    (+++) :: [a] -> [a] -> [a]"]) == ["+++"]

    def test_operator_definition(self):
        assert _names(["    (+++) xs ys = xs ++ ys"]) == ["+++"]

    def test_operator_sig_and_def_grouped(self):
        lines = [
            "    (>>>) :: (a -> b) -> (b -> c) -> a -> c",
            "    (>>>) f g x = g (f x)",
        ]
        syms = _syms(lines)
        assert len(syms) == 1
        assert syms[0].name == ">>>"

    def test_operator_source_includes_sig(self):
        lines = [
            "    (!!) :: [a] -> Int -> a",
            "    (!!) (x:_)  0 = x",
            "    (!!) (_:xs) n = xs !! (n-1)",
        ]
        sym = _syms(lines)[0]
        assert sym.name == "!!"
        assert "(!!) :: [a]" in sym.source
        assert "(!!) (x:_)" in sym.source


# ── Ignored constructs ────────────────────────────────────────

class TestIgnored:
    def test_instance_not_extracted(self):
        lines = [
            "    instance Show Color where",
            "        show Red = \"Red\"",
        ]
        assert _names(lines) == []

    def test_import_not_extracted(self):
        assert _names(["    import Data.List (sort)"]) == []

    def test_module_not_extracted(self):
        assert _names(["    module Foo where"]) == []

    def test_line_comment_not_extracted(self):
        assert _names(["    -- A comment"]) == []

    def test_pragma_not_extracted(self):
        assert _names(["    {-# LANGUAGE OverloadedStrings #-}"]) == []

    def test_infix_declaration_not_extracted(self):
        assert _names(["    infixl 6 +"]) == []

    def test_deriving_not_extracted(self):
        # standalone deriving (GHC extension)
        assert _names(["    deriving instance Show Foo"]) == []


# ── Edge cases ────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_input(self):
        assert _syms([]) == []

    def test_only_blank_lines(self):
        assert _syms(["", "", ""]) == []

    def test_single_function(self):
        assert _names(["    main = return ()"]) == ["main"]

    def test_definition_at_end_of_block_no_trailing_blank(self):
        # Ensure the last definition is flushed even without a trailing blank
        lines = ["    f x = x", "    g x = x"]
        assert _names(lines) == ["f", "g"]

    def test_mixed_block(self):
        lines = [
            "    numerals :: [(Int, String)]",
            "    numerals = [(1000, \"M\"), (500, \"D\")]",
            "",
            "    toRoman :: Int -> String",
            "    toRoman 0 = \"\"",
            "    toRoman n = snd h ++ toRoman (n - fst h)",
            "        where h = head $ filter ((<=n).fst) numerals",
            "",
            "    data Digit = I | V | X",
        ]
        names = _names(lines)
        assert names == ["numerals", "toRoman", "Digit"]

    def test_only_indented_lines_returns_empty(self):
        # If after dedent all lines are still indented (shouldn't normally
        # happen with a well-formed block), treat conservatively.
        # (In practice dedent removes common prefix, so mixed-indent blocks
        # could hit this.)
        assert _syms(["        x = 1", "            y = 2"]) != []
        # The dedented version would be "x = 1\n    y = 2" — x extracted.
