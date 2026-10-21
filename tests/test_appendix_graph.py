"""An ``#Appendix`` is part of the module, so every view of the module sees it.

LANGUAGE.md: Appendix code "is assembled exactly like main-body code" and
its body is "a regular body (prose, code, subheadings, claims)".
meta/bugs/2026-10-19-appendix-not-in-graph/bug.md: the graph's symbol and
claim pass and its reference pass walked only ``module.body``, so a
symbol, claim or prose reference in an Appendix was not in the graph,
``[imports]`` flagged an import used only there, and (as the same walk was
repeated in ``notlob run`` and the claim collectors) Appendix claims were
not collected. Retrospective:
meta/retrospectives/2026-10-19-appendix-blind-spot.

An Appendix is a section of the document with its own title, so it has its
own node (``mod#appendix#N``, kind ``APPENDIX``), contained by the module;
its symbols and claims hang from it and its claims are addressed within it
(``mod#appendix#1#example#1``), as a subheading's are. The graph holds each
node's body (tests/test_graph_body.py); the claim collectors read the
graph, so the assembler, the graph and the collectors cannot disagree about
where a claim is or what it is called.

The consistency tests are the point: the same module seen through the
assembler, the graph and the claim collectors must contain the same
things, wherever in the file the code is written.
"""

from __future__ import annotations

import dataclasses
import itertools
import re
from pathlib import Path

import pytest

import notlob.model as model
from notlob import EdgeKind, NodeKind, build, enrich, from_tree, parse
from notlob.bindings import collect_run_bodies
from notlob.bindings.python import extract_calls, extract_symbols
from notlob.bindings.python.assemble import assemble
from notlob.bindings.python.runner import (
    Status, _collect_example_assertions, _collect_properties,
    run_examples, run_properties,
)
from notlob.check import check_imports, check_style
from notlob.commands import _is_entry_point
from notlob.graph import add_references_edges
from notlob.project import build_package

_WITH_APPENDIX = (
    "#Mod\n\n"
    "Body text.\n\n"
    "    def in_body():\n        return 1\n\n"
    "---\n\n"
    "#Appendix Helpers\n\n"
    "Helper prose.\n\n"
    "    def in_appendix():\n        return 2\n"
)

_WITH_APPENDIX_SUBHEADING = (
    "#Mod\n\nBody.\n\n---\n\n"
    "#Appendix\n\n##Extras\n\nMore.\n\n"
    "    def in_appendix_sub():\n        return 3\n"
)

_TWO_APPENDICES = (
    "#Mod\n\nBody.\n\n---\n\n"
    "#Appendix First\n\n    def one():\n        return 1\n\n"
    "#Appendix Second\n\n    def two():\n        return 2\n"
)


def _module(source: str):
    return from_tree(parse(source))


def _graph(source: str):
    mod = _module(source)
    g = build(mod)
    enrich(g, mod, extract_symbols)
    return g


def _children(g, address: str, kind: EdgeKind) -> set[str]:
    return {n.address for n in g.children(address, kind)}


# ── The Appendix node ─────────────────────────────────────────

class TestAppendixNode:
    def test_has_its_own_node(self):
        node = _graph(_WITH_APPENDIX).node("mod#appendix#1")
        assert node is not None
        assert node.kind == NodeKind.APPENDIX

    def test_label_is_its_title(self):
        assert _graph(_WITH_APPENDIX).node("mod#appendix#1").label == (
            "Appendix Helpers")

    def test_untitled_appendix_is_labelled_appendix(self):
        g = _graph(_WITH_APPENDIX_SUBHEADING)
        assert g.node("mod#appendix#1").label == "Appendix"

    def test_is_contained_by_the_module(self):
        g = _graph(_WITH_APPENDIX)
        assert "mod#appendix#1" in _children(g, "mod", EdgeKind.CONTAINS)

    def test_has_a_source_line(self):
        g = _graph(_WITH_APPENDIX)
        lines = _WITH_APPENDIX.splitlines()
        want = lines.index("#Appendix Helpers") + 1
        assert g.node("mod#appendix#1").start_line == want

    def test_carries_its_own_prose_and_code(self):
        content = _graph(_WITH_APPENDIX).node("mod#appendix#1").content
        assert "Helper prose." in content["prose"]
        assert "def in_appendix" in content["code"]

    def test_the_module_node_holds_only_the_body(self):
        content = _graph(_WITH_APPENDIX).node("mod").content
        assert "Body text." in content["prose"]
        assert "Helper prose." not in content["prose"]
        assert "in_appendix" not in content["code"]

    def test_several_appendices_are_numbered(self):
        g = _graph(_TWO_APPENDICES)
        assert g.node("mod#appendix#1").label == "Appendix First"
        assert g.node("mod#appendix#2").label == "Appendix Second"
        assert _children(g, "mod#appendix#1", EdgeKind.DEFINES) == {
            "mod#one"}
        assert _children(g, "mod#appendix#2", EdgeKind.DEFINES) == {
            "mod#two"}

    def test_no_appendix_no_node(self):
        g = _graph("#Mod\n\nJust text.\n")
        assert list(g.nodes(kind=NodeKind.APPENDIX)) == []

    def test_body_holders_in_document_order(self):
        """The nodes that hold a body, as the graph reports them."""
        g = _graph(_places_source(frozenset(_PLACES)))
        assert [(n.address, n.kind) for n in g.body_holders("mod")] == [
            ("mod", NodeKind.MODULE),
            ("mod#BodySub", NodeKind.SUBHEADING),
            ("mod#appendix#1", NodeKind.APPENDIX),
            ("mod#AppSub", NodeKind.SUBHEADING),
        ]

    def test_no_body_holders_for_an_unknown_module(self):
        assert _graph("#Mod\n").body_holders("other") == []


