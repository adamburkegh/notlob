> **Provenance.** Copied verbatim (below this note) on 2026-10-03 from
> `notlob-vids/docs/notlob-backport.md`; the original lives in the
> notlob-vids repo and may have changed since. This is the source
> document for the proposals it led to, each of which has its own design
> note in a sibling directory of `meta/features/`:
>
> - section 1: `2026-10-03-test-json-shape`
> - section 2: `2026-10-03-token-spans`
> - section 3: `2026-10-03-graph-visualisation` (declined for core)
> - section 4: `2026-10-03-project-option`
> - follow-up dialogue: `2026-10-03-graph-data-and-queries`,
>   `2026-10-03-claim-body-style-check`, `2026-10-03-docs-gaps-from-notlob-vids`
> - "Smaller observations": `bugs/2026-10-03-on-build-single-file-build`;
>   the F811 item is already fixed (`bugs/2026-10-01-python-lint-cross-module`);
>   `~ignore` stays shelved.

# Features to backport into notlob

notlob-vids builds animations about notlob, in notlob. Along the way it
grew three pieces that are really features of notlob itself, plus one
small command-line gap. This document describes them for the notlob
project. The working code is in this repository's `src/` and can be
copied; each section says where.

The principle used to sort them: **data belongs in notlob, pictures
don't.** Anything a tool or an agent would want as structured output is
worth having in the core. Rendering (manim, palettes, animation) should
stay outside.

Summary:

| # | Feature | Proposed interface | Size | Priority |
|---|---------|--------------------|------|----------|
| 1 | Claim results as data | `notlob test --format json` | small | high |
| 2 | Token spans | `notlob tokens <file>` (or a library function) | small | high |
| 3 | Graph picture | `notlob graph --format svg` | medium | optional |
| 4 | Project directory option | `--project DIR` on commands | small | medium |

---

## 1. Claim results as data

### Why

notlob-vids shows the real results of running a module's claims, with a
tick on each source line notlob reports. To get them it runs
`notlob test` and parses the human-readable output with a regular
expression:

```
PASS   marking.lob:136  petri/marking#Enabling and Firing#example#1  tokenCount(_m0, 'p1') === 1
```

That works, but it depends on column layout that is meant for people.
Any tool that wants claim results (an editor showing pass/fail in the
margin, a CI summary, an agent deciding what to fix) has the same need.

### Proposed interface

```
notlob test [file] --format json
```

One JSON document on stdout:

```json
{
  "results": [
    {
      "status": "PASS",
      "file": "petri/marking.lob",
      "line": 136,
      "address": "petri/marking#Enabling and Firing#example#1",
      "kind": "EXAMPLE",
      "source": "tokenCount(_m0, 'p1') === 1"
    }
  ],
  "lint": [
    {"address": "teaser", "code": "F401", "message": "...", "column": 19}
  ],
  "checks": [
    {"check": "typos", "severity": "advisory", "message": "...", "addresses": ["board#draw_door", "board#draw_room"]}
  ],
  "summary": {"passed": 15, "failed": 0, "lint": 0}
}
```

Notes:

- `file` should be relative to the project root, not a bare file name.
  The text output prints `marking.lob:136`, which is ambiguous when two
  modules share a file name in different directories.
- `status` is one of `PASS`, `FAIL`, `ERROR`, `SKIP`, as now.
- For `FAIL`/`ERROR`, include `message`, and for properties the
  exception type (already carried since the property-reporting fix).
- Exit codes stay as they are.
- A schema file beside `schema/name_graph.json` would let consumers
  validate, the way notlob-vids validates its palette against the graph
  schema.

### Reference code here

`src/evidence.lob`, section `##Claim Results`:

- `RESULT_LINE` and `parse_results(output)`: the regex this feature
  would make unnecessary.
- `claim_results(project, module)`: the caller, which would become a
  `json.loads`.

---

## 2. Token spans

### Why

To colour `.lob` source faithfully, notlob-vids does not write a
highlighter. It parses with notlob's own grammar and reads positions
off the parse tree, so what is coloured as a claim is exactly what
notlob will run as a claim. The same data is what an editor plugin, an
HTML `notlob weave`, or a documentation site needs. Today each of those
would have to rediscover two non-obvious details:

1. The parser normalises token *values* (strips `#`, `##`, trailing
   newlines), so values cannot be used for positions. Positions must
   come from `start_pos`/`end_pos`/`line`, which survive normalisation.
2. One terminal means different things in different places.
   `INDENTED_LINE` is code in a `code_block`, a claim body in a `claim`,
   `named_test`, `test_group` or `test_item`, and a declaration in
   `references_section`. The kind has to come from the enclosing rule.

### Proposed interface

A library function in notlob, and optionally a command over it:

```python
from notlob.tokens import spans

spans(source: str) -> list[Span]   # Span(line, start, end, kind)
```

```
notlob tokens <file> [--format json]
```

- `line` is 0-based, `start`/`end` are columns, end exclusive.
- Spans never cross a line and never include the newline.
- **Tiling guarantee:** on every line the spans are in order, do not
  overlap, leave no gap and end where the line ends. Every character is
  in exactly one span.

Kinds, as used here (the names are a suggestion):

| Kind | From |
|------|------|
| `title` | `MOD_HEAD` |
| `subheading` | `SUBHEAD` |
| `prose` | `LINE_START_TEXT`, `PROSE_TEXT` |
| `ref` | `REF` |
| `bullet` | `BULLET` |
| `sigil` | `SIGIL`, `TEST_SIGIL` |
| `code` | `INDENTED_LINE` in `code_block` |
| `claim` | `INDENTED_LINE` in `claim`, `named_test`, `test_group`, `test_item` |
| `structure` | everything else: separator, post-text heads, binding declarations, references lines |

