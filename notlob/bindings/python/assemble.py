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

from notlob.bindings import assemble_section, collect_blocks
from notlob.graph import module_address, subheading_address
from notlob.model import Module, ReferencesSection, Subheading
from notlob.project import parse_python_imports


def assemble(module: Module) -> str:
    """Assemble module code blocks into one executable Python string.

    Returns an empty string if the module contains no code.
    """
    chunks: list[str] = []

    # ── 1. #References ──────────────────────────────────────────
    if module.post_text is not None:
        for section in module.post_text.sections:
            if isinstance(section, ReferencesSection):
                import_lines = parse_python_imports(section.lines)
                text = textwrap.dedent(
                    "\n".join(import_lines)
                ).strip()
                if text:
                    chunks.append(text)
                break

    # ── 2. Module-level code blocks ──────────────────────────────
    mod_addr = module_address(module.title)
    mod_blocks = collect_blocks(module.body)
    if mod_blocks:
        chunks.append(assemble_section(f"# {mod_addr}", mod_blocks))

    # ── 3. Subheading code blocks ────────────────────────────────
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            sub_blocks = collect_blocks(item.body)
            if sub_blocks:
                chunks.append(assemble_section(f"# {sub_addr}", sub_blocks))

    return "\n\n".join(chunks)


