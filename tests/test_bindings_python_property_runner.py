"""Tests for the ~property claim runner.

run_properties() assembles a module, then for each ~property claim
exec's the block into a fresh namespace and calls the decorated
function.  Hypothesis drives the execution.

The binding injects hypothesis names (given, st, settings, HealthCheck,
etc.) into every property claim namespace automatically — no import
needed in claim bodies or #References.
"""

from pathlib import Path

from notlob import parse, parse_file, from_tree
from notlob.bindings.python.runner import ClaimResult, Status, run_properties


EXAMPLES = Path(__file__).parent.parent / "examples"


def ran(source: str) -> list[ClaimResult]:
    return run_properties(from_tree(parse(source)))


# ── Empty / no properties ─────────────────────────────────────

class TestAbsent:
    def test_no_properties(self):
        assert ran("#T\n    x = 1\n") == []

    def test_example_claims_not_run(self):
        src = "#T\n    x = 1\n~example\n    x == 1\n"
        assert ran(src) == []


# ── Pass and fail ─────────────────────────────────────────────

class TestPassFail:
    def test_passing_property(self):
        src = (
            "#T\n    def double(n): return n * 2\n"
            "~property\n"
            "    @given(n=st.integers())\n"
            "    def _(n):\n"
            "        assert double(n) == n * 2\n"
        )
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_failing_property(self):
        src = (
            "#T\n    def f(n): return n\n"
            "~property\n"
            "    @given(n=st.integers())\n"
            "    @settings(suppress_health_check=list(HealthCheck))\n"
            "    def _(n):\n"
            "        assert n >= 0\n"   # fails for negatives
        )
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.FAIL
        assert results[0].error is not None

    def test_error_in_exec(self):
        src = (
            "#T\n    x = 1\n"
            "~property\n"
            "    def _(n)\n"   # missing colon — SyntaxError
        )
        results = ran(src)
        assert results[0].status == Status.ERROR

    def test_no_callable_in_block(self):
        src = "#T\n    x = 1\n~property\n    y = 2\n"
        results = ran(src)
        assert results[0].status == Status.ERROR


# ── Addresses ─────────────────────────────────────────────────

class TestAddresses:
    def test_unnamed_ordinal_address(self):
        src = (
            "#T\n    def f(n): return n\n"
            "~property\n"
            "    @given(n=st.integers())\n"
            "    def _(n): assert f(n) == n\n"
        )
        assert ran(src)[0].address == "t#property#1"

    def test_named_property_address(self):
        src = (
            "#T\n    def f(n): return n\n"
            "~property identity\n"
            "    @given(n=st.integers())\n"
            "    def _(n): assert f(n) == n\n"
        )
        assert ran(src)[0].address == "t#identity"

    def test_subheading_unnamed_address(self):
        src = (
            "#T\n##S\n    def f(n): return n\n"
            "~property\n"
            "    @given(n=st.integers())\n"
            "    def _(n): assert f(n) == n\n"
        )
        assert ran(src)[0].address == "t#S#property#1"

    def test_subheading_named_address(self):
        src = (
            "#T\n##S\n    def f(n): return n\n"
            "~property identity\n"
            "    @given(n=st.integers())\n"
            "    def _(n): assert f(n) == n\n"
        )
        assert ran(src)[0].address == "t#S#identity"

    def test_ordinals_reset_per_subheading(self):
        src = (
            "#T\n    def f(n): return n\n"
            "~property\n"
            "    @given(n=st.integers())\n    def _(n): assert f(n)==n\n"
            "##S\n"
            "~property\n"
            "    @given(n=st.integers())\n    def _(n): assert f(n)==n\n"
        )
        results = ran(src)
        assert results[0].address == "t#property#1"
        assert results[1].address == "t#S#property#1"

    def test_named_function_used_when_no_underscore(self):
        src = (
            "#T\n    def f(n): return n\n"
            "~property\n"
            "    @given(n=st.integers())\n"
            "    def my_prop(n): assert f(n) == n\n"
        )
        assert ran(src)[0].status == Status.PASS


# ── Fresh namespace isolation ─────────────────────────────────

class TestNamespaceIsolation:
    def test_properties_do_not_share_state(self):
        src = (
            "#T\n    def f(n): return n\n"
            "~property\n"
            "    @given(n=st.integers())\n    def _(n): assert f(n)==n\n"
            "~property\n"
            "    @given(n=st.integers())\n    def _(n): assert f(n)==n\n"
        )
        results = ran(src)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)


# ── Integration: example files ────────────────────────────────

class TestExampleFiles:
    def _run(self, path):
        return run_properties(from_tree(parse_file(path)))

    def test_roman_numerals_round_trip(self):
        results = self._run(EXAMPLES / "roman/roman/numerals.lob")
        assert results, "expected at least one ~property claim"
        failures = [r for r in results if r.status != Status.PASS]
        assert failures == [], [(r.address, r.error) for r in failures]

    def test_pricing_discounts_stacking(self):
        results = self._run(EXAMPLES / "retail/pricing/discounts.lob")
        assert results, "expected at least one ~property claim"
        failures = [r for r in results if r.status != Status.PASS]
        assert failures == [], [(r.address, r.error) for r in failures]
