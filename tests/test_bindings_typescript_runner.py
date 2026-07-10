"""Integration tests for the TypeScript claim runner.

These tests actually invoke tsx and are skipped when no runner is
available.  Pure unit tests (harness generation, output parsing) run
unconditionally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob import from_tree, parse
from notlob.bindings import Status
from notlob.bindings.typescript.runner import (
    _claim_call,
    _fast_check_available,
    _iter_assertions,
    _parse_output,
    _tsx_cmd,
    run_examples,
    run_properties,
    run_tests,
)


# ── Skip guard ────────────────────────────────────────────────
#
# The repo-root node_modules holds the TypeScript toolchain (tsx, tsc),
# paralleling notlobenv for Python.  Integration tests discover the
# runner there by passing a root-bearing cache, so they run whenever
# the toolchain is installed (``npm install`` at the repo root) rather
# than requiring tsx on PATH.

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HAS_TSX = _tsx_cmd(_REPO_ROOT) is not None
_RUNNER_SKIP = pytest.mark.skipif(
    not _HAS_TSX,
    reason='tsx not found (run `npm install` at the repo root)',
)


class _RootCache:
    """Minimal cache stand-in exposing only ``.root`` for runner
    toolchain discovery.  Synthetic test modules have no lob-ref deps,
    so no module loading is needed."""

    def __init__(self, root: Path):
        self.root = root


_TS_CACHE = _RootCache(_REPO_ROOT)


def _module(text: str):
    return from_tree(parse(text))


def _run_examples(mod):
    return run_examples(mod, cache=_TS_CACHE)


def _run_tests(mod):
    return run_tests(mod, cache=_TS_CACHE)


def _run_properties(mod, binding=None):
    return run_properties(mod, binding=binding, cache=_TS_CACHE)


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
        result = list(_iter_assertions(['x === 1']))
        assert [e for e, _ in result] == ['x === 1']

    def test_blank_lines_skipped(self):
        result = list(_iter_assertions(['', 'x === 1', '']))
        assert [e for e, _ in result] == ['x === 1']

    def test_multiline_joined(self):
        lines = ['arr.every(', '  x => x > 0)']
        result = list(_iter_assertions(lines))
        assert len(result) == 1
        assert 'arr.every(' in result[0][0]
        assert 'x => x > 0)' in result[0][0]

    def test_two_assertions(self):
        lines = ['x === 1', 'y === 2']
        result = list(_iter_assertions(lines))
        assert [e for e, _ in result] == ['x === 1', 'y === 2']

    def test_line_offsets(self):
        lines = ['x === 1', '', 'y === 2']
        result = list(_iter_assertions(lines))
        assert result == [('x === 1', 0), ('y === 2', 2)]


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
        results = _run_examples(mod)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    @_RUNNER_SKIP
    def test_failing_example(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n~example\n    x === 2\n'
        )
        results = _run_examples(mod)
        assert results[0].status == Status.FAIL
        assert results[0].left == 1
        assert results[0].right == 2

    @_RUNNER_SKIP
    def test_two_assertions(self):
        mod = _module(
            '#T\n\n    const x = 1\n    const y = 2\n\n'
            '~example\n    x === 1\n    y === 2\n'
        )
        results = _run_examples(mod)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)

    @_RUNNER_SKIP
    def test_example_address_format(self):
        mod = _module(
            '#My Module\n\n    const x = 1\n\n~example\n    x === 1\n'
        )
        results = _run_examples(mod)
        assert results[0].address == 'my/module#example#1'

    @_RUNNER_SKIP
    def test_boolean_expression(self):
        mod = _module(
            '#T\n\n    const xs = [1, 2, 3]\n\n'
            '~example\n    xs.every(x => x > 0)\n'
        )
        results = _run_examples(mod)
        assert results[0].status == Status.PASS

    @_RUNNER_SKIP
    def test_runtime_error_in_claim(self):
        mod = _module(
            '#T\n\n    const xs: number[] = []\n\n'
            '~example\n    (xs as any).noSuchMethod() === 1\n'
        )
        results = _run_examples(mod)
        assert results[0].status == Status.ERROR

    @_RUNNER_SKIP
    def test_no_examples_returns_empty(self):
        mod = _module('#T\n\n    const x = 1\n')
        assert _run_examples(mod) == []

    @_RUNNER_SKIP
    def test_subheading_example(self):
        mod = _module(
            '#T\n\n##Section\n\n    const x = 42\n\n'
            '~example\n    x === 42\n'
        )
        results = _run_examples(mod)
        assert results[0].status == Status.PASS
        assert '#Section#example#1' in results[0].address


# ── Integration: run_tests ────────────────────────────────────

class TestRunTestsIntegration:
    @_RUNNER_SKIP
    def test_passing_test(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n---\n\n#Tests\n    x === 1\n'
        )
        results = _run_tests(mod)
        assert results[0].status == Status.PASS

    @_RUNNER_SKIP
    def test_grouped_tests(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n---\n\n#Tests\n\n'
            '##my group\n    x === 1\n'
        )
        results = _run_tests(mod)
        assert results[0].status == Status.PASS
        assert '#Tests#my group' in results[0].address

    @_RUNNER_SKIP
    def test_no_tests_section(self):
        mod = _module('#T\n\n    const x = 1\n')
        assert _run_tests(mod) == []

    @_RUNNER_SKIP
    def test_named_test_in_group(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n---\n\n#Tests\n\n'
            '##my group\n    x === 1\n\n'
            '~test named_case\n    x === 1\n'
        )
        results = _run_tests(mod)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)
        addrs = {r.address for r in results}
        assert any(a.endswith('#Tests#my group') for a in addrs)
        assert any(a.endswith('#Tests#my group#named_case') for a in addrs)

    @_RUNNER_SKIP
    def test_named_test_failure_reported(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n---\n\n#Tests\n\n'
            '##my group\n~test broken\n    x === 99\n'
        )
        results = _run_tests(mod)
        assert len(results) == 1
        assert results[0].status == Status.FAIL
        assert results[0].address.endswith('#Tests#my group#broken')


# ── Unit: _fast_check_available ──────────────────────────────

class TestFastCheckAvailable:
    def test_true_when_fast_check_in_node_modules(self):
        assert _fast_check_available(_REPO_ROOT) is True

    def test_false_when_root_is_none(self):
        assert _fast_check_available(None) is False

    def test_false_when_fast_check_absent(self, tmp_path):
        assert _fast_check_available(tmp_path) is False


# ── Integration: run_properties ──────────────────────────────

_FC_SKIP = pytest.mark.skipif(
    not _fast_check_available(_REPO_ROOT),
    reason='fast-check not installed (run `npm install` at repo root)',
)


class TestRunPropertiesIntegration:
    @_RUNNER_SKIP
    @_FC_SKIP
    def test_passing_property(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n'
            '~property\n'
            '    fc.assert(fc.property(fc.constant(x), v => v === 1))\n'
        )
        results = _run_properties(mod)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    @_RUNNER_SKIP
    @_FC_SKIP
    def test_named_property_address(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n'
            '~property identity\n'
            '    fc.assert(fc.property(fc.constant(x), v => v === 1))\n'
        )
        results = _run_properties(mod)
        assert results[0].status == Status.PASS
        assert 'identity' in results[0].address

    @_RUNNER_SKIP
    @_FC_SKIP
    def test_failing_property(self):
        mod = _module(
            '#T\n\n    const x = 1\n\n'
            '~property\n'
            '    fc.assert(fc.property(fc.integer(), n => n === 0))\n'
        )
        results = _run_properties(mod)
        assert results[0].status == Status.ERROR  # fast-check raises on counterexample

    @_RUNNER_SKIP
    @_FC_SKIP
    def test_property_in_subheading(self):
        mod = _module(
            '#T\n\n##Section\n\n    const y = 42\n\n'
            '~property\n'
            '    fc.assert(fc.property(fc.constant(y), v => v === 42))\n'
        )
        results = _run_properties(mod)
        assert results[0].status == Status.PASS
        assert '#Section' in results[0].address

    @_RUNNER_SKIP
    @_FC_SKIP
    def test_no_properties_returns_empty(self):
        mod = _module('#T\n\n    const x = 1\n')
        assert _run_properties(mod) == []

    def test_fast_check_absent_returns_error(self, tmp_path):
        """Without fast-check, ~property claims error rather than skip."""
        mod = _module(
            '#T\n\n    const x = 1\n\n'
            '~property\n'
            '    fc.assert(fc.property(fc.constant(x), v => v === 1))\n'
        )

        class _NoFCCache:
            root = tmp_path  # tmp_path has no node_modules

        results = run_properties(mod, cache=_NoFCCache())
        assert len(results) == 1
        assert results[0].status == Status.ERROR
        assert 'fast-check' in str(results[0].error)
