"""Tests for notlob.weave.markdown — Markdown renderer.

weave_markdown(module, language) converts a parsed Module to a
GitHub-flavoured Markdown string.  These tests verify:

- each model type renders to the expected Markdown fragment
- inline Refs resolve to anchor links or inline code as appropriate
- post-text sections are included or omitted correctly
- the integration with example .lob files produces sensible output
"""

from pathlib import Path

import pytest

from notlob import parse, from_tree, parse_file
from notlob.weave import weave_markdown


EXAMPLES = Path(__file__).parent.parent / "examples"


def md(source: str, language: str = "python") -> str:
    """Parse *source* and render it as Markdown."""
    return weave_markdown(from_tree(parse(source)), language)


# ── Title ────────────────────────────────────────────────────

class TestTitle:
    def test_h1(self):
        out = md("#My Module\n")
        assert out.startswith("# My Module")

    def test_title_only(self):
        out = md("#T\n")
        assert out.strip() == "# T"


# ── ProseBlock ───────────────────────────────────────────────

class TestProseBlock:
    def test_simple_prose(self):
        out = md("#T\nSome prose.\n")
        assert "Some prose." in out

    def test_multiline_prose_preserves_breaks(self):
        out = md("#T\nLine one.\nLine two.\n")
        assert "Line one." in out
        assert "Line two." in out

    def test_inline_ref_becomes_inline_code(self):
        # #Label (sub=False) → `Label`
        out = md("#T\nSee #Foo Bar for details.\n")
        assert "`Foo Bar`" in out

    def test_inline_subref_becomes_anchor_link(self):
        # ##Label (sub=True) → [Label](#anchor)
        out = md("#T\nSee ##Word Frequencies below.\n")
        assert "[Word Frequencies](#word-frequencies)" in out

    def test_anchor_lowercases_label(self):
        out = md("#T\nAs in ##Stacking Discounts.\n")
        assert "#stacking-discounts" in out

    def test_anchor_replaces_spaces_with_hyphens(self):
        out = md("#T\nSee ##Round Trip property.\n")
        assert "#round-trip" in out

    def test_blank_separates_paragraphs(self):
        out = md("#T\nFirst.\n\nSecond.\n")
        assert "First." in out
        assert "Second." in out
        # Both paragraphs appear, with at least a blank line between
        idx_first  = out.index("First.")
        idx_second = out.index("Second.")
        between = out[idx_first + len("First."):idx_second]
        assert "\n\n" in between


# ── CodeBlock ────────────────────────────────────────────────

class TestCodeBlock:
    def test_fenced_block(self):
        out = md("#T\n    x = 1\n")
        assert "```python" in out
        assert "x = 1" in out
        assert "```" in out

    def test_language_tag_used(self):
        out = md("#T\n    x = 1\n", language="haskell")
        assert "```haskell" in out

    def test_dedented(self):
        out = md("#T\n    def f():\n        pass\n")
        assert "def f():" in out
        assert "    pass" in out     # inner indent preserved
        assert "```python\ndef f():" in out

    def test_blank_lines_within_block_preserved(self):
        out = md("#T\n    x = 1\n\n    y = 2\n")
        assert "x = 1" in out
        assert "y = 2" in out
        # blank line preserved inside the code fence
        code_start = out.index("```python")
        code_end   = out.index("```", code_start + 3)
        code_body  = out[code_start:code_end]
        assert "\n\n" in code_body


# ── Claim ────────────────────────────────────────────────────

class TestClaim:
    def test_example_label(self):
        out = md("#T\n~example\n    x == 1\n")
        assert "**Example:**" in out

    def test_property_label(self):
        out = md("#T\n~property\n    x > 0\n")
        assert "**Property:**" in out

    def test_run_omitted(self):
        out = md("#T\n~run\n    print('hi')\n")
        assert "~run" not in out
        assert "print" not in out

    def test_named_property_label(self):
        # A named ~property doesn't match the _SIGIL_LABELS keys
        # exactly, so it renders via the generic capitalised fallback.
        out = md("#T\n~property commutativity\n    x + y == y + x\n")
        assert "**Property commutativity:**" in out

    def test_claim_code_fenced(self):
        out = md("#T\n~example\n    f(1) == 2\n")
        assert "```python" in out
        assert "f(1) == 2" in out

    def test_claim_code_dedented(self):
        out = md("#T\n~example\n    f(1) == 2\n    f(2) == 4\n")
        assert "```python\nf(1) == 2\nf(2) == 4\n```" in out


# ── Subheading ───────────────────────────────────────────────

class TestSubheading:
    def test_subheading_h2(self):
        out = md("#T\n##Section\n    code\n")
        assert "## Section" in out

    def test_subheading_content_rendered(self):
        src = (
            "#T\n"
            "##Section\n"
            "Prose.\n"
            "    code\n"
            "~example\n"
            "    x == 1\n"
        )
        out = md(src)
        assert "## Section" in out
        assert "Prose." in out
        assert "```python" in out
        assert "**Example:**" in out

    def test_two_subheadings(self):
        out = md("#T\n##A\n    a\n##B\n    b\n")
        assert "## A" in out
        assert "## B" in out
        assert out.index("## A") < out.index("## B")


# ── Post-text: Tests section ─────────────────────────────────

