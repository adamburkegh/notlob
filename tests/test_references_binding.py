"""`#References` and `#Binding` are in the graph.

The last two post-text sections were the only parts of a `.lob` file the
graph did not hold. A line under `#References` is a listing (`#Title`,
told apart by the grammar) or an import statement of the bound language
(one node for each statement, found by the binding); a line under
`#Binding` is a declaration, with its facts as fields. The edges they
make, `IMPORTS` and `USES_EXTERNAL`, start at their lines.
"""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from notlob import EdgeKind, NodeKind, build, build_package, enrich
from notlob import from_tree, parse, parse_file
from notlob.bindings import default_split_imports
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import KINDS, LEVELS
from notlob.model import (
    BindingSection, Declaration, ImportLine, Listing, ReferencesSection,
    CodeBlock,
)
from notlob.project import module_lob_refs

EXAMPLES = Path(__file__).parent.parent / "examples"
SCHEMAS = Path(__file__).parent.parent / "notlob" / "schema"


def _references(lines: list[str]) -> ReferencesSection:
    """The `#References` section of a module whose section is *lines*."""
    text = "#M\n\n    x = 1\n\n---\n\n#References\n"
    text += "".join(f"{line}\n" for line in lines)
    module = from_tree(parse(text))
    (section,) = [s for s in module.post_text.sections
                  if isinstance(s, ReferencesSection)]
    return section


def _module(lines: list[str]):
    text = "#M\n\n    x = 1\n\n---\n\n#References\n"
    text += "".join(f"{line}\n" for line in lines)
    return from_tree(parse(text))


def _listed(lines: list[str]) -> list[str]:
    return module_lob_refs(_module(lines))


def _imports(lines: list[str]) -> list[str]:
    return [i.text for i in _references(lines).imports]


# ── The grammar tells a listing from an import line ──────────

class TestListingsAndImportLines:
    """What `parse_lob_refs` and `parse_python_imports` answered from a
    list of lines, which the grammar now answers."""

    @pytest.mark.parametrize("line, address", [
        ("    #Roman Numerals", "roman/numerals"),
        ("    #Pricing Discount Strategies", "pricing/discount/strategies"),
        ("    #Pricing", "pricing"),
    ])
    def test_an_indented_hash_and_a_title_is_a_listing(self, line, address):
        assert _listed([line]) == [address]
        assert _imports([line]) == []

    def test_listings_are_told_from_imports_and_keep_their_order(self):
        lines = ["    #Roman Numerals", "    from decimal import Decimal",
                 "    #Pricing Discounts"]
        assert _listed(lines) == ["roman/numerals", "pricing/discounts"]
        assert _imports(lines) == ["    from decimal import Decimal"]

    def test_the_order_of_listings_is_the_order_written(self):
        assert _listed(["    #A B", "    #C D", "    #E F"]) == [
            "a/b", "c/d", "e/f"]

    def test_any_other_indented_line_is_an_import_line(self):
        lines = ["    from pathlib import Path", "    import os"]
        assert _listed(lines) == []
        assert _imports(lines) == lines

    def test_a_blank_line_is_neither_a_listing_nor_lost(self):
        lines = ["", "    #Roman Numerals", ""]
        assert _listed(lines) == ["roman/numerals"]
        assert _imports(lines) == ["", ""]
        lines = ["    import os", "", "    import sys"]
        assert _imports(lines) == lines

    def test_no_lines_no_listings_no_imports(self):
        assert _listed([]) == []
        assert _imports([]) == []

    def test_a_bare_hash_is_not_a_listing(self):
        assert _listed(["    #"]) == []
        assert _imports(["    #"]) == ["    #"]

    def test_only_listings_leave_no_imports(self):
        lines = ["    #Roman Numerals", "    #Pricing Discounts"]
        assert _imports(lines) == []

    def test_an_import_line_keeps_its_indentation(self):
        (text,) = _imports(["    from pathlib import Path"])
        assert text.startswith("    ")

    def test_a_comment_is_an_import_line_not_a_listing(self):
        lines = ["    # used for parsing", "    #Roman Numerals"]
        assert _listed(lines) == ["roman/numerals"]
        assert _imports(lines) == ["    # used for parsing"]

    def test_two_hashes_are_an_import_line_not_a_listing(self):
        lines = ["    ##Notes", "    #Roman Numerals"]
        assert _listed(lines) == ["roman/numerals"]
        assert _imports(lines) == ["    ##Notes"]

    def test_lines_keep_every_line_in_order(self):
        lines = ["    #A B", "    import os", "", "    ##Notes"]
        assert _references(lines).lines == lines

    def test_each_has_its_line(self):
        section = _references(["    #A B", "    import os", "", "    #C D"])
        assert [(i.title, i.line) for i in section.listings] == [
            ("A B", 8), ("C D", 11)]
        assert [(i.text, i.line) for i in section.imports] == [
            ("    import os", 9), ("", 10)]

    def test_a_hash_comment_in_a_code_block_is_untouched(self):
        module = from_tree(parse("#M\n\n    # a comment\n    #Name = 1\n"))
        (block,) = [b for b in module.body if isinstance(b, CodeBlock)]
        assert block.lines == ["    # a comment", "    #Name = 1"]


