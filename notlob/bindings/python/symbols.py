"""notlob.bindings.python.symbols — Python symbol extractor.

Extracts top-level defined names from Python code block lines using
the standard-library ast module.  No additional dependencies required.

Extracted kinds
---------------
  Functions   def f(...) / async def f(...)
  Classes     class C:
  Assignments NUMERALS = [...] / x: int = 1

Local variables inside functions and class bodies are not extracted;
they are not part of the module's public name surface.

Syntax errors in a code block are silently ignored — the block may
be a fragment (e.g. a continuation of a previous block) and partial
extraction is not attempted.  The caller receives an empty list.
"""

from __future__ import annotations

import ast
import textwrap
from typing import Sequence


def extract_symbols(lines: Sequence[str]) -> list[str]:
    """Return the top-level names defined in a Python code block.

    lines  The lines of an INDENT block as stored in CodeBlock.lines,
           including leading whitespace and any embedded blank lines.

    >>> extract_symbols(["    def f(): pass"])
    ['f']
    >>> extract_symbols(["    NUMERALS = [1, 2, 3]"])
    ['NUMERALS']
    >>> extract_symbols(["    class C: pass", "    def g(): pass"])
    ['C', 'g']
    >>> extract_symbols(["    x = ("])   # syntax error fragment
    []
    """
    source = textwrap.dedent("\n".join(lines))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    names: list[str] = []
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.append(node.target.id)
    return names
