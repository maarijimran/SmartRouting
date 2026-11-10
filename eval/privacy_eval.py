"""Privacy evaluation: detector precision/recall AND unauthorised-dispatch count (separate)."""

from __future__ import annotations

import argparse

from app.privacy.detector import PrivacyScanner
from app.privacy.gate import check_outbound

from eval.common import DATASETS, read_jsonl


def privacy_eval(dataset_name: str) -> dict:
    cases = read_jsonl(DATASETS / dataset_name / "privacy.jsonl")
    scanner = PrivacyScanner()
    tp = fp = fn = tn = 0
    unauthorised = 0
    missed: dict[str, int] = {}
    false_alarms: list[str] = []
    for case in cases:
        scan = scanner.scan(case["text"], "prompt")
        detected = scan.sensitive
        if case["sensitive"] and detected:
            tp += 1
        elif case["sensitive"]:
            fn += 1
            missed[case["entity"] or "?"] = missed.get(case["entity"] or "?", 0) + 1
        elif detected:
            fp += 1
            false_alarms.append(case["case_id"])
        else:
            tn += 1
        # dispatch test: cloud allowed, no consent. A sensitive case that passes is an incident.
        gate = check_outbound(
            case["text"].encode("utf-8"),
            scanner=scanner,
            mode="cloud_allowed",
            label="internal",
            user_id="eval",
            session_id="privacy",
            model_id="cloud-eval",
        )
        if case["sensitive"] and gate.allowed:
            unauthorised += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "cases": len(cases),
        "detector": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "missed_by_entity": missed,
            "false_alarm_cases": false_alarms,
        },
        "unauthorised_dispatches": unauthorised,  # target 0; reported separately from P/R
        "note": "Detector misses are possible; unauthorised_dispatches counts sensitive "
        "cases the outbound gate would have let through without consent.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="synthetic-smoke")
    args = parser.parse_args()
    result = privacy_eval(args.dataset)
    print(result)
    if result["unauthorised_dispatches"]:
        print(
            "NOTE: sensitive cases the detector missed would be dispatched; see missed_by_entity."
        )


if __name__ == "__main__":
    main()
