"""Tests for the TypeScript tsc-based linter.

``_parse_tsc_output`` translates tsc diagnostic lines to notlob section
addresses via the source map; these unit tests run unconditionally.

Integration tests invoke real ``tsc`` and are skipped when it is not
installed.  The repo-root ``node_modules`` holds the TypeScript
toolchain (run ``npm install`` at the repo root), paralleling notlobenv
for Python.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob import from_tree, parse
from notlob.bindings.typescript.lint import (
    _parse_tsc_output, lint_typescript,
)
from notlob.bindings.typescript.runner import node_bin


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HAS_TSC = node_bin('tsc', _REPO_ROOT) is not None
_TSC_SKIP = pytest.mark.skipif(
    not _HAS_TSC,
    reason='tsc not found (run `npm install` at the repo root)',
)


def _module(text: str):
    return from_tree(parse(text))


# ── Unit: _parse_tsc_output ───────────────────────────────────

class TestParseTscOutput:
    def test_single_diagnostic(self):
        out = (
            "/tmp/abc.ts(3,7): error TS2322: "
            "Type 'string' is not assignable to type 'number'."
        )
        results = _parse_tsc_output(out, {3: "my/mod"}, 0, "my/mod")
        assert len(results) == 1
        r = results[0]
        assert r.address == "my/mod"
        assert r.code == "TS2322"
        assert r.col == 7
        assert "not assignable" in r.message

    def test_offset_subtracted(self):
        # Reported line 10, offset 7 → line 3 in the source map.
        out = "/tmp/x.ts(10,1): error TS2304: Cannot find name 'foo'."
        results = _parse_tsc_output(out, {3: "main/mod"}, 7, "fallback")
        assert results[0].address == "main/mod"

    def test_fallback_when_unmapped(self):
        out = "/tmp/x.ts(99,1): error TS1005: ';' expected."
        results = _parse_tsc_output(out, {}, 0, "fallback/addr")
        assert results[0].address == "fallback/addr"

    def test_non_diagnostic_lines_ignored(self):
        out = "Found 1 error.\n\n  more context here\n"
        assert _parse_tsc_output(out, {}, 0, "f") == []

    def test_multiple_diagnostics(self):
        out = (
            "/tmp/x.ts(2,1): error TS2322: bad\n"
            "/tmp/x.ts(5,3): error TS2304: nope\n"
        )
        results = _parse_tsc_output(out, {2: "a", 5: "b"}, 0, "f")
        assert [r.address for r in results] == ["a", "b"]
        assert [r.code for r in results] == ["TS2322", "TS2304"]

    def test_windows_path_with_drive_letter(self):
        # A leading drive letter (C:\...) must not confuse the regex.
        out = (
            "C:\\Temp\\abc.ts(4,2): error TS2322: "
            "Type 'number' is not assignable to type 'string'."
        )
        results = _parse_tsc_output(out, {4: "w/mod"}, 0, "w/mod")
        assert len(results) == 1
        assert results[0].address == "w/mod"
        assert results[0].code == "TS2322"

    def test_empty_output(self):
        assert _parse_tsc_output("", {}, 0, "f") == []


# ── Missing tool — raises, never silently passes ──────────────

class TestMissingTool:
    def test_missing_tsc_raises(self, monkeypatch):
        """A non-empty module with tsc absent raises, never returns []."""
        from notlob.bindings import LintToolUnavailable
        import notlob.bindings.typescript.lint as ts_lint
        monkeypatch.setattr(ts_lint, "node_bin", lambda name, root: None)
        mod = _module('#M\n\n    const x: number = 1\n')
        with pytest.raises(LintToolUnavailable):
            lint_typescript(mod, root=None)

    def test_no_code_no_tool_returns_empty(self, monkeypatch):
        """No code to check → no tool needed → [] even when tsc absent."""
        import notlob.bindings.typescript.lint as ts_lint
        monkeypatch.setattr(ts_lint, "node_bin", lambda name, root: None)
        mod = _module('#M\n\nJust prose.\n')
        assert lint_typescript(mod, root=None) == []


# ── Integration: real tsc ─────────────────────────────────────

@_TSC_SKIP
class TestLintTypescriptIntegration:
    def test_clean_module_no_findings(self):
        mod = _module('#T\n\n    const x: number = 1\n')
        assert lint_typescript(mod, root=_REPO_ROOT) == []

    def test_type_error_flagged(self):
        mod = _module('#Bad Mod\n\n    const x: number = "s"\n')
        results = lint_typescript(mod, root=_REPO_ROOT)
        assert len(results) >= 1
        assert results[0].code == "TS2322"
        assert results[0].address == "bad/mod"

    def test_undefined_name_flagged(self):
        mod = _module('#T\n\n    const y = notDefinedAnywhere\n')
        results = lint_typescript(mod, root=_REPO_ROOT)
        assert any(r.code == "TS2304" for r in results)

    def test_subheading_error_address(self):
        mod = _module(
            '#T\n\n    const a: number = 1\n\n'
            '##Section\n\n    const b: number = "x"\n'
        )
        results = lint_typescript(mod, root=_REPO_ROOT)
        assert any(r.address == "t#Section" for r in results)
        # The clean module-level block is not flagged.
        assert all(r.address != "t" for r in results)

    def test_no_code_returns_empty(self):
        mod = _module('#T\n\nJust prose, no code.\n')
        assert lint_typescript(mod, root=_REPO_ROOT) == []

    def test_valid_dom_usage_no_findings(self):
        # DOM lib is enabled, so document/HTMLElement resolve cleanly.
        mod = _module(
            '#T\n\n    const el = document.createElement("div")\n'
            '    el.textContent = "hi"\n'
        )
        assert lint_typescript(mod, root=_REPO_ROOT) == []