# ── The model keeps each declaration, with its line ──────────

_BINDING = (
    "#B\n\n---\n\n#Binding\n"
    "    ~language python\n"
    "    ~external data/pg1524.txt\n"
    "    ~on-build build.py\n"
    "    ~external data/other.txt\n"
    "    ~keep-generated-src\n"
)


def _binding(source: str = _BINDING) -> BindingSection:
    module = from_tree(parse(source))
    (section,) = [s for s in module.post_text.sections
                  if isinstance(s, BindingSection)]
    return section


class TestDeclarations:
    def test_in_document_order_with_keyword_value_and_line(self):
        assert [(d.keyword, d.value, d.line)
                for d in _binding().declarations] == [
            ("language", "python", 6),
            ("external", "data/pg1524.txt", 7),
            ("on-build", "build.py", 8),
            ("external", "data/other.txt", 9),
            ("keep-generated-src", None, 10),
        ]

    def test_each_keeps_the_line_as_written(self):
        assert [d.text for d in _binding().declarations][:2] == [
            "~language python", "~external data/pg1524.txt"]

    def test_the_typed_fields_stay(self):
        section = _binding()
        assert section.language == "python"
        assert section.externals == ["data/pg1524.txt", "data/other.txt"]
        assert section.on_build == "build.py"

    def test_the_classes_are_the_models(self):
        assert isinstance(_binding().declarations[0], Declaration)
        assert isinstance(_references(["    #A B"]).listings[0], Listing)
        assert isinstance(_references(["    x"]).imports[0], ImportLine)


# ── The kinds ────────────────────────────────────────────────

class TestTheKinds:
    def test_the_sections_are_named_and_are_not_scopes_or_sections(self):
        for kind in (NodeKind.REFERENCES, NodeKind.BINDING):
            facts = KINDS[kind]
            assert facts.segment is None
            assert not (facts.opens_scope or facts.section or facts.region
                        or facts.hidden_at_outline)

    def test_their_lines_are_anonymous_numbered_and_left_out_of_outline(
        self,
    ):
        segments = {NodeKind.LISTING: "listing", NodeKind.IMPORT: "import",
                    NodeKind.DECLARATION: "declaration"}
        for kind, segment in segments.items():
            facts = KINDS[kind]
            assert (facts.segment, facts.numbered) == (segment, True)
            assert facts.hidden_at_outline

    def test_what_outline_leaves_out(self):
        assert {k for k in NodeKind if KINDS[k].hidden_at_outline} == {
            NodeKind.PROSE, NodeKind.CODE, NodeKind.BULLETS,
            NodeKind.LISTING, NodeKind.IMPORT, NodeKind.DECLARATION,
            NodeKind.POST_TEXT}