# ── Symbols ───────────────────────────────────────────────────

class TestAppendixSymbols:
    def test_body_symbol_is_a_node(self):
        """Control: the body's symbol is in the graph."""
        assert _graph(_WITH_APPENDIX).node("mod#in_body") is not None

    def test_appendix_symbol_is_a_node(self):
        node = _graph(_WITH_APPENDIX).node("mod#in_appendix")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL

    def test_appendix_symbol_is_defined_by_the_appendix_node(self):
        g = _graph(_WITH_APPENDIX)
        assert _children(g, "mod#appendix#1", EdgeKind.DEFINES) == {
            "mod#in_appendix"}
        assert _children(g, "mod", EdgeKind.DEFINES) == {"mod#in_body"}

    def test_appendix_subheading_hangs_from_the_appendix_node(self):
        g = _graph(_WITH_APPENDIX_SUBHEADING)
        assert g.node("mod#Extras") is not None
        assert _children(g, "mod#appendix#1", EdgeKind.CONTAINS) == {
            "mod#Extras"}
        assert "mod#Extras" not in _children(g, "mod", EdgeKind.CONTAINS)

    def test_symbol_in_an_appendix_subheading(self):
        g = _graph(_WITH_APPENDIX_SUBHEADING)
        assert g.node("mod#in_appendix_sub") is not None
        assert "mod#in_appendix_sub" in _children(
            g, "mod#Extras", EdgeKind.DEFINES)


# ── Claims ────────────────────────────────────────────────────

_CLAIMS_IN_BOTH = (
    "#Mod\n\n"
    "    def in_body():\n        return 1\n\n"
    "~example\n    in_body() == 1\n\n"
    "---\n\n"
    "#Appendix\n\n"
    "    def in_appendix():\n        return 2\n\n"
    "~example\n    in_appendix() == 2\n\n"
    "~property\n"
    "    @given(n=st.integers(min_value=0, max_value=3))\n"
    "    def _(n):\n        assert in_appendix() == 2\n\n"
    "~run\n    print(in_appendix())\n"
)


