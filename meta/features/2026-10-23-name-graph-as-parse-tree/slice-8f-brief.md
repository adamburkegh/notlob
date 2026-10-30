# Slice 8f brief: fields and edges by rule

**For:** an implementing session. **Written by:** the design session,
2026-10-29. **Design:** D19 in `design.md` (Adam, 2026-10-29). After 8e.

## Why

8e first moved the tree into a `parent` field and was backed out, and
the deeper problem was that no rule said why one thing is a field and
another an edge. D19 is that rule:

> A value that is a node of the graph is an edge; any other value is a
> field of its node, and a field with several values is a list.

`notlob/schema/notlob.ttl` already states it in OWL: each edge kind is
an `owl:ObjectProperty` with `rdfs:range notlob:Node`; each node field
an `owl:DatatypeProperty`, or, for `notlob:ref`, an `ObjectProperty`
to a blank node (a structured value, not a node). Nothing yet holds the
JSON document to the same rule. This slice makes the ontology the one
statement of it and tests the JSON schema and the documents against it.
No output changes.

## The change

1. **Schema agrees with ontology.** A test reads `notlob.ttl` (with
   `rdflib`, as `tests/test_turtle.py` does) and `name_graph.json`:
   * the `GraphEdge` `kind` enum, lower-cased, is exactly the set of
     `owl:ObjectProperty`s whose `rdfs:range` is `notlob:Node`;
   * every `GraphNode` property maps to an ontology property that is
     not one of those, by the mapping the Turtle writer uses
     (`start_line` to `startLine`, `refs` to `ref`, `label` to
     `rdfs:label`, `kind` to `rdf:type`); a `GraphNode` property with
     no mapping fails the test, so a new field must be placed;
   * every property of `GraphRef` likewise maps to a non-edge property.
   Take the mapping from the Turtle writer if it can be read from there
   rather than restating it in the test; if it cannot without
   refactoring, restate it in the test and say so.
2. **Documents keep the rule.** Over every example project at every
   level: each edge's `source` and `target` is the `address` of a node
   in the document; no node field but `address` and `label` holds a
   node's address, at any depth (list items and `refs` entries
   included). `label` is excluded because a module whose title is one
   lower-case word would equal its own address.
3. **The ontology's comments brought up to 8e.** `notlob:file`: the
   file a *module* is, present on modules only. `notlob:named`: drop
   "its rdfs:label is the name" (only a module has one now); say its
   address ends in the name, as `name_graph.json` does. Read the other
   comments for anything else 8e made stale and fix it; report each.
4. **The rule in the schema.** One sentence in `name_graph.json`'s top
   description: a value that is a node is an edge, any other a field.

## Rules

* **May touch:** `notlob/schema/notlob.ttl` (comments only),
  `notlob/schema/name_graph.json` (descriptions only), tests.
* **Must not touch:** any output, `graph.py`, the bindings, the model,
  the grammar. If the rule finds a real violation in an output, stop and
  report it; do not fix it here.
* No assertion changes. **Failing tests first:** show each new test
  failing, by sabotage if the code already passes it (add a field
  holding an address to one node; add an edge kind to the enum that is
  not in the ontology), restored with Edit, and say so.
* Do not commit or stage. 80-character lines. No slice wording. Plain
  `pytest` and `ruff` calls.

## When to stop

Stop and report if the rule fails on a real document or on the
schemas: that is a design question, not a test to bend.

## When you are done

Report: the tests and how each was seen to fail; each ontology comment
changed, old and new; the full suite; anything you stopped on.
