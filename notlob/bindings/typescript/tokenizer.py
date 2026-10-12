"""notlob.bindings.typescript.tokenizer — lightweight TypeScript expression scanner.

Provides two public functions used by the claim runner:

``is_complete(text)``
    Returns True when *text* is a syntactically complete expression —
    all bracket pairs are balanced and no string is left open.  Used
    to accumulate multi-line claim expressions before executing them.

``find_split(text)``
    Returns ``(position, operator)`` for the root equality operator of
    *text*, or ``None`` if its root operator is not an equality.
    "Top-level" means not nested inside any bracket pair.  Used to
    split a claim expression into left and right sides for diagnostic
    reporting.  Only a ``===`` result is split by the runner; it is
    reported only when no looser operator (``&&``, ``||``, ``?:`` ...)
    sits at the top level, since that operator, not the ``===``, is the
    root of the expression.

Both functions share a single internal token scanner that recognises:

- Single-quoted strings  ``'...'`` with backslash escapes
- Double-quoted strings  ``"..."`` with backslash escapes
- Template literals      backtick strings treated as opaque (``${...}``
  interpolations are not parsed; a ``===`` inside a template literal
  will not be reported as a split point)
- Line comments          ``// ...``
- Block comments         ``/* ... */``
- Bracket pairs          ``()``  ``[]``  ``{}``
- Equality operators     ``===``  ``!==``  ``==``  ``!=``
- Operators that bind more loosely than equality (``'low'``): ``&&``
  ``||`` ``??`` the ternary ``?`` , ``,`` ``=>`` assignment ``=``
  and the bitwise ``&`` ``|`` ``^``

Any operator inside a string, comment, or bracket nest is invisible to
``find_split``.  The tokenizer degrades gracefully on edge cases: an
unclosed string causes it to consume the rest of the text silently,
which surfaces as an execution error rather than a split mistake.
"""

from __future__ import annotations


def _tokens(text: str):
    """Yield ``(kind, start)`` for structurally significant tokens.

    kind is one of: ``'open'``, ``'close'``, ``'eq3'``, ``'neq3'``,
    ``'eq2'`` (``==`` / ``!=``) or ``'low'`` (an operator binding more
    loosely than equality).  Characters inside strings and comments are
    skipped entirely.  Multi-character operators are consumed whole, so
    the ``=`` of ``<=`` or ``=>`` is never read as an assignment.
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

        step = 1

        # ── Brackets ─────────────────────────────────────────
        if c in '([{':
            yield 'open',  i
        elif c in ')]}':
            yield 'close', i

        # ── Equality, arrow and assignment ────────────────────
        elif c == '=':
            if text[i:i + 3] == '===':
                yield 'eq3', i
                step = 3
            elif text[i:i + 2] == '==':
                yield 'eq2', i
                step = 2
            elif text[i:i + 2] == '=>':
                yield 'low', i
                step = 2
            else:
                yield 'low', i          # assignment, incl. `+=` etc.
        elif c == '!':
            if text[i:i + 3] == '!==':
                yield 'neq3', i
                step = 3
            elif text[i:i + 2] == '!=':
                yield 'eq2', i
                step = 2

        # ── Relational / shift: bind tighter than equality ───
        # Consumed as a run so the `=` of `<=` / `>=` is not read as
        # an assignment.
        elif c in '<>':
            while i + step < n and text[i + step] in '<>=':
                step += 1

        # ── Operators binding more loosely than equality ─────
        elif c in '&|':
            if text[i + 1:i + 2] == c:
                step = 2                # && ||  (and &&= ||=)
            yield 'low', i
        elif c in '^,':
            yield 'low', i
        elif c == '?':
            nxt = text[i + 1:i + 2]
            if nxt == '.' and not text[i + 2:i + 3].isdigit():
                step = 2                # optional chaining `?.`
            else:
                if nxt == '?':
                    step = 2            # nullish coalescing `??`
                yield 'low', i          # `??` or the ternary `?`

        i += step


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
    """Return ``(position, operator)`` of the root ``===`` or ``!==``
    of *text*, or ``None`` if its root operator is not one of those.

    "Top-level" means not inside any bracket pair.  Operators inside
    strings or comments are never yielded by the scanner.

    The root of an expression is its loosest-binding top-level
    operator.  If any operator looser than equality (``&&``, ``||``,
    ``??``, ``?:``, ``,``, ``=>``, assignment, bitwise ``& | ^``) sits at
    the top level, that operator is the root and the line is not an
    equality: ``None``.  Otherwise equality is left-associative, so the
    *last* top-level equality operator is the root.  A root that is
    ``==`` or ``!=`` is also ``None``: only ``===`` is reported as
    left/right sides.

    >>> find_split('a === b')
    (2, '===')
    >>> find_split('fn(a === b) === c')
    (12, '===')
    >>> find_split('a !== b')
    (2, '!==')
    >>> find_split('Boolean(x)') is None
    True
    >>> find_split('a === 1 && b === 2') is None
    True
    """
    depth = 0
    root: tuple[int, str] | None = None
    for kind, pos in _tokens(text):
        if kind == 'open':
            depth += 1
        elif kind == 'close':
            depth -= 1
        elif depth != 0:
            continue
        elif kind == 'low':
            return None
        elif kind == 'eq3':
            root = (pos, '===')
        elif kind == 'neq3':
            root = (pos, '!==')
        elif kind == 'eq2':
            root = None
    return root
