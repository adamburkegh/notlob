"""Tests for the Python linter integration.

parse_source_map translates assembled-source line numbers to notlob
section addresses.  lint_python runs ruff and returns LintResult
objects.
"""

from __future__ import annotations

import pytest

from notlob import from_tree, parse
from notlob.bindings import LintResult
from notlob.bindings.python.lint import lint_python, parse_source_map


def _module(text: str):
    return from_tree(parse(text))


# ── parse_source_map ─────────────────────────────────────────

class TestParseSourceMap:
    def test_empty_string(self):
        assert parse_source_map("") == {}

    def test_single_section(self):
        src = "# roman/numerals\ndef to_roman(n):\n    return 'I'"
        m = parse_source_map(src)
        assert m[2] == "roman/numerals"
        assert m[3] == "roman/numerals"

    def test_location_comment_line_not_mapped(self):
        """The # <address> comment line itself is not in the map."""
        src = "# roman/numerals\nx = 1"
        m = parse_source_map(src)
        assert 1 not in m   # the comment line
        assert m[2] == "roman/numerals"

    def test_two_sections(self):
        src = (
            "# roman/numerals\n"
            "x = 1\n"
            "\n"
            "# roman/numerals#Decoding\n"
            "y = 2\n"
        )
        m = parse_source_map(src)
        assert m[2] == "roman/numerals"
        assert m[5] == "roman/numerals#Decoding"

    def test_pre_header_lines_assigned_to_first_section(self):
        """Lines before the first address marker (e.g. imports) go to
        the first section once it appears."""
        src = (
            "import re\n"
            "from collections import Counter\n"
            "\n"
            "# gutenberg/corpus\n"
            "def f(): pass\n"
        )
        m = parse_source_map(src)
        assert m[1] == "gutenberg/corpus"
        assert m[2] == "gutenberg/corpus"
        assert m[5] == "gutenberg/corpus"

    def test_subheading_address(self):
        src = (
            "# mymod\n"
            "x = 1\n"
            "\n"
            "# mymod#Loading\n"
            "y = 2\n"
        )
        m = parse_source_map(src)
        assert m[2] == "mymod"
        assert m[5] == "mymod#Loading"


# ── lint_python ───────────────────────────────────────────────

class TestLintPython:
    def test_empty_module_no_results(self):
        """A module with no code blocks produces no lint results.

        No source to check, so ruff is not invoked.
        """
        mod = _module("#Empty\nJust prose.\n")
        assert lint_python(mod) == []

    def test_missing_tool_raises(self, monkeypatch):
        """A non-empty module with ruff absent raises, never returns []."""
        from notlob.bindings import LintToolUnavailable
        import notlob.bindings.python.lint as lint_mod
        monkeypatch.setattr(
            lint_mod.importlib.util, "find_spec", lambda name: None
        )
        src = "#M\n\n    x = 1\n"
        with pytest.raises(LintToolUnavailable):
            lint_python(_module(src))

    def test_clean_code_no_results(self):
        """Clean, valid Python code produces no lint results."""
        src = (
            "#Clean Module\n"
            "\n"
            "    def greet(name: str) -> str:\n"
            "        return f'hello {name}'\n"
        )
        results = lint_python(_module(src))
        assert results == []

    def test_returns_lint_result_objects(self):
        """lint_python always returns LintResult instances."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        for r in results:
            assert isinstance(r, LintResult)

    def test_unused_import_flagged(self):
        """An unused import in #References is caught by ruff (F401)."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        codes = [r.code for r in results]
        assert "F401" in codes

    def test_lint_result_has_address(self):
        """Every LintResult has a non-empty address."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        assert all(r.address for r in results)

    def test_address_matches_module(self):
        """Lint results for module-level code are attributed to the
        module address."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        # F401 for unused import should map to the module address.
        # module_address("My Module") == "my/module"
        f401 = [r for r in results if r.code == "F401"]
        assert all(r.address == "my/module" for r in f401)


