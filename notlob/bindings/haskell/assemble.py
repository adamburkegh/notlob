"""notlob.bindings.haskell.assemble — Haskell code assembler.

Assembles a Module into a standalone Haskell source string suitable
for both direct compilation (ghc/runghc) and runner harness injection.

Assembly order
--------------
  1. module header: ``module <Name> where``
  2. ``#References`` lines  (Haskell import statements; lob-refs dropped)
  3. Module-level code blocks  (preceded by ``-- <module_address>``)
  4. Subheading code blocks in document order
     (each group preceded by ``-- <subheading_address>``)

The module name is derived from the module title by capitalising each
word and joining: ``"Roman Numerals"`` → ``"RomanNumerals"``.

All top-level chunks are separated by a single blank line.
Code blocks within a section are also separated by blank lines.
A location comment is joined directly to its first code block
with no intervening blank line.

The internal ``_assemble_body`` helper returns
``(import_lines, code_chunks)`` for use by the runner when it needs to
inject user code into a harness that supplies its own module header.
"""

from __future__ import annotations

import re
import textwrap

from notlob.graph import module_address, subheading_address
from notlob.model import CodeBlock, Module, ReferencesSection, Subheading


# ── Module-name derivation ────────────────────────────────────

def _module_name(title: str) -> str:
    """Derive a Haskell module name from a notlob title.

    Splits on non-alphanumeric characters, capitalises each word, joins.

    >>> _module_name("Roman Numerals")
    'RomanNumerals'
    >>> _module_name("Pricing Discounts")
    'PricingDiscounts'
    >>> _module_name("Primes")
    'Primes'
    >>> _module_name("my-module")
    'MyModule'
    """
    words = re.split(r"[^A-Za-z0-9]+", title)
    return "".join(w.capitalize() for w in words if w)


# ── References parsing ────────────────────────────────────────

def _haskell_imports(lines: list[str]) -> list[str]:
    """Return Haskell import lines from a ``#References`` line list.

    Drops blank lines and lob-ref lines (those whose stripped form
    starts with ``#``).  All other lines are assumed to be Haskell
    ``import`` statements.

    >>> _haskell_imports([
    ...     "    #Roman Numerals",
    ...     "    import Data.List (sort)",
    ...     "",
    ...     "    import Data.Char (toLower)",
    ... ])
    ['import Data.List (sort)', 'import Data.Char (toLower)']
    """
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            result.append(stripped)
    return result


# ── Block collection ──────────────────────────────────────────

def _collect_blocks(body: list) -> list[str]:
    """Return dedented, stripped text for each CodeBlock in body."""
    result = []
    for item in body:
        if isinstance(item, CodeBlock):
            text = textwrap.dedent("\n".join(item.lines)).strip()
            if text:
                result.append(text)
    return result


def _section(comment: str, blocks: list[str]) -> str:
    """Join a location comment and its code blocks.

    The comment is glued to the first block (no blank line between
    them); subsequent blocks within the same section are separated
    by blank lines.
    """
    first, *rest = blocks
    head = f"{comment}\n{first}"
    if rest:
        return head + "\n\n" + "\n\n".join(rest)
    return head


# ── Body decomposition ────────────────────────────────────────

def _assemble_body(
    module: Module,
) -> tuple[list[str], list[str]]:
    """Return ``(import_lines, code_chunks)`` for the module.

    *import_lines* — Haskell ``import`` statements extracted from
    the module's ``#References`` section.  Lob-ref lines (``#Title``)
    are excluded.

    *code_chunks* — dedented code-block text groups, each preceded by
    a ``-- address`` location comment.  One entry per module-level or
    subheading-level group.

    Used by the runner to build harness files where the module header
    and any runner-injected imports must come first.
    """
    import_lines: list[str] = []
    if module.post_text is not None:
        for section in module.post_text.sections:
            if isinstance(section, ReferencesSection):
                import_lines = _haskell_imports(section.lines)
                break

    code_chunks: list[str] = []
    mod_addr = module_address(module.title)

    mod_blocks = _collect_blocks(module.body)
    if mod_blocks:
        code_chunks.append(_section(f"-- {mod_addr}", mod_blocks))

    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            sub_blocks = _collect_blocks(item.body)
            if sub_blocks:
                code_chunks.append(_section(f"-- {sub_addr}", sub_blocks))

    return import_lines, code_chunks


# ── Public assembler ──────────────────────────────────────────

def assemble(module: Module) -> str:
    """Assemble module code blocks into a standalone Haskell module.

    Returns a string beginning with ``module <Name> where`` and
    containing all code blocks separated by blank lines.  Returns an
    empty string if the module contains no code and no imports.

    >>> from notlob.model import Module
    >>> m = Module(title="Hello World", body=[], post_text=None)
    >>> assemble(m)
    ''
    """
    mod_name = _module_name(module.title)
    import_lines, code_chunks = _assemble_body(module)

    if not code_chunks and not import_lines:
        return ""

    parts: list[str] = [f"module {mod_name} where"]
    if import_lines:
        parts.append("\n".join(import_lines))
    parts.extend(code_chunks)
    return "\n\n".join(parts)
