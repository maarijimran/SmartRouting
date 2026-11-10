"""Document-grouped 60/20/20 splits with a leakage check and a frozen hash."""

from __future__ import annotations

import json
from pathlib import Path

from eval.common import EvalItem, stable_hash

FRACTIONS = (("train", 0.6), ("dev", 0.2), ("test", 0.2))


def assign_splits(items: list[EvalItem], seed: int = 0) -> dict[str, str]:
    """Map group_id -> split. Whole groups (and hence whole documents) move together."""
    groups: dict[str, set[str]] = {}
    for item in items:
        groups.setdefault(item.group_id, set()).add(item.doc_id)
    # items of one document must share a split, so merge groups that share a document
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for group, docs in groups.items():
        for doc in docs:
            parent[find(f"g:{group}")] = find(f"d:{doc}")
    units: dict[str, list[str]] = {}
    for group in groups:
        units.setdefault(find(f"g:{group}"), []).append(group)
    ordered = sorted(units, key=lambda u: stable_hash(seed, u))
    total = len(ordered)
    cuts, running = [], 0.0
    for _, frac in FRACTIONS:
        running += frac
        cuts.append(round(total * running))
    mapping: dict[str, str] = {}
    for rank, unit in enumerate(ordered):
        split = next(name for (name, _), cut in zip(FRACTIONS, cuts, strict=True) if rank < cut)
        for group in units[unit]:
            mapping[group] = split
    return mapping


def apply_splits(items: list[EvalItem], seed: int = 0) -> dict[str, str]:
    mapping = assign_splits(items, seed)
    for item in items:
        item.split = mapping[item.group_id]
    check_leakage(items)
    return mapping


def check_leakage(items: list[EvalItem]) -> None:
    """Raise if a document or paraphrase group appears in more than one split."""
    for attr in ("doc_id", "group_id"):
        seen: dict[str, str] = {}
        for item in items:
            key = getattr(item, attr)
            if key in seen and seen[key] != item.split:
                raise AssertionError(f"leakage: {attr} {key!r} in {seen[key]} and {item.split}")
            seen[key] = item.split


def splits_payload(items: list[EvalItem]) -> dict:
    return {
        "items": {i.item_id: i.split for i in sorted(items, key=lambda i: i.item_id)},
        "counts": {name: sum(1 for i in items if i.split == name) for name, _ in FRACTIONS},
    }


def write_splits(path: Path, items: list[EvalItem]) -> str:
    payload = splits_payload(items)
    digest = stable_hash(json.dumps(payload, sort_keys=True))
    path.write_text(json.dumps({**payload, "sha256": digest}, indent=1), encoding="utf-8")
    return digest
