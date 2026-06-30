"""Tests for the notlob parser.

Parse trees are Lark Tree/Token objects.  Helper functions below keep
assertions readable without depending on pretty-print output.
"""

from pathlib import Path

import pytest
from lark import Token, Tree

from notlob import parse, parse_file

# ── Helpers ──────────────────────────────────────────────────

def module(tree: Tree) -> Tree:
    """Return the module node from a start tree."""
    return tree.children[0]


def title(tree: Tree) -> str:
    """Return the module title string."""
    return str(module(tree).children[0])


def body(tree: Tree) -> Tree:
    """Return the body node from a start tree."""
    return module(tree).children[1]


def meaningful(body_node: Tree) -> list[Tree]:
    """Body items that are not bare BLANK tokens."""
    result = []
    for item in body_node.children:
        # body_item wraps either a Tree or a BLANK Token
        if item.children and isinstance(item.children[0], Tree):
            result.append(item.children[0])
    return result


def post_text(tree: Tree) -> Tree | None:
    """Return the post_text node, or None."""
    m = module(tree)
    if len(m.children) > 2:
        return m.children[2]
    return None


def post_sections(tree: Tree) -> list[Tree]:
    """Return the list of post_section child Trees."""
    pt = post_text(tree)
    if pt is None:
        return []
    return [c for c in pt.children if isinstance(c, Tree)]


# ── Module head ──────────────────────────────────────────────

class TestModuleHead:
    def test_title_captured(self):
        tree = parse("#Pricing Discounts\n")
        assert title(tree) == "Pricing Discounts"

    def test_no_post_text(self):
        tree = parse("#Title\n")
        assert post_text(tree) is None

    def test_empty_body(self):
        tree = parse("#Title\n")
        assert meaningful(body(tree)) == []


# ── Prose blocks ─────────────────────────────────────────────

class TestProseBlock:
    def test_single_line(self):
        tree = parse("#T\nSome prose.\n")
        items = meaningful(body(tree))
        assert len(items) == 1
        assert items[0].data == "prose_block"

    def test_consecutive_lines_form_one_block(self):
        tree = parse("#T\nLine one.\nLine two.\nLine three.\n")
        items = meaningful(body(tree))
        assert len(items) == 1
        assert len(items[0].children) == 3

    def test_blank_separates_blocks(self):
        tree = parse("#T\nFirst para.\n\nSecond para.\n")
        items = meaningful(body(tree))
        assert len(items) == 2
        assert all(i.data == "prose_block" for i in items)


# ── Code blocks ──────────────────────────────────────────────

class TestCodeBlock:
    def test_single_line(self):
        tree = parse("#T\n    x = 1\n")
        items = meaningful(body(tree))
        assert len(items) == 1
        assert items[0].data == "code_block"

    def test_multiple_lines(self):
        tree = parse("#T\n    x = 1\n    y = 2\n")
        items = meaningful(body(tree))
        assert items[0].data == "code_block"
        indent_lines = [
            c for c in items[0].children
            if isinstance(c, Token) and c.type == "INDENT"
        ]
        assert len(indent_lines) == 2

    def test_internal_blank_stays_in_block(self):
        src = "#T\n    x = 1\n\n    y = 2\n"
        tree = parse(src)
        items = meaningful(body(tree))
        # The blank between the two indented lines should not split
        # the block into two separate code_block nodes.
        assert len(items) == 1
        assert items[0].data == "code_block"

    def test_prose_after_code_is_separate(self):
        src = "#T\n    x = 1\nSome prose.\n"
        tree = parse(src)
        items = meaningful(body(tree))
        assert len(items) == 2
        assert items[0].data == "code_block"
        assert items[1].data == "prose_block"


# ── Claims ───────────────────────────────────────────────────

class TestClaim:
    def test_example_claim(self):
        src = "#T\n~example\n    x == 1\n"
        tree = parse(src)
        items = meaningful(body(tree))
        assert len(items) == 1
        assert items[0].data == "claim"

    def test_sigil_is_first_child(self):
        src = "#T\n~property\n    x > 0\n"
        tree = parse(src)
        claim = meaningful(body(tree))[0]
        assert isinstance(claim.children[0], Token)
        assert claim.children[0].type == "SIGIL"

    def test_multiline_body_stays_in_claim(self):
        # Regression: Earley resolved ambiguity by splitting claim body
        # after the first line.  LALR greedy shift keeps all lines.
        src = (
            "#T\n"
            "~example\n"
            "    a == 1\n"
            "    b == 2\n"
            "    c == 3\n"
        )
        tree = parse(src)
        claim = meaningful(body(tree))[0]
        indent_lines = [
            c for c in claim.children
            if isinstance(c, Token) and c.type == "INDENT"
        ]
        assert len(indent_lines) == 3


# ── Subheadings ──────────────────────────────────────────────