class TestAppendixClaims:
    def test_graph_has_a_node_for_each_appendix_claim(self):
        g = _graph(_CLAIMS_IN_BOTH)
        kinds = {n.address: n.kind for n in g.nodes()}
        assert kinds["mod#example#1"] == NodeKind.EXAMPLE      # the body's
        assert kinds["mod#appendix#1#example#1"] == NodeKind.EXAMPLE
        assert kinds["mod#appendix#1#property#1"] == NodeKind.PROPERTY
        assert kinds["mod#appendix#1#run#1"] == NodeKind.RUN

    def test_appendix_claims_hang_from_the_appendix_node(self):
        g = _graph(_CLAIMS_IN_BOTH)
        assert _children(g, "mod#appendix#1", EdgeKind.DEFINES) == {
            "mod#in_appendix", "mod#appendix#1#example#1",
            "mod#appendix#1#property#1", "mod#appendix#1#run#1",
        }
        assert "mod#appendix#1#example#1" not in _children(
            g, "mod", EdgeKind.DEFINES)

    def test_appendix_example_is_run_and_passes(self):
        results = run_examples(_module(_CLAIMS_IN_BOTH))
        assert [(r.address, r.status) for r in results] == [
            ("mod#example#1", Status.PASS),
            ("mod#appendix#1#example#1", Status.PASS),
        ]

    def test_appendix_property_is_run_and_passes(self):
        results = run_properties(_module(_CLAIMS_IN_BOTH))
        assert [(r.address, r.status) for r in results] == [
            ("mod#appendix#1#property#1", Status.PASS),
        ]

    def test_appendix_run_block_is_collected(self):
        on_load, on_invocation = collect_run_bodies(_module(_CLAIMS_IN_BOTH))
        assert on_load == []
        assert on_invocation == ["print(in_appendix())"]

    def test_a_run_block_in_an_appendix_makes_an_entry_point(self):
        assert _is_entry_point(_module(_CLAIMS_IN_BOTH))
        assert not _is_entry_point(_module(_WITH_APPENDIX))

    def test_a_run_block_in_an_appendix_subheading_makes_an_entry_point(self):
        assert _is_entry_point(_module(
            "#Mod\n\n---\n\n#Appendix\n\n##Go\n\n~run\n    print(1)\n"))

    def test_a_failing_appendix_claim_fails(self):
        """A claim in the Appendix must be able to fail: being collected
        is no use if it is not also checked."""
        src = (
            "#Mod\n\n---\n\n#Appendix\n\n"
            "    def f():\n        return 1\n\n"
            "~example\n    f() == 2\n"
        )
        results = run_examples(_module(src))
        assert [r.status for r in results] == [Status.FAIL]

    def test_run_on_load_is_a_run_node_not_a_property(self):
        """The graph once made a `~run on-load` a PROPERTY named
        'on-load' (it compared the sigil to '~run' exactly)."""
        g = _graph("#Mod\n\n~run on-load\n    boot()\n")
        assert g.node("mod#run#1").kind == NodeKind.RUN
        assert list(g.nodes(kind=NodeKind.PROPERTY)) == []


# ── Prose references ──────────────────────────────────────────

class TestAppendixReferences:
    # A #label is a cross-reference only if its first letter is
    # uppercase (LANGUAGE.md), hence the capitalised class name.
    def _edges(self, src: str) -> set[tuple[str, str]]:
        mod = _module(src)
        g = build(mod)
        enrich(g, mod, extract_symbols)
        add_references_edges(g)
        return {(e["source"], e["target"]) for e in g.to_dict()["edges"]
                if e["kind"] == "REFERENCES"}

    def test_reference_in_appendix_prose_comes_from_the_appendix(self):
        edges = self._edges(
            "#Mod\n\n    class InBody:\n        pass\n\n"
            "---\n\n#Appendix\n\nSee #InBody for the definition.\n"
        )
        assert ("mod#appendix#1", "mod#InBody") in edges

    def test_reference_in_appendix_subheading_prose_is_an_edge(self):
        edges = self._edges(
            "#Mod\n\n    class InBody:\n        pass\n\n"
            "---\n\n#Appendix\n\n##Extras\n\nSee #InBody here.\n"
        )
        assert ("mod#Extras", "mod#InBody") in edges

    def test_reference_in_body_prose_is_an_edge(self):
        """Control: the same reference written in the body."""
        edges = self._edges(
            "#Mod\n\nSee #InBody here.\n\n    class InBody:\n        pass\n"
        )
        assert ("mod", "mod#InBody") in edges


# ── The reported symptom: [imports] ───────────────────────────

class TestImportsCheckSeesTheAppendix:
    def _project(self, tmp_path, where: str):
        (tmp_path / "binding.lob").write_text(
            "#P\n\n---\n\n#Binding\n    ~language python\n",
            encoding="utf-8")
        (tmp_path / "alpha.lob").write_text(
            "#Alpha\n\n    def shared():\n        return 1\n",
            encoding="utf-8")
        use = "    def uses_alpha():\n        return shared()\n"
        refs = "#References\n    #Alpha\n"
        body = {
            "body":     f"#Beta\n\n{use}\n---\n\n{refs}",
            "appendix": f"#Beta\n\nText.\n\n---\n\n#Appendix\n\n{use}\n{refs}",
            "none":     f"#Beta\n\nText.\n\n---\n\n{refs}",
        }[where]
        (tmp_path / "beta.lob").write_text(body, encoding="utf-8")
        return build_package(tmp_path, extract_symbols,
                             call_extractor=extract_calls)

    def test_use_in_the_body_is_seen(self, tmp_path):
        """Control."""
        assert check_imports(self._project(tmp_path, "body")) == []

    def test_use_in_the_appendix_is_seen(self, tmp_path):
        """kamtrinia's case: the only use of the import is in the
        Appendix."""
        assert check_imports(self._project(tmp_path, "appendix")) == []

    def test_a_genuinely_unused_import_is_still_flagged(self, tmp_path):
        findings = check_imports(self._project(tmp_path, "none"))
        assert [f.check for f in findings] == ["imports"]


