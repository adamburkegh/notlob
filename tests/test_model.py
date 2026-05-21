"""Tests for the notlob semantic model.

from_tree() translates a Lark parse Tree into typed dataclasses.
These tests verify that each grammar construct maps to the right
model object with the right content, and that BLANKs are dropped
where they are semantically inert.
"""

from pathlib import Path

import pytest

from notlob import parse, parse_file, from_tree
from notlob import (
    Module, Subheading, CodeBlock, Claim, ProseBlock,
    PostText, TestsSection, TestGroup,
    BindingSection, ReferencesSection,
)


def model(source: str) -> Module:
    return from_tree(parse(source))


EXAMPLES = Path(__file__).parent.parent / "examples"


# ── Module ───────────────────────────────────────────────────

class TestModule:
    def test_title(self):
        m = model("#Pricing Discounts\n")
        assert m.title == "Pricing Discounts"

    def test_empty_body(self):
        m = model("#T\n")
        assert m.body == []

    def test_no_post_text(self):
        m = model("#T\n")
        assert m.post_text is None

    def test_blanks_not_in_body(self):
        m = model("#T\n\n\n")
        assert m.body == []


# ── ProseBlock ───────────────────────────────────────────────

class TestProseBlock:
    def test_single_line(self):
        m = model("#T\nSome prose.\n")
        assert len(m.body) == 1
        assert isinstance(m.body[0], ProseBlock)
        assert m.body[0].lines == ["Some prose."]

    def test_consecutive_lines_one_block(self):
        m = model("#T\nLine one.\nLine two.\n")
        assert len(m.body) == 1
        assert m.body[0].lines == ["Line one.", "Line two."]

    def test_blank_separates_paragraphs(self):
        m = model("#T\nFirst.\n\nSecond.\n")
        assert len(m.body) == 2
        assert m.body[0].lines == ["First."]
        assert m.body[1].lines == ["Second."]


# ── CodeBlock ────────────────────────────────────────────────

class TestCodeBlock:
    def test_single_line(self):
        m = model("#T\n    x = 1\n")
        assert isinstance(m.body[0], CodeBlock)
        assert "    x = 1" in m.body[0].lines

    def test_blank_preserved_within_block(self):
        m = model("#T\n    x = 1\n\n    y = 2\n")
        assert len(m.body) == 1
        block = m.body[0]
        assert isinstance(block, CodeBlock)
        assert "" in block.lines   # blank preserved

    def test_leading_whitespace_preserved(self):
        m = model("#T\n    def f():\n        pass\n")
        block = m.body[0]
        assert block.lines[0] == "    def f():"
        assert block.lines[1] == "        pass"


# ── Claim ────────────────────────────────────────────────────

class TestClaim:
    def test_sigil_captured(self):
        m = model("#T\n~example\n    x == 1\n")
        claim = m.body[0]
        assert isinstance(claim, Claim)
        assert claim.sigil == "~example"

    def test_body_lines(self):
        m = model("#T\n~property\n    x > 0\n    y > 0\n")
        claim = m.body[0]
        assert "    x > 0" in claim.lines
        assert "    y > 0" in claim.lines

    def test_multiline_body_intact(self):
        # All body lines must stay in the single Claim, not spill
        # into a separate CodeBlock.
        src = (
            "#T\n"
            "~example\n"
            "    a == 1\n"
            "    b == 2\n"
            "    c == 3\n"
        )
        m = model(src)
        assert len(m.body) == 1
        assert isinstance(m.body[0], Claim)
        indent_lines = [
            l for l in m.body[0].lines if l.strip()
        ]
        assert len(indent_lines) == 3


# ── Subheading ───────────────────────────────────────────────

class TestSubheading:
    def test_title(self):
        m = model("#T\n##Section\n    code\n")
        sub = m.body[0]
        assert isinstance(sub, Subheading)
        assert sub.title == "Section"

    def test_content_grouped(self):
        src = (
            "#T\n"
            "##Section\n"
            "Prose.\n"
            "    code\n"
            "~example\n"
            "    x == 1\n"
        )
        m = model(src)
        sub = m.body[0]
        kinds = {type(i).__name__ for i in sub.body}
        assert kinds == {"ProseBlock", "CodeBlock", "Claim"}

    def test_blanks_not_in_sub_body(self):
        m = model("#T\n##S\n\nProse.\n\n    code\n")
        sub = m.body[0]
        assert all(
            isinstance(i, (ProseBlock, CodeBlock, Claim))
            for i in sub.body
        )

    def test_two_subheadings(self):
        m = model("#T\n##A\n    a\n##B\n    b\n")
        assert len(m.body) == 2
        assert m.body[0].title == "A"
        assert m.body[1].title == "B"


# ── Post-text ────────────────────────────────────────────────

class TestPostText:
    def test_present_after_separator(self):
        m = model("#T\n---\n")
        assert isinstance(m.post_text, PostText)

    def test_references_section(self):
        m = model("#T\n---\n#References\n    import x\n")
        section = m.post_text.sections[0]
        assert isinstance(section, ReferencesSection)
        assert "    import x" in section.lines

    def test_binding_section(self):
        m = model(
            "#T\n---\n#Binding\n"
            "    ~language python\n"
        )
        section = m.post_text.sections[0]
        assert isinstance(section, BindingSection)
        assert "    ~language python" in section.lines

    def test_tests_section_groups(self):
        src = (
            "#T\n---\n#Tests\n"
            "##group\n"
            "    x == 1\n"
        )
        m = model(src)
        section = m.post_text.sections[0]
        assert isinstance(section, TestsSection)
        assert len(section.items) == 1
        group = section.items[0]
        assert isinstance(group, TestGroup)
        assert group.title == "group"
        assert "    x == 1" in group.lines

    def test_multiple_sections_ordered(self):
        src = (
            "#T\n---\n"
            "#Tests\n##g\n    x\n"
            "#References\n    import x\n"
        )
        m = model(src)
        assert isinstance(m.post_text.sections[0], TestsSection)
        assert isinstance(
            m.post_text.sections[1], ReferencesSection
        )


# ── Integration: example files ───────────────────────────────

class TestExampleFiles:
    def test_roman_numerals_structure(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        assert m.title == "Roman Numerals"
        kinds = {type(i).__name__ for i in m.body}
        assert "CodeBlock" in kinds
        assert "Claim" in kinds
        assert "Subheading" in kinds
        assert "ProseBlock" in kinds

    def test_roman_numerals_subheadings(self):
        m = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        subs = [i for i in m.body if isinstance(i, Subheading)]
        titles = [s.title for s in subs]
        assert "Decoding" in titles
        assert "Round-Trip" in titles

    def test_pricing_references(self):
        m = from_tree(
            parse_file(EXAMPLES / "retail/pricing/discounts.lob")
        )
        refs = [
            s for s in m.post_text.sections
            if isinstance(s, ReferencesSection)
        ]
        assert len(refs) == 1
        combined = "\n".join(refs[0].lines)
        assert "Decimal" in combined
        # hypothesis is provided by the binding; not needed in #References

    def test_binding_lob_binding_section(self):
        m = from_tree(
            parse_file(EXAMPLES / "retail/binding.lob")
        )
        bindings = [
            s for s in m.post_text.sections
            if isinstance(s, BindingSection)
        ]
        assert len(bindings) == 1
        combined = "\n".join(bindings[0].lines)
        assert "python" in combined
        assert "hypothesis" in combined
        assert "pytest" in combined
