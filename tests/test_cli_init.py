"""Tests for notlob.commands.cmd_docs, cmd_init, and cmd_new."""

from __future__ import annotations

import json
import tomllib
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

import notlob
from notlob import commands
from notlob.commands import cmd_docs, cmd_init, cmd_new, _address_to_title


# ── _address_to_title ─────────────────────────────────────────

class TestAddressToTitle:
    def test_single_word(self):
        assert _address_to_title("fibonacci") == "Fibonacci"

    def test_path_segments_become_words(self):
        assert _address_to_title("roman/numerals") == "Roman Numerals"

    def test_hyphens_become_spaces(self):
        assert _address_to_title("my-project") == "My Project"

    def test_underscores_become_spaces(self):
        assert _address_to_title("my_project") == "My Project"

    def test_deep_path(self):
        assert _address_to_title("a/b/c") == "A B C"


# ── cmd_docs ──────────────────────────────────────────────────

class TestCmdDocs:
    def test_creates_language_md(self, tmp_path):
        rc = cmd_docs(tmp_path)
        assert rc == 0
        assert (tmp_path / "LANGUAGE.md").exists()

    def test_default_output_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_docs()
        assert (tmp_path / "notlob-docs" / "LANGUAGE.md").exists()

    def test_output_contains_commands_section(self, tmp_path):
        cmd_docs(tmp_path)
        content = (tmp_path / "LANGUAGE.md").read_text(encoding="utf-8")
        assert "## Commands" in content

    def test_output_contains_claims_section(self, tmp_path):
        cmd_docs(tmp_path)
        content = (tmp_path / "LANGUAGE.md").read_text(encoding="utf-8")
        assert "~example" in content
        assert "~property" in content

    def test_creates_output_dir_if_absent(self, tmp_path):
        out = tmp_path / "nested" / "docs"
        assert not out.exists()
        cmd_docs(out)
        assert out.exists()

    def test_returns_zero(self, tmp_path):
        assert cmd_docs(tmp_path) == 0

    def test_full_also_writes_design_md(self, tmp_path):
        cmd_docs(tmp_path, full=True)
        assert (tmp_path / "LANGUAGE.md").exists()
        assert (tmp_path / "DESIGN.md").exists()
        assert (tmp_path / "USER-AGENTS.md").exists()

    def test_default_does_not_write_design_md(self, tmp_path):
        cmd_docs(tmp_path)
        assert not (tmp_path / "DESIGN.md").exists()

    @pytest.mark.parametrize("language", ["python", "haskell", "typescript"])
    def test_writes_binding_docs(self, tmp_path, language):
        """LANGUAGE.md points readers at each binding's BINDING.md, so
        the default output must include them."""
        cmd_docs(tmp_path)
        source = (
            Path(notlob.__file__).parent / "bindings" / language / "BINDING.md"
        ).read_text(encoding="utf-8")
        written = tmp_path / f"BINDING-{language}.md"
        assert written.read_text(encoding="utf-8") == source

    def test_writes_registered_external_binding_doc(
        self, tmp_path, monkeypatch,
    ):
        """A binding registered under the `notlob.bindings` entry-point
        group by an outside package is documented too, as long as its
        package directory carries a BINDING.md."""
        pkg = tmp_path / "site" / "fake_rust_binding"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("raise RuntimeError('not imported')")
        (pkg / "BINDING.md").write_text("# Rust Binding\n", encoding="utf-8")
        monkeypatch.syspath_prepend(str(pkg.parent))
        monkeypatch.setattr(
            commands, "entry_points",
            lambda group: [EntryPoint("rust", "fake_rust_binding", group)],
        )
        out = tmp_path / "out"
        cmd_docs(out)
        assert (out / "BINDING-rust.md").read_text(
            encoding="utf-8") == "# Rust Binding\n"

    def test_registered_binding_without_doc_is_skipped(
        self, tmp_path, monkeypatch,
    ):
        """No BINDING.md (or a single-module binding, or an unfindable
        one) must not break `notlob docs`."""
        pkg = tmp_path / "site" / "no_doc_binding"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (tmp_path / "site" / "single_module.py").write_text("")
        monkeypatch.syspath_prepend(str(pkg.parent))
        monkeypatch.setattr(
            commands, "entry_points",
            lambda group: [
                EntryPoint("nodoc", "no_doc_binding", group),
                EntryPoint("single", "single_module", group),
                EntryPoint("gone", "no_such_module_anywhere", group),
            ],
        )
        out = tmp_path / "out"
        assert cmd_docs(out) == 0
        assert sorted(p.name for p in out.iterdir()) == ["LANGUAGE.md"]

    def test_every_binding_doc_is_packaged(self):
        """A BINDING.md missing from package-data would be written by
        `notlob docs` from a source checkout but absent from an install."""
        root = Path(notlob.__file__).parent.parent
        listed = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )["tool"]["setuptools"]["package-data"]["notlob"]
        on_disk = {
            p.relative_to(root / "notlob").as_posix()
            for p in (root / "notlob" / "bindings").glob("*/BINDING.md")
        }
        assert on_disk <= set(listed)


# ── cmd_init ──────────────────────────────────────────────────