# ── F401 suppressed when a claim uses the import ───────────────

class TestClaimOnlyImportNotFlagged:
    """An import used only inside a claim (~example/#Tests/~property),
    never in the module's own body code, must not be flagged F401 --
    the claim really does use it, even though claims aren't part of
    what gets assembled and linted."""

    def test_example_only_use_suppresses_f401(self):
        src = (
            "#Alpha\n"
            "\n"
            "    def load(text):\n"
            "        return json.loads(text)\n"
            "\n"
            "~example\n"
            "    load('1') == 1\n"
            "    Path('x').name == 'x'\n"
            "\n"
            "---\n"
            "#References\n"
            "    import json\n"
            "    from pathlib import Path\n"
        )
        results = lint_python(_module(src))
        assert "F401" not in [r.code for r in results]

    def test_unused_with_no_claim_use_still_flagged(self):
        """Regression guard: an import unused everywhere, including in
        any claim, is still reported -- the suppression is specific to
        claim usage, not a blanket F401 disable."""
        src = (
            "#Alpha\n"
            "\n"
            "    def load(text):\n"
            "        return json.loads(text)\n"
            "\n"
            "~example\n"
            "    load('1') == 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import json\n"
            "    from pathlib import Path\n"
        )
        results = lint_python(_module(src))
        assert "F401" in [r.code for r in results]

    def test_tests_section_use_suppresses_f401(self):
        src = (
            "#Alpha\n"
            "\n"
            "    def load(text):\n"
            "        return json.loads(text)\n"
            "\n"
            "---\n"
            "#Tests\n"
            "    Path('x').name == 'x'\n"
            "\n"
            "#References\n"
            "    from pathlib import Path\n"
        )
        results = lint_python(_module(src))
        assert "F401" not in [r.code for r in results]

    def test_property_use_suppresses_f401(self):
        src = (
            "#Alpha\n"
            "\n"
            "    def load(text):\n"
            "        return json.loads(text)\n"
            "\n"
            "~property roundtrips\n"
            "    @given(x=st.text())\n"
            "    def _(x):\n"
            "        assert Path(x).name == x\n"
            "\n"
            "---\n"
            "#References\n"
            "    from pathlib import Path\n"
        )
        results = lint_python(_module(src))
        assert "F401" not in [r.code for r in results]


class TestRunBodyImportNotFlagged:
    """An import used only by a `~run` body must not be flagged F401
    either: `assemble()` leaves `~run` bodies out of the linted source
    (only a build appends them), so ruff can't see the use. See
    meta/bugs/2026-10-03-run-body-imports-flagged-unused."""

    _BODY = (
        "#Gamma\n\n"
        "Doubles a number.\n\n"
        "    def double(n):\n"
        "        return n * 2\n\n"
        "~example\n"
        "    double(2) == 4\n\n"
    )
    _REFS = "---\n#References\n    from pathlib import Path\n"

    def test_bare_run_use_suppresses_f401(self):
        src = (
            self._BODY
            + "~run\n    print(Path('x').name, double(2))\n\n"
            + self._REFS
        )
        assert "F401" not in [r.code for r in lint_python(_module(src))]

    def test_on_load_run_use_suppresses_f401(self):
        src = (
            self._BODY
            + "~run on-load\n    print(Path('x').name)\n\n"
            + self._REFS
        )
        assert "F401" not in [r.code for r in lint_python(_module(src))]

    def test_run_in_subheading_suppresses_f401(self):
        src = (
            self._BODY
            + "##Entry\n\nRuns it.\n\n"
            + "~run\n    print(Path('x').name)\n\n"
            + self._REFS
        )
        assert "F401" not in [r.code for r in lint_python(_module(src))]

    def test_unused_everywhere_still_flagged(self):
        """Guard: a `~run` that doesn't use the import doesn't silence it."""
        src = (
            self._BODY
            + "~run\n    print(double(2))\n\n"
            + self._REFS
        )
        assert "F401" in [r.code for r in lint_python(_module(src))]


