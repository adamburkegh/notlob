"""Tests for the notlob semantic model.

from_tree() translates a Lark parse Tree into typed dataclasses.
These tests verify that each grammar construct maps to the right
model object with the right content, and that BLANKs are dropped
where they are semantically inert.
"""

from pathlib import Path

from notlob import parse, parse_file, from_tree
from notlob import (
    Ref,
    Module, Subheading, CodeBlock, Claim, ProseBlock, BulletBlock,
    PostText, TestsSection, TestGroup,
    BindingSection, ReferencesSection,
)
from notlob.model import AppendixSection, NamedTest


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
        assert m.body[0].spans == ["Some prose."]

    def test_consecutive_lines_one_block(self):
        m = model("#T\nLine one.\nLine two.\n")
        assert len(m.body) == 1
        # Line boundary is preserved as a "\n" span so that renderers
        # (weave, LLM context) produce accurate source text.
        assert m.body[0].spans == ["Line one.", "\n", "Line two."]

    def test_blank_separates_paragraphs(self):
        m = model("#T\nFirst.\n\nSecond.\n")
        assert len(m.body) == 2
        assert m.body[0].spans == ["First."]
        assert m.body[1].spans == ["Second."]

    def test_inline_ref_produces_ref_object(self):
        m = model("#T\nSee #Foo Bar for details.\n")
        block = m.body[0]
        assert isinstance(block, ProseBlock)
        refs = [s for s in block.spans if isinstance(s, Ref)]
        assert len(refs) == 1
        assert refs[0].label == "Foo Bar"
        assert refs[0].sub is False

    def test_inline_subheading_ref(self):
        m = model("#T\nAs shown in ##Word Frequencies below.\n")
        refs = [s for s in m.body[0].spans if isinstance(s, Ref)]
        assert len(refs) == 1
        assert refs[0].label == "Word Frequencies"
        assert refs[0].sub is True

    def test_multiple_refs_in_one_block(self):
        m = model("#T\nUses #Foo and #Bar Baz together.\n")
        refs = [s for s in m.body[0].spans if isinstance(s, Ref)]
        assert [r.label for r in refs] == ["Foo", "Bar Baz"]

    def test_plain_prose_no_refs(self):
        m = model("#T\nNo references here at all.\n")
        spans = m.body[0].spans
        assert all(isinstance(s, str) for s in spans)

    def test_hash_number_not_a_ref(self):
        m = model("#T\nSee EBook #1524 for the source.\n")
        refs = [s for s in m.body[0].spans if isinstance(s, Ref)]
        assert refs == []


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
            line for line in m.body[0].lines if line.strip()
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
        assert section.language == "python"

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
        assert "    x == 1" in group.items

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
        assert bindings[0].language == "python"


# ── BulletBlock ──────────────────────────────────────────────

class TestBulletBlock:
    def test_items_stripped_of_prefix(self):
        m = model("#T\n* item one\n* item two\n")
        assert len(m.body) == 1
        block = m.body[0]
        assert isinstance(block, BulletBlock)
        assert block.items == ["item one", "item two"]

    def test_lone_asterisk_item_is_empty_string(self):
        m = model("#T\n*\n")
        block = m.body[0]
        assert isinstance(block, BulletBlock)
        assert block.items == [""]

    def test_blank_between_blocks_separates(self):
        m = model("#T\n* a\n\n* b\n")
        assert len(m.body) == 2
        assert isinstance(m.body[0], BulletBlock)
        assert isinstance(m.body[1], BulletBlock)

    def test_bullet_and_prose_are_distinct_types(self):
        m = model("#T\nSome prose.\n\n* item\n")
        assert isinstance(m.body[0], ProseBlock)
        assert isinstance(m.body[1], BulletBlock)

    def test_start_line_set(self):
        m = model("#T\n\n* item\n")
        block = m.body[0]
        assert isinstance(block, BulletBlock)
        assert block.start_line is not None

    def test_bullet_in_subheading(self):
        m = model("#T\n##Section\n* item\n")
        sub = m.body[0]
        assert isinstance(sub, Subheading)
        assert isinstance(sub.body[0], BulletBlock)


# ── Positions ────────────────────────────────────────────────
#
# Every element of the model has a first and a last line, 1-based and
# inclusive. The last line is the last non-blank line of the element:
# the blank lines the grammar keeps at the end of a block do not count.

