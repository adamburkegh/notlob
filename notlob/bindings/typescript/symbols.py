"""notlob.bindings.typescript.symbols — TypeScript symbol extractor.

Extracts top-level defined names from indented TypeScript code-block
lines using line-start pattern matching.  Each matched declaration
yields one SymbolInfo with the declared name and its full source block
(header line plus all continuation lines).

Recognised declaration forms
-----------------------------
All forms may be preceded by an optional ``export`` (and for
functions, ``default``) keyword.

  function foo (...)         async function foo (...)
  function* foo (...)        async function* foo (...)
  const foo = ...            let foo = ...           var foo = ...
  class Foo                  abstract class Foo
  interface Foo              enum Foo                const enum Foo
  type Foo = ...             type Foo<T> = ...

Arrow functions assigned to ``const``/``let``/``var`` are captured
via the variable-declaration pattern (``const foo = ...``).

Declarations inside blocks (nested functions, class bodies) are not
extracted — the pattern only matches lines with zero leading
whitespace after dedenting.
"""

from __future__ import annotations

import re
import textwrap
from typing import Sequence

from notlob.bindings import SymbolInfo

# Keywords and global names that will never be notlob symbols.
_TS_BUILTINS = frozenset({
    "Array", "Boolean", "Error", "JSON", "Map", "Math", "Number",
    "Object", "Promise", "Set", "String", "Symbol",
    "abstract", "async", "await", "break", "case", "catch", "class",
    "const", "continue", "debugger", "default", "delete", "do", "else",
    "enum", "export", "extends", "false", "finally", "for", "from",
    "function", "if", "implements", "import", "in", "instanceof",
    "interface", "let", "new", "null", "of", "readonly", "return",
    "static", "super", "switch", "this", "throw", "true", "try",
    "type", "typeof", "undefined", "var", "void", "while", "yield",
    "console", "process", "require", "module", "exports",
})

# Bare call: identifier( not preceded by . or word char (excludes method calls).
_TS_CALL_RE = re.compile(r'(?<![.\w])([A-Za-z_$][A-Za-z0-9_$]*)\s*\(')


# Matches top-level TypeScript declaration first tokens.
# Each alternative captures the declared name in a distinct group.
_DECL_RE = re.compile(
    r'^'
    r'(?:export\s+(?:default\s+)?)?'   # optional export / export default
    r'(?:'
    r'(?:async\s+)?function\*?\s+(\w+)'        # (1) function / async function / generator
    r'|(?:const|let|var)(?!\s+enum\b)\s+(\w+)' # (2) const / let / var (not const enum)
    r'|(?:abstract\s+)?class\s+(\w+)'          # (3) class / abstract class
    r'|interface\s+(\w+)'                      # (4) interface
    r'|(?:const\s+)?enum\s+(\w+)'             # (5) enum / const enum
    r'|type\s+(\w+)\s*(?:<[^>]*>)?\s*='       # (6) type alias
    r')'
)


def extract_symbols(lines: Sequence[str]) -> list[SymbolInfo]:
    """Return SymbolInfo objects for each top-level declaration in *lines*.

    *lines* are the raw (indented) lines of a notlob CodeBlock.  They
    are dedented before scanning so that patterns anchor correctly at
    column 0.  Each SymbolInfo carries the full source block (header
    line plus all continuation lines) so call extraction can scan it.
    """
    dedented = textwrap.dedent('\n'.join(lines))
    result: list[SymbolInfo] = []
    current_name: str | None = None
    current_block: list[str] = []

    def _flush() -> None:
        if current_name is not None:
            result.append(SymbolInfo(
                name=current_name,
                source='\n'.join(current_block).rstrip(),
            ))

    for line in dedented.splitlines():
        m = _DECL_RE.match(line)
        if m and (not line[:1].isspace()):
            _flush()
            current_name = next(g for g in m.groups() if g is not None)
            current_block = [line]
        elif current_name is not None:
            current_block.append(line)

    _flush()
    return result


def extract_calls(source: str) -> list[str]:
    """Return bare function call names referenced in *source*.

    Matches identifiers immediately followed by ``(`` that are not
    preceded by ``.`` (method calls).  Method calls require type
    information to resolve and are excluded by design — this is a known
    ceiling of static analysis without ``tsc``.

    >>> sorted(extract_calls("const x = toRoman(n) + fromRoman(s);"))
    ['fromRoman', 'toRoman']
    >>> extract_calls("obj.toRoman(n);")
    []
    """
    defined = {info.name for info in extract_symbols(source.splitlines())}
    calls = set(_TS_CALL_RE.findall(source))
    return sorted(calls - defined - _TS_BUILTINS)
