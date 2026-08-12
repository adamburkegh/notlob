"""Tests for the Python code assembler.

assemble() collects code blocks from a Module in document order,
prepends #References imports, and inserts source-location comments.
"""

import subprocess
import sys

from notlob import parse, from_tree
from notlob.bindings.python.assemble import assemble


def assembled(source: str) -> str:
    return assemble(from_tree(parse(source)))


# ── Empty / no-code modules ──────────────────────────────────

class TestEmpty:
    def test_no_code_no_refs(self):
        assert assembled("#T\nJust prose.\n") == ""

    def test_blank_module(self):
        assert assembled("#T\n") == ""

    def test_claims_not_included(self):
        src = "#T\n~example\n    f() == 1\n"
        assert assembled(src) == ""


# ── References ────────────────────────────────────────────────

class TestReferences:
    def test_references_included(self):
        src = "#T\n---\n#References\n    import os\n"
        result = assembled(src)
        assert result == "import os"

    def test_references_dedented(self):
        src = "#T\n---\n#References\n    from pathlib import Path\n"
        result = assembled(src)
        assert result.startswith("from pathlib")

    def test_multiple_reference_lines(self):
        src = (
            "#T\n"
            "---\n"
            "#References\n"
            "    import os\n"
            "    from pathlib import Path\n"
        )
        result = assembled(src)
        assert result == "import os\nfrom pathlib import Path"

    def test_references_before_code(self):
        src = (
            "#T\n"
            "    x = 1\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        result = assembled(src)
        assert result.index("import os") < result.index("x = 1")


# ── Location comments ─────────────────────────────────────────

class TestLocationComments:
    def test_module_address_comment(self):
        result = assembled("#T\n    x = 1\n")
        assert result.startswith("# t\n")

    def test_multiword_title_address(self):
        result = assembled("#Roman Numerals\n    x = 1\n")
        assert result.startswith("# roman/numerals\n")

    def test_comment_directly_before_first_block(self):
        # No blank line between location comment and first block.
        result = assembled("#T\n    x = 1\n")
        assert "# t\nx = 1" in result

    def test_subheading_address_comment(self):
        src = "#T\n##Section\n    x = 1\n"
        result = assembled(src)
        assert "# t#Section\n" in result

    def test_no_comment_when_no_code(self):
        # Subheading with only prose → no comment for it.
        src = "#T\n##Section\nJust prose.\n"
        result = assembled(src)
        assert "# t#Section" not in result


# ── Blank line separation ─────────────────────────────────────

class TestBlankLineSeparation:
    """Two blank lines at every assembler-inserted separator, matching
    PEP8/isort's convention for top-level definitions -- verified
    against a real ruff run (see notlob.bindings.python.assemble's
    module docstring). Blank-line spacing *within* a single continuous
    code block (no dedent, so one CodeBlock) is the author's own
    choice and isn't touched by the assembler -- these tests are only
    about separators the assembler itself inserts."""

    def test_two_blank_lines_between_refs_and_code(self):
        src = (
            "#T\n"
            "    x = 1\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        result = assembled(src)
        # refs chunk ends, two blank lines, then module location comment
        assert "import os\n\n\n# t\n" in result

    def test_two_blank_lines_between_module_and_subheading(self):
        src = "#T\n    x = 1\n##S\n    y = 2\n"
        result = assembled(src)
        assert "x = 1\n\n\n# t#S\ny = 2" in result

    def test_two_blank_lines_between_consecutive_blocks(self):
        # Two code blocks separated by prose (a real dedent, so two
        # CodeBlock nodes) -- an assembler-inserted separator.
        src = "#T\n    x = 1\nprose\n    y = 2\n"
        result = assembled(src)
        assert "x = 1\n\n\ny = 2" in result

    def test_two_blank_lines_between_subheading_blocks(self):
        src = "#T\n##S\n    x = 1\nprose\n    y = 2\n"
        result = assembled(src)
        assert "x = 1\n\n\ny = 2" in result


# ── Ordering ──────────────────────────────────────────────────

class TestOrdering:
    def test_module_level_before_subheading(self):
        src = "#T\n    x = 1\n##S\n    y = 2\n"
        result = assembled(src)
        assert result.index("x = 1") < result.index("y = 2")

    def test_subheadings_in_document_order(self):
        src = "#T\n##First\n    a = 1\n##Second\n    b = 2\n"
        result = assembled(src)
        assert result.index("a = 1") < result.index("b = 2")

    def test_no_module_comment_without_module_code(self):
        # If there's only subheading code, the module comment is absent.
        src = "#T\n##S\n    x = 1\n"
        result = assembled(src)
        lines = result.splitlines()
        assert lines[0] == "# t#S"


# ── Multiline code blocks ─────────────────────────────────────

class TestMultilineBlocks:
    def test_function_body_preserved(self):
        src = (
            "#T\n"
            "    def f(n):\n"
            "        return n + 1\n"
        )
        result = assembled(src)
        assert "def f(n):\n    return n + 1" in result

    def test_blank_lines_inside_block_preserved(self):
        src = "#T\n    x = 1\n\n    def f(): pass\n"
        result = assembled(src)
        # The blank line is inside the single code block.
        assert "x = 1\n\ndef f(): pass" in result


# ── Lob references in #References ────────────────────────────

class TestLobRefsFiltered:
    def test_lob_ref_not_in_assembled_output(self):
        src = (
            "#T\n"
            "    x = 1\n"
            "---\n"
            "#References\n"
            "    #Roman Numerals\n"
        )
        result = assembled(src)
        assert "#Roman Numerals" not in result
        assert "roman" not in result

    def test_lob_ref_with_python_import(self):
        src = (
            "#T\n"
            "    x = 1\n"
            "---\n"
            "#References\n"
            "    #Roman Numerals\n"
            "    from decimal import Decimal\n"
        )
        result = assembled(src)
        assert "from decimal import Decimal" in result
        assert "#Roman Numerals" not in result

    def test_only_lob_refs_no_references_chunk(self):
        # When #References contains only lob refs, no references chunk
        # should appear (assemble filters them all out).
        src = (
            "#T\n"
            "    x = 1\n"
            "---\n"
            "#References\n"
            "    #Roman Numerals\n"
        )
        result = assembled(src)
        # The result is only the module code block
        assert result.strip().endswith("x = 1")


# ── Integration ───────────────────────────────────────────────

class TestIntegration:
    def test_full_assembly_is_executable(self):
        src = (
            "#T\n"
            "    def double(n):\n"
            "        return n * 2\n"
            "---\n"
            "#References\n"
            "    # no real imports needed\n"
        )
        code = assembled(src)
        ns: dict = {}
        exec(code, ns)
        assert ns["double"](3) == 6

    def test_references_in_scope_for_code(self):
        src = (
            "#T\n"
            "    result = Path('.')\n"
            "---\n"
            "#References\n"
            "    from pathlib import Path\n"
        )
        code = assembled(src)
        ns: dict = {}
        exec(code, ns)
        assert ns["result"] is not None


# ── #Appendix code ───────────────────────────────────────────

class TestAppendixCode:
    def test_appendix_code_included(self):
        src = (
            "#T\n"
            "    x = 1\n"
            "---\n"
            "#Appendix\n"
            "    def fixture_helper():\n"
            "        return 42\n"
        )
        assert "fixture_helper" in assembled(src)

    def test_appendix_location_comment(self):
        src = "#T\n    x = 1\n---\n#Appendix\n    y = 2\n"
        assert "# t#Appendix" in assembled(src)

    def test_appendix_subheading_uses_module_level_address(self):
        # Matches graph.py's own addressing for appendix subheadings
        # (mod_addr#Title, not nested under #Appendix) so a ##Name
        # reference from the main body resolves to the same address
        # this location comment names.
        src = (
            "#T\n    x = 1\n---\n"
            "#Appendix\n##Glossary\n    y = 2\n"
        )
        assert "# t#Glossary" in assembled(src)

    def test_appendix_code_usable_from_main_body_test(self):
        # The actual reported scenario: a helper defined in #Appendix
        # must be callable from #Tests/~example/~property, not just
        # present in the assembled text.
        src = (
            "#T\n"
            "    def target(n):\n"
            "        return n * 2\n"
            "---\n"
            "#Appendix\n"
            "    def fixture_helper():\n"
            "        return 42\n"
        )
        code = assembled(src)
        ns: dict = {}
        exec(code, ns)
        assert ns["fixture_helper"]() == 42
        assert ns["target"](3) == 6

    def test_no_appendix_no_change(self):
        src = "#T\n    x = 1\n"
        assert assembled(src) == "# t\nx = 1"


# ── Real-ruff regression: I001 (isort blank lines) ─────────────

class TestNoSpuriousI001:
    """Reported bug: a module with a single, correctly-formed
    `#References` import and a module body starting with a top-level
    `def` was flagged `I001` ("Import block is un-sorted or
    un-formatted") -- not because the import itself was wrong, but
    because the assembler only put one blank line between the import
    block and the following code, where isort wants two.

    `I` (isort) isn't in ruff's default rule set, so this only ever
    fires for projects whose own ruff config selects it (or explicit
    `--select`) -- reproduced here by asking for it explicitly, since
    that's the actual condition that made the bug real for the
    reporting project, not an artifact of this repo's own lint
    invocation happening not to select `I` by default.
    """

    def test_no_i001_after_references_import(self):
        src = (
            "#Example\n\n"
            "    def double(n: int) -> int:\n"
            "        return n * 2 + math.trunc(0.0)\n\n"
            "~example\n"
            "    double(21) == 42\n\n"
            "---\n\n"
            "#References\n"
            "    import math\n"
        )
        source = assembled(src)
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check",
             "--select=E,F,I", "--output-format=json",
             "--stdin-filename=module.py", "-"],
            input=source, capture_output=True, text=True,
        )
        assert proc.stdout.strip() == "[]", (
            f"ruff found issues in assembled source:\n{proc.stdout}\n"
            f"assembled source was:\n{source}"
        )