# ── Style guidance: claims in an Appendix ─────────────────────

class TestAppendixClaimStyle:
    """Claims are legal in an Appendix (the grammar reuses the body rule)
    but the design puts examples in the exposition and tests in #Tests,
    so a claim there gets an advisory nudge. ``~run`` is not nudged: the
    design says nothing about it. Decision: Adam, 2026-10-20; the grammar
    may later ban them."""

    def _findings(self, source: str):
        return [f for f in check_style(_graph(source))
                if "Appendix" in f.message]

    def test_example_in_an_appendix_is_flagged(self):
        findings = self._findings(
            "#Mod\n\n---\n\n#Appendix\n\n    x = 1\n\n~example\n    x == 1\n")
        assert len(findings) == 1
        f = findings[0]
        assert (f.check, f.severity) == ("style", "advisory")
        assert f.addresses == ("mod#appendix#1#example#1",)
        assert "~example" in f.message
        assert "#Tests" in f.message

    def test_property_in_an_appendix_is_flagged(self):
        findings = self._findings(
            "#Mod\n\n---\n\n#Appendix\n\n~property\n"
            "    @given(n=st.integers())\n    def _(n):\n        pass\n")
        assert [f.addresses for f in findings] == [
            ("mod#appendix#1#property#1",)]
        assert "~property" in findings[0].message

    def test_claim_in_an_appendix_subheading_is_flagged(self):
        findings = self._findings(
            "#Mod\n\n---\n\n#Appendix\n\n##Extras\n\n    x = 1\n\n"
            "~example\n    x == 1\n")
        assert [f.addresses for f in findings] == [
            ("mod#Extras#example#1",)]

    def test_each_claim_gets_its_own_finding(self):
        findings = self._findings(
            "#Mod\n\n---\n\n#Appendix\n\n    x = 1\n\n"
            "~example\n    x == 1\n\n~example\n    x == 1\n")
        assert len(findings) == 2

    def test_run_in_an_appendix_is_not_flagged(self):
        assert self._findings(
            "#Mod\n\n---\n\n#Appendix\n\n~run\n    print(1)\n") == []

    def test_claims_in_the_body_are_not_flagged(self):
        assert self._findings(
            "#Mod\n\n    x = 1\n\n~example\n    x == 1\n\n"
            "##Sub\n\n    y = 2\n\n~example\n    y == 2\n") == []

    def test_an_appendix_without_claims_is_not_flagged(self):
        assert self._findings(
            "#Mod\n\n---\n\n#Appendix\n\n    def f():\n        return 1\n"
        ) == []


# ── Every view agrees ─────────────────────────────────────────

# The places in a file where code can be written.
_PLACES = ("body", "body_sub", "appendix", "appendix_sub")


def _places_source(places: frozenset[str]) -> str:
    """A module with, in each named place, a function, an ~example, a
    ~property and a ~run."""
    def block(tag: str) -> str:
        return (
            f"{tag} prose.\n\n"
            f"    def fn_{tag}():\n        return 1\n\n"
            f"~example\n    fn_{tag}() == 1\n\n"
            "~property\n"
            "    @given(n=st.integers(min_value=0, max_value=2))\n"
            f"    def _(n):\n        assert fn_{tag}() == 1\n\n"
            f"~run\n    print(fn_{tag}())\n\n"
        )
    out = "#Mod\n\nIntro.\n\n"
    if "body" in places:
        out += block("body")
    if "body_sub" in places:
        out += "##BodySub\n\n" + block("body_sub")
    if "appendix" in places or "appendix_sub" in places:
        out += "---\n\n#Appendix Notes\n\n"
        if "appendix" in places:
            out += block("appendix")
        if "appendix_sub" in places:
            out += "##AppSub\n\n" + block("appendix_sub")
    return out


def _subsets():
    for r in range(1, len(_PLACES) + 1):
        for combo in itertools.combinations(_PLACES, r):
            yield frozenset(combo)


