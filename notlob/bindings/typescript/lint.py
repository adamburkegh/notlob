"""notlob.bindings.typescript.lint — placeholder for TypeScript linting.

Biome (https://biomejs.dev) is the planned linter — it is to TypeScript
what ruff is to Python: fast, zero-config, lint + format in one tool.

This module is a stub that returns no results until the biome
integration is implemented.  The ``BindingKit.lint`` field is set to
``None`` in ``__init__.py`` rather than pointing here; this file
exists as a documented extension point.

Implementation notes (for when this is built)
----------------------------------------------
* Run ``biome check --stdin-filename=module.ts --reporter=json -``
  with the assembled source on stdin.
* Discover biome the same way the runner discovers tsx: check
  ``node_modules/.bin/biome`` relative to the project root first,
  then fall back to PATH.
* Build the source map from ``// <address>`` location comments using
  the same regex as the Haskell lint module (pattern:
  ``^// ([a-z][a-z0-9/_-]*(?:#[^\\n]*)?)$``).
* Translate biome's ``location.start.line`` to a section address via
  the source map, falling back to the module address.
"""