# ── The nodes ────────────────────────────────────────────────

_SOURCE = (
    "#M\n\n    x = 1\n\n---\n\n#References\n"
    "    #Util\n"                              # 8
    "    import os\n"                          # 9
    "    from decimal import (\n"              # 10
    "        Decimal,\n"                       # 11
    "        ROUND_UP)\n"                      # 12
    "\n"                                       # 13
    "    #Other Thing\n"                       # 14
)


def _graph(source: str = _SOURCE, kit=python_kit, split=True):
    module = from_tree(parse(source))
    graph = build(module, "m.lob")
    enrich(graph, module, kit.extract_symbols,
           kit.split_imports if split else None)
    return graph


class TestReferencesNodes:
    def test_the_section_is_a_named_node_under_the_post_text(self):
        graph = _graph()
        node = graph.node("m#References")
        assert (node.kind, node.label, node.start_line) == (
            NodeKind.REFERENCES, "References", 7)
        assert graph.parent_of("m#References").kind == NodeKind.POST_TEXT
        assert graph.scope_of("m#References") == "m"

    def test_a_listing_is_the_line_as_written(self):
        graph = _graph()
        node = graph.node("m#References#listing#1")
        assert (node.kind, node.label, node.text) == (
            NodeKind.LISTING, "listing#1", "#Util")
        assert (node.start_line, node.end_line, node.file) == (
            8, 8, "m.lob")
        assert graph.node("m#References#listing#2").text == "#Other Thing"

    def test_an_import_is_one_node_for_a_statement(self):
        graph = _graph()
        one = graph.node("m#References#import#1")
        assert (one.kind, one.label, one.text) == (
            NodeKind.IMPORT, "import#1", "import os")
        assert (one.start_line, one.end_line) == (9, 9)
        two = graph.node("m#References#import#2")
        assert two.text == "from decimal import (\n    Decimal,\n    ROUND_UP)"
        assert (two.start_line, two.end_line) == (10, 12)

    def test_the_children_are_in_document_order(self):
        graph = _graph()
        assert [c.address for c in graph.children("m#References")] == [
            "m#References#listing#1", "m#References#import#1",
            "m#References#import#2", "m#References#listing#2"]

    def test_without_a_binding_the_section_and_its_listings_only(self):
        module = from_tree(parse(_SOURCE))
        graph = build(module)
        assert [c.address for c in graph.children("m#References")] == [
            "m#References#listing#1", "m#References#listing#2"]

    def test_without_a_splitter_a_statement_is_a_line(self):
        graph = _graph(split=False)
        assert [c.text for c in graph.children("m#References")
                if c.kind == NodeKind.IMPORT] == [
            "import os", "from decimal import (", "Decimal,", "ROUND_UP)"]

    def test_text_and_size_follow_the_leaves(self):
        doc = _graph().to_dict("full")
        by_address = {n["address"]: n for n in doc["nodes"]}
        assert by_address["m#References#listing#1"]["text"] == "#Util"
        assert "text" not in by_address["m#References"]


_BINDING_GRAPH_SOURCE = (
    "#Proj\n\n---\n\n#Binding\n"
    "    ~language python\n"                    # 6
    "    ~external data/pg1524.txt\n"           # 7
    "    ~keep-generated-src\n"                 # 8
)


