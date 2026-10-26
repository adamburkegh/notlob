"""notlob.bindings.python — Python binding kit.

Assembles the Python BindingKit from its component submodules and
exposes `kit` as the canonical Python binding instance.

Usage::

    from notlob.bindings.python import kit
    enrich(graph, module, kit.extract_symbols)
    source = kit.assemble(module)
    results = kit.run_examples(module, examples, file_path=path)

where *examples* are the ``~example`` claims notlob collected from the
module's graph (``notlob.graph.claims_to_run``).
"""

from pathlib import Path
from typing import Sequence

import textwrap

from notlob.bindings import (
    BindingKit, ClaimResult, ClaimToRun, Status, run_bodies,
)
from notlob.bindings.python.assemble import assemble, assemble_with_deps
from notlob.bindings.python.lint import lint_python
from notlob.bindings.python.runner import (
    run_examples, run_tests, run_properties,
)
from notlob.bindings.python.symbols import (
    extract_calls, extract_symbols, split_imports,
)
from notlob.model import Module


def build_python(
    module: Module,
    claims: Sequence[ClaimToRun],
    file_path: Path | None = None,
    *,
    deps: Sequence[Module] = (),
) -> str:
    """Assemble *module* with inlined deps for the build command.

    Inlines *deps*, the modules whose code *module* needs, before the
    module's own code (see ``assemble_with_deps``), and returns a single
    self-contained Python source string — only the target module's
    ``~run`` *claims* are appended, never a dependency's. *file_path* is
    accepted for the shared ``BindingKit`` call site.

    ``~run on-load`` bodies are appended unconditionally, at module
    scope. ``~run`` (bare) and ``~run on-invocation`` bodies -- Python
    treats these as equivalent, since there's only ever one meaningful
    choice for a Python process -- are appended together afterwards,
    wrapped in ``if __name__ == "__main__":`` so those side effects
    fire when the artifact is run directly but not when it's merely
    imported as a module.
    """
    source = assemble_with_deps(module, list(deps))
    on_load, on_invocation = run_bodies(claims)
    if on_load:
        source = source + "\n\n" + "\n\n".join(on_load)
    if on_invocation:
        run_body = textwrap.indent("\n\n".join(on_invocation), "    ")
        source = source + '\n\n\nif __name__ == "__main__":\n' + run_body
    return source


#: The assembled Python binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    extract_calls=extract_calls,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
    lint=lint_python,
    build=build_python,
    comment_prefix="#",
    complete_references=True,   # every ast.Name load, not only calls
    split_imports=split_imports,
)

__all__ = [
    "kit", "extract_symbols", "assemble",
    "run_examples", "run_tests", "run_properties", "ClaimResult", "Status",
]
