"""Tests for cross-file CLI behaviour: ModuleCache wiring, -m flag,
and prose cross-reference validation."""

import sys
from pathlib import Path

import pytest

from notlob.cli import cmd_run, cmd_test, _resolve_path
from notlob.project import find_project_root


# ── Shared fixtures ───────────────────────────────────────────

_BINDING = (
    "#Test Project\n\n---\n\n"
    "#Binding\n"
    "    ~language python\n"
    "    ~property-testing hypothesis\n"
    "    ~unit-testing pytest\n"
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    """Write binding.lob and return project root."""
    _write(tmp_path, "binding.lob", _BINDING)
    return tmp_path


# ── find_project_root with directory ─────────────────────────

class TestFindProjectRootDirectory:
    def test_finds_root_from_dir_containing_binding(self, tmp_path):
        (tmp_path / "binding.lob").touch()
        assert find_project_root(tmp_path) == tmp_path

    def test_finds_root_from_subdir(self, tmp_path):
        (tmp_path / "binding.lob").touch()
        sub = tmp_path / "pkg"
        sub.mkdir()
        assert find_project_root(sub) == tmp_path

    def test_returns_none_when_no_binding(self, tmp_path):
        assert find_project_root(tmp_path) is None


# ── cmd_test with cross-file imports ─────────────────────────

class TestCmdTestWithImports:
    def test_imported_names_available_in_examples(self, tmp_path):
        root = _project(tmp_path)
        _write(root, "utils.lob", (
            "#Utils\n\n"
            "    def greet(name):\n"
            "        return f'hello {name}'\n"
        ))
        target = _write(root, "app.lob", (
            "#App\n\n"
            "~example\n"
            "    greet('world') == 'hello world'\n\n"
            "---\n\n"
            "#References\n"
            "    #Utils\n"
        ))
        assert cmd_test(target) == 0

    def test_imported_names_available_in_tests_section(self, tmp_path):
        root = _project(tmp_path)
        _write(root, "math/ops.lob", (
            "#Math Ops\n\n"
            "    def add(a, b):\n"
            "        return a + b\n"
        ))
        target = _write(root, "checker.lob", (
            "#Checker\n\n"
            "---\n\n"
            "#Tests\n"
            "    add(1, 2) == 3\n"
            "    add(0, 0) == 0\n\n"
            "#References\n"
            "    #Math Ops\n"
        ))
        assert cmd_test(target) == 0

    def test_missing_import_produces_error(self, tmp_path):
        root = _project(tmp_path)
        target = _write(root, "bad.lob", (
            "#Bad\n\n"
            "~example\n"
            "    missing_fn() == 1\n\n"
            "---\n\n"
            "#References\n"
            "    #Nonexistent Module\n"
        ))
        assert cmd_test(target) == 1

    def test_no_project_root_cache_is_none(self, tmp_path):
        # A .lob file outside any project still works (no cross-file imports)
        target = _write(tmp_path, "standalone.lob", (
            "#Standalone\n\n"
            "    x = 1\n\n"
            "~example\n"
            "    x == 1\n"
        ))
        assert cmd_test(target) == 0


# ── cmd_run with cross-file imports ──────────────────────────

class TestCmdRunWithImports:
    def test_run_uses_imported_names(self, tmp_path, capsys):
        root = _project(tmp_path)
        _write(root, "greeter.lob", (
            "#Greeter\n\n"
            "    def greet():\n"
            "        return 'hello'\n"
        ))
        target = _write(root, "main.lob", (
            "#Main\n\n"
            "~run\n"
            "    print(greet())\n\n"
            "---\n\n"
            "#References\n"
            "    #Greeter\n"
        ))
        rc = cmd_run(target)
        assert rc == 0
        assert "hello" in capsys.readouterr().out


# ── _resolve_path and -m flag ─────────────────────────────────

class TestResolvePath:
    def test_no_module_mode_returns_path_directly(self, tmp_path):
        p = tmp_path / "foo.lob"
        result = _resolve_path(str(p), module_mode=False)
        assert result == p

    def test_module_mode_resolves_from_project_root(self, tmp_path, monkeypatch):
        (tmp_path / "binding.lob").touch()
        monkeypatch.chdir(tmp_path)
        result = _resolve_path("roman/numerals", module_mode=True)
        assert result == tmp_path / "roman" / "numerals.lob"

    def test_module_mode_exits_without_project_root(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            _resolve_path("roman/numerals", module_mode=True)
        assert exc_info.value.code == 1

    def test_module_mode_with_nested_cwd(self, tmp_path, monkeypatch):
        # binding.lob at root; CWD is a subdirectory
        (tmp_path / "binding.lob").touch()
        sub = tmp_path / "pkg" / "sub"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        result = _resolve_path("roman/numerals", module_mode=True)
        assert result == tmp_path / "roman" / "numerals.lob"


# ── Prose reference validation in cmd_test ───────────────────

class TestCmdTestRefValidation:
    def test_broken_ref_returns_exit_1(self, tmp_path):
        target = _write(tmp_path, "broken.lob", (
            "#Broken\n"
            "See #Missing here.\n"
        ))
        assert cmd_test(target) == 1

    def test_broken_ref_prints_to_stderr(self, tmp_path, capsys):
        target = _write(tmp_path, "broken.lob", (
            "#Broken\n"
            "See #Missing here.\n"
        ))
        cmd_test(target)
        err = capsys.readouterr().err
        assert "unresolved reference" in err
        assert "#Missing" in err

    def test_valid_subheading_ref_does_not_fail(self, tmp_path):
        target = _write(tmp_path, "good.lob", (
            "#Good\n"
            "##Section\n"
            "    code = 1\n"
            "See #Section above.\n"
            "~example\n"
            "    code == 1\n"
        ))
        assert cmd_test(target) == 0

    def test_ref_to_imported_module_does_not_fail(self, tmp_path):
        root = _project(tmp_path)
        _write(root, "lib.lob", "#Lib\n    x = 1\n")
        target = _write(root, "main.lob", (
            "#Main\n"
            "See #Lib for the library.\n"
            "~example\n"
            "    x == 1\n"
            "---\n"
            "#References\n"
            "    #Lib\n"
        ))
        assert cmd_test(target) == 0

    def test_ref_to_unimported_module_fails(self, tmp_path):
        root = _project(tmp_path)
        _write(root, "lib.lob", "#Lib\n    x = 1\n")
        target = _write(root, "main.lob", (
            "#Main\n"
            "See #Lib for the library.\n"
        ))
        # No #References declaration — Lib is not imported
        assert cmd_test(target) == 1

    def test_broken_ref_skips_claims(self, tmp_path, capsys):
        # Claims are not run when refs are broken: the output
        # should contain no PASS/FAIL lines.
        target = _write(tmp_path, "broken.lob", (
            "#Broken\n"
            "See #Missing here.\n"
            "~example\n"
            "    1 == 1\n"
        ))
        cmd_test(target)
        out = capsys.readouterr().out
        assert "PASS" not in out
        assert "FAIL" not in out
