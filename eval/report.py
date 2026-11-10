"""Aggregate baseline results into tables with document-clustered bootstrap CIs.

Primary target (docs/06): >=20% lower API cost than strong-cloud-only on matching
cloud-eligible requests, with the lower CI bound of the paired quality difference > -0.05.
Unmet or inconclusive outcomes are reported as such; "rules suffice" is a valid finding.
"""

from __future__ import annotations

import numpy as np

from eval.stats import cluster_bootstrap, cost_reduction_ci, paired_difference_ci

REFERENCE = "strong_cloud_only"


def _per_item(rows: list[dict], policy: str, field: str) -> dict[str, float]:
    """Mean over seeds per item for answered (non-abstained) records."""
    acc: dict[str, list[float]] = {}
    for r in rows:
        if r["policy"] == policy and not r["abstained"] and r.get(field) is not None:
            acc.setdefault(r["item_id"], []).append(float(r[field]))
    return {k: float(np.mean(v)) for k, v in acc.items()}


def summarize(rows: list[dict], n_boot: int = 1000) -> dict:
    doc_of = {r["item_id"]: r["doc_id"] for r in rows}
    policies = sorted({r["policy"] for r in rows})
    table = {}
    for policy in policies:
        mine = [r for r in rows if r["policy"] == policy]
        answered = [r for r in mine if not r["abstained"]]
        quality = _per_item(rows, policy, "quality")
        by_doc: dict[str, list[float]] = {}
        for item, value in quality.items():
            by_doc.setdefault(doc_of[item], []).append(value)
        q, q_lo, q_hi = cluster_bootstrap(by_doc, n_boot=n_boot) if by_doc else (float("nan"),) * 3
        cost = [r["cost"] for r in answered]
        lat = [r["latency"] for r in answered if r["latency"] is not None]
        table[policy] = {
            "requests": len(mine),
            "abstain_rate": round(1 - len(answered) / len(mine), 4) if mine else None,
            "failure_rate": round(
                sum(1 for r in answered if r["status"] != "ok") / len(answered), 4
            )
            if answered
            else None,
            "quality": {"mean": round(q, 4), "ci95": [round(q_lo, 4), round(q_hi, 4)]},
            "mean_cost_usd": round(float(np.mean(cost)), 6) if cost else None,
            "latency_p50_ms": round(float(np.percentile(lat, 50)), 1) if lat else None,
            "latency_p95_ms": round(float(np.percentile(lat, 95)), 1) if lat else None,
            "local_share": round(
                sum(1 for r in answered if str(r["model"]).startswith("local")) / len(answered), 4
            )
            if answered
            else None,
            "mean_reward": round(
                float(np.mean([r["reward"] for r in answered if r["reward"] is not None])), 4
            )
            if answered
            else None,
        }
    comparisons = {}
    if REFERENCE in policies:
        ref_quality = _per_item(rows, REFERENCE, "quality")
        ref_cost = _per_item(rows, REFERENCE, "cost")
        for policy in policies:
            if policy == REFERENCE:
                continue
            # matching cloud-eligible requests: items the reference actually answered
            qd, qd_lo, qd_hi = paired_difference_ci(
                _per_item(rows, policy, "quality"), ref_quality, doc_of, n_boot=n_boot
            )
            cr, cr_lo, cr_hi = cost_reduction_ci(
                _per_item(rows, policy, "cost"), ref_cost, doc_of, n_boot=n_boot
            )
            met = bool(cr >= 0.20 and qd_lo > -0.05)
            inconclusive = bool(cr_lo < 0.20 <= cr or qd_lo <= -0.05 < qd)
            comparisons[policy] = {
                "paired_quality_diff": {
                    "mean": round(qd, 4),
                    "ci95": [round(qd_lo, 4), round(qd_hi, 4)],
                },
                "cost_reduction": {
                    "mean": round(cr, 4),
                    "ci95": [round(cr_lo, 4), round(cr_hi, 4)],
                },
                "primary_target_met": met,
                "verdict": (
                    "target met" if met else "inconclusive" if inconclusive else "target not met"
                ),
            }
    return {"reference": REFERENCE, "policies": table, "vs_reference": comparisons}


def to_markdown(summary: dict, provenance: str) -> str:
    lines = [
        f"> provenance: **{provenance}**",
        "",
        "| policy | n | abstain | quality (95% CI) | mean cost USD | p50 ms | local share |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, row in summary["policies"].items():
        q = row["quality"]
        lines.append(
            f"| {name} | {row['requests']} | {row['abstain_rate']} | "
            f"{q['mean']} [{q['ci95'][0]}, {q['ci95'][1]}] | {row['mean_cost_usd']} | "
            f"{row['latency_p50_ms']} | {row['local_share']} |"
        )
    lines += [
        "",
        f"vs `{summary['reference']}` (paired, document-clustered bootstrap):",
        "",
        "| policy | quality diff (95% CI) | cost reduction (95% CI) | verdict |",
        "|---|---|---|---|",
    ]
    for name, row in summary["vs_reference"].items():
        qd, cr = row["paired_quality_diff"], row["cost_reduction"]
        lines.append(
            f"| {name} | {qd['mean']} [{qd['ci95'][0]}, {qd['ci95'][1]}] | "
            f"{cr['mean']} [{cr['ci95'][0]}, {cr['ci95'][1]}] | {row['verdict']} |"
        )
    return "\n".join(lines) + "\n"
