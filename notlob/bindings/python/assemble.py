"""notlob.bindings.python.assemble — Python code assembler.

Assembles a Module into a single executable Python string by
collecting code blocks in order, prepending #References imports,
and inserting source-location comments for debugging.

Assembly order
--------------
  1. #References lines  (import preamble; no location comment)
  2. Module-level code blocks  (preceded by "# <module_address>")
  3. Subheading code blocks in document order
     (each group preceded by "# <subheading_address>")

All top-level chunks are separated by a single blank line.
Code blocks within a section are also separated by blank lines.
A location comment is joined directly to its first code block
with no intervening blank line.
"""

from __future__ import annotations

import textwrap

from notlob.graph import module_address, subheading_address
from notlob.model import CodeBlock, Module, ReferencesSection, Subheading


def assemble(module: Module) -> str:
    """Assemble module code blocks into one executable Python string.

    Returns an empty string if the module contains no code.
    """
    chunks: list[str] = []

    # ── 1. #References ──────────────────────────────────────────
    if module.post_text is not None:
        for section in module.post_text.sections:
            if isinstance(section, ReferencesSection):
                text = textwrap.dedent(
                    "\n".join(section.lines)
                ).strip()
                if text:
                    chunks.append(text)
                break

    # ── 2. Module-level code blocks ──────────────────────────────
    mod_addr = module_address(module.title)
    mod_blocks = _collect_blocks(module.body)
    if mod_blocks:
        chunks.append(_section(f"# {mod_addr}", mod_blocks))

    # ── 3. Subheading code blocks ────────────────────────────────
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            sub_blocks = _collect_blocks(item.body)
            if sub_blocks:
                chunks.append(_section(f"# {sub_addr}", sub_blocks))

    return "\n\n".join(chunks)


# ── Helpers ───────────────────────────────────────────────────

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
    them); subsequent blocks are separated by blank lines.
    """
    first, *rest = blocks
    head = f"{comment}\n{first}"
    if rest:
        return head + "\n\n" + "\n\n".join(rest)
    return head
