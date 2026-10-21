"""The name-graph is a complete index of the document.

DESIGN.md ("The name-graph is complete") and the paper: the graph is of
"names, prose, concepts and code". Every prose block, code block,
bullet list and claim in a module appears in the graph, with its kind,
text, source position and order within the body that holds it, and the
module's imports appear on the module node.

A body is held by a module, a subheading or an ``#Appendix``; each is a
node, and ``graph.body(address)`` returns its body items in document
order. The oracle below walks the parse tree itself, independently of the
code under test, so these tests are the check of the contract: what the
tree says each body holds equals what the graph says.

meta/bugs/2026-10-20-name-graph-incomplete/bug.md
"""

from __future__ import annotations

import itertools
import json
import textwrap
from pathlib import Path

import jsonschema
import pytest

from notlob import NodeKind, build, enrich, from_tree, parse
from notlob.bindings.python import extract_symbols
from notlob.graph import (
    appendix_address, claim_address, module_address, property_address,
    subheading_address,
)
from notlob.model import (
    AppendixSection, BulletBlock, Claim, CodeBlock, ProseBlock, Ref,
    ReferencesSection, Subheading,
)

SCHEMA = (
    Path(__file__).parent.parent / "notlob" / "schema" / "name_graph.json"
)

_PLACES = ("body", "subheading", "appendix", "appendix subheading")


def _block(tag: str) -> str:
    """Prose with two refs, bullets, code, and one of each claim."""
    t = tag.replace(" ", "_")
    return (
        f"The {tag} prose, with #Ref{t} and ##Sub{t} in it.\n"
        "A second line of the paragraph.\n\n"
        "* first point\n* second point\n\n"
        f"    def fn_{t}():\n        return 1\n\n"
        f"Prose between the code and the claims.\n\n"
        f"~example\n    fn_{t}() == 1\n\n"
        f"~property named_{t}\n"
        "    @given(n=st.integers())\n    def _(n):\n        pass\n\n"
        "~property\n    @given(n=st.integers())\n    def _(n):\n        pass\n\n"
        f"~run on-load\n    print(fn_{t}())\n\n"
    )


def _source(places: frozenset[str]) -> str:
    out = "#Mod\n\nIntro.\n\n"
    if "body" in places:
        out += _block("body")
    if "subheading" in places:
        out += "##BodySub\n\n" + _block("subheading")
    out += "---\n\n#References\n    #Other\n    import json\n\n"
    if places & {"appendix", "appendix subheading"}:
        out += "#Appendix Notes\n\n"
        if "appendix" in places:
            out += _block("appendix")
        if "appendix subheading" in places:
            out += "##AppSub\n\n" + _block("appendix subheading")
    return out


def _subsets():
    for r in range(1, len(_PLACES) + 1):
        for combo in itertools.combinations(_PLACES, r):
            yield frozenset(combo)


def _graph(source: str):
    mod = from_tree(parse(source))
    g = build(mod)
    enrich(g, mod, extract_symbols)
    return mod, g


# ── The oracle: the parse tree, walked independently ──────────

def _prose_text(block: ProseBlock) -> str:
    return "".join(
        s if isinstance(s, str) else ("##" if s.sub else "#") + s.label
        for s in block.spans
    )


def _oracle_entries(items: list, addr: str):
    """What the tree says the body *items* of the node at *addr* are."""
    counts = {"example": 0, "run": 0, "property": 0}
    for item in items:
        if isinstance(item, ProseBlock):
            yield ("prose", _prose_text(item), item.start_line)
        elif isinstance(item, CodeBlock):
            yield ("code", textwrap.dedent("\n".join(item.lines)),
                   item.start_line)
        elif isinstance(item, BulletBlock):
            yield ("bullets", tuple(item.items), item.start_line)
        elif isinstance(item, Claim):
            if item.sigil == "~example":
                counts["example"] += 1
                claim = claim_address(addr, "example", counts["example"])
            elif item.sigil.startswith("~run"):
                counts["run"] += 1
                claim = claim_address(addr, "run", counts["run"])
            else:
                counts["property"] += 1
                parts = item.sigil.split(None, 1)
                claim = (property_address(addr, parts[1].strip())
                         if len(parts) > 1 else
                         claim_address(addr, "property", counts["property"]))
            yield ("claim", claim, item.start_line)


def _oracle_bodies(module) -> list[tuple[str, list]]:
    """``(node address, direct body items)`` for the module, each
    subheading, and each appendix with its subheadings."""
    mod_addr = module_address(module.title)

    def direct(body):
        return [i for i in body if not isinstance(i, Subheading)]

    def subs(body):
        return [(subheading_address(mod_addr, i.title), list(i.body))
                for i in body if isinstance(i, Subheading)]

    out = [(mod_addr, direct(module.body))] + subs(module.body)
    n = 0
    for section in (module.post_text.sections if module.post_text else []):
        if isinstance(section, AppendixSection):
            n += 1
            out.append((appendix_address(mod_addr, n), direct(section.body)))
            out += subs(section.body)
    return out


def _graph_entries(graph, addr: str):
    for e in graph.body(addr):
        kind = e["kind"]
        if kind == "prose":
            yield ("prose", e["text"], e["start_line"])
        elif kind == "code":
            yield ("code", e["text"], e["start_line"])
        elif kind == "bullets":
            yield ("bullets", tuple(e["items"]), e["start_line"])
        elif kind == "claim":
            yield ("claim", e["address"], e["start_line"])
        else:
            raise AssertionError(f"unknown body item kind {kind!r}")


