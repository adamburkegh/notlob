"""notlob.model — Semantic model for .lob source files.

Translates a Lark parse Tree into typed Python dataclasses.  The model
is a lossless structural representation: blank lines within blocks are
preserved as empty strings in line lists, and inline cross-references
in prose are first-class ``Ref`` objects rather than embedded strings.

Usage::

    from notlob import parse_file
    from notlob.model import from_tree, Module, CodeBlock, Claim

    module = from_tree(parse_file("examples/roman/numerals.lob"))
    print(module.title)
    for item in module.body:
        if isinstance(item, CodeBlock):
            print(item.lines)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from lark import Token, Tree


# ── Inline cross-references ──────────────────────────────────

@dataclass(frozen=True)
class Ref:
    """An inline cross-reference in prose: ``#Label`` or ``##Label``.

    ``#Label``  — resolved as symbol, subheading, or imported module
                  (the full three-step order from DESIGN.md).
    ``##Label`` — resolved as subheading of the current module only.

    *label* is the referenced name without sigil characters.
    *sub*   is True when the source wrote ``##``, False for ``#``.
    """
    label: str
    sub:   bool = False


#: A single span within a :class:`ProseBlock`: either plain text or a
#: cross-reference.
Span = Union[str, Ref]


# ── Body item types ──────────────────────────────────────────

@dataclass
class ProseBlock:
    """Prose content: a flat sequence of text fragments and cross-references.

    Each :class:`Ref` in *spans* is a ``#Label`` or ``##Label``
    cross-reference as written in source.  Plain strings are the
    surrounding text, preserving original whitespace.
    """
    spans: list[Span]


@dataclass
class CodeBlock:
    """An indented code block.

    Blank lines within the block are preserved as empty strings,
    consistent with the block-termination rule: only a non-blank
    dedented line ends the block.
    """
    lines: list[str]
    start_line: int | None = None


@dataclass
class Claim:
    """A ~sigil followed by its indented body."""
    sigil: str        # e.g. "~example", "~property"
    lines: list[str]  # body lines; blank lines preserved
    start_line: int | None = None


@dataclass
class BulletBlock:
    """A flush-left bullet list block.

    Each item in *items* is the line text with the leading ``* ``
    prefix stripped.  Indented bullet lines remain code (INDENTED_LINE tokens).
    """
    items: list[str]
    start_line: int | None = None


@dataclass
class Subheading:
    """A ## subheading with its subordinate content.

    Subheadings are flat — they do not nest.
    """
    title: str
    body: list[Union[CodeBlock, Claim, ProseBlock, "BulletBlock"]]
    start_line: int | None = None


# Union of all items that can appear at module body level.
BodyItem = Union[Subheading, CodeBlock, Claim, ProseBlock, BulletBlock]


# ── Post-text section types ──────────────────────────────────

@dataclass
class NamedTest:
    """A named ``~test <name>`` assertion block within a #Tests group.

    Structurally identical to Claim (a sigil followed by its indented
    body) but only reachable inside a #Tests group -- the grammar
    enforces that ~test never appears in the module body.
    """
    name: str
    lines: list[str]  # assertion lines; blank lines preserved
    start_line: int | None = None


@dataclass
class TestGroup:
    """A named ## group within the #Tests section.

    Items are bare assertion strings (INDENTED_LINE/BLANK lines), ProseBlock
    commentary, or NamedTest blocks, freely intermixed in source order.
    *line_offsets* maps a bare string's index in *items* to its source
    line -- needed because bare lines are no longer guaranteed to be
    consecutive (prose/named blocks can fall between them), the same
    reason TestsSection has its own line_offsets for its top-level bare
    items.
    """
    title: str
    items: list[Union[str, ProseBlock, NamedTest]]
    start_line: int | None = None
    line_offsets: dict[int, int] | None = None


@dataclass
class TestsSection:
    """The #Tests post-text section.

    Items are named TestGroups, bare assertion strings (INDENTED_LINE lines
    outside any ## group), or ProseBlock commentary -- freely
    intermixed, same as TestGroup's own items.
    """
    items: list[Union[TestGroup, str, ProseBlock]]
    line_offsets: dict[int, int] | None = None


@dataclass
class BindingSection:
    """The #Binding post-text section.

    Each declaration is a typed field; ``~language`` is required in
    practice (enforced at the grammar level — the lexer rejects unknown
    ``~sigil`` lines inside ``#Binding``).  ``externals`` is a list
    because ``~external`` may appear more than once.
    """
    language:           str | None  = None
    externals:          list[str]   = field(default_factory=list)
    on_build:           str | None  = None
    keep_generated_src: str | None  = None


@dataclass
class ReferencesSection:
    """The #References post-text section."""
    lines: list[str]


@dataclass
class AppendixSection:
    """A #Appendix … post-text section."""
    title: str  # full token value, e.g. "#Appendix Notes"
    body: list[BodyItem]


PostSection = Union[
    TestsSection, BindingSection, ReferencesSection, AppendixSection
]


@dataclass
class PostText:
    """Everything after the --- separator."""
    sections: list[PostSection]


# ── Top-level module ─────────────────────────────────────────

@dataclass
class Module:
    """The semantic model of a single .lob file."""
    title: str
    body: list[BodyItem]
    post_text: PostText | None = None
    start_line: int | None = None


# ── Tree → model ─────────────────────────────────────────────

def from_tree(tree: Tree) -> Module:
    """Build a Module from a Lark start Tree."""
    return _module(tree.children[0])


def _module(node: Tree) -> Module:
    title_tok = node.children[0]
    title = str(title_tok)
    body_items = _body(node.children[1])
    pt = (
        _post_text(node.children[2])
        if len(node.children) > 2
        else None
    )
    return Module(
        title=title, body=body_items, post_text=pt,
        start_line=getattr(title_tok, "line", None),
    )


def _body(node: Tree) -> list[BodyItem]:
    result = []
    for item in node.children:     # each child is a body_item Tree
        child = item.children[0]
        if isinstance(child, Token):   # BLANK body_item — skip
            continue
        result.append(_content(child))
    return result


def _content(node: Tree) -> BodyItem:
    """Convert a content node to its model object.

    Expects one of: subheading, code_block, claim, prose_block, bullet_block.
    """
    if node.data == "subheading":
        return _subheading(node)
    if node.data == "code_block":
        return _code_block(node)
    if node.data == "claim":
        return _claim(node)
    if node.data == "prose_block":
        return _prose_block(node)
    if node.data == "bullet_block":
        return _bullet_block(node)
    raise ValueError(f"Unexpected content node: {node.data!r}")


def _subheading(node: Tree) -> Subheading:
    title_tok = node.children[0]
    title = str(title_tok)
    body: list[Union[CodeBlock, Claim, ProseBlock, BulletBlock]] = []
    for child in node.children[1:]:
        if isinstance(child, Token):   # BLANK — skip
            continue
        item = _content(child)
        # grammar guarantees no nested subheadings here
        assert isinstance(item, (CodeBlock, Claim, ProseBlock, BulletBlock))
        body.append(item)
    return Subheading(
        title=title, body=body,
        start_line=getattr(title_tok, "line", None),
    )


def _code_block(node: Tree) -> CodeBlock:
    first = node.children[0] if node.children else None
    return CodeBlock(
        lines=[str(c) for c in node.children],
        start_line=getattr(first, "line", None),
    )


def _claim(node: Tree) -> Claim:
    sigil_tok = node.children[0]
    return Claim(
        sigil=str(sigil_tok),
        lines=[str(c) for c in node.children[1:]],
        start_line=getattr(sigil_tok, "line", None),
    )


def _prose_block(node: Tree) -> ProseBlock:
    # node.children are prose_line Trees.  Flatten their tokens into a
    # single span list, converting line-terminating BLANK tokens to "\n" string
    # spans at each line boundary (but not after the final line).
    # Preserving line structure matters for renderers (weave, LLM
    # context) that need accurate source text; consumers that only
    # inspect Ref objects are unaffected.
    spans: list[Span] = []
    lines = node.children
    for i, line_node in enumerate(lines):
        last_line = (i == len(lines) - 1)
        for tok in line_node.children:
            if tok.type == "BLANK":
                if not last_line:
                    spans.append("\n")      # line boundary within block
            elif tok.type == "REF":
                raw = str(tok)              # "##Stacking Discounts" or "#Foo"
                sub = raw.startswith("##")
                spans.append(Ref(label=raw.lstrip("#").strip(), sub=sub))
            else:                           # PROSE_TEXT
                spans.append(str(tok))
    return ProseBlock(spans=spans)


def _bullet_block(node: Tree) -> BulletBlock:
    first = node.children[0] if node.children else None
    items = [
        str(tok)[2:] if str(tok).startswith("* ") else str(tok).lstrip("*")
        for tok in node.children
    ]
    return BulletBlock(
        items=items,
        start_line=getattr(first, "line", None),
    )


def _post_text(node: Tree) -> PostText:
    sections = []
    for child in node.children:
        if isinstance(child, Token):   # SEPARATOR or BLANK
            continue
        # child is a post_section Tree; its one child is the section
        sections.append(_post_section(child.children[0]))
    return PostText(sections=sections)


def _post_section(node: Tree) -> PostSection:
    if node.data == "tests_section":
        return _tests_section(node)
    if node.data == "binding_section":
        return _binding_section(node)
    if node.data == "references_section":
        return _references_section(node)
    if node.data == "appendix_section":
        return _appendix_section(node)
    raise ValueError(f"Unknown post_section: {node.data!r}")


def _tests_section(node: Tree) -> TestsSection:
    items: list[Union[TestGroup, str, ProseBlock]] = []
    line_offsets: dict[int, int] = {}
    for child in node.children[1:]:    # skip TESTS_HEAD
        if isinstance(child, Token):   # BLANK
            continue
        if child.data == "prose_block":
            items.append(_prose_block(child))
            continue
        # child is a test_item Tree
        inner = child.children[0]
        if isinstance(inner, Token):   # bare INDENTED_LINE assertion
            ln = getattr(inner, "line", None)
            if ln is not None:
                line_offsets[len(items)] = ln
            items.append(str(inner))
        else:
            items.append(_test_group(inner))
    return TestsSection(
        items=items,
        line_offsets=line_offsets or None,
    )


def _test_group(node: Tree) -> TestGroup:
    title_tok = node.children[0]
    title = str(title_tok)
    items: list[Union[str, ProseBlock, NamedTest]] = []
    line_offsets: dict[int, int] = {}
    for child in node.children[1:]:
        if isinstance(child, Token):           # INDENTED_LINE or BLANK
            ln = getattr(child, "line", None)
            if ln is not None:
                line_offsets[len(items)] = ln
            items.append(str(child))
        elif child.data == "prose_block":
            items.append(_prose_block(child))
        elif child.data == "named_test":
            items.append(_named_test(child))
        else:
            raise ValueError(f"Unexpected test_group child: {child.data!r}")
    return TestGroup(
        title=title, items=items,
        start_line=getattr(title_tok, "line", None),
        line_offsets=line_offsets or None,
    )


def _named_test(node: Tree) -> NamedTest:
    sigil_tok = node.children[0]
    # sigil_tok value is "~test <name>" -- parser.py's normalisation
    # strips the trailing newline but not the "~test " prefix, the same
    # convention as ~property's Claim.sigil (e.g. "~property commutativity").
    name = str(sigil_tok).split(None, 1)[1].strip()
    return NamedTest(
        name=name,
        lines=[str(c) for c in node.children[1:]],
        start_line=getattr(sigil_tok, "line", None),
    )


def _binding_section(node: Tree) -> BindingSection:
    language           = None
    externals: list[str] = []
    on_build           = None
    keep_generated_src = None
    for child in node.children[1:]:   # skip BINDING_HEAD; INDENT and BLANK skipped below
        if not isinstance(child, Tree) or child.data != 'bind_detail_decl':
            continue
        decl = child.children[0]
        raw  = str(decl).strip()
        if decl.type == 'LANGUAGE_DECL':
            language = raw.removeprefix('~language ').strip()
        elif decl.type == 'EXTERNAL_DECL':
            externals.append(raw.removeprefix('~external ').strip())
        elif decl.type == 'ON_BUILD_DECL':
            on_build = raw.removeprefix('~on-build ').strip()
        elif decl.type == 'KEEP_SRC_DECL':
            keep_generated_src = raw.removeprefix('~keep-generated-src').strip() or None
    return BindingSection(
        language=language,
        externals=externals,
        on_build=on_build,
        keep_generated_src=keep_generated_src,
    )


def _references_section(node: Tree) -> ReferencesSection:
    return ReferencesSection(
        lines=[str(c) for c in node.children[1:]]
    )


def _appendix_section(node: Tree) -> AppendixSection:
    title = str(node.children[0])
    return AppendixSection(
        title=title,
        body=_body_from_items(node.children[1:]),
    )


def _body_from_items(items: list) -> list[BodyItem]:
    """Build a body list from a sequence of body_item Trees."""
    result = []
    for item in items:
        if isinstance(item, Token):
            continue
        child = item.children[0]
        if isinstance(child, Token):   # BLANK body_item
            continue
        result.append(_content(child))
    return result
