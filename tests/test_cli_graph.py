"""Tests for the notlob graph and query CLI commands."""

import json
from pathlib import Path

import pytest

from notlob.commands import (
    cmd_graph,
    cmd_query_children, cmd_query_resolve, cmd_query_search,
    cmd_query_imports, cmd_query_imported_by,
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
