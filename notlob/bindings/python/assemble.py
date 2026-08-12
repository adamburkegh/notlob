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
  4. #Appendix code blocks, if any -- same status as main-body code,
     not test-only or build-only.  #Appendix isn't structurally
     mandated to be test-support: an author might move a supporting
     helper there just to keep the main argument's pacing tight, and
     that helper needs to work in `notlob build`/`notlob run` too, not
     only during `notlob test` -- so there's no special-casing here,
     it's included exactly like a main-body subheading would be.

All top-level chunks -- and all code blocks within one chunk -- are
separated by two blank lines, matching PEP8/isort's convention for
top-level definitions (verified against a real ruff run with `I`
rules enabled: a single blank line there is reported as ``I001``,
"Import block is un-sorted or un-formatted", with isort's own
suggested fix being to add the second blank line). A location comment
is joined directly to its first code block with no intervening blank
line.
"""

from __future__ import annotations

import textwrap

from notlob.bindings import assemble_section, collect_blocks
from notlob.graph import module_address, subheading_address
from notlob.model import (
    AppendixSection, Module, ReferencesSection, Subheading,
)
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
        chunks.append(
            assemble_section(f"# {mod_addr}", mod_blocks, blank_lines=2)
        )

    # ── 3. Subheading code blocks ────────────────────────────────
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            sub_blocks = collect_blocks(item.body)
            if sub_blocks:
                chunks.append(assemble_section(
                    f"# {sub_addr}", sub_blocks, blank_lines=2,
                ))

    # ── 4. #Appendix code blocks ─────────────────────────────────
    if module.post_text is not None:
        for section in module.post_text.sections:
            if not isinstance(section, AppendixSection):
                continue
            appendix_blocks = collect_blocks(section.body)
            if appendix_blocks:
                chunks.append(assemble_section(
                    f"# {mod_addr}#Appendix", appendix_blocks,
                    blank_lines=2,
                ))
            for item in section.body:
                if isinstance(item, Subheading):
                    # Same address scheme graph.py's build() already
                    # uses for appendix subheadings (via
                    # _add_subheading) -- mod_addr#Title, not nested
                    # under #Appendix, so a ##Name reference from the
                    # main body resolves to the same address this
                    # location comment names.
                    sub_addr = subheading_address(mod_addr, item.title)
                    sub_blocks = collect_blocks(item.body)
                    if sub_blocks:
                        chunks.append(assemble_section(
                            f"# {sub_addr}", sub_blocks, blank_lines=2,
                        ))

    return "\n\n\n".join(chunks)


def assemble_with_deps(module: Module, dep_modules: list[Module]) -> str:
    """Assemble *module* with *dep_modules* inlined before it.

    Used by ``build_python`` so a build artifact is genuinely
    standalone-executable: ``notlob test``/``notlob run`` resolve
    cross-module ``#References`` at execution time via ``ModuleCache``,
    but a build artifact has no loader around it, so dependency source
    has to be inlined directly instead. Dependencies are assembled with
    the same ``assemble()`` used for the target module, so each one's
    own ``#References`` language imports come along for free — no
    separate import-merging step is needed. Mirrors
    ``notlob.bindings.haskell.assemble.assemble_with_deps``.

    Returns an empty string if neither the module nor any dependency
    contains code.
    """
    chunks = [text for dep in dep_modules if (text := assemble(dep))]
    own = assemble(module)
    if own:
        chunks.append(own)
    return "\n\n\n".join(chunks)


