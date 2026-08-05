"""Tests for build_typescript's ~run on-load / on-invocation handling.

Content-based tests run unconditionally. One execution-based regression
test actually invokes tsx (direct run vs import) and is skipped when no
TypeScript toolchain is available -- see test_bindings_typescript_runner
for the same skip-guard pattern.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from notlob import from_tree, parse
from notlob.bindings.typescript import build_typescript
from notlob.bindings.typescript.runner import _tsx_cmd


def built(source: str) -> str:
    return build_typescript(from_tree(parse(source)))


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HAS_TSX = _tsx_cmd(_REPO_ROOT) is not None
_RUNNER_SKIP = pytest.mark.skipif(
    not _HAS_TSX,
    reason='tsx not found (run `npm install` at the repo root)',
)


class TestNoRun:
    def test_no_run_no_guard(self):
        src = '#T\n\n    const x = 1\n'
        result = built(src)
        assert 'import.meta.url' not in result
        assert "from 'node:url'" not in result


class TestBareRun:
    def test_wrapped_in_esm_guard(self):
        src = '#T\n\n    const x = 1\n\n~run\n    console.log(x)\n'
        result = built(src)
        assert "import { pathToFileURL } from 'node:url';" in result
        assert 'if (import.meta.url === pathToFileURL(process.argv[1]).href) {' in result
        assert 'console.log(x)' in result

    def test_body_inside_guard_not_at_module_scope(self):
        src = '#T\n\n    const x = 1\n\n~run\n    console.log(x)\n'
        result = built(src)
        guard_start = result.index('if (import.meta.url')
        body_pos = result.index('console.log(x)')
        assert body_pos > guard_start


class TestOnInvocation:
    def test_same_as_bare(self):
        src = '#T\n\n    const x = 1\n\n~run on-invocation\n    console.log(x)\n'
        result = built(src)
        assert 'if (import.meta.url === pathToFileURL(process.argv[1]).href) {' in result


class TestOnLoad:
    def test_unconditional_no_guard(self):
        src = '#T\n\n    const x = 1\n\n~run on-load\n    console.log(x)\n'
        result = built(src)
        assert 'import.meta.url' not in result
        assert "from 'node:url'" not in result
        assert 'console.log(x)' in result


class TestBothModes:
    def test_on_load_and_on_invocation_coexist(self):
        src = (
            '#T\n\n    const x = 1\n\n'
            "~run on-load\n    console.log('load')\n\n"
            "~run on-invocation\n    console.log('invocation')\n"
        )
        result = built(src)
        assert "console.log('load')" in result
        assert "console.log('invocation')" in result
        # on-load body must sit outside the guard.
        guard_start = result.index('if (import.meta.url')
        load_pos = result.index("console.log('load')")
        invocation_pos = result.index("console.log('invocation')")
        assert load_pos < guard_start < invocation_pos


# ── Execution-based regression ──────────────────────────────────

@_RUNNER_SKIP
class TestExecutionRegression:
    """Prove the guard actually discriminates run-vs-import under tsx,
    not just that the generated text looks plausible."""

    def test_direct_run_fires_both_import_fires_only_load(self, tmp_path):
        src = (
            '#T\n\n    const x = 1\n\n'
            "~run on-load\n    console.log('LOAD_FIRED')\n\n"
            "~run on-invocation\n    console.log('INVOCATION_FIRED')\n"
        )
        artifact = built(src)
        artifact_path = tmp_path / 'artifact.ts'
        artifact_path.write_text(artifact, encoding='utf-8')

        cmd = _tsx_cmd(_REPO_ROOT)
        direct = subprocess.run(
            cmd + [str(artifact_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert 'LOAD_FIRED' in direct.stdout
        assert 'INVOCATION_FIRED' in direct.stdout

        importer_path = tmp_path / 'importer.ts'
        importer_path.write_text(
            "import './artifact.ts';\nconsole.log('importer finished');\n",
            encoding='utf-8',
        )
        imported = subprocess.run(
            cmd + [str(importer_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert 'LOAD_FIRED' in imported.stdout
        assert 'INVOCATION_FIRED' not in imported.stdout
        assert 'importer finished' in imported.stdout