def at(element) -> tuple[int | None, int | None]:
    return (element.start_line, element.end_line)


def post(m: Module, kind):
    return [s for s in m.post_text.sections if isinstance(s, kind)]


class TestProsePosition:
    def test_one_line(self):
        m = model("#T\n\nOne line.\n")
        assert at(m.body[0]) == (3, 3)

    def test_several_lines_and_a_second_paragraph(self):
        m = model("#T\n\nFirst para\nsecond line.\n\nNext.\n")
        assert [at(b) for b in m.body] == [(3, 4), (6, 6)]

    def test_a_paragraph_with_references(self):
        m = model("#T\nSee #Foo Bar.\nAnd ##Baz.\n")
        assert at(m.body[0]) == (2, 3)


class TestBlockPositions:
    def test_code_block_excludes_trailing_blank_lines(self):
        m = model("#T\n    a = 1\n\n    b = 2\n\n\nProse.\n")
        assert at(m.body[0]) == (2, 4)
        assert at(m.body[1]) == (7, 7)

    def test_one_line_code_block(self):
        m = model("#T\n    a = 1\n")
        assert at(m.body[0]) == (2, 2)

    def test_claim_excludes_trailing_blank_lines(self):
        m = model("#T\n~example\n    x == 1\n    y == 2\n\n\nAfter.\n")
        assert at(m.body[0]) == (2, 4)

    def test_claim_with_no_body_is_its_sigil_line(self):
        m = model("#T\n~example\n\nAfter.\n")
        assert at(m.body[0]) == (2, 2)

    def test_bullet_block(self):
        m = model("#T\n* a\n* b\n* c\n")
        assert at(m.body[0]) == (2, 4)

    def test_lone_asterisk_bullet(self):
        m = model("#T\n*\n")
        assert at(m.body[0]) == (2, 2)


class TestSectionPositions:
    def test_subheading_runs_to_its_last_item(self):
        m = model("#T\n\n##Sub\n\nProse.\n\n    code\n\n\n##Empty\n")
        sub, empty = m.body
        assert at(sub) == (3, 7)
        assert [at(i) for i in sub.body] == [(5, 5), (7, 7)]

    def test_subheading_with_no_items_is_its_heading_line(self):
        m = model("#T\n\n##Sub\n\n\n##Empty\n")
        assert [at(s) for s in m.body] == [(3, 3), (6, 6)]

    def test_module_without_post_text(self):
        m = model("#T\n\nText.\n\n\n")
        assert at(m) == (1, 3)

    def test_module_with_only_a_title(self):
        assert at(model("#T\n")) == (1, 1)

    def test_module_includes_its_post_text(self):
        m = model("#T\n\nProse.\n\n---\n\n#References\n    #Foo\n\n")
        assert at(m) == (1, 8)

    def test_module_includes_a_bare_separator(self):
        assert at(model("#T\n\n---\n")) == (1, 3)


class TestPostTextPosition:
    def test_it_runs_from_the_separator_to_the_last_section_line(self):
        m = model("#T\n\nProse.\n\n---\n\n#References\n    #Foo\n\n")
        assert at(m.post_text) == (5, 8)
        assert at(m) == (1, 8)

    def test_its_last_line_is_the_modules(self):
        m = model(_TESTS)
        assert at(m.post_text) == (3, 14)
        assert m.post_text.end_line == m.end_line

    def test_a_bare_separator_is_one_line(self):
        assert at(model("#T\n\n---\n").post_text) == (3, 3)

    def test_trailing_blank_lines_are_not_part_of_it(self):
        assert at(model("#T\n\n---\n\n#Tests\n\n\n\n").post_text) == (3, 5)

    def test_it_holds_its_sections(self):
        m = model(
            "#T\n\n---\n\n#Tests\n    a == 1\n\n#Appendix\n\nProse.\n")
        post_text = m.post_text
        assert [at(s) for s in post_text.sections] == [(5, 6), (8, 10)]
        assert at(post_text) == (3, 10)


_TESTS = (
    "#T\n"              # 1
    "\n"                # 2
    "---\n"             # 3
    "\n"                # 4
    "#Tests\n"          # 5
    "\n"                # 6
    "##g\n"             # 7
    "    a == 1\n"      # 8
    "\n"                # 9
    "~test nm\n"        # 10
    "    b == 2\n"      # 11
    "\n"                # 12
    "\n"                # 13
    "##h\n"             # 14
)


