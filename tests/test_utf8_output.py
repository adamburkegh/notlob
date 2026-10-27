"""notlob writes UTF-8, on every platform, and JSON does not escape.

These run notlob as a subprocess with PYTHONIOENCODING and PYTHONUTF8
unset and the output captured as bytes: the case where the interpreter
would otherwise pick the system codepage for a pipe. Prose in CJK, or an
em dash, must come out as itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

PROSE = "漢字のコメント — an em dash, and ελληνικά."

MODULE = f"""\
#Prose

{PROSE}

    def one() -> int:
        return 1
"""

BINDING = "#Unicode\n\n---\n\n#Binding\n    ~language python\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "binding.lob").write_text(BINDING, encoding="utf-8")
    (tmp_path / "prose.lob").write_text(MODULE, encoding="utf-8")
    return tmp_path


def _notlob(
    project: Path, *args: str, stdin: bytes | None = None,
) -> subprocess.CompletedProcess:
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PYTHONIOENCODING", "PYTHONUTF8")
    }
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "notlob.cli", *args],
        cwd=project, env=env, capture_output=True, input=stdin,
    )


class TestPipedOutputIsUtf8:
    def test_query_content_text(self, project):
        proc = _notlob(project, "query", "content", "prose")
        assert proc.returncode == 0, proc.stderr
        assert PROSE in proc.stdout.decode("utf-8")

    def test_graph_json(self, project):
        proc = _notlob(
            project, "graph", "--format", "json", "--level", "full")
        assert proc.returncode == 0, proc.stderr
        text = proc.stdout.decode("utf-8")
        assert PROSE in text
        assert "\\u" not in text
        nodes = json.loads(text)["nodes"]
        assert any(PROSE in n.get("text", "") for n in nodes)

    def test_query_content_json(self, project):
        proc = _notlob(
            project, "query", "content", "prose", "--format", "json")
        assert proc.returncode == 0, proc.stderr
        text = proc.stdout.decode("utf-8")
        assert PROSE in text
        assert "\\u" not in text

    def test_mcp_server(self, project):
        request = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "notlob_query_content",
                "arguments": {"address": "prose"},
            },
        }
        line = json.dumps(request, ensure_ascii=False) + "\n"
        proc = _notlob(project, "mcp", stdin=line.encode("utf-8"))
        assert proc.returncode == 0, proc.stderr
        text = proc.stdout.decode("utf-8")
        assert PROSE in text
        assert "\\u" not in text
