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
import builtins as _builtins_mod
import textwrap
from typing import Sequence

from notlob.bindings import SymbolInfo, default_split_imports
from notlob.model import ImportLine

_PYTHON_BUILTINS = frozenset(dir(_builtins_mod))


def extract_symbols(lines: Sequence[str]) -> list[SymbolInfo]:
    """Return the top-level symbols defined in a Python code block.

    Each :class:`~notlob.bindings.SymbolInfo` carries the symbol name,
    its dedented source text (the exact lines for that definition) and
    the first and last of those lines within *lines*.

    lines  The lines of an INDENT block as stored in CodeBlock.lines,
           including leading whitespace and any embedded blank lines.

    >>> [s.name for s in extract_symbols(["    def f(): pass"])]
    ['f']
    >>> [s.name for s in extract_symbols(["    NUMERALS = [1, 2, 3]"])]
    ['NUMERALS']
    >>> [s.name for s in extract_symbols(["    class C: pass", "    def g(): pass"])]
    ['C', 'g']
    >>> extract_symbols(["    x = ("])   # syntax error fragment
    []
    """
    source       = textwrap.dedent("\n".join(lines))
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    result: list[SymbolInfo] = []
    for node in tree.body:
        node_src = "\n".join(
            source_lines[node.lineno - 1 : node.end_lineno]
        )
        def symbol(name: str) -> SymbolInfo:
            return SymbolInfo(
                name=name, source=node_src,
                first_line=node.lineno, last_line=node.end_lineno,
            )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.append(symbol(node.name))
        elif isinstance(node, ast.ClassDef):
            result.append(symbol(node.name))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result.append(symbol(target.id))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                result.append(symbol(node.target.id))
    return result


def extract_calls(source: str) -> list[tuple[str, int]]:
    """Return (name, line) pairs for names statically referenced in *source*.

    Walks the AST for all Name loads and subtracts Python builtins.
    *line* is 1-indexed within *source*.  When a name appears on multiple
    lines the first occurrence is returned.  Dynamic calls (eval, getattr,
    __getattr__) are invisible by design.  Returns an empty list on syntax
    errors.

    >>> sorted(extract_calls("def f(x):\\n    return g(x) + h(x)"))
    [('g', 2), ('h', 2), ('x', 2)]
    >>> extract_calls("def f():\\n    return len([1, 2, 3])")
    []
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    first_line: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name = node.id
            if name not in _PYTHON_BUILTINS:
                if name not in first_line or node.lineno < first_line[name]:
                    first_line[name] = node.lineno
    return sorted(first_line.items())


def split_imports(
    lines: Sequence[ImportLine],
) -> list[tuple[str, int | None]]:
    """Split the import lines of ``#References`` into Python statements.

    The compiler decides where a statement ends, so an import in
    parentheses over several lines, or one continued by a backslash at
    the end of a line, is one statement. Each comes with its text,
    dedented, and the line its first line is on. A comment line is no
    statement. Lines that do not compile as a whole fall back to one
    statement for each non-blank line.
    """
    block = textwrap.dedent("\n".join(line.text for line in lines))
    try:
        tree = ast.parse(block)
    except SyntaxError:
        return default_split_imports(lines)
    rows = block.split("\n")
    return [
        ("\n".join(rows[node.lineno - 1:node.end_lineno]).rstrip(),
         lines[node.lineno - 1].line)
        for node in tree.body
    ]
