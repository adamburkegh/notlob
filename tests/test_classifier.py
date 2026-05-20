"""Tests for the notlob line classifier.

Each source line is classified into exactly one token type before
the grammar parser sees it.  These tests exercise _classify directly,
independent of grammar rules.
"""

import pytest
from notlob.parser import _classify


# ── Structural markers ───────────────────────────────────────

def test_separator():
    tok = _classify("---\n")
    assert tok.type == "SEPARATOR"
    assert str(tok) == "---"


def test_tests_head():
    tok = _classify("#Tests\n")
    assert tok.type == "TESTS_HEAD"


def test_binding_head():
    tok = _classify("#Binding\n")
    assert tok.type == "BINDING_HEAD"


def test_references_head():
    tok = _classify("#References\n")
    assert tok.type == "REFERENCES_HEAD"


def test_appendix_head():
    tok = _classify("#Appendix: Notes\n")
    assert tok.type == "APPENDIX_HEAD"


# ── Headings ─────────────────────────────────────────────────

def test_mod_head_strips_sigil():
    tok = _classify("#Roman Numerals\n")
    assert tok.type == "MOD_HEAD"
    assert str(tok) == "Roman Numerals"


def test_subhead_strips_sigil():
    tok = _classify("##Stacking Discounts\n")
    assert tok.type == "SUBHEAD"
    assert str(tok) == "Stacking Discounts"


def test_subhead_trims_whitespace():
    tok = _classify("##  Padded  \n")
    assert tok.type == "SUBHEAD"
    assert str(tok) == "Padded"


# ── Claims ───────────────────────────────────────────────────

def test_sigil_example():
    tok = _classify("~example\n")
    assert tok.type == "SIGIL"
    assert str(tok) == "~example"


def test_sigil_property():
    tok = _classify("~property\n")
    assert tok.type == "SIGIL"


def test_sigil_requires_lowercase():
    # Capital letter after ~ is not a sigil — falls through to PROSE
    tok = _classify("~Example\n")
    assert tok.type == "PROSE"


# ── Body lines ───────────────────────────────────────────────

def test_blank_empty_line():
    tok = _classify("\n")
    assert tok.type == "BLANK"
    assert str(tok) == ""


def test_indent_leading_spaces():
    tok = _classify("    result = x * y\n")
    assert tok.type == "INDENT"
    assert str(tok) == "    result = x * y"


def test_indent_leading_tab():
    tok = _classify("\treturn result\n")
    assert tok.type == "INDENT"


def test_prose_unindented():
    tok = _classify("A discount strategy applies a multiplier.\n")
    assert tok.type == "PROSE"


def test_prose_not_confused_with_indent():
    # Regression: stripped vs line.lstrip() bug caused all prose to
    # be misclassified as INDENT due to the trailing newline difference.
    tok = _classify("Plain prose with no leading whitespace.\n")
    assert tok.type == "PROSE"