class TestBindingNodes:
    def test_the_section_and_its_declarations(self):
        module = from_tree(parse(_BINDING_GRAPH_SOURCE))
        graph = build(module, "binding.lob")
        section = graph.node("proj#Binding")
        assert (section.kind, section.label) == (NodeKind.BINDING, "Binding")
        assert [c.address for c in graph.children("proj#Binding")] == [
            "proj#Binding#declaration#1", "proj#Binding#declaration#2",
            "proj#Binding#declaration#3"]

    def test_a_declaration_has_its_facts_as_fields(self):
        module = from_tree(parse(_BINDING_GRAPH_SOURCE))
        graph = build(module, "binding.lob")
        first = graph.node("proj#Binding#declaration#1")
        assert (first.kind, first.declares, first.value) == (
            NodeKind.DECLARATION, "language", "python")
        assert (first.text, first.start_line, first.end_line) == (
            "~language python", 6, 6)
        external = graph.node("proj#Binding#declaration#2")
        assert (external.declares, external.value) == (
            "external", "data/pg1524.txt")
        bare = graph.node("proj#Binding#declaration#3")
        assert (bare.declares, bare.value) == ("keep-generated-src", None)

    def test_the_fields_print_like_mode(self):
        module = from_tree(parse(_BINDING_GRAPH_SOURCE))
        doc = build(module, "binding.lob").to_dict("index")
        entry = next(n for n in doc["nodes"]
                     if n["address"] == "proj#Binding#declaration#2")
        assert entry["declares"] == "external"
        assert entry["value"] == "data/pg1524.txt"
        assert list(entry)[:4] == [
            "address", "kind", "declares", "value"]
        bare = next(n for n in doc["nodes"]
                    if n["address"] == "proj#Binding#declaration#3")
        assert "value" not in bare
        language = next(n for n in doc["nodes"]
                        if n["address"] == "proj#Binding")
        assert "declares" not in language

    def test_outline_leaves_the_lines_out_and_keeps_the_sections(self):
        module = from_tree(parse(_SOURCE))
        doc = _graph().to_dict("outline")
        addresses = {n["address"] for n in doc["nodes"]}
        assert "m#References" in addresses
        assert not any("#listing#" in a or "#import#" in a
                       for a in addresses)
        module = from_tree(parse(_BINDING_GRAPH_SOURCE))
        doc = build(module).to_dict("outline")
        assert "proj#Binding" in {n["address"] for n in doc["nodes"]}
        assert not any("#declaration#" in n["address"]
                       for n in doc["nodes"])


# ── The splitter: where a statement ends is the language's rule ──

def _lines(*texts: str, first: int = 3) -> list[ImportLine]:
    return [ImportLine(t, first + i) for i, t in enumerate(texts)]


class TestTheStatementSplitter:
    def test_the_default_is_one_statement_for_each_nonblank_line(self):
        assert default_split_imports(
            _lines("    a b c", "", "    d e")) == [("a b c", 3), ("d e", 5)]

    def test_every_kit_has_one_and_the_default_is_the_default(self):
        for kit in (python_kit, haskell_kit, typescript_kit):
            assert callable(kit.split_imports)

    def test_python_one_line(self):
        assert python_kit.split_imports(_lines("    import os")) == [
            ("import os", 3)]

    def test_python_two_statements_and_a_blank_line(self):
        assert python_kit.split_imports(_lines(
            "    import os", "", "    import sys")) == [
            ("import os", 3), ("import sys", 5)]

    def test_python_parentheses(self):
        assert python_kit.split_imports(_lines(
            "    from decimal import (",
            "        Decimal,",
            "        ROUND_UP)",
            "    import os")) == [
            ("from decimal import (\n    Decimal,\n    ROUND_UP)", 3),
            ("import os", 6)]

    def test_python_a_backslash_continuation(self):
        assert python_kit.split_imports(_lines(
            "    from os import \\", "        path", "    import sys")) == [
            ("from os import \\\n    path", 3), ("import sys", 5)]

    def test_python_a_comment_line_is_no_statement(self):
        assert python_kit.split_imports(_lines(
            "    # used for parsing", "    import os")) == [
            ("import os", 4)]

    def test_python_what_it_cannot_parse_falls_back_to_lines(self):
        assert python_kit.split_imports(_lines(
            "    from x import (", "    import os")) == [
            ("from x import (", 3), ("import os", 4)]

    def test_typescript_one_line(self):
        assert typescript_kit.split_imports(_lines(
            "    import { a } from 'x'")) == [("import { a } from 'x'", 3)]

    def test_typescript_braces(self):
        assert typescript_kit.split_imports(_lines(
            "    import {",
            "      a,",
            "      b",
            "    } from 'x'",
            "    import fs from 'fs'")) == [
            ("import {\n  a,\n  b\n} from 'x'", 3),
            ("import fs from 'fs'", 7)]

    def test_haskell_one_line(self):
        assert haskell_kit.split_imports(_lines(
            "    import Data.List (sort)")) == [
            ("import Data.List (sort)", 3)]

    def test_haskell_a_statement_continued_on_indented_lines(self):
        assert haskell_kit.split_imports(_lines(
            "    import Data.List",
            "      (sort,",
            "       nub)",
            "    import Data.Char (toLower)")) == [
            ("import Data.List\n  (sort,\n   nub)", 3),
            ("import Data.Char (toLower)", 6)]


