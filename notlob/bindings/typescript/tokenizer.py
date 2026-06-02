"""notlob.bindings.typescript.tokenizer — lightweight TypeScript expression scanner.

Provides two public functions used by the claim runner:

``is_complete(text)``
    Returns True when *text* is a syntactically complete expression —
    all bracket pairs are balanced and no string is left open.  Used
    to accumulate multi-line claim expressions before executing them.

``find_split(text)``
    Returns ``(position, operator)`` for the first top-level ``===``
    or ``!==`` in *text*, or ``None`` if none exists.  "Top-level"
    means not nested inside any bracket pair.  Used to split a claim
    expression into left and right sides for diagnostic reporting.

Both functions share a single internal token scanner that recognises:

- Single-quoted strings  ``'...'`` with backslash escapes
- Double-quoted strings  ``"..."`` with backslash escapes
- Template literals      backtick strings treated as opaque (``${...}``
  interpolations are not parsed; a ``===`` inside a template literal
  will not be reported as a split point)
- Line comments          ``// ...``
- Block comments         ``/* ... */``
- Bracket pairs          ``()``  ``[]``  ``{}``
- Equality operators     ``===``  ``!==``

Any ``===`` or ``!==`` inside a string, comment, or bracket nest is
invisible to ``find_split``.  The tokenizer degrades gracefully on
edge cases: an unclosed string causes it to consume the rest of the
text silently, which surfaces as an execution error rather than a
split mistake.
"""

from __future__ import annotations


def _tokens(text: str):
    """Yield ``(kind, start)`` for structurally significant tokens.

    kind is one of: ``'open'``, ``'close'``, ``'eq3'``, ``'neq3'``.
    Characters inside strings and comments are skipped entirely.
    """
    i = 0
    n = len(text)
    while i < n:
        c = text[i]

        # ── Line comment ─────────────────────────────────────
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            i += 2
            while i < n and text[i] != '\n':
                i += 1
            continue

        # ── Block comment ────────────────────────────────────
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            i += 2
            while i < n:
                if text[i] == '*' and i + 1 < n and text[i + 1] == '/':
                    i += 2
                    break
                i += 1
            continue

        # ── String / template literal ────────────────────────
        if c in ('"', "'", '`'):
            quote = c
            i += 1
            while i < n:
                ch = text[i]
                if ch == '\\' and i + 1 < n:
                    i += 2        # skip escaped character
                    continue
                i += 1
                if ch == quote:
                    break         # string closed
            continue              # even if unclosed, move on

        # ── Brackets ─────────────────────────────────────────
        if c in '([{':
            yield 'open',  i
        elif c in ')]}':
            yield 'close', i

        # ── Equality operators ────────────────────────────────
        elif c == '=' and text[i:i + 3] == '===':
            yield 'eq3',  i
        elif c == '!' and text[i:i + 3] == '!==':
            yield 'neq3', i

        i += 1


# ── Public API ────────────────────────────────────────────────

def is_complete(text: str) -> bool:
    """Return True if *text* is a syntactically complete expression.

    An expression is complete when all bracket pairs are balanced.
    A negative depth (unmatched close bracket) is also treated as
    complete — it is a syntax error that will surface at execution.

    Unclosed strings are silently consumed; the function may return
    True for them, which is acceptable because execution will then
    produce a syntax error reported as ERROR.

    >>> is_complete('f(1, 2)')
    True
    >>> is_complete('f(1,')
    False
    >>> is_complete('f(1,\\n    2)')
    True
    >>> is_complete('a === b')
    True
    """
    depth = 0
    for kind, _ in _tokens(text):
        if kind == 'open':
            depth += 1
        elif kind == 'close':
            depth -= 1
            if depth < 0:
                return True   # mismatched close — complete as-is
    return depth == 0


def find_split(text: str) -> tuple[int, str] | None:
    """Return ``(position, operator)`` of the first top-level ``===``
    or ``!==``, or ``None`` if none is found.

    "Top-level" means not inside any bracket pair.  Operators inside
    strings or comments are never yielded by the scanner.

    >>> find_split('a === b')
    (2, '===')
    >>> find_split('fn(a === b) === c')
    (12, '===')
    >>> find_split('a !== b')
    (2, '!==')
    >>> find_split('Boolean(x)') is None
    True
    """
    depth = 0
    for kind, pos in _tokens(text):
        if kind == 'open':
            depth += 1
        elif kind == 'close':
            depth -= 1
        elif kind == 'eq3' and depth == 0:
            return pos, '==='
        elif kind == 'neq3' and depth == 0:
            return pos, '!=='
    return None
