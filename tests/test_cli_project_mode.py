"""Tests for project-mode (no path arg) behaviour of cmd_test,
cmd_weave, and cmd_graph.

These commands discover the project from CWD when invoked without an
explicit file argument, mirroring the behaviour of ``stack test`` and
``mvn test``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from notlob.commands import cmd_graph, cmd_test, cmd_weave


# ── Helpers ───────────────────────────────────────────────────

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


# ── cmd_test project mode ─────────────────────────────────────

class TestCmdTestProjectMode:
    def test_runs_all_modules(self, tmp_path, monkeypatch):
        """No path arg tests every module in the project."""
        root = _project(tmp_path)
        _write(root, "alpha.lob", (
            "#Alpha\n\n"
            "    def double(x): return x * 2\n\n"
            "~example\n"
            "    double(3) == 6\n"
        ))
        _write(root, "beta.lob", (
            "#Beta\n\n"
            "    def inc(x): return x + 1\n\n"
            "~example\n"
            "    inc(4) == 5\n"
        ))
        monkeypatch.chdir(root)
        assert cmd_test() == 0

    def test_failure_in_one_module_returns_1(self, tmp_path, monkeypatch):
        root = _project(tmp_path)
        _write(root, "good.lob", (
            "#Good\n\n    x = 1\n\n"
            "~example\n    x == 1\n"
        ))
        _write(root, "bad.lob", (
            "#Bad\n\n    x = 1\n\n"
            "~example\n    x == 99\n"   # fails
        ))
        monkeypatch.chdir(root)
        assert cmd_test() == 1

    def test_skips_binding_lob(self, tmp_path, monkeypatch):
        """binding.lob is not tested (it has no claims and its address
        would not match the filename)."""
        root = _project(tmp_path)
        _write(root, "mod.lob", (
            "#Mod\n\n    x = 1\n\n~example\n    x == 1\n"
        ))
        monkeypatch.chdir(root)
        # Should not raise an address-mismatch error for binding.lob.
        assert cmd_test() == 0

    def test_no_project_root_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_test() == 1

    def test_summary_line_printed(self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _write(root, "thing.lob", (
            "#Thing\n\n    x = 1\n\n~example\n    x == 1\n"
        ))
        monkeypatch.chdir(root)
        cmd_test()
        out = capsys.readouterr().out
        assert "passed" in out


# ── cmd_weave project mode ────────────────────────────────────

class TestCmdWeaveProjectMode:
    def test_renders_all_modules(self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _write(root, "alpha.lob", "#Alpha\n\nSome prose.\n")
        _write(root, "beta.lob",  "#Beta\n\nMore prose.\n")
        monkeypatch.chdir(root)
        assert cmd_weave() == 0
        out = capsys.readouterr().out
        assert "Alpha" in out
        assert "Beta" in out

    def test_modules_separated_by_divider(self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _write(root, "alpha.lob", "#Alpha\n\nSome prose.\n")
        _write(root, "beta.lob",  "#Beta\n\nMore prose.\n")
        monkeypatch.chdir(root)
        cmd_weave()
        out = capsys.readouterr().out
        assert "---" in out

    def test_skips_binding_lob(self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _write(root, "mod.lob", "#Mod\n\nContent.\n")
        monkeypatch.chdir(root)
        cmd_weave()
        out = capsys.readouterr().out
        assert "Binding" not in out

    def test_no_project_root_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_weave() == 1

    def test_language_flag_applied(self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _write(root, "mod.lob", "#Mod\n\n    x = 1\n")
        monkeypatch.chdir(root)
        cmd_weave(language="haskell")
        out = capsys.readouterr().out
        assert "```haskell" in out


# ── cmd_graph project mode ────────────────────────────────────

class TestCmdGraphProjectMode:
    def test_no_path_uses_cwd(self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _write(root, "mod.lob", "#Mod\n\n    def f(): pass\n")
        monkeypatch.chdir(root)
        assert cmd_graph() == 0
        data = json.loads(capsys.readouterr().out)
        addresses = [n["address"] for n in data["nodes"]]
        assert "mod" in addresses

    def test_no_project_root_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_graph() == 1
