"""Tests for the Python code assembler.

assemble() collects code blocks from a Module in document order,
prepends #References imports, and inserts source-location comments.
"""

import pytest

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
    def test_blank_line_between_refs_and_code(self):
        src = (
            "#T\n"
            "    x = 1\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        result = assembled(src)
        # refs chunk ends, blank line, then module location comment
        assert "import os\n\n# t\n" in result

    def test_blank_line_between_module_and_subheading(self):
        src = "#T\n    x = 1\n##S\n    y = 2\n"
        result = assembled(src)
        assert "x = 1\n\n# t#S\ny = 2" in result

    def test_blank_line_between_consecutive_blocks(self):
        # Two code blocks separated by prose → blank line between them.
        src = "#T\n    x = 1\nprose\n    y = 2\n"
        result = assembled(src)
        # Both blocks under the module comment; blank line between.
        assert "x = 1\n\ny = 2" in result

    def test_blank_line_between_subheading_blocks(self):
        src = "#T\n##S\n    x = 1\nprose\n    y = 2\n"
        result = assembled(src)
        assert "x = 1\n\ny = 2" in result


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
