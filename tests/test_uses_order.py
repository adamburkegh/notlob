"""The order the ``USES`` edges come in.

A symbol's edges come first, and then those of the claims and tests, each
in the order it is in the graph, which is the order of the document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob import EdgeKind, build, build_package, enrich, from_tree, parse
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import KINDS, NodeKind, add_uses_edges

EXAMPLES = Path(__file__).parent.parent / "examples"

_KITS = {
    "roman": python_kit,
    "retail": python_kit,
    "gutenberg": python_kit,
    "haskell-roman": haskell_kit,
    "ts-media": typescript_kit,
}


def _sources(graph) -> list[str]:
    """The source of each run of ``USES`` edges, in order."""
    found: list[str] = []
    for edge in graph.edges(EdgeKind.USES):
        if not found or found[-1] != edge.source:
            found.append(edge.source)
    return found


def _in_order(graph) -> bool:
    """Whether the sources are the symbols, in the graph's order, and then
    the runnable nodes, in the graph's order."""
    sources = _sources(graph)
    position = {n.address: i for i, n in enumerate(graph.nodes())}
    symbols = [a for a in sources
               if graph.node(a).kind == NodeKind.SYMBOL]
    runnable = [a for a in sources
                if KINDS[graph.node(a).kind].runnable]
    return (
        sources == symbols + runnable
        and symbols == sorted(symbols, key=position.__getitem__)
        and runnable == sorted(runnable, key=position.__getitem__)
    )


_SOURCE = (
    "#M\n\n"
    "    def f():\n        return 1\n\n"
    "~property p\n"
    "    @given()\n    def _():\n        assert f() == 1\n\n"
    "~example\n"
    "    f() == 1\n\n"
    "~run\n"
    "    f()\n\n"
    "---\n\n"
    "#Tests\n"
    "    f() == 1\n"
)


class TestSmallModule:
    def _graph(self):
        module = from_tree(parse(_SOURCE))
        graph = build(module)
        enrich(graph, module, python_kit.extract_symbols)
        add_uses_edges(graph, python_kit.extract_calls)
        return graph

    def test_claims_come_in_the_order_they_are_written(self):
        assert _sources(self._graph()) == [
            "m#p", "m#example#1", "m#run#1", "m#Tests#test#1"]

    def test_an_edge_is_kept_for_each_of_them(self):
        edges = {(e.source, e.target)
                 for e in self._graph().edges(EdgeKind.USES)}
        assert edges == {(s, "m#f") for s in (
            "m#p", "m#example#1", "m#run#1", "m#Tests#test#1")}


@pytest.mark.parametrize("project", sorted(_KITS))
def test_an_example_projects_edges_are_in_document_order(project):
    kit = _KITS[project]
    graph = build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls)
    assert _sources(graph)
    assert _in_order(graph)
