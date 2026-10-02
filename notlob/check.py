"""notlob.check — semantic consistency checker.

Analyses the name graph for naming inconsistencies and structural
issues.  Findings have a severity:

- ``advisory`` — informational, never fails a build.
- ``error`` — fails ``notlob check`` and blocks the build.

The architecture is extensible: future checks (embedding-based
similarity, LLM judgment) register as new entries in the checker
registry without changing the public interface.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from notlob.graph import EdgeKind, NameGraph, NodeKind


@dataclass(frozen=True)
class Finding:
    check: str
    message: str
    addresses: tuple[str, ...]
    severity: str = "advisory"


#: Registered check names, in run order. The single source of truth for
#: what ``run_checks`` runs and what ``--only`` accepts (``notlob/cli.py``
#: imports this rather than keeping its own ``choices=`` list, which
#: otherwise drifts the moment a check is added here and not there).
CHECK_NAMES: tuple[str, ...] = (
    "imports", "typos", "conventions", "titles", "references",
    "style", "quantifier",
)


def run_checks(
    graph: NameGraph,
    enabled: set[str] | None = None,
) -> tuple[list[Finding], dict[str, int]]:
    """Run all (or selected) checks and return (findings, counts).

    *counts* maps each check name to the number of findings it produced,
    including checks that found nothing (count 0).
    """
    checkers: dict[str, object] = {
        "imports": lambda: check_imports(graph),
        "typos": lambda: check_typos(graph),
        "conventions": lambda: check_conventions(graph),
        "titles": lambda: check_titles(graph),
        "references": lambda: check_references(graph),
        "style": lambda: check_style(graph),
        "quantifier": lambda: check_quantifier(graph),
    }
    assert set(checkers) == set(CHECK_NAMES), (
        "CHECK_NAMES has drifted from run_checks's own registry"
    )
    if enabled is not None:
        checkers = {k: v for k, v in checkers.items() if k in enabled}
    findings: list[Finding] = []
    counts: dict[str, int] = {}
    for name, checker in checkers.items():
        batch = checker()
        counts[name] = len(batch)
        findings.extend(batch)
    return findings, counts


def has_errors(findings: list[Finding]) -> bool:
    """Return True if any finding has error severity."""
    return any(f.severity == "error" for f in findings)


def coverage_summary(graph: NameGraph) -> str:
    """Return a one-line coverage summary for ``--verbose`` output."""
    n_modules = sum(1 for _ in graph.nodes(kind=NodeKind.MODULE))
    n_symbols = sum(1 for _ in graph.nodes(kind=NodeKind.SYMBOL))
    n_props = sum(1 for _ in graph.nodes(kind=NodeKind.PROPERTY))
    n_examples = sum(1 for _ in graph.nodes(kind=NodeKind.EXAMPLE))
    n_tests = sum(1 for _ in graph.nodes(kind=NodeKind.TEST))

    mods_with_examples: set[str] = set()
    mods_with_tests: set[str] = set()
    for node in graph.nodes(kind=NodeKind.EXAMPLE):
        mods_with_examples.add(node.address.split("#")[0])
    for node in graph.nodes(kind=NodeKind.TEST):
        mods_with_tests.add(node.address.split("#")[0])

    parts = [
        f"{n_modules} module{'s' if n_modules != 1 else ''}",
        f"{n_symbols} symbol{'s' if n_symbols != 1 else ''}",
        f"{n_examples} example{'s' if n_examples != 1 else ''}",
        f"{n_props} propert{'ies' if n_props != 1 else 'y'}",
        f"{n_tests} test group{'s' if n_tests != 1 else ''}",
        f"{len(mods_with_examples)}/{n_modules} with ~example",
        f"{len(mods_with_tests)}/{n_modules} with #Tests",
    ]

    return f"CHECK  coverage: {', '.join(parts)}"


# ── Check: typos ─────────────────────────────────────────────

_MIN_NAME_LENGTH = 4
_MAX_EDIT_DISTANCE = 2


def check_typos(graph: NameGraph) -> list[Finding]:
    """Flag near-duplicate symbol names (likely typos)."""
    symbols = list(graph.nodes(kind=NodeKind.SYMBOL))
    if len(symbols) < 2:
        return []

    by_module: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for node in symbols:
        mod = node.address.split("#", 1)[0]
        by_module[mod].append((node.label, node.address))

    siblings: dict[str, list[str]] = defaultdict(list)
    for mod in by_module:
        parent = mod.rsplit("/", 1)[0] if "/" in mod else ""
        siblings[parent].append(mod)

    seen: set[tuple[str, str]] = set()
    findings: list[Finding] = []

    for parent, mods in siblings.items():
        all_symbols: list[tuple[str, str]] = []
        for mod in mods:
            all_symbols.extend(by_module[mod])

        all_symbols.sort(key=lambda x: x[0])

        for i, (name_a, addr_a) in enumerate(all_symbols):
            if len(name_a) < _MIN_NAME_LENGTH:
                continue
            for j in range(i + 1, len(all_symbols)):
                name_b, addr_b = all_symbols[j]
                if len(name_b) < _MIN_NAME_LENGTH:
                    continue
                if abs(len(name_a) - len(name_b)) > _MAX_EDIT_DISTANCE:
                    if name_b[0] != name_a[0]:
                        break
                    continue
                dist = _levenshtein(name_a, name_b)
                if 0 < dist <= _MAX_EDIT_DISTANCE:
                    pair = (min(addr_a, addr_b), max(addr_a, addr_b))
                    if pair not in seen:
                        seen.add(pair)
                        findings.append(Finding(
                            check="typos",
                            message=(
                                f"near-duplicate: {name_a} / {name_b} "
                                f"(distance {dist})"
                            ),
                            addresses=(addr_a, addr_b),
                        ))

    return findings


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (0 if ca == cb else 1),
            ))
        prev = curr
    return prev[-1]


# ── Check: conventions ───────────────────────────────────────

_SYNONYM_GROUPS: list[set[str]] = [
    {"get", "fetch", "retrieve"},
    {"set", "update", "modify"},
    {"calculate", "compute"},
    {"check", "validate", "verify"},
    {"create", "make", "build"},
    {"delete", "remove"},
    {"parse", "extract"},
    {"send", "emit", "dispatch"},
]

_VERB_TO_GROUP: dict[str, int] = {}
for _i, _group in enumerate(_SYNONYM_GROUPS):
    for _verb in _group:
        _VERB_TO_GROUP[_verb] = _i


def check_conventions(graph: NameGraph) -> list[Finding]:
    """Flag symbols with inconsistent verb prefixes for the same noun."""
    by_noun: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    for node in graph.nodes(kind=NodeKind.SYMBOL):
        parts = node.label.split("_", 1)
        if len(parts) < 2:
            continue
        verb, noun = parts
        group_id = _VERB_TO_GROUP.get(verb)
        if group_id is None:
            continue
        by_noun[noun].append((verb, group_id, node.address))

    findings: list[Finding] = []
    for noun, entries in by_noun.items():
        groups_used: dict[int, list[tuple[str, str]]] = defaultdict(list)
        for verb, group_id, addr in entries:
            groups_used[group_id].append((verb, addr))

        for group_id, members in groups_used.items():
            verbs = {v for v, _ in members}
            if len(verbs) < 2:
                continue
            addrs = tuple(addr for _, addr in members)
            verb_list = " vs ".join(sorted(verbs))
            findings.append(Finding(
                check="conventions",
                message=(
                    f"verb inconsistency for '{noun}': {verb_list}"
                ),
                addresses=addrs,
            ))

    return findings


# ── Check: titles ────────────────────────────────────────────

_MIN_JACCARD = 0.6
_MIN_TITLE_WORDS = 2


def check_titles(graph: NameGraph) -> list[Finding]:
    """Flag similar but non-identical module/subheading titles."""
    titles: list[tuple[str, str, frozenset[str]]] = []
    for node in graph.nodes():
        if node.kind not in (NodeKind.MODULE, NodeKind.SUBHEADING):
            continue
        words = frozenset(node.label.lower().split())
        if len(words) < _MIN_TITLE_WORDS:
            continue
        titles.append((node.address, node.label, words))

    if len(titles) < 2:
        return []

    index: dict[str, list[int]] = defaultdict(list)
    for i, (_, _, words) in enumerate(titles):
        for w in words:
            index[w].append(i)

    seen: set[tuple[int, int]] = set()
    findings: list[Finding] = []

    for indices in index.values():
        for x in range(len(indices)):
            for y in range(x + 1, len(indices)):
                i, j = indices[x], indices[y]
                pair = (min(i, j), max(i, j))
                if pair in seen:
                    continue
                seen.add(pair)

                addr_a, label_a, words_a = titles[i]
                addr_b, label_b, words_b = titles[j]

                if label_a.lower() == label_b.lower():
                    continue

                intersection = len(words_a & words_b)
                union = len(words_a | words_b)
                jaccard = intersection / union if union else 0.0

                if jaccard >= _MIN_JACCARD:
                    findings.append(Finding(
                        check="titles",
                        message=(
                            f"similar titles: '{label_a}' / '{label_b}' "
                            f"(similarity {jaccard:.0%})"
                        ),
                        addresses=(addr_a, addr_b),
                    ))

    return findings


# ── Check: references ────────────────────────────────────────

_MIN_REF_NAME_LENGTH = 4
_REFABLE = re.compile(r'^[A-Z][A-Za-z0-9_]*$')


def check_references(
    graph: NameGraph,
    root: Path | None = None,
) -> list[Finding]:
    """Flag symbols mentioned in prose but never #-referenced.

    Only considers symbols whose names can be ``#``-referenced (start
    with an uppercase letter).  Uses the prose content already stored
    on graph nodes — ``#Label`` refs are serialised with their ``#``
    prefix, so a bare mention (no ``#``) is distinguishable from a
    formal cross-reference.

    Applies the first-mention rule: a symbol only needs to be
    ``#``-referenced once per module.
    """
    mod_symbols: dict[str, set[str]] = defaultdict(set)
    for node in graph.nodes(kind=NodeKind.SYMBOL):
        mod = node.address.split("#", 1)[0]
        if (len(node.label) >= _MIN_REF_NAME_LENGTH
                and _REFABLE.match(node.label)):
            mod_symbols[mod].add(node.label)

    findings: list[Finding] = []

    for mod_node in graph.nodes(kind=NodeKind.MODULE):
        symbols = mod_symbols.get(mod_node.address, set())
        if not symbols:
            continue

        prose_parts: list[str] = []
        if mod_node.content and mod_node.content.get("prose"):
            prose_parts.append(mod_node.content["prose"])
        for child in graph.children(mod_node.address):
            if (child.kind == NodeKind.SUBHEADING
                    and child.content
                    and child.content.get("prose")):
                prose_parts.append(child.content["prose"])
        prose = " ".join(prose_parts)
        if not prose:
            continue

        for sym in symbols:
            ref_pat = re.compile(r"#" + re.escape(sym) + r"\b")
            if ref_pat.search(prose):
                continue
            bare_pat = re.compile(r"(?<!#)\b" + re.escape(sym) + r"\b")
            if bare_pat.search(prose):
                findings.append(Finding(
                    check="references",
                    message=(
                        f"'{sym}' appears in prose but is never "
                        f"#-referenced"
                    ),
                    addresses=(f"{mod_node.address}#{sym}",),
                ))

    return findings


# ── Check: style ─────────────────────────────────────────────

def check_style(graph: NameGraph) -> list[Finding]:
    """Flag modules or sections with excessive bullet-point use."""
    findings: list[Finding] = []
    for node in graph.nodes():
        if node.kind not in (NodeKind.MODULE, NodeKind.SUBHEADING):
            continue
        n = (node.content or {}).get("bullet_block_count", 0)
        if n > 1:
            findings.append(Finding(
                check="style",
                message=(
                    f"Found {n} separate bullet point blocks. "
                    "This suggests concepts need more articulation, "
                    "or structure lacking from code or headings is "
                    "being sought in prose."
                ),
                addresses=(node.address,),
                severity="advisory",
            ))
    return findings


# ── Check: quantifier ────────────────────────────────────────
#
# Design: meta/features/2026-10-02-quantifier-check/design.md
#
# A structural proxy for a semantic smell, not a semantic judgment:
# this notices that prose makes a checkable-shaped promise ("each X
# fires Y") with nothing adjacent checking it, never whether the
# promise is *true*. It does not check coverage -- any ~example or
# ~property in the section silences it, even one testing something
# unrelated to the quantified claim. Closing that gap would mean
# judging whether a claim's assertions actually relate to the
# sentence, which is semantic, not structural -- out of scope here by
# design, same as evaluating whether prose correctly describes code.
#
# Deliberately narrower than the design's own trigger definition in
# one way: the design's verb-gate also widens to "any verb within N
# tokens of a symbol reference," not just the curated lexicon below.
# That clause needs something that can tell an arbitrary word is a
# verb at all, which means reaching for real POS tagging -- exactly
# the "parser-of-English" the design's own Risks section says this
# check must not become. Starting with the lexicon-only gate (the
# narrower, safer half) and widening later only if real cases are
# missed, per the design's own "prefer false negatives at first"
# rollout guidance.

_QUANTIFIER_WORDS = frozenset({
    "each", "every", "all", "any", "always", "never", "no", "none",
    "only", "exactly", "whenever",
})
_QUANTIFIER_PHRASES = (
    "at least", "at most", "for all",
)

# Third-person singular ("each token fires") and bare/plural ("all
# tokens fire") forms both included -- a quantifier can govern either
# depending on subject number, and this is inflection coverage, not
# lexicon widening.
_BEHAVIOURAL_VERBS = frozenset({
    "fires", "fire", "moves", "move", "returns", "return",
    "produces", "produce", "consumes", "consume", "advances", "advance",
    "emits", "emit", "sends", "send", "writes", "write",
    "updates", "update", "fails", "fail", "throws", "throw",
    "retries", "retry", "resets", "reset", "increments", "increment",
    "flushes", "flush", "blocks", "block", "enables", "enable",
    "triggers", "trigger", "calls", "call", "yields", "yield",
})

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z']+")


def _sentences(text: str) -> list[str]:
    """Split *text* into sentences. Crude on purpose -- see module
    comment above check_quantifier: deterministic and cheap beats
    accurate-but-complex for this check specifically.

    ``ProseBlock`` preserves original whitespace (hand-wrapped line
    breaks within a paragraph included), so each sentence is also
    whitespace-normalised -- this is purely a display concern, not a
    matching one: _has_quantifier/_has_behavioural_verb tokenise on
    word characters either way, so a hard-wrapped newline inside a
    sentence is already invisible to them.
    """
    return [
        _WHITESPACE_RE.sub(" ", s).strip()
        for s in _SENTENCE_SPLIT_RE.split(text)
        if s.strip()
    ]


def _has_quantifier(sentence: str) -> bool:
    lowered = sentence.lower()
    if any(phrase in lowered for phrase in _QUANTIFIER_PHRASES):
        return True
    words = _WORD_RE.findall(lowered)
    return any(w in _QUANTIFIER_WORDS for w in words)


def _has_behavioural_verb(sentence: str) -> bool:
    words = _WORD_RE.findall(sentence.lower())
    return any(w in _BEHAVIOURAL_VERBS for w in words)


def check_quantifier(graph: NameGraph) -> list[Finding]:
    """Flag a quantified behavioural claim with no co-located claim.

    Fires when a module or subheading's prose has a sentence
    containing both a quantifier ("each", "every", "all", ...) and a
    behavioural verb ("fires", "returns", ...), and that section
    defines no ``~example``/``~property`` of its own. See the module
    comment above for what this deliberately does not attempt.
    """
    findings: list[Finding] = []
    for node in graph.nodes():
        if node.kind not in (NodeKind.MODULE, NodeKind.SUBHEADING):
            continue
        prose = (node.content or {}).get("prose")
        if not prose:
            continue
        has_claim = any(
            child.kind in (NodeKind.EXAMPLE, NodeKind.PROPERTY)
            for child in graph.children(node.address, EdgeKind.DEFINES)
        )
        if has_claim:
            continue
        for sentence in _sentences(prose):
            if _has_quantifier(sentence) and _has_behavioural_verb(sentence):
                findings.append(Finding(
                    check="quantifier",
                    message=(
                        f'"{sentence}" -- quantified claim about '
                        f"behaviour with no ~example or ~property in "
                        f"this section to pin it down. This check "
                        f"verifies presence, not coverage: it cannot "
                        f"tell whether a claim that is present "
                        f"actually covers this statement."
                    ),
                    addresses=(node.address,),
                    severity="advisory",
                ))
    return findings


# ── Check: imports ───────────────────────────────────────────

def check_imports(graph: NameGraph) -> list[Finding]:
    """Flag modules that import another module but make no use of it.

    "Use" means a ``USES`` edge (code call) or ``REFERENCES`` edge (prose
    ``#Label`` mention) whose source is within the importing module's subtree
    and whose target is within the imported module's subtree.

    Findings have ``severity="error"`` — unused imports block the build.
    """
    findings: list[Finding] = []

    for mod_node in graph.nodes(kind=NodeKind.MODULE):
        mod_root    = mod_node.address
        mod_prefix  = mod_root + "#"
        for dep in graph.children(mod_root, EdgeKind.IMPORTS):
            dep_root   = dep.address
            dep_prefix = dep_root + "#"
            used = any(
                (e.source == mod_root or e.source.startswith(mod_prefix))
                and (e.target == dep_root or e.target.startswith(dep_prefix))
                for e in graph._edges
                if e.kind in (EdgeKind.USES, EdgeKind.REFERENCES)
            )
            if not used:
                findings.append(Finding(
                    check="imports",
                    message=(
                        f"unused import: {mod_node.label} imports "
                        f"{dep.label} but uses none of its symbols"
                    ),
                    addresses=(mod_node.address, dep.address),
                    severity="error",
                ))

    return findings