@pytest.mark.parametrize(
    "places", list(_subsets()), ids=lambda s: "+".join(sorted(s)),
)
class TestEveryViewAgrees:
    """The assembler (which reads the parse tree), the graph and the claim
    collectors must find the same things wherever the code is written:
    one view that cannot see a place is blind to it, silently."""

    def _module_and_graph(self, places):
        mod = _module(_places_source(places))
        g = build(mod)
        enrich(g, mod, extract_symbols)
        return mod, g

    def test_assembled_symbols_equal_graph_symbols(self, places):
        mod, g = self._module_and_graph(places)
        assembled = {s.name for s in
                     extract_symbols(assemble(mod).splitlines())}
        in_graph = {n.label for n in g.nodes(kind=NodeKind.SYMBOL)}
        assert assembled == in_graph
        assert len(assembled) == len(places)       # one function each

    def test_example_claims_equal_graph_examples(self, places):
        mod, g = self._module_and_graph(places)
        collected = {addr for addr, _expr, _sl
                     in _collect_example_assertions(mod)}
        in_graph = {n.address for n in g.nodes(kind=NodeKind.EXAMPLE)}
        assert collected == in_graph
        assert len(collected) == len(places)

    def test_property_claims_equal_graph_properties(self, places):
        mod, g = self._module_and_graph(places)
        collected = {p[0] for p in _collect_properties(mod)}
        in_graph = {n.address for n in g.nodes(kind=NodeKind.PROPERTY)}
        assert collected == in_graph
        assert len(collected) == len(places)

    def test_run_blocks_equal_graph_runs(self, places):
        mod, g = self._module_and_graph(places)
        on_load, on_invocation = collect_run_bodies(mod)
        in_graph = list(g.nodes(kind=NodeKind.RUN))
        assert len(on_load) + len(on_invocation) == len(in_graph)
        assert _is_entry_point(mod) == bool(in_graph)
        assert len(in_graph) == len(places)

    def test_appendix_node_exists_iff_the_module_has_an_appendix(
        self, places,
    ):
        _mod, g = self._module_and_graph(places)
        has_appendix = bool(places & {"appendix", "appendix_sub"})
        assert len(list(g.nodes(kind=NodeKind.APPENDIX))) == (
            1 if has_appendix else 0)

    def test_every_function_is_callable_from_a_claim(self, places):
        """End to end: the claims that exist all run, and pass."""
        mod, _g = self._module_and_graph(places)
        results = run_examples(mod)
        assert len(results) == len(places)
        assert all(r.status == Status.PASS for r in results), results


# ── The model's body-holding fields ───────────────────────────

def _grammar_body_holders() -> set[str]:
    """Names of the grammar rules that contain a body: those that use
    ``body``, ``body_item*`` or ``_sub_item*``. Derived from
    ``grammar.lark`` (the formal definition of the syntax), not listed by
    hand, so a body added to the grammar shows up here."""
    text = (Path(model.__file__).parent / "grammar.lark").read_text(
        encoding="utf-8")
    text = re.sub(r"//[^\n]*", "", text)                 # comments
    holders = set()
    # A rule: `name: rhs`, with `|` alternatives on continuation lines.
    for m in re.finditer(
        r"^([a-z_]\w*)[ \t]*:[ \t]*(.*(?:\n[ \t]+\|.*)*)", text, re.M,
    ):
        name, rhs = m.group(1), m.group(2)
        if name in ("body", "body_item", "_sub_item"):
            continue                                     # the definitions
        if re.search(r"\bbody\b(?!_)|\bbody_item\*|\b_sub_item\*", rhs):
            holders.add(name)
    return holders


def _camel(rule: str) -> str:
    return "".join(part.capitalize() for part in rule.split("_"))


class TestModelBodies:
    def test_grammar_body_holders_are_found(self):
        """Canary for the extraction above: it must find the module, the
        subheading and the appendix, and not the #Tests section."""
        holders = _grammar_body_holders()
        assert {"module", "subheading", "appendix_section"} <= holders
        assert "tests_section" not in holders

    def test_model_fields_holding_bodies_match_the_grammar(self):
        """The model has a body field for exactly the grammar's body
        holders. If the grammar gains one (or the model a field that
        holds body items), this fails until the graph's ``build`` (the one
        place that walks the parse tree for bodies) and the assemblers are
        taught about it: the omission this guards against was silent."""
        in_model = set()
        for name, cls in vars(model).items():
            if not (isinstance(cls, type) and dataclasses.is_dataclass(cls)):
                continue
            for f in dataclasses.fields(cls):
                annotation = str(f.type)
                if "BodyItem" in annotation or "CodeBlock" in annotation:
                    in_model.add(name)
        assert in_model == {_camel(r) for r in _grammar_body_holders()}

    def test_the_appendix_section_has_a_source_line(self):
        src = _WITH_APPENDIX
        mod = _module(src)
        section = next(s for s in mod.post_text.sections
                       if isinstance(s, model.AppendixSection))
        assert section.start_line == src.splitlines().index(
            "#Appendix Helpers") + 1
