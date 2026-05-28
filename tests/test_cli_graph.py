"""Tests for the notlob graph and query CLI commands."""

import json
from pathlib import Path

import pytest

from notlob.commands import (
    cmd_graph,
    cmd_query_children, cmd_query_content, cmd_query_resolve,
    cmd_query_search, cmd_query_imports, cmd_query_imported_by,
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
        assert cmd_graph(target) == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "nodes" in data
        assert "edges" in data

    def test_standalone_file_has_module_node(self, tmp_path, capsys):
        target = _write(tmp_path, "roman/numerals.lob",
                        "#Roman Numerals\n    def to_roman(): pass\n")
        cmd_graph(target)
        data  = json.loads(capsys.readouterr().out)
        addrs = {n["address"] for n in data["nodes"]}
        assert "roman/numerals" in addrs

    def test_project_graph_spans_all_modules(self, tmp_path, capsys):
        root = _project(tmp_path)
        _write(root, "lib.lob",  "#Lib\n    def helper(): pass\n")
        _write(root, "app.lob",  "#App\n")
        target = _write(root, "lib.lob",
                        "#Lib\n    def helper(): pass\n")
        cmd_graph(target)
        data  = json.loads(capsys.readouterr().out)
        addrs = {n["address"] for n in data["nodes"]}
        assert "lib" in addrs
        assert "app" in addrs

    def test_node_shapes_valid(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n##Section\n    def f(): pass\n")
        cmd_graph(target)
        data = json.loads(capsys.readouterr().out)
        for node in data["nodes"]:
            assert {"address", "label", "kind"} <= set(node.keys())
            assert node["kind"] in {"MODULE", "SUBHEADING", "SYMBOL", "PROPERTY"}

    def test_edge_shapes_valid(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n##Section\n    def f(): pass\n")
        cmd_graph(target)
        data = json.loads(capsys.readouterr().out)
        for edge in data["edges"]:
            assert {"source", "target", "kind"} <= set(edge.keys())
            assert edge["kind"] in {"CONTAINS", "DEFINES", "IMPORTS"}


# ── cmd_query_children ────────────────────────────────────────

class TestCmdQueryChildren:
    def test_contains_children(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "roman/numerals.lob",
               "#Roman Numerals\n##Decoding\n    code\n")
        monkeypatch.chdir(root)
        assert cmd_query_children("roman/numerals") == 0
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "Decoding" in labels

    def test_defines_children(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n    def f(): pass\n")
        monkeypatch.chdir(root)
        cmd_query_children("t", "DEFINES")
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "f" in labels

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
        cmd_query_search("apply_*")
        data   = json.loads(capsys.readouterr().out)
        labels = {n["label"] for n in data}
        assert labels == {"apply_discount", "apply_tax"}

    def test_kind_filter(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "t.lob",
               "#T\n##Alpha\n    def alpha(): pass\n")
        monkeypatch.chdir(root)
        cmd_query_search("*", "SYMBOL")
        data = json.loads(capsys.readouterr().out)
        assert all(n["kind"] == "SYMBOL" for n in data)

    def test_no_match_returns_empty_array(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n")
        monkeypatch.chdir(root)
        cmd_query_search("nonexistent_*")
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
        cmd_query_search("discount")   # no wildcards
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
        cmd_query_search("missing")
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
        cmd_query_imports("app")
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
        cmd_query_imported_by("lib")
        data   = json.loads(capsys.readouterr().out)
        labels = [n["label"] for n in data]
        assert "App" in labels

    def test_no_imports_returns_empty_array(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "standalone.lob", "#Standalone\n")
        monkeypatch.chdir(root)
        cmd_query_imports("standalone")
        data = json.loads(capsys.readouterr().out)
        assert data == []


# ── cmd_graph --content ───────────────────────────────────────

class TestCmdGraphContent:
    def test_content_absent_by_default(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n    def f(): pass\n")
        cmd_graph(target)
        data = json.loads(capsys.readouterr().out)
        for node in data["nodes"]:
            assert "content" not in node

    def test_content_present_with_flag(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n    def f(): pass\n")
        cmd_graph(target, include_content=True)
        data = json.loads(capsys.readouterr().out)
        syms = [n for n in data["nodes"] if n["kind"] == "SYMBOL"]
        assert all("content" in s for s in syms)

    def test_symbol_code_in_content(self, tmp_path, capsys):
        target = _write(tmp_path, "t.lob",
                        "#T\n    def to_roman(n): return str(n)\n")
        cmd_graph(target, include_content=True)
        data = json.loads(capsys.readouterr().out)
        sym = next(n for n in data["nodes"] if n["kind"] == "SYMBOL")
        assert "def to_roman" in sym["content"]["code"]


# ── cmd_query_content ────────────────────────────────────────

class TestCmdQueryContent:
    def test_returns_node_with_content(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n    def f(): pass\n")
        monkeypatch.chdir(root)
        rc = cmd_query_content("t#f")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["address"] == "t#f"
        assert data["kind"] == "SYMBOL"
        assert "content" in data
        assert "def f" in data["content"]["code"]

    def test_module_content_returned(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "lib.lob",
               "#Lib\nThis module provides helpers.\n")
        monkeypatch.chdir(root)
        rc = cmd_query_content("lib")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["kind"] == "MODULE"
        assert "helpers" in data["content"]["prose"]

    def test_subheading_content_returned(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob",
               "#T\n##Decoding\nConverts input.\n    def f(): pass\n")
        monkeypatch.chdir(root)
        cmd_query_content("t#Decoding")
        data = json.loads(capsys.readouterr().out)
        assert data["kind"] == "SUBHEADING"
        assert "Converts" in data["content"]["prose"]
        assert "def f" in data["content"]["code"]

    def test_unknown_address_returns_null_and_exit_1(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _project(tmp_path)
        _write(root, "t.lob", "#T\n")
        monkeypatch.chdir(root)
        rc = cmd_query_content("t#nonexistent")
        data = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert data is None

    def test_no_project_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_query_content("any/address") == 1
