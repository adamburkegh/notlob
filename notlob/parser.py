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

Two things the grammar can't fully own are handled here, in a thin layer
around the raw parse:

1. **Token normalisation.** Every line-oriented terminal in the grammar
   consumes through its own trailing newline (so the lexer's cursor is
   always at true line-start for the next token). Downstream consumers
   (``model.py``, ``weave/markdown.py``) expect the *stripped* content —
   e.g. a ``SUBHEAD`` token's value is the title text alone, not
   ``"##Title\\n"``. ``_normalize`` rewrites each raw token's value to
   match, once, right after parsing, so nothing downstream needs to know
   the grammar changed.

2. **Reserved sigils.** The grammar's ``SIGIL`` terminal treats ``~test``
   as a syntactically legitimate token (it's a real, known word — just
   not implemented yet), rather than silently misparsing it or failing to
   lex it at all. Whether it's *allowed* is a semantic question, not a
   lexical one, so it's checked here, after parsing, with a specific
   message. A genuinely unrecognised sigil (``~foo``) isn't in the
   grammar's literal set at all and fails during lexing instead, with a
   generic message — there's nothing more specific to say about a typo.

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
    "MOD_HEAD", "SUBHEAD", "SIGIL", "SEPARATOR", "TESTS_HEAD",
    "BINDING_HEAD", "REFERENCES_HEAD", "APPENDIX_HEAD", "INDENT",
    "BULLET", "BLANK", "PROSE_NL",
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


# ── Reserved sigils ──────────────────────────────────────────
#
# Sigils that look plausible but are deliberately not (yet) implemented.
# Syntactically legitimate (part of the grammar's closed SIGIL
# vocabulary) but rejected here with a specific reason — see
# grammar.lark's header comment for why this is a semantic check rather
# than a lexer-level one.
_RESERVED_SIGILS: dict[str, str] = {
    "~test": (
        "'~test' is reserved for a future feature (naming individual "
        "assertions within a #Tests group) and is not implemented. "
        "Use the #Tests post-text section instead."
    ),
}

# The closed vocabulary of recognised claim sigils, including reserved
# ones. Mirrors grammar.lark's SIGIL terminal; kept here as a plain tuple
# for cross-checking against notlob.graph's dispatch (see
# tests/test_graph_completeness.py), which fails loudly if the two drift
# apart.
_KNOWN_SIGILS = ("~example", "~run", "~property")


def _check_reserved_sigils(tree: Tree) -> None:
    for claim in tree.find_data("claim"):
        sigil_tok = claim.children[0]
        word = str(sigil_tok).split(None, 1)[0]
        if word in _RESERVED_SIGILS:
            raise ValueError(_RESERVED_SIGILS[word])


# ── Public API ───────────────────────────────────────────────

def parse(source: str) -> Tree:
    """Parse a .lob source string and return a Lark Tree."""
    if not source.endswith("\n"):
        source += "\n"
    tree = _parser.parse(source)
    _normalize(tree)
    _check_reserved_sigils(tree)
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