class TestTestsPositions:
    def test_tests_section_runs_to_its_last_group(self):
        (tests,) = post(model(_TESTS), TestsSection)
        assert at(tests) == (5, 14)

    def test_group_excludes_trailing_blank_lines(self):
        (tests,) = post(model(_TESTS), TestsSection)
        g, h = tests.items
        assert at(g) == (7, 11)
        assert at(h) == (14, 14)

    def test_named_test(self):
        (tests,) = post(model(_TESTS), TestsSection)
        named = [i for i in tests.items[0].items
                 if isinstance(i, NamedTest)]
        assert [at(n) for n in named] == [(10, 11)]

    def test_prose_in_a_group(self):
        m = model(
            "#T\n\n---\n\n#Tests\n\n##g\n    a == 1\n\n"
            "Commentary\non two lines.\n")
        (tests,) = post(m, TestsSection)
        prose = [i for i in tests.items[0].items
                 if isinstance(i, ProseBlock)]
        assert [at(p) for p in prose] == [(10, 11)]
        assert at(tests.items[0]) == (7, 11)

    def test_bare_assertions_and_prose_at_the_section_level(self):
        m = model("#T\n\n---\n\n#Tests\n    a == 1\n\nCommentary.\n")
        (tests,) = post(m, TestsSection)
        assert at(tests) == (5, 8)
        assert at(tests.items[1]) == (8, 8)

    def test_tests_section_with_no_items(self):
        (tests,) = post(model("#T\n\n---\n\n#Tests\n"), TestsSection)
        assert at(tests) == (5, 5)


class TestOtherPostTextPositions:
    def test_binding_section(self):
        m = model(
            "#T\n\n---\n\n#Binding\n    ~language python\n"
            "    ~external a.txt\n\n")
        (binding,) = post(m, BindingSection)
        assert at(binding) == (5, 7)

    def test_binding_section_with_no_declarations(self):
        m = model("#T\n\n---\n\n#Binding\n")
        (binding,) = post(m, BindingSection)
        assert at(binding) == (5, 5)

    def test_references_section(self):
        m = model("#T\n\n---\n\n#References\n    #Foo\n    import x\n\n")
        (refs,) = post(m, ReferencesSection)
        assert at(refs) == (5, 7)

    def test_references_section_with_no_lines(self):
        m = model("#T\n\n---\n\n#References\n")
        (refs,) = post(m, ReferencesSection)
        assert at(refs) == (5, 5)

    def test_appendix_runs_to_its_last_item(self):
        m = model(
            "#T\n\n---\n\n#Appendix Notes\n\nProse.\n\n    code\n\n\n")
        (appendix,) = post(m, AppendixSection)
        assert at(appendix) == (5, 9)
        assert [at(i) for i in appendix.body] == [(7, 7), (9, 9)]

    def test_appendix_with_no_items(self):
        m = model("#T\n\n---\n\n#Appendix\n")
        (appendix,) = post(m, AppendixSection)
        assert at(appendix) == (5, 5)

    def test_the_per_line_positions_are_unchanged(self):
        m = model(
            "#T\n\n---\n\n#Binding\n    ~language python\n"
            "    ~external a.txt\n    ~on-build hook.py\n\n"
            "#References\n    #Foo\n    import x\n")
        (binding,) = post(m, BindingSection)
        (refs,) = post(m, ReferencesSection)
        assert binding.external_lines == [7]
        assert binding.on_build_line == 8
        assert refs.line_numbers == [11, 12]


