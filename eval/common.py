"""Shared helpers for the evaluation harness. Importing this puts backend/ on sys.path."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

EVAL_DIR = ROOT / "eval"
DATASETS = EVAL_DIR / "datasets"
REPORTS = EVAL_DIR / "reports"
CACHE = EVAL_DIR / "cache"
ARTIFACTS = EVAL_DIR / "artifacts"

LOCAL = "local-eval"
CHEAP = "cloud-cheap-eval"
STRONG = "cloud-strong-eval"
MODELS = (LOCAL, CHEAP, STRONG)


@dataclass
class EvalItem:
    item_id: str
    doc_id: str
    group_id: str  # items sharing a group (paraphrases, privacy variants) stay in one split
    task_type: str  # qa | summary | explain
    kind: str  # qa | summary | stress | explain
    prompt: str
    references: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    label: str = "public"  # public | internal | confidential
    split: str = ""
    difficulty: float = 0.5  # used only by the SIMULATED executor


def stable_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def stable_unit(*parts: object) -> float:
    """Deterministic float in [0, 1) from arbitrary parts."""
    return int(stable_hash(*parts)[:12], 16) / float(16**12)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_items(dataset: Path) -> list[EvalItem]:
    return [EvalItem(**row) for row in read_jsonl(dataset / "items.jsonl")]


def save_items(dataset: Path, items: list[EvalItem]) -> None:
    write_jsonl(dataset / "items.jsonl", [asdict(i) for i in items])


def doc_text(dataset: Path, doc_id: str) -> str:
    return (dataset / "docs" / f"{doc_id}.txt").read_text(encoding="utf-8")


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "no-git"
    except Exception:
        return "no-git"


def config_hash() -> str:
    parts = []
    for path in sorted((ROOT / "configs").glob("*.yaml")):
        parts.append(path.name + path.read_text(encoding="utf-8"))
    return stable_hash(*parts)