class TestCmdInit:
    def test_creates_binding_lob(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init()
        assert (tmp_path / "binding.lob").exists()

    def test_binding_contains_language(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="python")
        content = (tmp_path / "binding.lob").read_text()
        assert "~language python" in content

    def test_creates_starter_module(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init()
        lob_files = [p for p in tmp_path.iterdir()
                     if p.suffix == ".lob" and p.name != "binding.lob"]
        assert len(lob_files) == 1

    def test_creates_agents_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init()
        assert (tmp_path / "AGENTS.md").exists()

    def test_agents_md_contains_commands(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init()
        content = (tmp_path / "AGENTS.md").read_text()
        assert "notlob test" in content
        assert "notlob query" in content

    def test_creates_notlob_docs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init()
        assert (tmp_path / "notlob-docs" / "LANGUAGE.md").exists()

    def test_bare_skips_agents_and_docs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(bare=True)
        assert not (tmp_path / "AGENTS.md").exists()
        assert not (tmp_path / "notlob-docs").exists()

    def test_bare_still_creates_binding(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(bare=True)
        assert (tmp_path / "binding.lob").exists()

    def test_fails_if_binding_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "binding.lob").write_text("existing", encoding="utf-8")
        assert cmd_init() == 1

    def test_returns_zero_on_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_init() == 0

    def test_haskell_language(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="haskell")
        content = (tmp_path / "binding.lob").read_text()
        assert "~language haskell" in content

    def test_project_title_from_dirname(self, tmp_path, monkeypatch):
        project = tmp_path / "my-cool-project"
        project.mkdir()
        monkeypatch.chdir(project)
        cmd_init()
        content = (project / "binding.lob").read_text()
        assert "My Cool Project" in content


# ── cmd_init — TypeScript toolchain scaffolding ──────────────

class TestCmdInitTypeScript:
    def test_creates_package_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="typescript")
        assert (tmp_path / "package.json").exists()

    def test_package_json_declares_toolchain(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="typescript")
        data = json.loads((tmp_path / "package.json").read_text())
        deps = data["devDependencies"]
        assert "tsx" in deps
        assert "typescript" in deps

    def test_package_json_name_from_dirname(self, tmp_path, monkeypatch):
        project = tmp_path / "my-ts-app"
        project.mkdir()
        monkeypatch.chdir(project)
        cmd_init(language="typescript")
        data = json.loads((project / "package.json").read_text())
        assert data["name"] == "my_ts_app"

    def test_creates_tsconfig(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="typescript")
        tsconfig = tmp_path / "tsconfig.json"
        assert tsconfig.exists()
        opts = json.loads(tsconfig.read_text())["compilerOptions"]
        assert opts["target"] == "ES2020"
        assert "DOM" in opts["lib"]

    def test_python_creates_no_package_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="python")
        assert not (tmp_path / "package.json").exists()
        assert not (tmp_path / "tsconfig.json").exists()

    def test_haskell_creates_no_package_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="haskell")
        assert not (tmp_path / "package.json").exists()

    def test_bare_still_scaffolds_toolchain(self, tmp_path, monkeypatch):
        # The toolchain manifest is essential (not docs), so --bare keeps it.
        monkeypatch.chdir(tmp_path)
        cmd_init(language="typescript", bare=True)
        assert (tmp_path / "package.json").exists()
        assert (tmp_path / "tsconfig.json").exists()

    def test_existing_package_json_preserved(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing = '{"name": "mine", "dependencies": {"left-pad": "1.0.0"}}'
        (tmp_path / "package.json").write_text(existing, encoding="utf-8")
        cmd_init(language="typescript")
        # Untouched — notlob must not clobber an existing manifest.
        assert (tmp_path / "package.json").read_text() == existing

    def test_valid_json_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cmd_init(language="typescript")
        # Both files parse as JSON (no hand-quoting errors).
        json.loads((tmp_path / "package.json").read_text())
        json.loads((tmp_path / "tsconfig.json").read_text())


# ── cmd_new ───────────────────────────────────────────────────

class TestCmdNew:
    def _project(self, tmp_path: Path) -> Path:
        (tmp_path / "binding.lob").write_text(
            "#Test\n\n---\n\n#Binding\n    ~language python\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_creates_lob_file(self, tmp_path, monkeypatch):
        root = self._project(tmp_path)
        monkeypatch.chdir(root)
        cmd_new("hello")
        assert (root / "hello.lob").exists()

    def test_nested_address_creates_subdirectory(self, tmp_path, monkeypatch):
        root = self._project(tmp_path)
        monkeypatch.chdir(root)
        cmd_new("roman/numerals")
        assert (root / "roman" / "numerals.lob").exists()

    def test_title_derived_from_address(self, tmp_path, monkeypatch):
        root = self._project(tmp_path)
        monkeypatch.chdir(root)
        cmd_new("roman/numerals")
        content = (root / "roman" / "numerals.lob").read_text()
        assert content.startswith("#Roman Numerals")

    def test_strips_lob_suffix_if_given(self, tmp_path, monkeypatch):
        root = self._project(tmp_path)
        monkeypatch.chdir(root)
        cmd_new("hello.lob")
        assert (root / "hello.lob").exists()
        assert not (root / "hello.lob.lob").exists()

    def test_fails_if_file_exists(self, tmp_path, monkeypatch):
        root = self._project(tmp_path)
        monkeypatch.chdir(root)
        (root / "hello.lob").write_text("#Hello\n", encoding="utf-8")
        assert cmd_new("hello") == 1

    def test_fails_outside_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cmd_new("hello") == 1

    def test_returns_zero_on_success(self, tmp_path, monkeypatch):
        root = self._project(tmp_path)
        monkeypatch.chdir(root)
        assert cmd_new("hello") == 0
