"""Tests for notlob.check — semantic consistency checker."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from notlob.graph import Edge, EdgeKind, NameGraph, Node, NodeKind
from notlob.check import (
    Finding, run_checks, has_errors,
    check_imports, check_typos, check_conventions,
    check_titles, check_references, check_style,
    _levenshtein,
)
from notlob import from_tree, parse
from notlob.project import build_package
from notlob.bindings.python.symbols import extract_symbols


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

    @given(st.text(max_size=30))
    def test_identity(self, s):
        assert _levenshtein(s, s) == 0

    @given(st.text(max_size=30), st.text(max_size=30))
    def test_symmetry(self, a, b):
        assert _levenshtein(a, b) == _levenshtein(b, a)

    @given(st.text(max_size=20), st.text(max_size=20), st.text(max_size=20))
    def test_triangle_inequality(self, a, b, c):
        assert _levenshtein(a, c) <= _levenshtein(a, b) + _levenshtein(b, c)

    @given(st.text(max_size=30), st.text(max_size=30))
    def test_upper_bound(self, a, b):
        assert _levenshtein(a, b) <= max(len(a), len(b))

    @given(st.text(min_size=1, max_size=30))
    def test_empty_vs_nonempty(self, s):
        assert _levenshtein("", s) == len(s)


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
        assert set(counts) == {"imports", "typos", "conventions", "titles", "references", "style"}

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
        assert counts["imports"] == 0
        assert counts["typos"] == 0
        assert counts["conventions"] == 0
        assert counts["titles"] == 0
        assert counts["references"] == 0


# ── check_references ─────────────────────────────────────────

class TestCheckReferences:
    def _graph(self, lob_src):
        """Build an enriched graph from a .lob source string."""
        from notlob.graph import build, enrich
        module = from_tree(parse(lob_src))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        return graph

    def test_unreferenced_symbol_in_prose(self):
        g = self._graph(
            "#Test\n\n"
            "The NUMERALS table maps values.\n\n"
            "    NUMERALS = [(1000, 'M'), (900, 'CM')]\n"
        )
        findings = check_references(g)
        assert len(findings) == 1
        assert findings[0].check == "references"
        assert "NUMERALS" in findings[0].message

    def test_referenced_symbol_no_finding(self):
        g = self._graph(
            "#Test\n\n"
            "The #NUMERALS table maps values.\n\n"
            "    NUMERALS = [(1000, 'M'), (900, 'CM')]\n"
        )
        findings = check_references(g)
        assert findings == []

    def test_referenced_once_used_many_times(self):
        g = self._graph(
            "#Test\n\n"
            "The #NUMERALS table maps values.\n\n"
            "    NUMERALS = [(1000, 'M'), (900, 'CM')]\n\n"
            "We look up NUMERALS for encoding.\n"
            "Each entry in NUMERALS has a value.\n"
        )
        findings = check_references(g)
        assert findings == []

    def test_symbol_not_in_prose_no_finding(self):
        g = self._graph(
            "#Test\n\n"
            "This module handles roman numeral conversion.\n\n"
            "    NUMERALS = [(1000, 'M'), (900, 'CM')]\n"
        )
        findings = check_references(g)
        assert findings == []

    def test_lowercase_symbols_skipped(self):
        g = self._graph(
            "#Test\n\n"
            "We use apply_discount to calculate prices.\n\n"
            "    def apply_discount(rate, price):\n"
            "        return rate * price\n"
        )
        findings = check_references(g)
        assert findings == []

    def test_short_names_skipped(self):
        g = self._graph(
            "#Test\n\n"
            "Set Max to the value.\n\n"
            "    Max = 42\n"
        )
        findings = check_references(g)
        assert findings == []

    def test_empty_graph_returns_empty(self):
        assert check_references(NameGraph()) == []

    def test_substring_not_matched(self):
        g = self._graph(
            "#Test\n\n"
            "We use the Discounter class.\n\n"
            "    class Discount:\n"
            "        pass\n"
        )
        findings = check_references(g)
        assert findings == []


# ── check_imports ────────────────────────────────────────────

class TestCheckImports:
    def test_unused_import_flagged(self, tmp_path):
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")
        self._write(tmp_path, "util.lob",
                    "#Util\n\n    def helper(): return 1\n")
        self._write(tmp_path, "main.lob",
                    "#Main\n\n    x = 42\n"
                    "---\n\n#References\n    #Util\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_imports(graph)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "unused import" in findings[0].message

    def test_used_import_no_finding(self, tmp_path):
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")
        self._write(tmp_path, "util.lob",
                    "#Util\n\n    def helper(): return 1\n")
        self._write(tmp_path, "main.lob",
                    "#Main\n\n    x = helper()\n"
                    "---\n\n#References\n    #Util\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_imports(graph)
        assert findings == []

    def test_no_imports_no_finding(self, tmp_path):
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")
        self._write(tmp_path, "main.lob",
                    "#Main\n\n    x = 42\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_imports(graph)
        assert findings == []

    def test_import_with_no_symbols_skipped(self, tmp_path):
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")
        self._write(tmp_path, "notes.lob",
                    "#Notes\n\nJust prose, no code.\n")
        self._write(tmp_path, "main.lob",
                    "#Main\n\n    x = 42\n"
                    "---\n\n#References\n    #Notes\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_imports(graph)
        assert findings == []

    def test_symbol_used_in_run_block_not_flagged(self, tmp_path):
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")
        self._write(tmp_path, "util.lob",
                    "#Util\n\n    def helper(): pass\n")
        self._write(tmp_path, "main.lob",
                    "#Main\n\n~run\n    helper()\n"
                    "---\n\n#References\n    #Util\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_imports(graph)
        assert findings == []

    def test_symbol_mentioned_in_prose_not_flagged(self, tmp_path):
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")
        self._write(tmp_path, "util.lob",
                    "#Util\n\n    def helper(): pass\n")
        self._write(tmp_path, "main.lob",
                    "#Main\n\nThis module delegates to helper.\n\n"
                    "    x = 42\n"
                    "---\n\n#References\n    #Util\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_imports(graph)
        assert findings == []

    def test_hash_ref_in_prose_not_flagged(self, tmp_path):
        # #Name notation in prose is explicit module usage — should satisfy
        # the unused import checker even when no symbol names appear in text.
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")
        self._write(tmp_path, "game_map.lob",
                    "#Game Map\n\n    class GameMap: pass\n")
        self._write(tmp_path, "main.lob",
                    "#Main\n\nThis module uses the #Game Map module.\n\n"
                    "    x = 42\n"
                    "---\n\n#References\n    #Game Map\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_imports(graph)
        assert findings == []

    def test_empty_graph(self):
        assert check_imports(NameGraph()) == []

    def _write(self, tmp_path, name, content):
        (tmp_path / name).write_text(content, encoding="utf-8")


# ── has_errors ───────────────────────────────────────────────

class TestHasErrors:
    def test_no_findings(self):
        assert has_errors([]) is False

    def test_advisory_only(self):
        f = Finding("typos", "msg", ("a",), severity="advisory")
        assert has_errors([f]) is False

    def test_error_present(self):
        f = Finding("imports", "msg", ("a",), severity="error")
        assert has_errors([f]) is True

    def test_mixed(self):
        f1 = Finding("typos", "msg", ("a",), severity="advisory")
        f2 = Finding("imports", "msg", ("b",), severity="error")
        assert has_errors([f1, f2]) is True


# ── check_style ───────────────────────────────────────────────

class TestCheckStyle:
    def _write(self, tmp_path, name, content):
        (tmp_path / name).write_text(content, encoding="utf-8")

    def _binding(self, tmp_path):
        self._write(tmp_path, "binding.lob",
                    "#P\n\n---\n\n#Binding\n    ~language python\n")

    def test_single_bullet_block_no_finding(self, tmp_path):
        self._binding(tmp_path)
        self._write(tmp_path, "main.lob",
                    "#Main\n\n* item one\n* item two\n\n    x = 1\n")
        graph = build_package(tmp_path, extract_symbols)
        assert check_style(graph) == []

    def test_two_bullet_blocks_triggers_advisory(self, tmp_path):
        self._binding(tmp_path)
        self._write(tmp_path, "main.lob",
                    "#Main\n\n* item one\n* item two\n\n* item three\n\n    x = 1\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_style(graph)
        assert len(findings) == 1
        assert findings[0].severity == "advisory"
        assert findings[0].check == "style"
        assert "2" in findings[0].message

    def test_no_bullets_no_finding(self, tmp_path):
        self._binding(tmp_path)
        self._write(tmp_path, "main.lob",
                    "#Main\n\nJust flowing prose here.\n\n    x = 1\n")
        graph = build_package(tmp_path, extract_symbols)
        assert check_style(graph) == []

    def test_style_in_run_checks(self, tmp_path):
        self._binding(tmp_path)
        self._write(tmp_path, "main.lob",
                    "#Main\n\n* a\n\n* b\n\n* c\n\n    x = 1\n")
        graph = build_package(tmp_path, extract_symbols)
        _, counts = run_checks(graph)
        assert "style" in counts

    def test_advisory_not_error(self, tmp_path):
        self._binding(tmp_path)
        self._write(tmp_path, "main.lob",
                    "#Main\n\n* a\n\n* b\n\n    x = 1\n")
        graph = build_package(tmp_path, extract_symbols)
        findings = check_style(graph)
        assert not has_errors(findings)
