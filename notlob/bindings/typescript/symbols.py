"""notlob.bindings.typescript.symbols — TypeScript symbol extractor.

Extracts top-level defined names from indented TypeScript code-block
lines using line-start pattern matching.  Each matched line yields one
SymbolInfo with the declared name; source text is not currently
captured (source=None).

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
    column 0.
    """
    dedented = textwrap.dedent('\n'.join(lines))
    result: list[SymbolInfo] = []
    for line in dedented.splitlines():
        m = _DECL_RE.match(line)
        if m:
            name = next(g for g in m.groups() if g is not None)
            result.append(SymbolInfo(name=name))
    return result