class TestPostTests:
    def test_tests_section_heading(self):
        src = "#T\n---\n#Tests\n##g\n    x == 1\n"
        out = md(src)
        assert "## Tests" in out

    def test_test_group_subheading(self):
        src = "#T\n---\n#Tests\n##encoding\n    f(1) == 'I'\n"
        out = md(src)
        assert "### encoding" in out

    def test_test_group_code_fenced(self):
        src = "#T\n---\n#Tests\n##g\n    x == 1\n"
        out = md(src)
        assert "```python" in out
        assert "x == 1" in out

    def test_empty_tests_section_omitted(self):
        src = "#T\n---\n#Tests\n"
        out = md(src)
        assert "## Tests" not in out

    def test_multiple_test_groups(self):
        src = (
            "#T\n---\n#Tests\n"
            "##alpha\n    a == 1\n"
            "##beta\n    b == 2\n"
        )
        out = md(src)
        assert "### alpha" in out
        assert "### beta" in out
        assert out.index("### alpha") < out.index("### beta")


# ── Post-text: machinery sections omitted ────────────────────

class TestPostMachinery:
    def test_binding_section_omitted(self):
        src = "#T\n---\n#Binding\n    ~language python\n"
        out = md(src)
        assert "#Binding" not in out
        assert "~language" not in out

    def test_references_section_omitted(self):
        src = "#T\n---\n#References\n    from decimal import Decimal\n"
        out = md(src)
        assert "#References" not in out
        assert "import Decimal" not in out

    def test_separator_not_in_output(self):
        src = "#T\n---\n#References\n    import x\n"
        out = md(src)
        assert "---" not in out


# ── Post-text: Appendix section ──────────────────────────────

class TestPostAppendix:
    def test_appendix_rendered_as_h2(self):
        src = "#T\n---\n#Appendix: Notes\nSome notes.\n"
        out = md(src)
        assert "## Notes" in out
        assert "Some notes." in out

    def test_appendix_strips_prefix(self):
        src = "#T\n---\n#Appendix: Background\n    code\n"
        out = md(src)
        assert "## Background" in out
        assert "Appendix:" not in out


# ── Document structure ────────────────────────────────────────

class TestDocumentStructure:
    def test_ends_with_newline(self):
        out = md("#T\n")
        assert out.endswith("\n")

    def test_parts_separated_by_blank_lines(self):
        src = (
            "#T\n"
            "Prose.\n"
            "    code\n"
            "~example\n"
            "    x == 1\n"
        )
        out = md(src)
        # Verify double newlines appear between elements
        assert "\n\n" in out

    def test_title_comes_first(self):
        out = md("#T\nProse.\n")
        assert out.startswith("# T")


# ── Integration: example files ───────────────────────────────

class TestExampleFiles:
    def test_roman_numerals_has_title(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        out = weave_markdown(m)
        assert out.startswith("# Roman Numerals")

    def test_roman_numerals_has_subheadings(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        out = weave_markdown(m)
        assert "## Decoding" in out
        assert "## Round-Trip" in out

    def test_roman_numerals_has_code(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        out = weave_markdown(m)
        assert "```python" in out
        assert "to_roman" in out

    def test_roman_numerals_has_examples(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        out = weave_markdown(m)
        assert "**Example:**" in out

    def test_roman_numerals_has_property(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        out = weave_markdown(m)
        assert "**Property:**" in out

    def test_roman_numerals_has_tests(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        out = weave_markdown(m)
        assert "## Tests" in out
        assert "### encoding" in out

    def test_roman_references_omitted(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        out = weave_markdown(m)
        assert "#References" not in out

    def test_discounts_subref_rendered(self):
        m = from_tree(
            parse_file(EXAMPLES / "retail/pricing/discounts.lob")
        )
        out = weave_markdown(m)
        # ##Stacking Discounts inline ref in prose
        assert "[Stacking Discounts](#stacking-discounts)" in out

    def test_discounts_binding_omitted(self):
        m = from_tree(
            parse_file(EXAMPLES / "retail/pricing/discounts.lob")
        )
        out = weave_markdown(m)
        assert "#Binding" not in out

    def test_discounts_ends_with_newline(self):
        m = from_tree(
            parse_file(EXAMPLES / "retail/pricing/discounts.lob")
        )
        out = weave_markdown(m)
        assert out.endswith("\n")


# ── BulletBlock rendering ─────────────────────────────────────

def _weave(source: str) -> str:
    return weave_markdown(from_tree(parse(source)))


class TestBulletBlockWeave:
    def test_single_item_renders_as_list(self):
        out = _weave("#T\n* item one\n")
        assert "* item one" in out

    def test_multiple_items_each_on_own_line(self):
        out = _weave("#T\n* alpha\n* beta\n* gamma\n")
        assert "* alpha\n* beta\n* gamma" in out

    def test_two_blocks_separated_in_output(self):
        out = _weave("#T\n* first block\n\n* second block\n")
        assert "* first block" in out
        assert "* second block" in out
        # the two blocks should not be adjacent lines
        lines = out.splitlines()
        first_idx = next(i for i, l in enumerate(lines) if "first block" in l)
        second_idx = next(i for i, l in enumerate(lines) if "second block" in l)
        assert second_idx > first_idx + 1

    def test_bullet_in_subheading_rendered(self):
        out = _weave("#T\n##Section\n* item\n")
        assert "## Section" in out
        assert "* item" in out
