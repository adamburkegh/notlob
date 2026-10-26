# Recorded data

`claims_<example>.json` is what each language's runner collected from every
module of the example project of that name, before the claims were collected
from the name-graph: for each module its `examples`, `tests` and `properties`
(as address, assertion or sigil, and line) and the bodies of its `~run`
claims. `tests/test_claims_to_run.py` requires `claims_to_run` to give the
same, but for two addresses that have moved on purpose since (a run of bare
assertions, and a named `~property`), which the test compares through
`_as_recorded`.

They are data, not expected values to edit by hand.
