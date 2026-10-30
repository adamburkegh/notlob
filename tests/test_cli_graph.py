"""Tests for the notlob graph and query CLI commands."""

import json
from pathlib import Path

import pytest

from notlob.commands import (
    cmd_graph,
    cmd_query_children, cmd_query_content, cmd_query_resolve,
    cmd_query_search, cmd_query_imports, cmd_query_imported_by,
    cmd_query_callers, cmd_query_callees,
    cmd_query_cites, cmd_query_cited_by,
)


_BINDING = (
    "#Test Project\n\n---\n\n"
    "#Binding\n"
    "    ~language python\n"
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    _write(tmp_path, "binding.lob", _BINDING)
    return tmp_path


EXAMPLES = Path(__file__).parent.parent / "examples"


# ── cmd_graph ─────────────────────────────────────────────────

class TestCmdGraph:
    def test_outputs_valid_json(self, tmp_path, capsys):
        target = _write(tmp_path, "mod.lob", "#Mod\n    def f(): pass\n")
        assert cmd_graph(target, fmt="json") == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "nodes" in data
        assert "edges" in data
        assert (data["version"], data["level"]) == (2, "outline")

    def test_standalone_file_has_module_node(self, tmp_path, capsys):
        target = _write(tmp_path, "roman/numerals.lob",
                        "#Roman Numerals\n    def to_roman(): pass\n")
        cmd_graph(target, fmt="json")
        data  = json.loads(capsys.readouterr().out)
        addrs = {n["address"] for n in data["nodes"]}
        assert "roman/numerals" in addrs

    def test_project_graph_spans_all_modules(self, tmp_path, capsys):
        root = _project(tmp_path)
        _write(root, "lib.lob",  "#Lib\n    def helper(): pass\n")
        _write(root, "app.lob",  "#App\n")
        target = _write(root, "lib.lob",
                        "#Lib\n    def helper(): pass\n")
        cmd_graph(target, fmt="json")
        data  = json.loads(capsys.readouterr().out)
        addrs = {n["address"] for n in data["nodes"]}
        assert "lib" in addrs
        assert "app" in addrs

    def test_node_shapes_valid(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n##Section\n    def f(): pass\n")
        cmd_graph(target, fmt="json")
        data = json.loads(capsys.readouterr().out)
        for node in data["nodes"]:
            assert {"address", "kind"} <= set(node.keys())
            assert node["kind"] in {"MODULE", "SUBHEADING", "SYMBOL", "PROPERTY"}

    def test_edge_shapes_valid(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n##Section\n    def f(): pass\n")
        cmd_graph(target, fmt="json")
        data = json.loads(capsys.readouterr().out)
        for edge in data["edges"]:
            assert {"source", "target", "kind"} <= set(edge.keys())
            assert edge["kind"] in {"CONTAINS", "IMPORTS"}

    def test_a_module_names_its_file_in_a_project(self, tmp_path, capsys):
        root = _project(tmp_path)
        target = _write(root, "pkg/t.lob", "#Pkg T\n    def f(): pass\n")
        cmd_graph(target, fmt="json")
        data = json.loads(capsys.readouterr().out)
        module = next(n for n in data["nodes"] if n["address"] == "pkg/t")
        sym = next(n for n in data["nodes"] if n["kind"] == "SYMBOL")
        assert module["file"] == "pkg/t.lob"
        assert "file" not in sym
        assert sym["start_line"] == 2
        assert "end_line" not in sym


# ── cmd_graph --level ─────────────────────────────────────────

_LEVELLED = "#T\n\nSome text, see #Sec.\n\n    def f(): pass\n\n##Sec\n"


class TestCmdGraphLevel:
    def _run(self, tmp_path, capsys, **kwargs):
        target = _write(tmp_path, "t.lob", _LEVELLED)
        rc = cmd_graph(target, **{"fmt": "json", **kwargs})
        captured = capsys.readouterr()
        return rc, captured

    def test_the_default_is_the_outline(self, tmp_path, capsys):
        rc, captured = self._run(tmp_path, capsys)
        data = json.loads(captured.out)
        assert rc == 0 and data["level"] == "outline"
        assert {n["kind"] for n in data["nodes"]} == {
            "MODULE", "SUBHEADING", "SYMBOL"}

    @pytest.mark.parametrize("level,name", [
        ("outline", "outline"), ("index", "index"), ("full", "full"),
        ("1", "outline"), ("2", "index"), ("3", "full"),
        (1, "outline"), (2, "index"), (3, "full"),
    ])
    def test_a_level_by_name_or_number(self, tmp_path, capsys, level, name):
        rc, captured = self._run(tmp_path, capsys, level=level)
        assert rc == 0
        assert json.loads(captured.out)["level"] == name

    def test_index_adds_the_leaves_and_sizes(self, tmp_path, capsys):
        _rc, captured = self._run(tmp_path, capsys, level="index")
        data = json.loads(captured.out)
        assert {"PROSE", "CODE"} <= {n["kind"] for n in data["nodes"]}
        assert all("size" in n for n in data["nodes"])
        assert all("text" not in n for n in data["nodes"])

    def test_full_adds_the_text(self, tmp_path, capsys):
        _rc, captured = self._run(tmp_path, capsys, level="full")
        data = json.loads(captured.out)
        prose = next(n for n in data["nodes"] if n["kind"] == "PROSE")
        assert prose["text"] == "Some text, see #Sec."

    def test_an_unknown_level_is_an_error_naming_the_choices(
        self, tmp_path, capsys,
    ):
        rc, captured = self._run(tmp_path, capsys, level="detail")
        assert rc == 1 and captured.out == ""
        for choice in ("outline", "index", "full"):
            assert choice in captured.err

    def test_turtle_takes_the_same_levels(self, tmp_path, capsys):
        rc, captured = self._run(tmp_path, capsys, fmt="turtle")
        assert rc == 0 and "notlob:text" not in captured.out
        rc, captured = self._run(tmp_path, capsys, fmt="turtle",
                                 level="full")
        assert rc == 0 and "notlob:text" in captured.out

    def test_there_is_no_content_option(self, tmp_path):
        target = _write(tmp_path, "t.lob", _LEVELLED)
        with pytest.raises(TypeError):
            cmd_graph(target, include_content=True)


# ── cmd_query_children ────────────────────────────────────────

class TestCmdQueryChildren:
    def test_contains_children(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "roman/numerals.lob",
               "#Roman Numerals\n##Decoding\n    code\n")
        monkeypatch.chdir(root)
        assert cmd_query_children("roman/numerals", fmt="json") == 0
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "Decoding" in labels

    def test_a_code_blocks_children_are_its_symbols(
        self, tmp_path, capsys, monkeypatch,
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n    def f(): pass\n")
        monkeypatch.chdir(root)
        cmd_query_children("t#code#1", fmt="json")
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "f" in labels

    def test_defines_is_no_longer_a_choice(
        self, tmp_path, capsys, monkeypatch,
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n    def f(): pass\n")
        monkeypatch.chdir(root)
        assert cmd_query_children("t", "DEFINES") == 1
        assert "DEFINES" in capsys.readouterr().err

    def test_no_project_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_query_children("any/address") == 1


# ── cmd_query_resolve ─────────────────────────────────────────

class TestCmdQueryResolve:
    def test_resolves_subheading(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "roman/numerals.lob",
               "#Roman Numerals\n##Decoding\n    code\n")
        monkeypatch.chdir(root)
        rc   = cmd_query_resolve("Decoding", "roman/numerals")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["address"] == "roman/numerals#Decoding"
        assert data["kind"]    == "SUBHEADING"

    def test_unresolved_returns_null_and_exit_1(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n")
        monkeypatch.chdir(root)
        rc   = cmd_query_resolve("Missing")
        data = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert data is None


# ── cmd_query_search ──────────────────────────────────────────

class TestCmdQuerySearch:
    def test_wildcard_search(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "t.lob", (
            "#T\n"
            "    def apply_discount(): pass\n"
            "    def apply_tax(): pass\n"
            "    def compute(): pass\n"
        ))
        monkeypatch.chdir(root)
        cmd_query_search("apply_*", fmt="json")
        data   = json.loads(capsys.readouterr().out)
        labels = {n["label"] for n in data}
        assert labels == {"apply_discount", "apply_tax"}

    def test_kind_filter(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "t.lob",
               "#T\n##Alpha\n    def alpha(): pass\n")
        monkeypatch.chdir(root)
        cmd_query_search("*", "SYMBOL", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert all(n["kind"] == "SYMBOL" for n in data)

    def test_no_match_returns_empty_array(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n")
        monkeypatch.chdir(root)
        cmd_query_search("nonexistent_*", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_bare_word_auto_wraps_as_substring(
        self, tmp_path, capsys, monkeypatch
    ):
        """A pattern with no wildcards is wrapped as *pattern*."""
        root = _project(tmp_path)
        _write(root, "t.lob", (
            "#T\n"
            "    def apply_discount(): pass\n"
            "    def apply_tax(): pass\n"
        ))
        monkeypatch.chdir(root)
        cmd_query_search("discount", fmt="json")   # no wildcards
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "apply_discount" in labels

    def test_bare_word_no_match_returns_empty(
        self, tmp_path, capsys, monkeypatch
    ):
        """A bare word that matches nothing returns []."""
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n    def compute(): pass\n")
        monkeypatch.chdir(root)
        cmd_query_search("missing", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert data == []


# ── cmd_query_imports / imported_by ───────────────────────────

class TestCmdQueryImports:
    def test_imports(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "lib.lob", "#Lib\n    def f(): pass\n")
        _write(root, "app.lob", (
            "#App\n"
            "---\n"
            "#References\n"
            "    #Lib\n"
        ))
        monkeypatch.chdir(root)
        cmd_query_imports("app", fmt="json")
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "Lib" in labels

    def test_imported_by(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "lib.lob", "#Lib\n    def f(): pass\n")
        _write(root, "app.lob", (
            "#App\n"
            "---\n"
            "#References\n"
            "    #Lib\n"
        ))
        monkeypatch.chdir(root)
        cmd_query_imported_by("lib", fmt="json")
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "App" in labels

    def test_no_imports_returns_empty_array(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "standalone.lob", "#Standalone\n")
        monkeypatch.chdir(root)
        cmd_query_imports("standalone", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert data == []


# ── cmd_graph: no content ─────────────────────────────────────

class TestCmdGraphContent:
    def test_content_absent_at_every_level(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n    def f(): pass\n")
        for level in ("outline", "index", "full"):
            cmd_graph(target, fmt="json", level=level)
            data = json.loads(capsys.readouterr().out)
            for node in data["nodes"]:
                assert "content" not in node

    def test_the_code_of_a_symbol_is_in_its_block_at_full(
        self, tmp_path, capsys,
    ):
        target = _write(tmp_path, "t.lob",
                        "#T\n    def to_roman(n): return str(n)\n")
        cmd_graph(target, fmt="json", level="full")
        data = json.loads(capsys.readouterr().out)
        sym = next(n for n in data["nodes"] if n["kind"] == "SYMBOL")
        assert "text" not in sym
        code = next(n for n in data["nodes"] if n["kind"] == "CODE")
        assert "def to_roman" in code["text"]


# ── cmd_query_content ────────────────────────────────────────

class TestCmdQueryContent:
    def test_a_symbol_alone_has_its_code(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n    def f(): pass\n")
        monkeypatch.chdir(root)
        rc = cmd_query_content("t#f", None, "json")
        node = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert node["address"] == "t#f"
        assert node["kind"] == "SYMBOL"
        assert "content" not in node
        assert "def f" in node["text"]

    def test_module_content_returned(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "lib.lob",
               "#Lib\nThis module provides helpers.\n")
        monkeypatch.chdir(root)
        rc = cmd_query_content("lib", None, "json")
        module = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert module["address"] == "lib"
        (prose,) = module["children"]
        assert module["kind"] == "MODULE"
        assert "helpers" in prose["text"]

    def test_subheading_content_returned(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob",
               "#T\n##Decoding\nConverts input.\n    def f(): pass\n")
        monkeypatch.chdir(root)
        cmd_query_content("t#Decoding", None, "json")
        data = json.loads(capsys.readouterr().out)
        nodes = {n["address"]: n for n in data["children"]}
        assert data["kind"] == "SUBHEADING"
        assert "Converts" in nodes["t#Decoding#prose#1"]["text"]
        assert "def f" in nodes["t#Decoding#code#1"]["text"]

    def test_unknown_address_returns_null_and_exit_1(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n")
        monkeypatch.chdir(root)
        rc = cmd_query_content("t#nonexistent", None, "json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert data is None

    def test_no_project_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_query_content("any/address") == 1


# ── cmd_query_callers / cmd_query_callees ─────────────────────

_CALLER_LOB = (
    "#M\n"
    "    def caller():\n"
    "        return callee()\n"
    "\n"
    "    def callee():\n"
    "        return 1\n"
)


class TestCmdQueryCallers:
    def test_returns_caller_symbol(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "m.lob", _CALLER_LOB)
        monkeypatch.chdir(root)
        rc = cmd_query_callers("m#callee", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        labels = [n["label"] for n in data]
        assert "caller" in labels

    def test_no_callers_returns_empty_array(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "m.lob", _CALLER_LOB)
        monkeypatch.chdir(root)
        cmd_query_callers("m#caller", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_no_project_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_query_callers("any#symbol") == 1


class TestCmdQueryCallees:
    def test_returns_callee_symbol(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "m.lob", _CALLER_LOB)
        monkeypatch.chdir(root)
        rc = cmd_query_callees("m#caller", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        labels = [n["label"] for n in data]
        assert "callee" in labels

    def test_no_callees_returns_empty_array(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "m.lob", _CALLER_LOB)
        monkeypatch.chdir(root)
        cmd_query_callees("m#callee", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_no_project_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_query_callees("any#symbol") == 1


_REFS_LOB = (
    "#Refs\n"
    "See #Section here.\n"
    "##Section\n"
    "    code\n"
)


class TestCmdQueryCites:
    def test_returns_cited_node(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "refs.lob", _REFS_LOB)
        monkeypatch.chdir(root)
        rc = cmd_query_cites("refs", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        labels = [n["label"] for n in data]
        assert "Section" in labels

    def test_no_refs_returns_empty_array(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "refs.lob", _REFS_LOB)
        monkeypatch.chdir(root)
        cmd_query_cites("refs#Section", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_no_project_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_query_cites("any") == 1


class TestCmdQueryReferencedBy:
    def test_returns_referencing_node(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "refs.lob", _REFS_LOB)
        monkeypatch.chdir(root)
        rc = cmd_query_cited_by("refs#Section", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        addrs = [n["address"] for n in data]
        assert "refs" in addrs

    def test_no_referencing_nodes_returns_empty(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "refs.lob", _REFS_LOB)
        monkeypatch.chdir(root)
        cmd_query_cited_by("refs", fmt="json")
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_no_project_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_query_cited_by("any#section") == 1
