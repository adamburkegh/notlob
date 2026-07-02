"""Tests for notlob's structural line terminals (MOD_HEAD, SUBHEAD,
SIGIL, INDENT, BLANK, SEPARATOR, and the reserved post-text heads).

These used to exercise a hand-written Python line classifier
(``_classify``) directly. That classifier is gone: every structural
line-type is now a native Lark terminal in ``grammar.lark``, resolved via
terminal priority and line-start anchoring (see its header comment). These
tests exercise the same line-classification behaviours through the public
``parse()`` API, inspecting the resulting tree instead of calling a
private function.
"""

from lark import Token
from lark.exceptions import UnexpectedCharacters, UnexpectedToken
import pytest

from notlob.parser import parse


def _first_token_of_type(tree, *token_types):
    """Return the first token anywhere in *tree* matching *token_types*."""
    for value in tree.scan_values(
        lambda v: isinstance(v, Token) and v.type in token_types
    ):
        return value
    raise AssertionError(f"no token of type {token_types!r} in tree")


# ── Structural markers ───────────────────────────────────────

def test_separator():
    tree = parse("#T\n---\n#Tests\n    x == 1\n")
    tok = _first_token_of_type(tree, "SEPARATOR")
    assert str(tok) == "---"


def test_tests_head():
    tree = parse("#T\n---\n#Tests\n    x == 1\n")
    _first_token_of_type(tree, "TESTS_HEAD")


def test_binding_head():
    tree = parse("#T\n---\n#Binding\n    ~language python\n")
    _first_token_of_type(tree, "BINDING_HEAD")


def test_references_head():
    tree = parse("#T\n---\n#References\n    from decimal import Decimal\n")
    _first_token_of_type(tree, "REFERENCES_HEAD")


def test_appendix_head():
    tree = parse("#T\n---\n#Appendix: Notes\nSome notes.\n")
    _first_token_of_type(tree, "APPENDIX_HEAD")


# ── Headings ─────────────────────────────────────────────────

def test_mod_head_strips_sigil():
    tree = parse("#Roman Numerals\n")
    tok = _first_token_of_type(tree, "MOD_HEAD")
    assert str(tok) == "Roman Numerals"


def test_subhead_strips_sigil():
    tree = parse("#T\n##Stacking Discounts\n    code\n")
    tok = _first_token_of_type(tree, "SUBHEAD")
    assert str(tok) == "Stacking Discounts"


def test_subhead_trims_whitespace():
    tree = parse("#T\n##  Padded  \n    code\n")
    tok = _first_token_of_type(tree, "SUBHEAD")
    assert str(tok) == "Padded"


# ── Claims ───────────────────────────────────────────────────

def test_sigil_example():
    tree = parse("#T\n~example\n    x == 1\n")
    tok = _first_token_of_type(tree, "SIGIL")
    assert str(tok) == "~example"


def test_sigil_property():
    tree = parse("#T\n~property\n    x > 0\n")
    _first_token_of_type(tree, "SIGIL")


def test_sigil_requires_lowercase():
    # A capital letter after ~ is not sigil-shaped -- it's ordinary
    # prose starting with a literal tilde, same as the pre-refactor
    # classifier's `stripped[1:2].islower()` check.
    tree = parse("#T\n~Example is not a sigil.\n")
    tok = _first_token_of_type(tree, "LINE_START_TEXT", "PROSE_TEXT")
    assert str(tok).startswith("~Example")


def test_unknown_sigil_fails_to_lex():
    # Closed vocabulary: a lowercase word after ~ that isn't a known
    # sigil fails to lex entirely, rather than silently becoming prose.
    with pytest.raises((UnexpectedCharacters, UnexpectedToken)):
        parse("#T\n~lemma\n    x == 1\n")


# ── Body lines ───────────────────────────────────────────────

def test_blank_empty_line():
    tree = parse("#T\n\nProse.\n")
    tok = _first_token_of_type(tree, "BLANK")
    assert str(tok) == ""


def test_indent_leading_spaces():
    tree = parse("#T\n    result = x * y\n")
    tok = _first_token_of_type(tree, "INDENT")
    assert str(tok) == "    result = x * y"


def test_indent_leading_tab():
    tree = parse("#T\n\treturn result\n")
    _first_token_of_type(tree, "INDENT")


def test_prose_unindented():
    tree = parse("#T\nA discount strategy applies a multiplier.\n")
    _first_token_of_type(tree, "LINE_START_TEXT", "PROSE_TEXT")


def test_prose_not_confused_with_indent():
    # Regression: a flush-left prose line must not be classified INDENT.
    tree = parse("#T\nPlain prose with no leading whitespace.\n")
    _first_token_of_type(tree, "LINE_START_TEXT", "PROSE_TEXT")
