"""Integration tests for the TypeScript claim runner.

These tests actually invoke tsx and are skipped when no runner is
available.  Pure unit tests (harness generation, output parsing) run
unconditionally.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from notlob import from_tree, parse
from notlob.bindings import ClaimResult, Status
from notlob.bindings.typescript.runner import (
    _build_harness,
    _claim_call,
    _iter_assertions,
    _parse_output,
    _tsx_cmd,
    run_examples,
    run_tests,
)


# ── Skip guard ────────────────────────────────────────────────

_HAS_TSX = _tsx_cmd(None) is not None
_RUNNER_SKIP = pytest.mark.skipif(
    not _HAS_TSX,
    reason='tsx or ts-node not found',
)


def _module(text: str):
    return from_tree(parse(text))


# ── Unit: _claim_call ─────────────────────────────────────────

class TestClaimCall:
    def test_equality_split(self):
        call = _claim_call('mod#ex#1', 'x === 5')
        assert '() => (x)' in call
        assert '() => (5)' in call

    def test_boolean_no_split(self):
        call = _claim_call('mod#ex#1', 'arr.every(x => x > 0)')
        assert ', null)' in call

    def test_addr_escaped(self):
        call = _claim_call('mod#ex#1', 'x === 1')
        assert '"mod#ex#1"' in call

    def test_nested_eq_not_split(self):
        # fn(a === b) === c  — should split at the outer ===
        call = _claim_call('addr', 'fn(a === b) === c')
        assert '() => (fn(a === b))' in call
        assert '() => (c)' in call


# ── Unit: _iter_assertions ────────────────────────────────────

class TestIterAssertions:
    def test_single_line(self):
        assert list(_iter_assertions(['x === 1'])) == ['x === 1']

    def test_blank_lines_skipped(self):
        assert list(_iter_assertions(['', 'x === 1', ''])) == ['x === 1']

    def test_multiline_joined(self):
        lines = ['arr.every(', '  x => x > 0)']
        result = list(_iter_assertions(lines))
        assert len(result) == 1
        assert 'arr.every(' in result[0]
        assert 'x => x > 0)' in result[0]

    def test_two_assertions(self):
        lines = ['x === 1', 'y === 2']
        assert list(_iter_assertions(lines)) == ['x === 1', 'y === 2']


# ── Unit: _parse_output ───────────────────────────────────────

class TestParseOutput:
    def test_pass(self):
        out = 'CLAIM\tmod\texpr\nPASS\n'
        results = _parse_output(out, '', 'mod')
        assert len(results) == 1
        assert results[0].status == Status.PASS
        assert results[0].line == 'expr'

    def test_fail_with_sides(self):
        out = 'CLAIM\tmod\ta === b\nFAIL\t"actual"\t"expected"\n'
        results = _parse_output(out, '', 'mod')
        assert results[0].status == Status.FAIL
        assert results[0].left == 'actual'
        assert results[0].right == 'expected'

    def test_fail_no_sides(self):
        out = 'CLAIM\tmod\texpr\nFAIL\n'
        results = _parse_output(out, '', 'mod')
        assert results[0].status == Status.FAIL
        assert results[0].left is None

    def test_error(self):
        out = 'CLAIM\tmod\texpr\nERROR\tsome error\n'
        results = _parse_output(out, '', 'mod')
        assert results[0].status == Status.ERROR
        assert 'some error' in str(results[0].error)

    def test_multiple_claims(self):
        out = (
            'CLAIM\tmod\tx === 1\nPASS\n'
            'CLAIM\tmod\ty === 2\nFAIL\t1\t2\n'
        )
        results = _parse_output(out, '', 'mod')
        assert len(results) == 2
        assert results[0].status == Status.PASS
        assert results[1].status == Status.FAIL


# ── Integration: run_examples ─────────────────────────────────

class TestRunExamplesIntegration:
    @_RUNNER_SKIP
    def test_passing_example(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n~example\n    x === 1\n'
        )
        results = run_examples(mod)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    @_RUNNER_SKIP
    def test_failing_example(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n~example\n    x === 2\n'
        )
        results = run_examples(mod)
        assert results[0].status == Status.FAIL
        assert results[0].left == 1
        assert results[0].right == 2

    @_RUNNER_SKIP
    def test_two_assertions(self):
        mod = _module(
            '#T\n\n    const x = 1\n    const y = 2\n\n'
            '~example\n    x === 1\n    y === 2\n'
        )
        results = run_examples(mod)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)

    @_RUNNER_SKIP
    def test_example_address_format(self):
        mod = _module(
            '#My Module\n\n    const x = 1\n\n~example\n    x === 1\n'
        )
        results = run_examples(mod)
        assert results[0].address == 'my/module#example#1'

    @_RUNNER_SKIP
    def test_boolean_expression(self):
        mod = _module(
            '#T\n\n    const xs = [1, 2, 3]\n\n'
            '~example\n    xs.every(x => x > 0)\n'
        )
        results = run_examples(mod)
        assert results[0].status == Status.PASS

    @_RUNNER_SKIP
    def test_runtime_error_in_claim(self):
        mod = _module(
            '#T\n\n    const xs: number[] = []\n\n'
            '~example\n    (xs as any).noSuchMethod() === 1\n'
        )
        results = run_examples(mod)
        assert results[0].status == Status.ERROR

    @_RUNNER_SKIP
    def test_no_examples_returns_empty(self):
        mod = _module('#T\n\n    const x = 1\n')
        assert run_examples(mod) == []

    @_RUNNER_SKIP
    def test_subheading_example(self):
        mod = _module(
            '#T\n\n##Section\n\n    const x = 42\n\n'
            '~example\n    x === 42\n'
        )
        results = run_examples(mod)
        assert results[0].status == Status.PASS
        assert '#Section#example#1' in results[0].address


# ── Integration: run_tests ────────────────────────────────────

class TestRunTestsIntegration:
    @_RUNNER_SKIP
    def test_passing_test(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n---\n\n#Tests\n    x === 1\n'
        )
        results = run_tests(mod)
        assert results[0].status == Status.PASS

    @_RUNNER_SKIP
    def test_grouped_tests(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n---\n\n#Tests\n\n'
            '##my group\n    x === 1\n'
        )
        results = run_tests(mod)
        assert results[0].status == Status.PASS
        assert '#Tests#my group' in results[0].address

    @_RUNNER_SKIP
    def test_no_tests_section(self):
        mod = _module('#T\n\n    const x = 1\n')
        assert run_tests(mod) == []