# ── Cross-module names: F821 suppressed, nothing else leaks ────

class TestCrossModuleReferences:
    """Only a module's own assembled source is ever sent to ruff -- a
    dependency's source is never prepended (see lint.py's module
    docstring for why an earlier version that did prepend it was
    wrong). Instead, an F821 "undefined name" finding is dropped when
    the name is one a lob-ref dependency defines. This both avoids
    misattributing a dependency's own findings to the referencing
    module, and avoids a dependency's own imports ever colliding with
    the referencing module's (F811) -- neither dependency's source is
    ever in the linted text at all."""

    def _write_project(
        self, tmp_path, beta_body="return json.dumps(load(value))",
    ):
        (tmp_path / "binding.lob").write_text(
            "#Lint Repro\n\n---\n\n#Binding\n    ~language python\n"
        )
        (tmp_path / "alpha.lob").write_text(
            "#Alpha\n\n"
            "    def load(text):\n"
            "        return json.loads(text)\n\n"
            "~example\n"
            "    load('1') == 1\n"
            "    Path('x').name == 'x'\n\n"
            "---\n\n"
            "#References\n"
            "    import json\n"
            "    from pathlib import Path\n"
        )
        (tmp_path / "beta.lob").write_text(
            "#Beta\n\n"
            f"    def dump(value):\n        {beta_body}\n\n"
            "~example\n"
            "    dump('2') == '2'\n\n"
            "---\n\n"
            "#References\n"
            "    #Alpha\n"
            "    import json\n"
        )
        return tmp_path

    def test_cross_module_call_suppressed_with_root(self, tmp_path):
        """beta's own body calls alpha's load() directly -- the actual
        case F821 suppression exists for (not exercised by a call that
        only ever appears inside a claim, since claims aren't linted;
        see the sibling test below for that distinction)."""
        root = self._write_project(tmp_path)
        beta = _module((root / "beta.lob").read_text())
        results = lint_python(beta, root=root)
        assert "F821" not in [r.code for r in results]

    def test_cross_module_call_flagged_without_root(self, tmp_path):
        """Regression guard: the same call, with no root/dependency
        context at all, is a genuine F821 -- confirming the suppression
        above is really about dependency awareness, not that `load`
        could never be flagged."""
        root = self._write_project(tmp_path)
        beta = _module((root / "beta.lob").read_text())
        results = lint_python(beta)  # no root
        assert "F821" in [r.code for r in results]

    def test_unrelated_typo_still_flagged_with_root(self, tmp_path):
        """A real typo, unrelated to any dependency, must still be
        reported even when dependency context is available -- this
        isn't a blanket F821 disable."""
        root = self._write_project(
            tmp_path, beta_body="return load(totally_undefined_name())",
        )
        beta = _module((root / "beta.lob").read_text())
        results = lint_python(beta, root=root)
        undefined = [r for r in results if r.code == "F821"]
        assert len(undefined) == 1
        assert "totally_undefined_name" in undefined[0].message

    def test_dependency_f401_not_reported_against_referencing_module(
        self, tmp_path,
    ):
        """The exact bug-report repro: beta references alpha (whose
        own claim-only Path import would be F401) and re-imports json
        itself. Neither alpha's F401 nor an F811 for json should ever
        reach beta's results, since alpha's source is never part of
        what beta's lint call sees."""
        root = self._write_project(tmp_path)
        beta = _module((root / "beta.lob").read_text())
        results = lint_python(beta, root=root)
        assert results == []

    def test_dependency_itself_has_no_findings(self, tmp_path):
        """Sanity check: alpha alone (its own claim uses Path) is clean,
        confirming the F401 above really would belong to alpha, not to
        some other cause."""
        root = self._write_project(tmp_path)
        alpha = _module((root / "alpha.lob").read_text())
        assert lint_python(alpha, root=root) == []
