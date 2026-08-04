"""Tests for the Python symbol extractor.

extract_symbols maps a list of indented code lines (as stored in
CodeBlock.lines) to a list of SymbolInfo objects.  Each carries the
top-level defined name and its dedented source text.
"""

from notlob.bindings.python import extract_symbols
from notlob.bindings.python.symbols import extract_calls


def _names(lines):
    """Helper: extract just the names from extract_symbols output."""
    return [s.name for s in extract_symbols(lines)]


# ── Functions ────────────────────────────────────────────────

def test_function_def():
    assert _names(["    def f(): pass"]) == ["f"]


def test_async_function_def():
    assert _names(["    async def f(): pass"]) == ["f"]


def test_function_with_body():
    lines = [
        "    def apply_discount(strategy, price):",
        "        return price * strategy",
    ]
    assert _names(lines) == ["apply_discount"]


def test_two_functions():
    lines = [
        "    def to_roman(n): pass",
        "    def from_roman(s): pass",
    ]
    assert _names(lines) == ["to_roman", "from_roman"]


# ── Classes ──────────────────────────────────────────────────

def test_class_def():
    assert _names(["    class Discount: pass"]) == ["Discount"]


def test_class_with_methods():
    # Methods are not extracted — only the class name.
    lines = [
        "    class Discount:",
        "        def apply(self): pass",
    ]
    assert _names(lines) == ["Discount"]


# ── Assignments ──────────────────────────────────────────────

def test_simple_assignment():
    assert _names(["    NUMERALS = [1, 2, 3]"]) == ["NUMERALS"]


def test_annotated_assignment():
    assert _names(["    x: int = 1"]) == ["x"]


def test_multi_target_assignment():
    assert _names(["    a = b = 1"]) == ["a", "b"]


# ── Mixed content ────────────────────────────────────────────

def test_mixed_block():
    lines = [
        "    NUMERALS = [(1000, 'M')]",
        "",
        "    def to_roman(n): pass",
        "    class Codec: pass",
    ]
    assert _names(lines) == ["NUMERALS", "to_roman", "Codec"]


# ── Blank lines and dedenting ────────────────────────────────

def test_blank_lines_ignored():
    lines = ["    def f(): pass", "", "    def g(): pass"]
    assert _names(lines) == ["f", "g"]


def test_dedents_before_parsing():
    # Lines have 4 spaces of leading indent; ast.parse requires
    # top-level code at column 0.
    lines = ["    def f():", "        return 1"]
    assert _names(lines) == ["f"]


def test_deeply_indented():
    lines = ["        def f(): pass"]   # 8 spaces
    assert _names(lines) == ["f"]


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
    assert _names(lines) == ["f"]


def test_imports_not_extracted():
    # Imports live in #References, not code blocks.
    lines = ["    import os", "    from pathlib import Path"]
    assert _names(lines) == []


# ── Source extraction ────────────────────────────────────────

def test_function_source():
    lines = [
        "    def to_roman(n):",
        "        return str(n)",
    ]
    result = extract_symbols(lines)
    assert len(result) == 1
    assert result[0].name == "to_roman"
    assert "def to_roman" in result[0].source
    assert "return str(n)" in result[0].source


def test_two_functions_have_separate_source():
    lines = [
        "    def f(): pass",
        "    def g(): pass",
    ]
    result = extract_symbols(lines)
    assert result[0].name == "f"
    assert result[1].name == "g"
    assert "def f" in result[0].source
    assert "def g" in result[1].source
    # Each function's source should not bleed into the other's.
    assert "def g" not in result[0].source
    assert "def f" not in result[1].source


def test_assignment_source():
    result = extract_symbols(["    NUMERALS = [1, 2, 3]"])
    assert result[0].source == "NUMERALS = [1, 2, 3]"


def test_class_source_includes_methods():
    lines = [
        "    class Codec:",
        "        def encode(self): pass",
    ]
    result = extract_symbols(lines)
    assert result[0].name == "Codec"
    assert "encode" in result[0].source


# ── extract_calls ────────────────────────────────────────────

def _call_names(calls):
    return [n for n, _ in calls]


class TestExtractCalls:
    def test_returns_called_names(self):
        src = "def f():\n    return g() + h()"
        names = _call_names(extract_calls(src))
        assert "g" in names
        assert "h" in names

    def test_excludes_builtins(self):
        src = "def f(xs):\n    return len(xs)"
        assert "len" not in _call_names(extract_calls(src))

    def test_excludes_print(self):
        assert "print" not in _call_names(extract_calls("def f():\n    print('hi')"))

    def test_parameter_included_unfiltered(self):
        src = "def f(x):\n    return g(x)"
        names = _call_names(extract_calls(src))
        assert "x" in names
        assert "g" in names

    def test_cross_function_refs(self):
        src = "def pipeline(x):\n    return encode(decode(x))"
        names = _call_names(extract_calls(src))
        assert "encode" in names
        assert "decode" in names

    def test_syntax_error_returns_empty(self):
        assert extract_calls("def f(") == []

    def test_empty_source_returns_empty(self):
        assert extract_calls("") == []

    def test_defined_name_still_included_if_called_recursively(self):
        src = "def fact(n):\n    return n * fact(n - 1)"
        assert "fact" in _call_names(extract_calls(src))

    def test_returns_line_numbers(self):
        src = "def f():\n    return g()\ndef f2():\n    return h()"
        pairs = dict(extract_calls(src))
        assert pairs["g"] == 2
        assert pairs["h"] == 4

    def test_first_occurrence_wins(self):
        src = "def f():\n    g()\ndef f2():\n    g()"
        pairs = dict(extract_calls(src))
        assert pairs["g"] == 2


def test_syntax_error_source_is_not_present():
    result = extract_symbols(["    x = ("])
    assert result == []
