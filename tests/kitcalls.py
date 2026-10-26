"""Calls to a binding kit the way notlob makes them.

notlob collects the claims of a module from its graph and hands each
binding the ones it runs: ``run_examples(module, claims, ...)``. These
helpers let a test call a kit callable with only the module, as a test of
the binding itself wants to, and have the claims collected the way notlob
collects them.
"""

from __future__ import annotations

from pathlib import Path

from notlob import build, build_package, from_tree, parse
from notlob.bindings import ClaimToRun
from notlob.graph import claims_to_run, module_address
from notlob.project import find_project_root, load_dependencies


def claims_of(module, *kinds: str) -> list[ClaimToRun]:
    """The claims of *module* as notlob collects them, only those of the
    given *kinds* (``"EXAMPLE"``, ``"PROPERTY"``, ``"RUN"``, ``"TEST"``)
    when there are any."""
    graph = build(module)
    return [c for c in claims_to_run(graph, module_address(module.title))
            if not kinds or c.kind in kinds]


def claims_in(source: str, *kinds: str) -> list[ClaimToRun]:
    """The claims of the module written in *source*."""
    return claims_of(from_tree(parse(source)), *kinds)


def dependency_modules(module, root: Path, kit=None) -> list:
    """The modules whose code *module* needs, parsed and in load order,
    as a command works them out from the package graph of the project at
    *root* and hands them to a binding as ``deps``. Without a *kit* use
    cannot be told from the graph, and the address tree decides."""
    graph = build_package(
        root, kit.extract_symbols if kit else None,
        call_extractor=kit.extract_calls if kit else None)
    return load_dependencies(graph, module_address(module.title), root, kit)


def in_project(function, kit, *kinds: str):
    """*function*, a kit callable taking ``(module, claims, *, file_path,
    deps, ...)``, as a callable taking ``(module, file_path=..., ...)``
    that collects the claims of the given *kinds* from the module and the
    dependencies from the project the file is in, as a command does."""
    def call(module, *args, file_path=None, **kwargs):
        root = find_project_root(file_path) if file_path else None
        deps = dependency_modules(module, root, kit) if root else []
        return function(module, claims_of(module, *kinds), *args,
                        file_path=file_path, deps=deps, **kwargs)
    call.__name__ = function.__name__
    call.__doc__ = function.__doc__
    return call


def building(function, kit):
    """*function*, a kit ``build`` taking ``(module, claims, file_path, *,
    deps)``, as a callable taking ``(module, file_path)`` that collects
    the ``~run`` claims and the dependencies as a command does."""
    def call(module, file_path):
        root = find_project_root(file_path)
        deps = dependency_modules(module, root, kit) if root else []
        return function(module, claims_of(module, "RUN"), file_path,
                        deps=deps)
    call.__name__ = function.__name__
    call.__doc__ = function.__doc__
    return call


def collecting(function, *kinds: str):
    """*function*, a kit callable taking ``(module, claims, ...)``, as a
    callable taking ``(module, ...)`` that collects the claims of the given
    *kinds* (all, when none are given) from the module itself."""
    def call(module, *args, **kwargs):
        return function(module, claims_of(module, *kinds), *args, **kwargs)
    call.__name__ = function.__name__
    call.__doc__ = function.__doc__
    return call
