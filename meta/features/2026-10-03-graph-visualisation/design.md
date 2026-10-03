# Design note: a picture of the name-graph

**Status:** declined for core; where it lives instead is undecided
**Origin:** notlob-vids backport report (section 3) and follow-up
dialogue, 2026-10-03.

## The proposal

notlob-vids has a layout for the name-graph that works on real projects
and comes with checked guarantees, using only the standard library. The
report suggested `notlob graph --format svg`, optionally, and a
`--format layout` that emits positions as JSON.

The layout, in two levels:

- **Inside a module, a flower.** The tree edges (`CONTAINS`, `DEFINES`,
  `USES_EXTERNAL`) make each module a tree. The module sits at the
  centre, its contents on an outer ring in source order grouped by
  subheading, each subheading on an inner ring at the mean angle of its
  children. Ring radii are computed, not tuned.
- **Between modules, a sunflower spiral in dependency order.** Modules
  are ordered by import depth; the k-th sits at radius proportional to
  the square root of k, turned by the golden angle from the last
  (Vogel's model), the scale growing until clusters keep a gap.
  Concentric rings by depth failed on real data (pn-chomper's imports
  form almost a single chain, so each ring held one module).

Guarantees, all checked: every node has a position and lies inside its
cluster's circle; clusters keep a minimum gap; nodes keep a minimum
spacing; the layout is deterministic.

## Decision

Not in core. Visualisation is a UI layer: it pulls in dependencies and
tends to promote coupling to the graph's shape. Core keeps to data and
the agent-facing queries (`2026-10-03-graph-data-and-queries`).
`--format layout` was also deferred: even positions as JSON is a
long-term commitment to an algorithm and its guarantees.

Adam's interest remains: notlob programs are graph-shaped, and as agents
take more of the line-of-code load, maps matter even in a literate
project. The open question is the home, with two candidates:

- a separate small package consuming `notlob graph --format json`;
- a literate notlob project under `examples/`. The geometry is already
  written in notlob with property tests, which also suits the paper.

## Reference code

notlob-vids (`C:\Users\adamb\bpm\notlob-vids`): `src/graph.lob` (pure
geometry: `tree_parents`, `cluster_of`, `flower`, `depths`, `arrange`,
`layout`, `well_formed`, `~property layouts-are-well-formed`,
`synthetic_graph`), `src/style.lob` (palette, plus the claim that every
kind in `name_graph.json` has a colour) and `src/teaser.lob`
(`node_dots`, `edge_lines`: how positions become a drawing).
