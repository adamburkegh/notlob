"""Tests for the TypeScript expression tokenizer."""

from __future__ import annotations

import pytest

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


class TestFindSplitPrecedence:
    """A line is an equality claim only when `===` is its root operator.

    `&&`, `||`, `??`, a ternary, a comma, an arrow, an assignment and the
    bitwise operators all bind more loosely than `===`, so a line with one
    at the top level is a boolean expression, not an equality: splitting
    it at the `===` compares the wrong things (false failures) and can
    drop the other operand entirely (false passes). See
    meta/bugs/2026-10-12-claim-equality-precedence.
    """

    @pytest.mark.parametrize("expr", [
        '1 === 1 && 2 === 2',
        'a === 1 && b === 0',
        'a === 1 && true',
        '0 === 0 && false',
        'true && b === 0',
        'a === 1 || b === 0',
        'a === 1 || false',
        'a === b ?? c',
        'a === 1 ? x : y',
        'a === 1 & b',
        'a === 1 | b',
        'a === 1 ^ b',
        'a === 1, b === 2',
        'x => x === 1',
        'a = b === 1',
        'typeof x === "string" && x.length === 3',
    ])
    def test_looser_top_level_operator_means_no_split(self, expr):
        assert find_split(expr) is None

    @pytest.mark.parametrize("expr", [
        '(a === 1) && (b === 0)',
        'f(a === 1 && b === 2)',
        '[a === 1 && b]',
    ])
    def test_equality_only_inside_brackets_is_not_a_split(self, expr):
        assert find_split(expr) is None

    @pytest.mark.parametrize("expr", [
        '"a && b" === c',
        "a /* && */ === b",
        'a ?. b === 1',
        'a?.b === 1',
        'a + 1 === b * 2',
        'a < b === true',
        'a >= 1 === true',
        '!a === b',
        'typeof x === "string"',
    ])
    def test_tighter_or_hidden_operator_still_splits(self, expr):
        result = find_split(expr)
        assert result is not None
        assert result[1] == '==='

    def test_chained_equality_splits_at_the_last_one(self):
        """`a === b === c` is `(a === b) === c`: left-associative."""
        expr = 'a === b === c'
        pos, op = find_split(expr)
        assert op == '==='
        assert expr[:pos].rstrip() == 'a === b'

    def test_trailing_not_equal_is_not_a_split(self):
        """The root of `a === b !== c` is the `!==`, which is evaluated
        as a boolean, not reported as left/right."""
        assert find_split('a === b !== c') == (8, '!==')

    def test_loose_equality_is_never_reported_as_triple(self):
        for expr in ('a == b', 'a != b'):
            result = find_split(expr)
            assert result is None or result[1] != '==='


class TestRealClaimLines:
    """Claim lines from pn-chomper (reporter of the precedence bug): the
    bug itself, plus lines that stress the scanner without containing a
    top-level equality (operators inside strings, `?.`/`??`, arrows)."""

    @pytest.mark.parametrize("expr", [
        # the reported line
        '_noDecl.defaults.dot === 1 && _noDecl.defaults.ghost === 0',
        # no top-level ===
        "(_afterCollisionAtNw.eaten?.places ?? []).includes('nw')",
        '[...makeClassicMap().ghostStart.keys()].every('
        'id => makeClassicMap().net.places.has(id))',
        "exportPNML(makeSplitMap(), 'Split').includes("
        "'<initialMarking><text>1</text></initialMarking>')",
        'runTrials(makeDiamondMap, randomPolicy, 200).won >= 20',
    ])
    def test_not_an_equality(self, expr):
        assert find_split(expr) is None

    @pytest.mark.parametrize("expr", [
        # operators `&`, `<`, `>` and quotes live inside string literals
        '''escXml('a & b < c > d "e"') === '''
        '''\'a &amp; b &lt; c &gt; d &quot;e&quot;\'''',
        "tokenCount(makeMandalaMap().ghostStart, 'den') === 1",
    ])
    def test_still_an_equality(self, expr):
        result = find_split(expr)
        assert result is not None
        assert result[1] == '==='


# ── helpers ──────────────────────────────────────────────────

def text_at(pos: int, text: str) -> str:
    return text[pos:pos + 3]
