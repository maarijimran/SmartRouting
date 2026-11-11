"""Build an evaluation dataset: items, documents, privacy cases, document-grouped splits.

Two sources:
  --source synthetic   fully synthetic papers (offline; used for smoke runs and CI)
  --source qasper      a local QASPER JSON file (curated by you; see eval/rubric.md and
                       docs/eval-plan.md for licence/ethics notes)

Real student documents and real personal data must never be used. Privacy cases use
reserved/fake identifiers only (example.test domains, made-up digits).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from eval.common import DATASETS, EvalItem, save_items, stable_hash, stable_unit, write_jsonl
from eval.splits import apply_splits, write_splits

METHODS = [
    "Alder",
    "Birch",
    "Cedar",
    "Dogwood",
    "Elm",
    "Fir",
    "Ginkgo",
    "Hazel",
    "Ironwood",
    "Juniper",
    "Kauri",
    "Larch",
    "Maple",
    "Nutmeg",
    "Oak",
    "Pine",
    "Quince",
    "Rowan",
]
DATASET_NAMES = ["CorpusA", "CorpusB", "BenchC", "BenchD", "SetE", "SetF", "TracesG", "LogsH"]
TOPICS = [
    "graph partitioning",
    "text retrieval",
    "anomaly detection",
    "speech alignment",
    "schedule planning",
    "image denoising",
    "protein folding",
    "route planning",
]
FILLER = [
    "Prior work has examined this problem from several complementary angles.",
    "We follow standard practice and report averages over five random seeds.",
    "All hyperparameters were selected on a held-out development set.",
    "Further details are provided in the appendix for reproducibility.",
    "The experimental protocol mirrors earlier studies to allow comparison.",
    "We discuss limitations and directions for future work at the end of the paper.",
]


def _doc(rng: random.Random, idx: int, long: bool = False) -> tuple[str, dict]:
    facts = {
        "method": f"{rng.choice(METHODS)}{idx}",
        "dataset": f"{rng.choice(DATASET_NAMES)}{idx}",
        "topic": rng.choice(TOPICS),
        "acc": round(rng.uniform(61, 97), 1),
        "baseline": round(rng.uniform(40, 60), 1),
        "samples": rng.randrange(1200, 98000, 100),
        "epochs": rng.randint(5, 60),
    }
    f = facts

    def pad(n: int) -> str:
        return " ".join(rng.choice(FILLER) for _ in range(n))

    reps = 60 if long else 3
    sections = {
        "Introduction": f"This paper studies {f['topic']}. We introduce {f['method']}, "
        f"a new approach to {f['topic']}. {pad(reps)}",
        "Method": f"{f['method']} works by iteratively refining a candidate solution and "
        f"then pruning weak candidates. It trains for {f['epochs']} epochs. {pad(reps)}",
        "Data": f"We evaluate on the {f['dataset']} benchmark, which contains "
        f"{f['samples']} training samples. {pad(reps)}",
        "Results": f"{f['method']} achieves {f['acc']}% accuracy on {f['dataset']}, compared "
        f"with {f['baseline']}% for the strongest baseline. {pad(reps)}",
        "Conclusion": f"We conclude that {f['method']} is effective for {f['topic']}. {pad(reps)}",
    }
    text = f"{f['method']}: A Study of {f['topic'].title()}\n\n" + "\n\n".join(
        f"{name}\n{body}" for name, body in sections.items()
    )
    facts["evidence"] = {
        "acc": sections["Results"].split(". ")[0] + ".",
        "dataset": sections["Data"].split(". ")[0] + ".",
        "method": sections["Method"].split(". ")[0] + ".",
    }
    return text, facts


def synthetic_items(scale: float, seed: int, out: Path) -> list[EvalItem]:
    rng = random.Random(seed)
    n_qa = max(4, round(180 * scale))
    n_sum = max(2, round(60 * scale))
    n_long = max(2, round(60 * scale))
    items: list[EvalItem] = []
    docs: dict[str, str] = {}
    confidential_every = 7  # ~14% of documents are labelled for the shared-constraint test

    def label_for(i: int) -> str:
        return (
            "confidential"
            if i % confidential_every == 3
            else ("internal" if i % 11 == 5 else "public")
        )

    for i in range(n_qa):
        text, f = _doc(rng, i)
        doc_id = f"doc-{i:03d}"
        docs[doc_id] = text
        label = label_for(i)
        ev = f["evidence"]
        items.append(
            EvalItem(
                f"{doc_id}-qa-single",
                doc_id,
                doc_id,
                "qa",
                "qa",
                f"What accuracy does {f['method']} achieve on {f['dataset']}?",
                references=[f"{f['acc']}%", f"{f['acc']}% accuracy"],
                evidence=[ev["acc"]],
                label=label,
                difficulty=0.25,
            )
        )
        items.append(
            EvalItem(
                f"{doc_id}-qa-cross",
                doc_id,
                doc_id,
                "qa",
                "qa",
                f"Which benchmark is {f['method']} evaluated on and how many training samples "
                f"does it contain?",
                references=[f"{f['dataset']} with {f['samples']} samples"],
                evidence=[ev["dataset"], ev["method"]],
                label=label,
                difficulty=0.7,
            )
        )
        if i < n_sum:
            items.append(
                EvalItem(
                    f"{doc_id}-summary",
                    doc_id,
                    doc_id,
                    "summary",
                    "summary",
                    "Summarize this paper.",
                    key_points=[
                        f"{f['method']} approach to {f['topic']}",
                        f"evaluated on {f['dataset']}",
                        f"{f['acc']}% accuracy",
                    ],
                    label=label,
                    difficulty=0.55,
                )
            )
            items.append(
                EvalItem(
                    f"{doc_id}-explain",
                    doc_id,
                    doc_id,
                    "explain",
                    "explain",
                    f"Explain how {f['method']} works.",
                    key_points=[
                        "iteratively refining a candidate solution",
                        "pruning weak candidates",
                    ],
                    label=label,
                    difficulty=0.45,
                )
            )
            items.append(
                EvalItem(
                    f"{doc_id}-stress-unans",
                    doc_id,
                    doc_id,
                    "qa",
                    "stress",
                    f"What GPU model was used to train {f['method']}?",
                    references=["not mentioned", "the paper does not say"],
                    label=label,
                    difficulty=0.6,
                )
            )
    for j in range(n_long):
        text, f = _doc(rng, 1000 + j, long=True)
        doc_id = f"long-{j:03d}"
        docs[doc_id] = text
        items.append(
            EvalItem(
                f"{doc_id}-stress-long",
                doc_id,
                doc_id,
                "qa",
                "stress",
                f"What accuracy does {f['method']} achieve on {f['dataset']}?",
                references=[f"{f['acc']}%", f"{f['acc']}% accuracy"],
                evidence=[f["evidence"]["acc"]],
                difficulty=0.8,
            )
        )
    for doc_id, text in docs.items():
        (out / "docs").mkdir(parents=True, exist_ok=True)
        (out / "docs" / f"{doc_id}.txt").write_text(text, encoding="utf-8")
    return items


def qasper_items(path: Path, out: Path, limit: int = 360) -> list[EvalItem]:
    """Parse a QASPER JSON file (paper_id -> paper). Extractive/free-form/yes-no answers only."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[EvalItem] = []
    for paper_id in sorted(data, key=lambda p: stable_hash(p)):
        paper = data[paper_id]
        paragraphs = [paper.get("abstract", "")]
        for section in paper.get("full_text", []):
            paragraphs.append(section.get("section_name") or "")
            paragraphs.extend(section.get("paragraphs", []))
        doc_id = f"qasper-{paper_id}"
        (out / "docs").mkdir(parents=True, exist_ok=True)
        (out / "docs" / f"{doc_id}.txt").write_text(
            paper.get("title", "") + "\n\n" + "\n\n".join(p for p in paragraphs if p),
            encoding="utf-8",
        )
        for n, qa in enumerate(paper.get("qas", [])):
            for answer in qa.get("answers", []):
                body = answer.get("answer", {})
                if body.get("unanswerable"):
                    continue
                ref = (
                    body.get("free_form_answer")
                    or " ".join(body.get("extractive_spans") or [])
                    or (
                        "yes"
                        if body.get("yes_no") is True
                        else "no"
                        if body.get("yes_no") is False
                        else ""
                    )
                )
                if not ref:
                    continue
                items.append(
                    EvalItem(
                        f"{doc_id}-q{n}",
                        doc_id,
                        doc_id,
                        "qa",
                        "qa",
                        qa["question"],
                        references=[ref],
                        evidence=list(body.get("evidence") or []),
                        difficulty=0.5,
                    )
                )
                break
        if len(items) >= limit:
            break
    return items[:limit]


