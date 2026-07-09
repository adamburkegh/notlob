"""Tests for the TypeScript expression tokenizer."""

from __future__ import annotations


from notlob.bindings.typescript.tokenizer import find_split, is_complete


class TestIsComplete:
    def test_empty_string(self):
        assert is_complete('') is True

    def test_simple_identifier(self):
        assert is_complete('x') is True

    def test_equality(self):
        assert is_complete('a === b') is True

    def test_function_call(self):
        assert is_complete('f(1, 2)') is True

    def test_unclosed_paren(self):
        assert is_complete('f(1,') is False

    def test_multiline_complete(self):
        assert is_complete('f(1,\n    2)') is True

    def test_multiline_incomplete(self):
        assert is_complete('f(\n    1,') is False

    def test_nested_brackets(self):
        assert is_complete('a[b[c]]') is True

    def test_nested_incomplete(self):
        assert is_complete('a[b[c]') is False

    def test_object_literal(self):
        assert is_complete('{a: 1, b: 2}') is True

    def test_equals_inside_string_not_confused(self):
        assert is_complete('"a === b"') is True

    def test_paren_inside_string_not_confused(self):
        assert is_complete('"f("') is True   # string with paren — complete

    def test_template_literal(self):
        assert is_complete('`hello`') is True

    def test_comment_ignored(self):
        assert is_complete('x // (unclosed') is True

    def test_block_comment(self):
        assert is_complete('x /* ( */ + y') is True

    def test_arrow_function(self):
        assert is_complete('arr.every(x => x > 0)') is True

    def test_chained_call_incomplete(self):
        assert is_complete('arr.every(\n    x =>') is False


class TestFindSplit:
    def test_simple_equality(self):
        assert find_split('a === b') == (2, '===')

    def test_with_spaces(self):
        pos, op = find_split('foo === bar')
        assert text_at(pos, 'foo === bar') == '==='
        assert op == '==='

    def test_function_call_lhs(self):
        pos, op = find_split('dist([0, 0], [3, 4]) === 5')
        assert op == '==='
        assert pos == len('dist([0, 0], [3, 4]) ')

    def test_nested_equals_not_split(self):
        # The === inside fn() is at depth 1, should be skipped
        result = find_split('fn(a === b) === c')
        assert result is not None
        pos, op = result
        assert op == '==='
        # The split should be at the outer ===, after fn(a === b)
        lhs = 'fn(a === b) === c'[:pos]
        assert lhs.strip() == 'fn(a === b)'

    def test_no_split_boolean(self):
        assert find_split('Boolean(x)') is None

    def test_no_split_chain(self):
        assert find_split('arr.every(a => a >= 0)') is None

    def test_not_equal(self):
        result = find_split('a !== b')
        assert result == (2, '!==')

    def test_equals_inside_string_ignored(self):
        # No top-level === in 'foo === bar' because it's all a string
        assert find_split('"foo === bar"') is None

    def test_split_gives_correct_sides(self):
        expr = 'AXES.length === 5'
        pos, op = find_split(expr)
        lhs = expr[:pos].rstrip()
        rhs = expr[pos + 3:].lstrip()
        assert lhs == 'AXES.length'
        assert rhs == '5'

    def test_multiline_expression(self):
        expr = 'kmeans(MEDIA, 3).length\n  === MEDIA.length'
        result = find_split(expr)
        assert result is not None
        pos, op = result
        assert op == '==='
        lhs = expr[:pos].rstrip()
        assert 'kmeans' in lhs


# ── helpers ──────────────────────────────────────────────────

def text_at(pos: int, text: str) -> str:
    return text[pos:pos + 3]