class TestRomanPositions:
    """`examples/roman/roman/numerals.lob`, whose lines are fixed."""

    def roman(self) -> Module:
        return from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))

    def sub(self, title: str) -> Subheading:
        return next(i for i in self.roman().body
                    if isinstance(i, Subheading) and i.title == title)

    def test_the_module(self):
        assert at(self.roman()) == (1, 105)

    def test_the_body_items(self):
        body = self.roman().body
        prose = [at(i) for i in body if isinstance(i, ProseBlock)]
        code = [at(i) for i in body if isinstance(i, CodeBlock)]
        claims = [at(i) for i in body if isinstance(i, Claim)]
        assert prose == [(3, 6), (8, 10), (32, 35)]
        assert code == [(12, 25)]
        assert claims == [(27, 30), (37, 38)]

    def test_decoding(self):
        sub = self.sub("Decoding")
        assert at(sub) == (40, 60)
        assert [at(i) for i in sub.body] == [(42, 44), (46, 56), (58, 60)]

    def test_round_trip(self):
        sub = self.sub("Round-Trip")
        assert at(sub) == (62, 71)
        assert [at(i) for i in sub.body] == [(64, 66), (68, 71)]

    def test_tests_section_and_groups(self):
        (tests,) = post(self.roman(), TestsSection)
        assert at(tests) == (75, 103)
        groups = {g.title: g for g in tests.items
                  if isinstance(g, TestGroup)}
        assert at(groups["encoding"]) == (77, 93)
        assert at(groups["decoding"]) == (95, 98)
        assert at(groups["round-trip"]) == (100, 103)

    def test_inside_the_encoding_group(self):
        (tests,) = post(self.roman(), TestsSection)
        encoding = next(g for g in tests.items
                        if isinstance(g, TestGroup)
                        and g.title == "encoding")
        prose = [i for i in encoding.items if isinstance(i, ProseBlock)]
        named = [i for i in encoding.items if isinstance(i, NamedTest)]
        assert [at(p) for p in prose] == [(88, 90)]
        assert [(n.name, at(n)) for n in named] == [("mcmxciv", (92, 93))]

    def test_references(self):
        (refs,) = post(self.roman(), ReferencesSection)
        assert at(refs) == (105, 105)

    def test_the_post_text(self):
        assert at(self.roman().post_text) == (73, 105)


# The invariant, over every example project: every element has a first
# and a last line, the first is not after the last, the items of a
# container (the module, the post-text, a subheading, an appendix, the
# #Tests section, a test group) are in order and do not overlap, and each
# lies within the container that holds it. A test of this shape notices an
# element that someone forgets.

def _bare_span(owner, index: int):
    line = (owner.line_offsets or {}).get(index)
    return None if line is None else (line, line)


def _items(container):
    """What *container* directly holds, in source order, as
    (label, element, span). A bare assertion line has no element of its
    own; a blank one holds no position and is left out."""
    if isinstance(container, Module):
        held = [*container.body, *([container.post_text]
                                   if container.post_text else [])]
    elif isinstance(container, PostText):
        held = container.sections
    elif isinstance(container, (Subheading, AppendixSection)):
        held = container.body
    elif isinstance(container, (TestsSection, TestGroup)):
        held = container.items
    else:
        return []
    out = []
    for i, item in enumerate(held):
        label = f"{type(item).__name__}[{i}]"
        if not isinstance(item, str):
            out.append((label, item, at(item)))
        elif item.strip():
            out.append((label, None, _bare_span(container, i)))
    return out


def _problems(element, name: str = "module") -> list[str]:
    start, end = at(element)
    if start is None or end is None:
        return [f"{name}: no position"]
    problems = []
    if start > end:
        problems.append(f"{name}: starts at {start}, ends at {end}")
    lines = []
    if isinstance(element, ReferencesSection):
        lines = element.line_numbers
    elif isinstance(element, BindingSection):
        lines = [*element.external_lines, element.on_build_line]
    for line in lines:
        if line is not None and not start <= line <= end:
            problems.append(f"{name}: line {line} is outside {start}-{end}")
    previous = start
    for label, child, span in _items(element):
        if span is None or None in span:
            problems.append(f"{name}/{label}: no position")
            continue
        first, last = span
        if first <= previous:
            problems.append(
                f"{name}/{label}: {span} does not follow line {previous}")
        if last > end:
            problems.append(f"{name}/{label}: {span} is outside {start}-{end}")
        previous = max(previous, last)
        if child is not None:
            problems += _problems(child, f"{name}/{label}")
    return problems


def _example_files() -> list[Path]:
    return sorted(EXAMPLES.rglob("*.lob"))


class TestPositionsInEveryExample:
    def test_the_examples_are_found(self):
        assert EXAMPLES / "roman/roman/numerals.lob" in _example_files()

    def test_every_element_has_a_consistent_position(self):
        failures = {}
        for path in _example_files():
            problems = _problems(from_tree(parse_file(path)))
            if problems:
                failures[str(path.relative_to(EXAMPLES))] = problems
        assert not failures