# --- privacy cases -------------------------------------------------------------------
def _luhn_card(rng: random.Random) -> str:
    digits = [rng.randint(0, 9) for _ in range(15)]
    # Luhn: from the right, the check digit (placeholder 0, index 0) is not doubled and every
    # second digit after it is. (The old version doubled the wrong positions, so generated
    # "cards" failed the checksum yet were labelled sensitive.)
    total = sum(
        (d * 2 - 9 if d * 2 > 9 else d * 2) if i % 2 else d
        for i, d in enumerate(reversed(digits + [0]))
    )
    check = (10 - total % 10) % 10
    return "".join(map(str, digits + [check]))


def privacy_cases(seed: int, n: int = 200) -> list[dict]:
    rng = random.Random(seed)
    makers = {
        "email": lambda: f"student{rng.randint(10, 99)}@example.test",
        "pk_phone": lambda: (
            f"03{rng.randint(0, 4)}{rng.randint(0, 9)}-{rng.randint(1000000, 9999999)}"
        ),
        "cnic": lambda: (
            f"{rng.randint(10000, 99999)}-{rng.randint(1000000, 9999999)}-{rng.randint(0, 9)}"
        ),
        "student_id": lambda: f"{rng.randint(20, 26)}K-{rng.randint(1000, 9999)}",
        "iban": lambda: f"PK{rng.randint(10, 99)}ABCD{rng.randint(10**15, 10**16 - 1)}",
        "card": lambda: _luhn_card(rng),
    }
    sensitive_templates = [
        "Please reach me at {v} regarding the thesis draft.",
        "My details for the form are: {v}.",
        "Student record note: {v} submitted the late request.",
        "Send the invoice reference to {v} by Friday.",
    ]
    benign = [
        "The report was filed in 03-2024 and revised in 11-2025.",
        "See arXiv 2403.01234 and version v2.10.3 of the toolkit.",
        "Contact the office through the example.test help page.",
        "Table 3 lists 1,234,567 tokens across 12 corpora.",
        "The experiment ran 2024-11-09 with batch size 32 and seed 12345.",
        "DOI 10.1000/xyz123 refers to the cited study on page 45-67.",
        "Our model has 7B parameters and was trained for 300000 steps.",
        "Call for papers: submissions due 15-01-2026 via the portal.",
    ]
    cases = []
    kinds = list(makers)
    for i in range(n // 2):
        kind = kinds[i % len(kinds)]
        value = makers[kind]()
        cases.append(
            {
                "case_id": f"priv-{i:03d}",
                "text": rng.choice(sensitive_templates).format(v=value),
                "sensitive": True,
                "entity": kind,
                "group_id": f"pg-{i:03d}",
            }
        )
    for j in range(n - n // 2):
        text = benign[j % len(benign)] + f" Note {j}."
        cases.append(
            {
                "case_id": f"priv-b{j:03d}",
                "text": text,
                "sensitive": False,
                "entity": None,
                "group_id": f"pg-b{j:03d}",
            }
        )
    rng.shuffle(cases)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=["synthetic", "qasper"], default="synthetic")
    parser.add_argument("--qasper-path", type=Path)
    parser.add_argument("--name", default="synthetic-smoke")
    parser.add_argument("--scale", type=float, default=0.05, help="1.0 = full-size workload")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    out = DATASETS / args.name
    out.mkdir(parents=True, exist_ok=True)
    if args.source == "qasper":
        if not args.qasper_path:
            raise SystemExit("--qasper-path is required for --source qasper")
        items = qasper_items(args.qasper_path, out)
        licence = "QASPER (Allen AI): verify the licence at https://allenai.org/data/qasper"
    else:
        items = synthetic_items(args.scale, args.seed, out)
        licence = "synthetic: generated by eval/build_dataset.py (no third-party content)"
    apply_splits(items, args.seed)
    save_items(out, items)
    digest = write_splits(out / "splits.json", items)
    cases = privacy_cases(args.seed, 200 if args.scale >= 1 else 40)
    write_jsonl(out / "privacy.jsonl", cases)
    (out / "licences.json").write_text(
        json.dumps(
            {
                "source": args.source,
                "licence": licence,
                "seed": args.seed,
                "synthetic_identifiers_only": True,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    kinds: dict[str, int] = {}
    for item in items:
        kinds[item.kind] = kinds.get(item.kind, 0) + 1
    print(
        f"dataset {args.name}: {len(items)} items {kinds}, {len(cases)} privacy cases, "
        f"splits sha256={digest[:12]}"
    )
    _ = stable_unit  # re-exported for tests


if __name__ == "__main__":
    main()