### Not proposed for the core

notlob-vids goes one step further and colours the *inside* of code
using Pygments, choosing the lexer from the binding's `~language`. That
is a rendering concern and adds a dependency; it should stay outside
notlob. A consumer can do it in a few lines given the spans (see
`syntax_spans` below).

### Reference code here

`src/highlight.lob`:

- `Span`, `TOKEN_KINDS`, `INDENTED_KINDS`, `classify(rule, token_type)`
- `_tokens(tree)`: pairs each token with its enclosing rule
- `spans(source)`: the function to port
- `tiles(source, spans)`: the tiling check
- `~property spans-tile-source`: generated documents all tile
- `#Tests` `real sources tile`: every `.lob` in pn-chomper, notlob's
  examples and this project tiles. Worth porting as a test over
  notlob's own `examples/`.
- `binding_language(root)`, `code_blocks`, `syntax_kind`,
  `syntax_spans`, `highlight`: the Pygments layer, for reference only.

---

## 3. Graph picture

### Why

`notlob graph` exports the name-graph as JSON or Turtle. A picture of
it is a good way to see a project's shape, and notlob-vids has a layout
that works on real projects and comes with guarantees. It needs only
the standard library.

### What the layout does

Two levels, matching the two kinds of structure in the graph:

- **Inside a module, a flower.** The tree edges (`CONTAINS`, `DEFINES`,
  `USES_EXTERNAL`) make each module a tree. The module node sits at the
  centre, everything it holds on an outer ring in source order, grouped
  by subheading, and each subheading on an inner ring at the mean angle
  of its children. Ring radii are computed, not tuned, so neighbours are
  a fixed spacing apart.
- **Between modules, dependency order on a sunflower spiral.** Modules
  are ordered by import depth (a module that imports nothing is depth
  0; otherwise one more than the deepest module it imports; the binding
  last). The k-th module in that order sits at radius proportional to
  √k, turned by the golden angle from the last (Vogel's model). The
  spiral's scale grows until no two clusters are closer than a gap.

Concentric rings by depth were tried first and failed on real data:
pn-chomper's imports form nearly a single chain, so each ring held one
module and the picture collapsed into a line. The spiral fills a disc
whatever the depth structure.

### Guarantees (all checked)

- Every node has a position.
- Every node lies inside its cluster's circle.
- Clusters keep a minimum gap.
- Nodes within a cluster keep a minimum spacing.
- The layout is deterministic: same graph, same picture.

### Proposed interface

```
notlob graph --format svg [--output FILE]
```

- Nodes coloured by kind, edges styled by kind. A legend is worth
  having in a standalone picture (notlob-vids leaves it out because the
  video teaches the palette first).
- Suggested as an **optional** feature, or a separate small package, so
  the core graph command stays a data export.
- An `--format layout` that emits positions as JSON (addresses to x, y,
  plus cluster circles) would serve tools that want to draw the graph
  themselves, and is smaller than committing to SVG styling.

### Reference code here

`src/graph.lob` (pure geometry, no drawing):

- `tree_parents`, `cluster_of`: which module each node belongs to;
  externals join the binding
- `flower(root, members, parents, kinds, lines)`: one module's layout
- `depths(clusters, imports, binding)`: dependency order
- `arrange(radii, depth)`: the sunflower spiral
- `layout(graph, binding) -> Layout(positions, clusters, cluster_of)`
- `well_formed(graph, layout)`: the guarantees, as one function
- `~property layouts-are-well-formed`: over generated module graphs
- `synthetic_graph(sizes, imports)`: the generator's fixture

`src/style.lob`: `NODE_COLOURS`, `EDGE_COLOURS`, `EDGE_OPACITY`,
`EDGE_WIDTH`, and the claim that every kind in `name_graph.json` has a
colour. Useful as a starting palette.

`src/teaser.lob`: `node_dots`, `edge_lines` show how positions become
a drawing (in manim; an SVG writer would be the equivalent).

---

## 4. Project directory option

### Why

`notlob graph`, `notlob query` and whole-project `notlob test` find the
project from the current directory. To run them against another project
(here: reference projects under `ref-projects/`), the caller has to
change directory or spawn a subprocess with a different working
directory. Every use in notlob-vids does the latter:

```python
subprocess.run(["notlob", "graph", "--format", "json"], cwd=project_dir, ...)
```

### Proposed interface

```
notlob --project DIR graph --format json
notlob --project DIR query content "petri/marking#Enabling and Firing"
notlob --project DIR test
```

A global option naming the project root (the directory containing
`binding.lob`), like `git -C`. File arguments already locate their
project by walking up, so this only matters for the commands that take
no file.

---

## Smaller observations

These came up while building and may already be tracked:

- **`notlob build --output DIR <file>` with an `~on-build` hook.** A
  single-module build of a project whose hook expects the whole build
  (pn-chomper's `inject-bundle.ts`) prints a warning and the hook exits
  1, though the module is built and notlob exits 0. Skipping the hook
  for single-file builds, or a `--no-on-build` flag, would avoid the
  noise.
- **F811 across lob-refs** (reported; follow-up deferred): two modules
  importing the same name. notlob-vids has no remaining workaround in
  its sources now that dependency imports are no longer prepended, so
  this may already be resolved by the stub approach.
- **`~ignore`** (shelved): notlob-vids moved its modules under `src/`
  instead, so reference projects are siblings of the project root.

## Fixed during this project

For the record, reported from notlob-vids and fixed in notlob-lab:

- Lint F401 for imports used only by claims
- Lint findings in a dependency attributed to the importing module
- Address collision (`##Layout` with `class Layout`) crashing instead
  of reporting
- Property failures losing their real exception behind Hypothesis's
  seed hint
