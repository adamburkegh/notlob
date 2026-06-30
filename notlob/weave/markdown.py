"""notlob.weave.markdown — Markdown rendering for .lob modules.

Converts a parsed Module to GitHub-flavoured Markdown.

Design decisions
----------------
- The ``---`` separator and post-text machinery sections (#Binding,
  #References) are omitted: they are runtime infrastructure, not
  documentation.
- ``#Tests`` sections are included as a ``## Tests`` heading with
  fenced code blocks for each group, keeping the document
  self-contained.
- ``#Appendix`` sections are rendered as second-level headings.
- ``~run`` claims are omitted; ``~example`` and ``~property`` (and
  any other sigil) are rendered with a bold label followed by a
  fenced code block.
- Inline ``##Label`` cross-references become local anchor links
  (GitHub-style slug); ``#Label`` references become inline code
  because the target may live in another document.
"""

from __future__ import annotations

import textwrap
from typing import Union

from notlob.model import (
    AppendixSection,
    BindingSection,
    BulletBlock,
    Claim,
    CodeBlock,
    Module,
    ProseBlock,
    Ref,
    ReferencesSection,
    Subheading,
    TestGroup,
    TestsSection,
)


# ── Ref rendering ─────────────────────────────────────────────

def _anchor(label: str) -> str:
    """Return a GitHub-style heading anchor slug from *label*."""
    return label.lower().replace(" ", "-")


def _render_ref(ref: Ref) -> str:
    """Render an inline cross-reference as Markdown."""
    if ref.sub:
        # ##Label — local subheading; use an anchor link
        return f"[{ref.label}](#{_anchor(ref.label)})"
    # #Label — module or symbol reference; render as inline code
    return f"`{ref.label}`"


# ── Prose rendering ───────────────────────────────────────────

def _prose(block: ProseBlock) -> str:
    """Render a prose block as a Markdown paragraph."""
    parts: list[str] = []
    for span in block.spans:
        if isinstance(span, Ref):
            parts.append(_render_ref(span))
        else:
            parts.append(span)       # plain text or "\n" boundary span
    return "".join(parts)


# ── Bullet rendering ─────────────────────────────────────────

def _bullets(block: BulletBlock) -> str:
    """Render a bullet block as a Markdown unordered list."""
    return "\n".join(f"* {item}" for item in block.items)


# ── Code rendering ────────────────────────────────────────────

def _fenced(lines: list[str], language: str) -> str:
    """Render *lines* as a fenced Markdown code block.

    Common leading indentation is stripped by ``textwrap.dedent``
    so that the output is flush-left inside the fence.  Trailing
    blank lines are removed: the grammar may absorb a following
    blank line into the block, but it serves no purpose in output.
    """
    raw  = "\n".join(lines)
    body = textwrap.dedent(raw).rstrip("\n")
    return f"```{language}\n{body}\n```"


def _code(block: CodeBlock, language: str) -> str:
    return _fenced(block.lines, language)


# ── Claim rendering ───────────────────────────────────────────

_SIGIL_LABELS: dict[str, str] = {
    "~example":  "**Example:**",
    "~property": "**Property:**",
}


def _sigil_label(sigil: str) -> str:
    """Return a bold Markdown label for *sigil*."""
    if sigil in _SIGIL_LABELS:
        return _SIGIL_LABELS[sigil]
    name = sigil.lstrip("~")
    return f"**{name.capitalize()}:**"


def _claim(claim: Claim, language: str) -> str | None:
    """Render a claim as Markdown, or ``None`` for ``~run`` claims."""
    if claim.sigil == "~run":
        return None     # runtime-only — not documentary
    label = _sigil_label(claim.sigil)
    code  = _fenced(claim.lines, language)
    return f"{label}\n\n{code}"


# ── Subheading rendering ──────────────────────────────────────

def _subheading(sub: Subheading, language: str) -> str:
    parts: list[str] = [f"## {sub.title}"]
    for item in sub.body:
        rendered = _body_item(item, language)
        if rendered is not None:
            parts.append(rendered)
    return "\n\n".join(parts)


# ── Body dispatch ─────────────────────────────────────────────

def _body_item(
    item: Union[Subheading, CodeBlock, Claim, ProseBlock, BulletBlock],
    language: str,
) -> str | None:
    """Dispatch a body item to its renderer; return ``None`` to omit."""
    if isinstance(item, ProseBlock):
        return _prose(item)
    if isinstance(item, BulletBlock):
        return _bullets(item)
    if isinstance(item, CodeBlock):
        return _code(item, language)
    if isinstance(item, Claim):
        return _claim(item, language)
    if isinstance(item, Subheading):
        return _subheading(item, language)
    return None


# ── Post-text rendering ───────────────────────────────────────

def _tests_section(section: TestsSection, language: str) -> str | None:
    """Render a #Tests section, or ``None`` when empty."""
    if not section.items:
        return None
    parts: list[str] = ["## Tests"]
    # Accumulate consecutive bare-assertion strings into one block
    # so they read as a unified assertion list rather than many fences.
    pending: list[str] = []

    def _flush() -> None:
        if pending:
            parts.append(_fenced(pending[:], language))
            pending.clear()

    for item in section.items:
        if isinstance(item, TestGroup):
            _flush()
            parts.append(f"### {item.title}")
            parts.append(_fenced(item.lines, language))
        else:
            pending.append(item)    # bare INDENT assertion string

    _flush()
    return "\n\n".join(parts)


def _appendix_section(
    section: AppendixSection, language: str
) -> str:
    """Render a #Appendix: … section as a second-level heading."""
    # section.title is the full token, e.g. "#Appendix: Notes"
    raw = section.title.lstrip("#").strip()
    if raw.lower().startswith("appendix:"):
        raw = raw[len("appendix:"):].strip()
    parts: list[str] = [f"## {raw}"]
    for item in section.body:
        rendered = _body_item(item, language)
        if rendered is not None:
            parts.append(rendered)
    return "\n\n".join(parts)


def _post_section(section, language: str) -> str | None:
    """Dispatch a post-text section; return ``None`` to omit."""
    if isinstance(section, (BindingSection, ReferencesSection)):
        return None         # runtime machinery — omit from document
    if isinstance(section, TestsSection):
        return _tests_section(section, language)
    if isinstance(section, AppendixSection):
        return _appendix_section(section, language)
    return None


# ── Public API ────────────────────────────────────────────────

def weave_markdown(module: Module, language: str = "python") -> str:
    """Render *module* as a GitHub-flavoured Markdown document.

    Parameters
    ----------
    module:
        A parsed and modelled ``.lob`` module.
    language:
        Language tag for fenced code blocks (default: ``"python"``).
        Typically derived from the project's ``binding.lob``.

    Returns
    -------
    str
        The full Markdown document, terminated by a single newline.
    """
    parts: list[str] = [f"# {module.title}"]

    for item in module.body:
        rendered = _body_item(item, language)
        if rendered is not None:
            parts.append(rendered)

    if module.post_text:
        for section in module.post_text.sections:
            rendered = _post_section(section, language)
            if rendered is not None:
                parts.append(rendered)

    return "\n\n".join(parts) + "\n"
