"""notlob.bindings.typescript.assemble — TypeScript code assembler.

Assembles a Module into a single executable TypeScript string by
collecting code blocks in order, prepending #References imports,
and inserting ``// <address>`` source-location comments for the
linter's source map and for human readers.

Assembly order
--------------
  1. #References lines  (import statements; lob-refs dropped)
  2. Module-level code blocks  (preceded by ``// <module_address>``)
  3. Subheading code blocks in document order
     (each group preceded by ``// <subheading_address>``)

Lob-ref lines in #References (those whose stripped form starts with
``#``) are dropped; only real TypeScript ``import`` statements are
forwarded.  All other lines are emitted as-is.

Location comments use ``//`` (TypeScript's line-comment syntax) so
they are valid TypeScript and invisible to the runtime.
"""

from __future__ import annotations

import textwrap

from notlob.graph import module_address, subheading_address
from notlob.model import CodeBlock, Module, ReferencesSection, Subheading


def assemble(module: Module) -> str:
    """Assemble module code blocks into one executable TypeScript string.

    Returns an empty string if the module contains no code.
    """
    chunks: list[str] = []

    # ── 1. #References ──────────────────────────────────────────
    if module.post_text is not None:
        for section in module.post_text.sections:
            if isinstance(section, ReferencesSection):
                import_lines = _ts_imports(section.lines)
                text = textwrap.dedent('\n'.join(import_lines)).strip()
                if text:
                    chunks.append(text)
                break

    # ── 2. Module-level code blocks ──────────────────────────────
    mod_addr   = module_address(module.title)
    mod_blocks = _collect_blocks(module.body)
    if mod_blocks:
        chunks.append(_section(f'// {mod_addr}', mod_blocks))

    # ── 3. Subheading code blocks ────────────────────────────────
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr   = subheading_address(mod_addr, item.title)
            sub_blocks = _collect_blocks(item.body)
            if sub_blocks:
                chunks.append(_section(f'// {sub_addr}', sub_blocks))

    return '\n\n'.join(chunks)


# ── Helpers ───────────────────────────────────────────────────

def _ts_imports(lines: list[str]) -> list[str]:
    """Return TypeScript import lines, dropping lob-refs.

    A lob-ref line is any line whose stripped form starts with ``#``.
    All other non-blank lines are assumed to be TypeScript ``import``
    statements or other top-level declarations and are kept verbatim.
    """
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith('#')
    ]


def _collect_blocks(body: list) -> list[str]:
    """Return dedented, stripped text for each CodeBlock in body."""
    result = []
    for item in body:
        if isinstance(item, CodeBlock):
            text = textwrap.dedent('\n'.join(item.lines)).strip()
            if text:
                result.append(text)
    return result


def _section(comment: str, blocks: list[str]) -> str:
    """Join a location comment and its code blocks.

    The comment is glued directly to the first block; subsequent
    blocks within the same section are separated by blank lines.
    """
    first, *rest = blocks
    head = f'{comment}\n{first}'
    if rest:
        return head + '\n\n' + '\n\n'.join(rest)
    return head
