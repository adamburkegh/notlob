"""notlob.bindings.haskell.symbols — Symbol extractor for Haskell code.

Extracts top-level name definitions from a Haskell code block without
requiring a full parser.  The extractor relies on the structural
invariants of well-formatted Haskell:

  • Top-level definitions start at column 0.
  • Continuation lines (where-clauses, multi-line type signatures,
    guards split onto separate lines) are indented.
  • A blank line terminates the current definition.

These properties hold for Haskell written in a literate .lob document;
they are sufficient for the symbol extraction task.

Recognised forms
----------------
  name :: Type                function / value type signature
  name pattern… = expr        function definition (one or more equations)
  data   Name …               data type declaration
  newtype Name …              newtype declaration
  type   Name …               type alias
  class  … Name …  where      type class declaration
  (op)   :: Type              infix operator type signature
  (op)   a b = expr           infix operator definition

Not extracted
-------------
  instance declarations (no single name; implementation detail)
  import statements, module headers, pragmas, comments

Limitation
----------
A function definition whose first equation has all guards on separate
continuation lines (i.e. the line ``f x`` has no ``=`` or ``|``) is
*not* detected as a new definition if it lacks a type signature.  This
is unusual style; adding a type signature (good Haskell practice) cures
it.
"""

from __future__ import annotations

import re
import textwrap
from typing import Sequence

from notlob.bindings import SymbolInfo


# ── Per-line classifiers ──────────────────────────────────────

# Function / value type signature:  name ::
_TYPE_SIG_RE = re.compile(r"^([a-z_][A-Za-z0-9_']*)\s*::")

# Operator type signature:  (+++) ::
# Haskell operator chars per the Haskell report.
_OP_CHARS = r"[!#$%&*+./<=>?@\\^|\-~:]"
_OP_SIG_RE  = re.compile(rf"^\(({_OP_CHARS}+)\)\s*::")

# data / newtype declaration
_DATA_RE    = re.compile(r"^(?:data|newtype)\s+([A-Z][A-Za-z0-9_']*)")

# type alias
_TYPE_ALIAS_RE = re.compile(r"^type\s+([A-Z][A-Za-z0-9_']*)")

# Lowercase identifier at column 0 (function name or keyword)
_IDENT_RE   = re.compile(r"^([a-z_][A-Za-z0-9_']*)")

# Operator definition at column 0:  (+++) a b = …
_OP_DEF_RE  = re.compile(rf"^\(({_OP_CHARS}+)\)")


_HASKELL_KEYWORDS = frozenset({
    "case", "class", "data", "default", "deriving", "do", "else",
    "foreign", "if", "import", "in", "infix", "infixl", "infixr",
    "instance", "let", "module", "newtype", "of", "then", "type",
    "where",
})


def _top_level_name(line: str) -> str | None:
    """Return the symbol name defined by this column-0 Haskell line.

    Returns ``None`` for lines that are not top-level definitions
    (comments, imports, ``instance`` declarations, pragmas, etc.).
    """
    # ── Type signatures ──────────────────────────────────────
    m = _TYPE_SIG_RE.match(line)
    if m:
        return m.group(1)

    m = _OP_SIG_RE.match(line)
    if m:
        return m.group(1)

    # ── data / newtype / type alias ──────────────────────────
    m = _DATA_RE.match(line)
    if m:
        return m.group(1)

    m = _TYPE_ALIAS_RE.match(line)
    if m:
        return m.group(1)

    # ── class declaration ────────────────────────────────────
    if line.startswith("class ") or line == "class":
        return _class_name(line)

    # ── Function / value definition ──────────────────────────
    # Must contain '=' or start the RHS with '|' (guard) to be
    # distinguished from a bare expression or unrecognised form.
    m = _IDENT_RE.match(line)
    if m:
        name = m.group(1)
        if name not in _HASKELL_KEYWORDS:
            rest = line[m.end():].lstrip()
            if "=" in rest or rest.startswith("|"):
                return name
        return None

    # ── Operator definition ───────────────────────────────────
    m = _OP_DEF_RE.match(line)
    if m:
        rest = line[m.end():].lstrip()
        if "=" in rest or rest.startswith("|"):
            return m.group(1)

    return None


