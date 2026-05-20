"""Tests for the Python symbol extractor.

extract_symbols maps a list of indented code lines (as stored in
CodeBlock.lines) to a list of top-level defined names.
"""

import pytest
from notlob.bindings.python import extract_symbols


# ── Functions ────────────────────────────────────────────────

def test_function_def():
    assert extract_symbols(["    def f(): pass"]) == ["f"]


def test_async_function_def():
    assert extract_symbols(["    async def f(): pass"]) == ["f"]


def test_function_with_body():
    lines = [
        "    def apply_discount(strategy, price):",
        "        return price * strategy",
    ]
    assert extract_symbols(lines) == ["apply_discount"]


def test_two_functions():
    lines = [
        "    def to_roman(n): pass",
        "    def from_roman(s): pass",
    ]
    assert extract_symbols(lines) == ["to_roman", "from_roman"]


# ── Classes ──────────────────────────────────────────────────

def test_class_def():
    assert extract_symbols(["    class Discount: pass"]) == ["Discount"]


def test_class_with_methods():
    # Methods are not extracted — only the class name.
    lines = [
        "    class Discount:",
        "        def apply(self): pass",
    ]
    assert extract_symbols(lines) == ["Discount"]


# ── Assignments ──────────────────────────────────────────────

def test_simple_assignment():
    assert extract_symbols(["    NUMERALS = [1, 2, 3]"]) == ["NUMERALS"]


def test_annotated_assignment():
    assert extract_symbols(["    x: int = 1"]) == ["x"]


def test_multi_target_assignment():
    assert extract_symbols(["    a = b = 1"]) == ["a", "b"]


# ── Mixed content ────────────────────────────────────────────

def test_mixed_block():
    lines = [
        "    NUMERALS = [(1000, 'M')]",
        "",
        "    def to_roman(n): pass",
        "    class Codec: pass",
    ]
    result = extract_symbols(lines)
    assert result == ["NUMERALS", "to_roman", "Codec"]


# ── Blank lines and dedenting ────────────────────────────────

def test_blank_lines_ignored():
    lines = ["    def f(): pass", "", "    def g(): pass"]
    assert extract_symbols(lines) == ["f", "g"]


def test_dedents_before_parsing():
    # Lines have 4 spaces of leading indent; ast.parse requires
    # top-level code at column 0.
    lines = ["    def f():", "        return 1"]
    assert extract_symbols(lines) == ["f"]


def test_deeply_indented():
    lines = ["        def f(): pass"]   # 8 spaces
    assert extract_symbols(lines) == ["f"]


# ── Error handling ───────────────────────────────────────────

def test_syntax_error_returns_empty():
    # An incomplete expression is a common case for code fragments.
    assert extract_symbols(["    x = ("]) == []


def test_empty_lines_returns_empty():
    assert extract_symbols([]) == []
    assert extract_symbols([""]) == []


# ── Not extracted ────────────────────────────────────────────

def test_local_variables_not_extracted():
    lines = [
        "    def f():",
        "        local = 1",
        "        return local",
    ]
    assert extract_symbols(lines) == ["f"]


def test_imports_not_extracted():
    # Imports live in #References, not code blocks.
    lines = ["    import os", "    from pathlib import Path"]
    assert extract_symbols(lines) == []