def _ids(places):
    return "+".join(sorted(p.replace(" ", "_") for p in places))


# ── The contract ──────────────────────────────────────────────

@pytest.mark.parametrize("places", list(_subsets()), ids=_ids)
class TestBodyMatchesTheTree:
    def test_every_nodes_body_equals_what_the_tree_holds(self, places):
        mod, g = _graph(_source(places))
        for addr, items in _oracle_bodies(mod):
            assert list(_graph_entries(g, addr)) == list(
                _oracle_entries(items, addr)), addr

    def test_every_body_holding_node_exists(self, places):
        mod, g = _graph(_source(places))
        for addr, _items in _oracle_bodies(mod):
            assert g.node(addr) is not None, addr

    def test_items_are_in_source_order(self, places):
        _mod, g = _graph(_source(places))
        for node in g.nodes():
            lines = [e["start_line"] for e in g.body(node.address)]
            assert lines == sorted(lines), node.address

    def test_every_item_has_a_source_line(self, places):
        _mod, g = _graph(_source(places))
        for node in g.nodes():
            for e in g.body(node.address):
                assert isinstance(e["start_line"], int), (node.address, e)

    def test_prose_refs_are_data(self, places):
        mod, g = _graph(_source(places))
        for addr, items in _oracle_bodies(mod):
            want = [
                [{"label": s.label, "sub": s.sub, "start_line": s.start_line}
                 for s in item.spans if isinstance(s, Ref)]
                for item in items if isinstance(item, ProseBlock)
            ]
            got = [e["refs"] for e in g.body(addr) if e["kind"] == "prose"]
            assert got == want, addr

    def test_claim_nodes_keep_their_sigil_and_lines(self, places):
        mod, g = _graph(_source(places))
        for addr, items in _oracle_bodies(mod):
            entries = [e for e in g.body(addr) if e["kind"] == "claim"]
            claims = [i for i in items if isinstance(i, Claim)]
            assert len(entries) == len(claims)
            for entry, claim in zip(entries, claims):
                node = g.node(entry["address"])
                assert node.content["sigil"] == claim.sigil
                assert node.content["code"] == textwrap.dedent(
                    "\n".join(claim.lines)).rstrip()
                assert node.start_line == claim.start_line

    def test_the_modules_imports_are_on_its_node(self, places):
        mod, g = _graph(_source(places))
        section = next(s for s in mod.post_text.sections
                       if isinstance(s, ReferencesSection))
        want = [
            {"text": line.strip(), "lob_ref": line.strip().startswith("#"),
             "start_line": n}
            for line, n in zip(section.lines, section.line_numbers)
            if line.strip()
        ]
        assert g.node("mod").content["imports"] == want
        assert [i["text"] for i in want] == ["#Other", "import json"]

    def test_the_graph_serialises_with_its_bodies(self, places):
        _mod, g = _graph(_source(places))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(g.to_dict(include_content=True), schema)


# ── Specifics ─────────────────────────────────────────────────

class TestSpecifics:
    def test_run_mode_is_recorded(self):
        _mod, g = _graph(
            "#Mod\n\n~run on-load\n    boot()\n\n~run\n    main()\n")
        assert g.node("mod#run#1").content["sigil"] == "~run on-load"
        assert g.node("mod#run#2").content["sigil"] == "~run"

    def test_an_empty_module_has_an_empty_body(self):
        _mod, g = _graph("#Mod\n")
        assert g.body("mod") == []

    def test_subheadings_are_nodes_not_body_items(self):
        _mod, g = _graph("#Mod\n\nIntro.\n\n##Sub\n\nIn sub.\n")
        assert [e["kind"] for e in g.body("mod")] == ["prose"]
        assert [e["kind"] for e in g.body("mod#Sub")] == ["prose"]

    def test_an_unknown_address_has_no_body(self):
        _mod, g = _graph("#Mod\n\nText.\n")
        assert g.body("no/such#address") == []

    def test_a_symbol_node_has_no_body(self):
        _mod, g = _graph("#Mod\n\n    def f():\n        return 1\n")
        assert g.node("mod#f").kind == NodeKind.SYMBOL
        assert g.body("mod#f") == []

    def test_prose_and_code_concatenations_are_kept(self):
        """The existing `prose` and `code` content (used by checks and
        `query content`) is unchanged by the addition of the body."""
        _mod, g = _graph(
            "#Mod\n\nSome prose.\n\n    x = 1\n\nMore prose.\n")
        content = g.node("mod").content
        assert "Some prose." in content["prose"]
        assert "More prose." in content["prose"]
        assert content["code"].strip() == "x = 1"

    def test_bodies_survive_a_merge(self):
        _mod, g = _graph("#Mod\n\nText.\n")
        merged = type(g)()
        merged.merge(g)
        assert merged.body("mod") == g.body("mod")

    def test_a_claim_keeps_leading_blank_lines_so_offsets_hold(self):
        """A claim's first line is at start_line + 1 only if nothing
        leading was stripped from its source."""
        src = "#Mod\n\n~example\n\n    x == 1\n"
        mod, g = _graph(src)
        node = g.node("mod#example#1")
        assert node.start_line == 3
        assert node.content["code"].splitlines() == ["", "x == 1"]
