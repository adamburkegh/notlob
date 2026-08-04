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

from notlob.bindings import SymbolInfo

_PYTHON_BUILTINS = frozenset(dir(_builtins_mod))


def extract_symbols(lines: Sequence[str]) -> list[SymbolInfo]:
    """Return the top-level symbols defined in a Python code block.

    Each :class:`~notlob.bindings.SymbolInfo` carries the symbol name
    and its dedented source text (the exact lines for that definition).

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
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.append(SymbolInfo(name=node.name, source=node_src))
        elif isinstance(node, ast.ClassDef):
            result.append(SymbolInfo(name=node.name, source=node_src))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result.append(
                        SymbolInfo(name=target.id, source=node_src)
                    )
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                result.append(
                    SymbolInfo(name=node.target.id, source=node_src)
                )
    return result


def extract_calls(source: str) -> list[str]:
    """Return names statically referenced in *source* but not defined there.

    Walks the AST for all Name loads and subtracts Python builtins.
    Dynamic calls (eval, getattr, __getattr__) are invisible by design.
    Returns an empty list on syntax errors.

    >>> sorted(extract_calls("def f(x):\\n    return g(x) + h(x)"))
    ['g', 'h', 'x']
    >>> extract_calls("def f():\\n    return len([1, 2, 3])")
    []
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
    return sorted(names - _PYTHON_BUILTINS)