# ── The edges start at their lines ───────────────────────────

def _project(tmp_path: Path, files: dict[str, str], kit=python_kit):
    (tmp_path / "binding.lob").write_text(
        "#Proj\n\n---\n\n#Binding\n    ~language python\n"
        "    ~external data/x.txt\n    ~on-build build.py\n",
        encoding="utf-8")
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return build_package(
        tmp_path, kit.extract_symbols, call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)


_USER = ("#User\n\n    X = f()\n\n---\n\n#References\n"
         "    import os\n    #Lib\n")
_LIB = "#Lib\n\n    def f():\n        return 1\n"


class TestEdgesStartAtTheirLines:
    def test_imports_starts_at_the_listing(self, tmp_path):
        graph = _project(tmp_path, {"user.lob": _USER, "lib.lob": _LIB})
        (edge,) = list(graph.edges(EdgeKind.IMPORTS))
        assert (edge.source, edge.target, edge.start_line) == (
            "user#References#listing#1", "lib", 9)

    def test_a_listing_of_a_module_not_in_the_graph_makes_no_edge(
        self, tmp_path,
    ):
        graph = _project(tmp_path, {"user.lob": _USER})
        assert list(graph.edges(EdgeKind.IMPORTS)) == []
        assert graph.node("user#References#listing#1") is not None

    def test_uses_external_starts_at_the_declaration(self, tmp_path):
        graph = _project(tmp_path, {"user.lob": _USER})
        edges = list(graph.edges(EdgeKind.USES_EXTERNAL))
        assert [(e.source, e.target, e.start_line) for e in edges] == [
            ("proj#Binding#declaration#2", "data/x.txt", 7),
            ("proj#Binding#declaration#3", "build.py", 8)]

    def test_the_outline_holds_none_of_them(self, tmp_path):
        graph = _project(tmp_path, {"user.lob": _USER, "lib.lob": _LIB})
        edges = graph.to_dict("outline")["edges"]
        assert {e["kind"] for e in edges} == {"CONTAINS"}

    def test_at_index_they_start_at_the_line(self, tmp_path):
        graph = _project(tmp_path, {"user.lob": _USER, "lib.lob": _LIB})
        edges = graph.to_dict("index")["edges"]
        assert {"source": "user#References#listing#1", "target": "lib",
                "kind": "IMPORTS", "start_line": 9} in edges


class TestWhatAModuleLists:
    def test_the_modules_it_lists_in_document_order(self, tmp_path):
        graph = _project(tmp_path, {
            "user.lob": ("#User\n\n    X = 1\n\n---\n\n#References\n"
                         "    #Lib\n    import os\n    #Other\n"),
            "lib.lob": _LIB, "other.lob": "#Other\n\n    Y = 1\n"})
        assert [n.address for n in graph.imports_of("user")] == [
            "lib", "other"]

    def test_the_modules_that_list_it(self, tmp_path):
        graph = _project(tmp_path, {
            "a.lob": "#A\n\n    X = 1\n\n---\n\n#References\n    #Lib\n",
            "b.lob": "#B\n\n    X = 1\n\n---\n\n#References\n    #Lib\n",
            "lib.lob": _LIB})
        assert [n.address for n in graph.imported_by("lib")] == ["a", "b"]

    def test_it_is_modules_not_listings(self, tmp_path):
        graph = _project(tmp_path, {"user.lob": _USER, "lib.lob": _LIB})
        assert [n.kind for n in graph.imports_of("user")] == [
            NodeKind.MODULE]
        assert graph.imports_of("lib") == []
        assert graph.imported_by("user") == []


