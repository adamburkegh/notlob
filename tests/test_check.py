"""Tests for notlob.check — semantic consistency checker."""

from __future__ import annotations

from notlob.graph import Edge, EdgeKind, NameGraph, Node, NodeKind
from notlob.check import (
    Finding, run_checks,
    check_typos, check_conventions, check_titles,
    _levenshtein,
)


def _sym(module: str, name: str) -> tuple[Node, Edge]:
    """Create a SYMBOL node and its DEFINES edge."""
    addr = f"{module}#{name}"
    node = Node(address=addr, label=name, kind=NodeKind.SYMBOL)
    edge = Edge(source=module, target=addr, kind=EdgeKind.DEFINES)
    return node, edge


def _mod(address: str, label: str) -> Node:
    return Node(address=address, label=label, kind=NodeKind.MODULE)


def _sub(module: str, label: str) -> Node:
    return Node(
        address=f"{module}#{label}",
        label=label,
        kind=NodeKind.SUBHEADING,
    )


# ── _levenshtein ─────────────────────────────────────────────

class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("abc", "abc") == 0

    def test_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_both_empty(self):
        assert _levenshtein("", "") == 0

    def test_single_substitution(self):
        assert _levenshtein("kitten", "sitten") == 1

    def test_single_deletion(self):
        assert _levenshtein("abc", "ab") == 1

    def test_single_insertion(self):
        assert _levenshtein("ab", "abc") == 1

    def test_classic_example(self):
        assert _levenshtein("kitten", "sitting") == 3


# ── check_typos ──────────────────────────────────────────────

class TestCheckTypos:
    def test_near_duplicate_in_same_module(self):
        g = NameGraph()
        g.add_node(_mod("pricing/discounts", "Pricing Discounts"))
        n1, e1 = _sym("pricing/discounts", "calculate_discount")
        n2, e2 = _sym("pricing/discounts", "calcualte_discount")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        findings = check_typos(g)
        assert len(findings) == 1
        assert findings[0].check == "typos"
        assert "distance" in findings[0].message

    def test_distant_names_no_finding(self):
        g = NameGraph()
        g.add_node(_mod("m", "M"))
        n1, e1 = _sym("m", "apply_discount")
        n2, e2 = _sym("m", "total_price")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        assert check_typos(g) == []

    def test_short_names_ignored(self):
        g = NameGraph()
        g.add_node(_mod("m", "M"))
        n1, e1 = _sym("m", "foo")
        n2, e2 = _sym("m", "bar")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        assert check_typos(g) == []

    def test_sibling_modules(self):
        g = NameGraph()
        g.add_node(_mod("pricing/discounts", "Discounts"))
        g.add_node(_mod("pricing/margins", "Margins"))
        n1, e1 = _sym("pricing/discounts", "apply_rate")
        n2, e2 = _sym("pricing/margins", "apply_ratte")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        findings = check_typos(g)
        assert len(findings) == 1

    def test_identical_names_no_finding(self):
        g = NameGraph()
        g.add_node(_mod("a", "A"))
        g.add_node(_mod("b", "B"))
        n1, e1 = _sym("a", "apply_discount")
        n2, e2 = _sym("b", "apply_discount")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        assert check_typos(g) == []

    def test_empty_graph(self):
        assert check_typos(NameGraph()) == []


# ── check_conventions ────────────────────────────────────────

class TestCheckConventions:
    def test_synonym_verbs_flagged(self):
        g = NameGraph()
        g.add_node(_mod("a", "A"))
        g.add_node(_mod("b", "B"))
        n1, e1 = _sym("a", "get_price")
        n2, e2 = _sym("b", "fetch_price")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        findings = check_conventions(g)
        assert len(findings) == 1
        assert "price" in findings[0].message

    def test_same_verb_no_finding(self):
        g = NameGraph()
        g.add_node(_mod("a", "A"))
        g.add_node(_mod("b", "B"))
        n1, e1 = _sym("a", "get_price")
        n2, e2 = _sym("b", "get_name")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        assert check_conventions(g) == []

    def test_non_synonym_verbs_no_finding(self):
        g = NameGraph()
        g.add_node(_mod("a", "A"))
        g.add_node(_mod("b", "B"))
        n1, e1 = _sym("a", "get_price")
        n2, e2 = _sym("b", "set_price")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        assert check_conventions(g) == []

    def test_single_word_names_skipped(self):
        g = NameGraph()
        g.add_node(_mod("m", "M"))
        n1, e1 = _sym("m", "discount")
        g.add_node(n1); g.add_edge(e1)
        assert check_conventions(g) == []

    def test_unknown_verb_skipped(self):
        g = NameGraph()
        g.add_node(_mod("a", "A"))
        g.add_node(_mod("b", "B"))
        n1, e1 = _sym("a", "run_task")
        n2, e2 = _sym("b", "start_task")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        assert check_conventions(g) == []

    def test_empty_graph(self):
        assert check_conventions(NameGraph()) == []


# ── check_titles ─────────────────────────────────────────────

class TestCheckTitles:
    def test_similar_titles_flagged(self):
        g = NameGraph()
        g.add_node(_mod("a", "Price Calculation"))
        g.add_node(_mod("b", "Calculation Price"))
        findings = check_titles(g)
        assert len(findings) == 1
        assert "similar" in findings[0].message

    def test_identical_titles_not_flagged(self):
        g = NameGraph()
        g.add_node(_mod("a", "Pricing"))
        g.add_node(_mod("b", "Pricing"))
        assert check_titles(g) == []

    def test_unrelated_titles_no_finding(self):
        g = NameGraph()
        g.add_node(_mod("a", "Price Calculation"))
        g.add_node(_mod("b", "Roman Numerals"))
        assert check_titles(g) == []

    def test_single_word_titles_skipped(self):
        g = NameGraph()
        g.add_node(_mod("a", "Pricing"))
        g.add_node(_mod("b", "Prices"))
        assert check_titles(g) == []

    def test_subheading_titles_checked(self):
        g = NameGraph()
        g.add_node(_mod("a", "Module A"))
        g.add_node(_sub("a", "Discount Rules"))
        g.add_node(_mod("b", "Module B"))
        g.add_node(_sub("b", "Rules Discount"))
        findings = check_titles(g)
        assert len(findings) == 1

    def test_empty_graph(self):
        assert check_titles(NameGraph()) == []


# ── run_checks ───────────────────────────────────────────────

class TestRunChecks:
    def _graph_with_typo(self):
        g = NameGraph()
        g.add_node(_mod("m", "M"))
        n1, e1 = _sym("m", "calculate_discount")
        n2, e2 = _sym("m", "calcualte_discount")
        g.add_node(n1); g.add_edge(e1)
        g.add_node(n2); g.add_edge(e2)
        return g

    def test_all_checks_run_by_default(self):
        g = self._graph_with_typo()
        findings, counts = run_checks(g)
        checks_run = {f.check for f in findings}
        assert "typos" in checks_run
        assert set(counts) == {"typos", "conventions", "titles"}

    def test_filter_by_name(self):
        g = self._graph_with_typo()
        findings, counts = run_checks(g, enabled={"conventions"})
        assert all(f.check == "conventions" for f in findings)
        assert set(counts) == {"conventions"}

    def test_empty_graph_no_findings(self):
        findings, counts = run_checks(NameGraph())
        assert findings == []
        assert all(n == 0 for n in counts.values())

    def test_counts_include_zero_checks(self):
        g = NameGraph()
        g.add_node(_mod("m", "M"))
        _, counts = run_checks(g)
        assert counts["typos"] == 0
        assert counts["conventions"] == 0
        assert counts["titles"] == 0
