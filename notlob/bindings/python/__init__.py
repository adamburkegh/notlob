"""notlob.bindings.python — Python binding kit.

Assembles the Python BindingKit from its component submodules and
exposes `kit` as the canonical Python binding instance.

Usage::

    from notlob.bindings.python import kit
    enrich(graph, module, kit.extract_symbols)
    source = kit.assemble(module)
    results = kit.run_examples(module, file_path=path)
"""

from pathlib import Path

import textwrap

from notlob.bindings import BindingKit, ClaimResult, Status
from notlob.bindings.python.assemble import assemble, assemble_with_deps
from notlob.bindings.python.lint import lint_python
from notlob.bindings.python.runner import (
    _load_dep_modules, run_examples, run_tests, run_properties,
)
from notlob.bindings.python.symbols import extract_symbols
from notlob.model import Claim, Module, Subheading


def build_python(
    module: Module,
    file_path: Path | None = None,
) -> str:
    """Assemble *module* with inlined deps for the build command.

    Loads lob-ref dependencies from the project tree rooted at
    *file_path*, inlines their code before the module's own code (see
    ``assemble_with_deps``), and returns a single self-contained Python
    source string. ``~run`` claim bodies are appended after the
    module's own code so the artifact is directly executable — only
    the target module's ``~run`` claims fire, never a dependency's.
    """
    dep_modules = _load_dep_modules(module, file_path)
    source = assemble_with_deps(module, dep_modules)
    run_parts: list[str] = []
    for item in module.body:
        if isinstance(item, Claim) and item.sigil == "~run":
            run_parts.append(
                textwrap.dedent("\n".join(item.lines)).strip()
            )
        elif isinstance(item, Subheading):
            for sub in item.body:
                if isinstance(sub, Claim) and sub.sigil == "~run":
                    run_parts.append(
                        textwrap.dedent("\n".join(sub.lines)).strip()
                    )
    if run_parts:
        source = source + "\n\n" + "\n\n".join(run_parts)
    return source


#: The assembled Python binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
    lint=lint_python,
    build=build_python,
    comment_prefix="#",
)

__all__ = [
    "kit", "extract_symbols", "assemble",
    "run_examples", "run_tests", "run_properties", "ClaimResult", "Status",
]
