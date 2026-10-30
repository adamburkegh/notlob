"""``notlob -C <dir>`` runs notlob as if it had been started in <dir>.

These run notlob as a subprocess from the repository root, the place an
agent or a person is when they cannot ``cd`` first.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
RETAIL = "examples/retail"


def _notlob(
    *args: str, cwd: Path = ROOT, stdin: str | None = None,
) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "notlob.cli", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", input=stdin,
    )


class TestRunsAsIfStartedThere:
    def test_a_query_answers_as_it_does_from_inside(self):
        there = _notlob("query", "search", "discount", cwd=ROOT / RETAIL)
        assert there.returncode == 0, there.stderr
        assert there.stdout.strip()
        here = _notlob("-C", RETAIL, "query", "search", "discount")
        assert here.returncode == there.returncode
        assert here.stdout == there.stdout

    def test_a_path_argument_is_relative_to_the_directory(self):
        proc = _notlob("-C", RETAIL, "test", "pricing/discounts.lob")
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_the_directory_itself_is_relative_to_where_it_was_run(self):
        proc = _notlob(
            "-C", "retail", "query", "search", "discount",
            cwd=ROOT / "examples")
        assert proc.returncode == 0, proc.stderr
        assert "discount" in proc.stdout.lower()

    def test_the_mcp_server_serves_that_project(self):
        request = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "notlob_query_search",
                "arguments": {"pattern": "discount"},
            },
        }
        line = json.dumps(request) + "\n"
        there = _notlob("mcp", cwd=ROOT / RETAIL, stdin=line)
        assert there.returncode == 0, there.stderr
        here = _notlob("-C", RETAIL, "mcp", stdin=line)
        assert here.returncode == 0, here.stderr
        assert "discount" in here.stdout.lower()
        assert here.stdout == there.stdout


class TestABadDirectory:
    def _fails(self, proc: subprocess.CompletedProcess) -> None:
        assert proc.returncode == 1
        assert proc.stdout == ""
        assert proc.stderr.startswith("ERROR  <cli>  "), proc.stderr

    def test_a_missing_directory(self):
        self._fails(_notlob("-C", "no/such/dir", "query", "search", "x"))

    def test_a_file_given_as_the_directory(self):
        self._fails(_notlob(
            "-C", f"{RETAIL}/binding.lob", "query", "search", "x"))

    def test_the_error_is_given_before_any_command_runs(self, tmp_path):
        """``init`` writes into the working directory: it must not."""
        self._fails(_notlob(
            "-C", "no/such/dir", "init", "--bare", cwd=tmp_path))
        assert list(tmp_path.iterdir()) == []

    def test_a_good_directory_is_where_a_command_writes(self, tmp_path):
        (tmp_path / "there").mkdir()
        proc = _notlob("-C", "there", "init", "--bare", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert (tmp_path / "there" / "binding.lob").exists()
        assert not (tmp_path / "binding.lob").exists()


class TestOnlyOne:
    def test_repeating_it_is_an_error(self):
        proc = _notlob(
            "-C", "examples", "-C", "retail", "query", "search", "x")
        assert proc.returncode == 1
        assert proc.stdout == ""
        assert proc.stderr.startswith("ERROR  <cli>  "), proc.stderr


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_the_help_lists_it(flag):
    proc = _notlob(flag)
    assert proc.returncode == 0
    assert "-C" in proc.stdout