class TestSubheading:
    def test_subhead_token(self):
        src = "#T\n##Section\n    code\n"
        tree = parse(src)
        items = meaningful(body(tree))
        assert items[0].data == "subheading"
        assert str(items[0].children[0]) == "Section"

    def test_subheading_groups_content(self):
        src = (
            "#T\n"
            "##Section\n"
            "Prose.\n"
            "    code\n"
            "~example\n"
            "    x == 1\n"
        )
        tree = parse(src)
        items = meaningful(body(tree))
        assert len(items) == 1
        sub = items[0]
        assert sub.data == "subheading"
        sub_content = [
            c for c in sub.children if isinstance(c, Tree)
        ]
        kinds = [c.data for c in sub_content]
        assert "prose_block" in kinds
        assert "code_block" in kinds
        assert "claim" in kinds

    def test_new_subheading_starts_fresh(self):
        src = "#T\n##A\n    a\n##B\n    b\n"
        tree = parse(src)
        items = meaningful(body(tree))
        assert len(items) == 2
        assert items[0].children[0] == "A"
        assert items[1].children[0] == "B"


# ── Post-text sections ───────────────────────────────────────

class TestPostText:
    def test_separator_opens_post_text(self):
        src = "#T\n---\n"
        tree = parse(src)
        assert post_text(tree) is not None

    def test_tests_section(self):
        src = "#T\n---\n#Tests\n##group\n    x == 1\n"
        tree = parse(src)
        sections = post_sections(tree)
        assert sections[0].children[0].data == "tests_section"

    def test_binding_section(self):
        src = "#T\n---\n#Binding\n    ~language python\n"
        tree = parse(src)
        sections = post_sections(tree)
        assert sections[0].children[0].data == "binding_section"

    def test_references_section(self):
        src = "#T\n---\n#References\n    import x\n"
        tree = parse(src)
        sections = post_sections(tree)
        assert sections[0].children[0].data == "references_section"

    def test_blank_after_separator_allowed(self):
        src = "#T\n---\n\n#References\n    import x\n"
        tree = parse(src)
        assert post_text(tree) is not None

    def test_multiple_sections(self):
        src = "#T\n---\n#Tests\n##g\n    x\n#References\n    import x\n"
        tree = parse(src)
        sections = post_sections(tree)
        assert len(sections) == 2


# ── BulletBlock ──────────────────────────────────────────────

class TestBulletBlock:
    def test_single_bullet_parsed(self):
        src = "#T\n* item one\n"
        items = meaningful(body(parse(src)))
        assert len(items) == 1
        assert items[0].data == "bullet_block"

    def test_consecutive_bullets_one_block(self):
        src = "#T\n* item one\n* item two\n* item three\n"
        items = meaningful(body(parse(src)))
        assert len(items) == 1
        assert items[0].data == "bullet_block"
        assert len(items[0].children) == 3

    def test_blank_separates_bullet_blocks(self):
        src = "#T\n* item one\n\n* item two\n"
        items = meaningful(body(parse(src)))
        assert len(items) == 2
        assert all(i.data == "bullet_block" for i in items)

    def test_indented_bullet_is_code_not_bullet(self):
        src = "#T\n    * indented item\n"
        items = meaningful(body(parse(src)))
        assert items[0].data == "code_block"

    def test_prose_and_bullets_separate_items(self):
        src = "#T\nSome prose.\n\n* item\n"
        items = meaningful(body(parse(src)))
        assert items[0].data == "prose_block"
        assert items[1].data == "bullet_block"

    def test_lone_asterisk_is_bullet(self):
        src = "#T\n*\n"
        items = meaningful(body(parse(src)))
        assert items[0].data == "bullet_block"


# ── Integration: example files ───────────────────────────────

EXAMPLES = Path(__file__).parent.parent / "examples"


class TestExampleFiles:
    def test_roman_numerals(self):
        tree = parse_file(EXAMPLES / "roman/roman/numerals.lob")
        assert title(tree) == "Roman Numerals"
        items = meaningful(body(tree))
        kinds = {i.data for i in items}
        assert "code_block" in kinds
        assert "claim" in kinds
        assert "subheading" in kinds

    def test_pricing_discounts(self):
        tree = parse_file(EXAMPLES / "retail/pricing/discounts.lob")
        assert title(tree) == "Pricing Discounts"

    def test_roman_binding(self):
        tree = parse_file(EXAMPLES / "roman/binding.lob")
        assert title(tree) == "Roman"
        sections = post_sections(tree)
        assert sections[0].children[0].data == "binding_section"

    def test_pricing_binding(self):
        tree = parse_file(EXAMPLES / "retail/binding.lob")
        assert title(tree) == "Pricing"
        sections = post_sections(tree)
        assert sections[0].children[0].data == "binding_section"
