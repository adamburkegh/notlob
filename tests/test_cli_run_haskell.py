"""Regression tests for notlob run on Haskell modules.

_cmd_run_haskell previously assembled via assemble_with_deps directly,
which only walks CodeBlock nodes -- ~run claim bodies (where `main` is
conventionally defined) were silently dropped, so `notlob run` on any
module relying on ~run for its entry point failed with
"Not in scope: 'main'". Fixed by routing through build_haskell, which
already handles ~run's on-load/on-invocation split correctly for
`notlob build`.

These tests actually invoke runghc/stack and are skipped when neither
is available.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from notlob.commands import cmd_run

_HAS_RUNNER = shutil.which("runghc") is not None or shutil.which("stack") is not None
_RUNNER_SKIP = pytest.mark.skipif(
    not _HAS_RUNNER,
    reason="no Haskell runner found (install runghc or stack)",
)

_HS_BINDING = (
    "#Test Project\n\n---\n\n"
    "#Binding\n"
    "    ~language haskell\n"
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _hs_project(tmp_path: Path) -> Path:
    _write(tmp_path, "binding.lob", _HS_BINDING)
    return tmp_path


@_RUNNER_SKIP
class TestCmdRunHaskell:
    def test_bare_run_defines_entry_point(self, tmp_path, capsys):
        root = _hs_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    greet :: String\n"
            "    greet = \"hello from run\"\n\n"
            "~run\n"
            "    main :: IO ()\n"
            "    main = putStrLn greet\n"
        ))
        assert cmd_run(lob) == 0
        assert "hello from run" in capsys.readouterr().out

    def test_on_invocation_same_as_bare(self, tmp_path, capsys):
        root = _hs_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    greet :: String\n"
            "    greet = \"hello again\"\n\n"
            "~run on-invocation\n"
            "    main :: IO ()\n"
            "    main = putStrLn greet\n"
        ))
        assert cmd_run(lob) == 0
        assert "hello again" in capsys.readouterr().out

    def test_on_load_errors_instead_of_crashing(self, tmp_path, capsys):
        root = _hs_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    greet :: String\n"
            "    greet = \"unreachable\"\n\n"
            "~run on-load\n"
            "    main :: IO ()\n"
            "    main = putStrLn greet\n"
        ))
        assert cmd_run(lob) == 1
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "on-load" in err
        assert "equivalent for this binding" in err

    def test_plain_code_block_main_still_works(self, tmp_path, capsys):
        """The other valid pattern (main as a bare top-level code block,
        no ~run at all) must keep working -- this is what
        examples/haskell-roman used before its ~run migration, and
        Haskell's own semantics already make it equivalent to
        on-invocation."""
        root = _hs_project(tmp_path)
        lob = _write(root, "greet.lob", (
            "#Greet\n\n"
            "    main :: IO ()\n"
            "    main = putStrLn \"plain block\"\n"
        ))
        assert cmd_run(lob) == 0
        assert "plain block" in capsys.readouterr().out