def _class_name(line: str) -> str | None:
    """Return the class name from a ``class … where`` line."""
    rest = line[len("class"):].strip()
    # Strip superclass context: everything up to and including '=>'
    if "=>" in rest:
        rest = rest.split("=>", 1)[1].strip()
    # First token starting with an uppercase letter is the class name
    for token in rest.split():
        clean = token.lstrip("(")
        if clean and clean[0].isupper():
            m = re.match(r"[A-Za-z0-9_']+", clean)
            if m and m.group() != "where":
                return m.group()
    return None


# ── Main extractor ────────────────────────────────────────────

def extract_symbols(lines: Sequence[str]) -> list[SymbolInfo]:
    """Extract top-level Haskell symbol definitions from code-block lines.

    *lines* are the raw indented lines stored in a
    :class:`~notlob.model.CodeBlock` (leading whitespace preserved).
    They are dedented before processing so the column-0 invariant
    applies correctly.

    One :class:`~notlob.bindings.SymbolInfo` is produced per distinct
    name.  A type signature and the equations that follow it are merged
    into a single entry.  Multiple pattern-matching equations for the
    same function are also merged.  Indented continuation lines
    (where-clauses, guards, multi-line type signatures) are folded into
    the ``source`` field of their enclosing definition.

    >>> [s.name for s in extract_symbols(["    f :: Int -> Int", "    f x = x + 1"])]
    ['f']
    >>> [s.name for s in extract_symbols(["    data Color = Red | Green | Blue"])]
    ['Color']
    >>> extract_symbols([])
    []
    """
    source_text  = textwrap.dedent("\n".join(lines))
    source_lines = source_text.splitlines()

    result:    list[SymbolInfo] = []
    cur_name:  str | None       = None
    cur_lines: list[str]        = []

    def _flush() -> None:
        if cur_name is not None:
            result.append(SymbolInfo(
                name=cur_name,
                source="\n".join(cur_lines),
            ))

    for raw in source_lines:
        line = raw.rstrip()

        if not line:
            # Blank line — close current definition
            _flush()
            cur_name  = None
            cur_lines = []
            continue

        if line[0] in (" ", "\t"):
            # Indented continuation — attach to current definition
            if cur_name is not None:
                cur_lines.append(line)
            continue

        # Non-blank, column-0 line — classify
        name = _top_level_name(line)

        if name is None:
            # Unrecognised (import, comment, instance, pragma, …)
            _flush()
            cur_name  = None
            cur_lines = []
            continue

        if name == cur_name:
            # Further equation / case for the same function
            cur_lines.append(line)
        else:
            _flush()
            cur_name  = name
            cur_lines = [line]

    _flush()   # final definition
    return result


def extract_calls(source: str) -> list[str]:
    """Return lowercase identifiers referenced in *source* but not defined there.

    Scans for all lowercase Haskell identifiers, subtracts names defined
    at the top level of the block and Haskell keywords.  Qualified names
    (e.g. ``Data.List.sort``) contribute only the leaf (``sort``).
    Local variables and type variables are included in the output; the
    graph resolution step filters to only addresses that exist.

    >>> "numerals" in extract_calls("toRoman 0 = \\\"\\\"\\ntoRoman n = snd h ++ toRoman (n - fst h)\\n  where h = head (filter ((<=n) . fst) numerals)")
    True
    >>> "toRoman" in extract_calls("toRoman 0 = \\\"\\\"\\ntoRoman n = snd h")
    False
    """
    defined = {info.name for info in extract_symbols(source.splitlines())}
    raw = set(re.findall(r'\b([a-z_][A-Za-z0-9_\']*)\b', source))
    return sorted(raw - defined - _HASKELL_KEYWORDS)