# ── The completeness of the two sections ─────────────────────

_PROJECTS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}


@pytest.mark.parametrize("project", sorted(_PROJECTS))
class TestEveryLineOfTheExamples:
    def _each(self, project):
        kit = _PROJECTS[project]
        root = EXAMPLES / project
        for path in sorted(root.rglob("*.lob")):
            if "node_modules" in path.parts:
                continue
            module = from_tree(parse_file(path))
            graph = build(module)
            enrich(graph, module, kit.extract_symbols, kit.split_imports)
            yield module, graph

    def test_every_listing_import_and_declaration_is_a_node(self, project):
        seen = 0
        for module, graph in self._each(project):
            if module.post_text is None:
                continue
            for section in module.post_text.sections:
                if isinstance(section, ReferencesSection):
                    node = [n for n in graph.nodes()
                            if n.kind == NodeKind.REFERENCES]
                    assert len(node) == 1
                    kids = list(graph.children(node[0].address))
                    listings = [k for k in kids
                                if k.kind == NodeKind.LISTING]
                    assert [(k.text, k.start_line) for k in listings] == [
                        (f"#{x.title}", x.line) for x in section.listings]
                    lines = [k.start_line for k in kids]
                    assert lines == sorted(lines)
                    imported = [k for k in kids
                                if k.kind == NodeKind.IMPORT]
                    covered = {n for k in imported
                               for n in range(k.start_line, k.end_line + 1)}
                    assert {i.line for i in section.imports
                            if i.text.strip()} <= covered
                    seen += len(kids)
                elif isinstance(section, BindingSection):
                    (node,) = [n for n in graph.nodes()
                               if n.kind == NodeKind.BINDING]
                    decls = list(graph.children(node.address))
                    assert [(d.declares, d.value, d.start_line)
                            for d in decls] == [
                        (d.keyword, d.value, d.line)
                        for d in section.declarations]
                    seen += len(decls)
        assert seen, f"{project} has no listing, import or declaration"


# ── Schemas and the ontology ─────────────────────────────────

class TestSchemasAndOntology:
    @pytest.mark.parametrize("level", LEVELS)
    def test_a_document_with_the_new_kinds_validates(self, level, tmp_path):
        import json
        graph = _project(tmp_path, {"user.lob": _USER, "lib.lob": _LIB})
        schema = json.loads(
            (SCHEMAS / "name_graph.json").read_text(encoding="utf-8"))
        jsonschema.validate(graph.to_dict(level), schema)

    def test_the_kinds_and_properties_are_declared(self):
        text = (SCHEMAS / "notlob.ttl").read_text(encoding="utf-8")
        for name in ("References", "Binding", "Listing", "Import",
                     "Declaration"):
            assert f"notlob:{name} a owl:Class" in text
        assert "notlob:declares a owl:DatatypeProperty" in text
        assert "notlob:value a owl:DatatypeProperty" in text

    def test_the_kinds_enum_lists_them(self):
        import json
        for name in ("name_graph.json", "query_result.json"):
            schema = json.loads(
                (SCHEMAS / name).read_text(encoding="utf-8"))
            kinds = [e for e in _enums(schema) if "MODULE" in e]
            assert kinds
            for values in kinds:
                for kind in ("REFERENCES", "BINDING", "LISTING", "IMPORT",
                             "DECLARATION"):
                    assert kind in values


def _enums(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum":
                yield value
            else:
                yield from _enums(value)
    elif isinstance(node, list):
        for item in node:
            yield from _enums(item)
