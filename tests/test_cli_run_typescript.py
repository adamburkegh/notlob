"""Regression tests for notlob run on TypeScript modules.

cmd_run only special-cased language == "haskell" before falling
through to Python-specific build/execution logic (resolving a Python
interpreter, writing the assembled source to a `.py` file regardless
of what language it actually was). For a TypeScript-bound project this
meant perfectly valid TypeScript source got written to a `.py` file
and handed to the Python interpreter, which failed on the first
TS-specific syntax it hit. `notlob test`/`notlob build` were unaffected
-- they already dispatch per-language through the BindingKit
abstraction; only `notlob run`'s own hardcoded Haskell-or-Python branch
was missing the TypeScript case. Fixed by adding a `_cmd_run_typescript`
mirroring `_cmd_run_haskell`'s shape: build_typescript() (which already
handles ~run's on-load/on-invocation split for `notlob build`) then
execute with tsx/ts-node.

These tests actually invoke tsx/ts-node and are skipped when neither is
available.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from notlob.bindings.typescript.runner import _tsx_cmd
from notlob.commands import cmd_run

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HAS_TSX = _tsx_cmd(_REPO_ROOT) is not None
_RUNNER_SKIP = pytest.mark.skipif(
    not _HAS_TSX,
    reason="no tsx/ts-node found (npm install -D tsx)",
)


@pytest.fixture(autouse=True)
def _tsx_on_path(monkeypatch):
    """cmd_run resolves `root` via find_project_root(path), which for
    a tmp_path-based test project is the tmp dir itself -- it has no
    node_modules, so _tsx_cmd(root) only has PATH left to search.
    tsx here is only installed under this repo's own node_modules/.bin
    (see _HAS_TSX above, which needs _REPO_ROOT specifically), so put
    that on PATH for the duration of each test.
    """
    bin_dir = _REPO_ROOT / "node_modules" / ".bin"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

_TS_BINDING = (
    "#Test Project\n\n---\n\n"
    "#Binding\n"
    "    ~language typescript\n"
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _ts_project(tmp_path: Path) -> Path:
    _write(tmp_path, "binding.lob", _TS_BINDING)
    return tmp_path


@_RUNNER_SKIP
class TestCmdRunTypeScript:
    def test_bare_run_defines_entry_point(self, tmp_path, capsys):
        root = _ts_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    const greet: string = 'hello from run';\n\n"
            "~run\n"
            "    console.log(greet);\n"
        ))
        assert cmd_run(lob) == 0
        assert "hello from run" in capsys.readouterr().out

    def test_on_invocation_same_as_bare(self, tmp_path, capsys):
        root = _ts_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    const greet: string = 'hello again';\n\n"
            "~run on-invocation\n"
            "    console.log(greet);\n"
        ))
        assert cmd_run(lob) == 0
        assert "hello again" in capsys.readouterr().out

    def test_on_load_runs_unconditionally(self, tmp_path, capsys):
        """Unlike Haskell, TypeScript's binding supports ~run on-load
        (build_typescript appends it at module scope unconditionally)
        -- this must actually execute, not error."""
        root = _ts_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    const greet: string = 'on load';\n\n"
            "~run on-load\n"
            "    console.log(greet);\n"
        ))
        assert cmd_run(lob) == 0
        assert "on load" in capsys.readouterr().out

    def test_plain_module_with_no_run_claim(self, tmp_path, capsys):
        """A module with no ~run claim at all still assembles and runs
        -- nothing in cmd_run should require a ~run claim to exist."""
        root = _ts_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    console.log('plain block');\n"
        ))
        assert cmd_run(lob) == 0
        assert "plain block" in capsys.readouterr().out

    def test_output_is_not_written_as_python(self, tmp_path, capsys):
        """Regression guard for the actual reported bug: TypeScript
        syntax that is a hard SyntaxError in Python (a template literal
        with ${} interpolation) must run cleanly, not get written to a
        .py file and handed to a Python interpreter."""
        root = _ts_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    const count: number = 3;\n\n"
            "~run\n"
            "    console.log(`count is ${count} -- not python`);\n"
        ))
        assert cmd_run(lob) == 0
        assert "count is 3 -- not python" in capsys.readouterr().out
