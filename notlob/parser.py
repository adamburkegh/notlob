"""notlob.parser - Parse .lob source files into a Lark Tree.

Native grammar
--------------
``grammar.lark`` is parsed with Lark's own contextual LALR lexer — every
structural line-type (``MOD_HEAD``, ``SUBHEAD``, ``SIGIL``, ``INDENT``,
``BLANK``, ``BULLET``, ``SEPARATOR``, the reserved post-text heads) is a
native terminal in the grammar file itself, not a token produced by a
hand-written Python line classifier. See ``grammar.lark``'s header comment
for how heading/sigil/prose disambiguation is resolved via terminal
priority and line-start anchoring.

One thing the grammar can't fully own is handled here, in a thin layer
around the raw parse:

**Token normalisation.** Every line-oriented terminal in the grammar
consumes through its own trailing newline (so the lexer's cursor is
always at true line-start for the next token). Downstream consumers
(``model.py``, ``weave/markdown.py``) expect the *stripped* content —
e.g. a ``SUBHEAD`` token's value is the title text alone, not
``"##Title\\n"``. ``_normalize`` rewrites each raw token's value to
match, once, right after parsing, so nothing downstream needs to know
the grammar changed.

Usage::

    from notlob.parser import parse_file, to_json
    tree = parse_file("examples/pricing/discounts.lob")
    print(tree.pretty())
    print(to_json(tree))
"""

from __future__ import annotations

import json
from pathlib import Path

from lark import Lark, Token, Tree

_GRAMMAR = (Path(__file__).parent / "grammar.lark").read_text(
    encoding="utf-8"
)

_parser = Lark(
    _GRAMMAR,
    parser="lalr",
    propagate_positions=True,
    regex=True,
)

# ── Token normalisation ─────────────────────────────────────
#
# Maps a raw terminal's matched text to the value downstream code
# expects: trailing "\n" stripped from every line-token, and the leading
# "#"/"##" marker stripped from MOD_HEAD/SUBHEAD (their title text is the
# grammar-meaningful part; the marker itself is not).

_STRIP_PREFIX: dict[str, int] = {
    "MOD_HEAD": 1,
    "SUBHEAD": 2,
}

_LINE_TOKEN_TYPES = {
    "MOD_HEAD", "SUBHEAD", "SIGIL", "TEST_SIGIL", "SEPARATOR",
    "TESTS_HEAD", "BINDING_HEAD", "REFERENCES_HEAD", "APPENDIX_HEAD",
    "INDENTED_LINE", "BULLET", "BLANK",
}


def _normalize_token(tok: Token) -> Token:
    text = str(tok).rstrip("\n")
    prefix_len = _STRIP_PREFIX.get(tok.type)
    if prefix_len is not None:
        text = text[prefix_len:].strip()
    return tok.update(value=text)


def _normalize(tree: Tree) -> Tree:
    """Rewrite line-token values in place to match pre-refactor shape."""
    for subtree in tree.iter_subtrees():
        children = subtree.children
        for i, child in enumerate(children):
            if isinstance(child, Token) and child.type in _LINE_TOKEN_TYPES:
                children[i] = _normalize_token(child)
    return tree


# The closed vocabulary of recognised claim sigils (body-level; excludes
# ~test, which is TEST_SIGIL, a separate terminal only reachable inside
# a #Tests group). Mirrors grammar.lark's SIGIL terminal; kept here for
# cross-checking against notlob.graph's dispatch (see
# tests/test_graph_completeness.py), which fails loudly if the two drift
# apart.
_KNOWN_SIGILS = ("~example", "~run", "~property")


# ── Public API ───────────────────────────────────────────────

def parse(source: str) -> Tree:
    """Parse a .lob source string and return a Lark Tree."""
    if not source.endswith("\n"):
        source += "\n"
    tree = _parser.parse(source)
    _normalize(tree)
    return tree


def parse_file(path: str | Path) -> Tree:
    """Parse a .lob file and return a Lark Tree."""
    return parse(Path(path).read_text(encoding="utf-8"))


# ── Serialisation ────────────────────────────────────────────

def to_dict(node: Tree | Token) -> dict:
    """Recursively convert a Tree or Token to a plain dict."""
    if isinstance(node, Token):
        return {"token": node.type, "value": str(node)}
    return {
        "rule": node.data,
        "children": [to_dict(c) for c in node.children],
    }


def to_json(tree: Tree, *, indent: int = 2) -> str:
    """Serialise a parse Tree to a JSON string."""
    return json.dumps(to_dict(tree), indent=indent)
