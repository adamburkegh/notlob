"""Tests for shared binding utilities in notlob.bindings."""

from notlob.bindings import (
    assemble_section, collect_blocks, iter_assertions, parse_source_map,
)
from notlob.model import CodeBlock, Claim, ProseBlock


# ── collect_blocks ───────────────────────────────────────────

class TestCollectBlocks:
    def test_extracts_code_blocks(self):
        body = [
            CodeBlock(lines=["    x = 1"]),
            CodeBlock(lines=["    y = 2"]),
        ]
        result = collect_blocks(body)
        assert result == ["x = 1", "y = 2"]

    def test_skips_non_code(self):
        body = [
            ProseBlock(spans=["some prose"]),
            CodeBlock(lines=["    x = 1"]),
            Claim(sigil="~example", lines=["    x == 1"]),
        ]
        result = collect_blocks(body)
        assert result == ["x = 1"]

    def test_skips_empty_blocks(self):
        body = [CodeBlock(lines=["    ", ""])]
        assert collect_blocks(body) == []

    def test_empty_body(self):
        assert collect_blocks([]) == []

    def test_dedents(self):
        body = [CodeBlock(lines=["    def f():", "        return 1"])]
        result = collect_blocks(body)
        assert "def f():" in result[0]
        assert "    return 1" in result[0]


# ── assemble_section ────────────────────────────────────────

class TestAssembleSection:
    def test_single_block(self):
        result = assemble_section("# mod", ["x = 1"])
        assert result == "# mod\nx = 1"

    def test_multiple_blocks(self):
        result = assemble_section("-- mod", ["x = 1", "y = 2"])
        assert result == "-- mod\nx = 1\n\ny = 2"

    def test_comment_prefix_preserved(self):
        result = assemble_section("// addr", ["code"])
        assert result.startswith("// addr\n")


# ── iter_assertions ──────────────────────────────────────────

class TestIterAssertions:
    def test_simple_mode_yields_per_line(self):
        lines = ["    a == 1", "", "    b == 2"]
        result = list(iter_assertions(lines))
        assert result == [("a == 1", 0), ("b == 2", 2)]

    def test_simple_mode_skips_blanks(self):
        result = list(iter_assertions(["", "  ", "    x"]))
        assert result == [("x", 2)]

    def test_simple_mode_empty(self):
        assert list(iter_assertions([])) == []

    def test_multiline_mode_joins(self):
        def always_complete(text):
            return True
        lines = ["    a", "    b"]
        result = list(iter_assertions(lines, is_complete=always_complete))
        assert [e for e, _ in result] == ["a", "b"]

    def test_multiline_mode_buffers_incomplete(self):
        calls = []
        def complete_on_close(text):
            calls.append(text)
            return text.count("(") == text.count(")")
        lines = ["    f(", "      1)", "    g()"]
        result = list(iter_assertions(lines, is_complete=complete_on_close))
        assert len(result) == 2
        assert result[0] == ("f(\n1)", 0)
        assert result[1] == ("g()", 2)

    def test_multiline_mode_yields_incomplete_at_end(self):
        def never_complete(text):
            return False
        lines = ["    orphan"]
        result = list(iter_assertions(lines, is_complete=never_complete))
        assert result == [("orphan", 0)]


# ── parse_source_map ─────────────────────────────────────────

class TestParseSourceMap:
    def test_python_comments(self):
        src = "import os\n\n# my/mod\nx = 1\ny = 2\n"
        m = parse_source_map(src, comment_prefix="#")
        assert m[4] == "my/mod"
        assert m[5] == "my/mod"
        assert m[1] == "my/mod"

    def test_haskell_comments(self):
        src = "module F where\n\n-- my/mod\nx = 1\n"
        m = parse_source_map(src, comment_prefix="--")
        assert m[4] == "my/mod"
        assert m[1] == "my/mod"

    def test_default_is_hash(self):
        src = "# addr\nx = 1\n"
        m = parse_source_map(src)
        assert m[2] == "addr"

    def test_empty_source(self):
        assert parse_source_map("") == {}

    def test_multiple_sections(self):
        src = "# a\nx = 1\n\n# b\ny = 2\n"
        m = parse_source_map(src)
        assert m[2] == "a"
        assert m[5] == "b"
