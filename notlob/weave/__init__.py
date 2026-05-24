"""notlob.weave — Document rendering for .lob modules.

A .lob file is a single artifact with multiple renderings.  The weave
layer produces human-readable document formats from a parsed Module;
the source file and the runtime are unaffected.

Supported formats
-----------------
markdown   Plain Markdown suitable for GitHub, documentation sites,
           and README generation.  Use ``weave_markdown``.

Planned
-------
typst      Typst source for typeset PDF output with theorem/property
           environments and validated cross-reference links.
"""

from .markdown import weave_markdown

__all__ = ["weave_markdown"]
