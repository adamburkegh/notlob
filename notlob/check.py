"""notlob.check — deterministic semantic consistency checker.

Analyses the name graph for naming inconsistencies: near-duplicate
symbols (typos), verb-prefix convention drift, and similar titles.
Each check produces advisory Findings — no check causes a non-zero
exit code.

The architecture is extensible: future checks (embedding-based
similarity, LLM judgment) register as new entries in _CHECKERS
without changing the public interface.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from notlob.graph import NameGraph, NodeKind


@dataclass(frozen=True)
class Finding:
    check: str
    message: str
    addresses: tuple[str, ...]
    severity: str = "advisory"


CHECKERS: dict[str, object] = {
    "typos": None,
    "conventions": None,
    "titles": None,
}


def run_checks(
    graph: NameGraph,
    enabled: set[str] | None = None,
) -> tuple[list[Finding], dict[str, int]]:
    """Run all (or selected) checks and return (findings, counts).

    *counts* maps each check name to the number of findings it produced,
    including checks that found nothing (count 0).
    """
    checkers = {
        "typos": check_typos,
        "conventions": check_conventions,
        "titles": check_titles,
    }
    if enabled is not None:
        checkers = {k: v for k, v in checkers.items() if k in enabled}
    findings: list[Finding] = []
    counts: dict[str, int] = {}
    for name, checker in checkers.items():
        batch = checker(graph)
        counts[name] = len(batch)
        findings.extend(batch)
    return findings, counts


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
