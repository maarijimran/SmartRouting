"""OpenRouter pricing + latency pilot (Phase 0). Needs an admin evaluation key, <= USD 15.

Step 1 (no key needed): list candidate models and their current prices
    python scripts/price_pilot.py --list --max-input-price 1.0
Step 2: measure two chosen models (cheap + strong) with the admin key
    $env:EVAL_API_KEY = "sk-or-..."
    python scripts/price_pilot.py --cheap-model <id> --strong-model <id>
Optionally add --write-reward to store provisional C_ref / L_ref in configs/reward.yaml.

Only synthetic prompts are sent. Results (dated prices, measured latency, whether per-call
usage/cost is returned) are written to docs/pilot-pricing.json; nothing is invented.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = "https://openrouter.ai/api/v1"
PROMPTS = [
    "Summarise in two sentences why privacy-aware routing between local and cloud models helps.",
    "Explain what a contextual bandit is to a first-year student in about 80 words.",
    "List three risks of sending a confidential document to a third-party API.",
    "Define precision and recall and give a one-line example of each.",
    "Why might a short question be answerable by a small local model?",
]


def list_models(max_input_price: float | None) -> None:
    data = httpx.get(f"{BASE}/models", timeout=30).json()["data"]
    rows = []
    for m in data:
        p = m.get("pricing", {})
        try:
            pin, pout = float(p["prompt"]) * 1e6, float(p["completion"]) * 1e6
        except (KeyError, TypeError, ValueError):
            continue
        if max_input_price is None or pin <= max_input_price:
            rows.append((pin, pout, m["id"], m.get("context_length")))
    for pin, pout, mid, ctx in sorted(rows)[:60]:
        print(f"{mid:60s} in ${pin:8.3f}/M  out ${pout:8.3f}/M  ctx {ctx}")


def measure(model_id: str, key: str, prices: dict) -> dict:
    latencies, costs, usage_reported = [], [], 0
    for prompt in PROMPTS:
        started = time.perf_counter()
        r = httpx.post(
            f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0,
                "usage": {"include": True},
            },
            timeout=120,
        )
        elapsed = (time.perf_counter() - started) * 1000
        r.raise_for_status()
        body = r.json()
        latencies.append(elapsed)
        usage = body.get("usage") or {}
        if usage:
            usage_reported += 1
        if "cost" in usage:
            costs.append(float(usage["cost"]))
        elif usage:
            costs.append(
                usage.get("prompt_tokens", 0) * prices["input_per_mtok"] / 1e6
                + usage.get("completion_tokens", 0) * prices["output_per_mtok"] / 1e6
            )
    return {
        "model": model_id,
        "calls": len(PROMPTS),
        "latency_ms": {
            "median": statistics.median(latencies),
            "p90": sorted(latencies)[int(0.9 * (len(latencies) - 1))],
        },
        "usage_reported_per_call": usage_reported == len(PROMPTS),
        "cost_reported_directly": bool(costs) and usage_reported == len(PROMPTS),
        "cost_usd_total": sum(costs),
        "cost_usd_per_call_median": statistics.median(costs) if costs else None,
        "ttft_note": "non-streaming pilot; TTFT is measured by the streaming adapters",
        "prices": prices,
    }


def model_prices(model_id: str) -> dict:
    data = httpx.get(f"{BASE}/models", timeout=30).json()["data"]
    for m in data:
        if m["id"] == model_id:
            p = m["pricing"]
            return {
                "input_per_mtok": float(p["prompt"]) * 1e6,
                "output_per_mtok": float(p["completion"]) * 1e6,
                "captured_at": datetime.now(UTC).isoformat(),
                "source": f"{BASE}/models",
            }
    raise SystemExit(f"model not found on OpenRouter: {model_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list models and prices (no key)")
    parser.add_argument("--max-input-price", type=float, help="USD per million input tokens")
    parser.add_argument("--cheap-model")
    parser.add_argument("--strong-model")
    parser.add_argument("--output", type=Path, default=Path("docs/pilot-pricing.json"))
    parser.add_argument("--write-reward", action="store_true")
    args = parser.parse_args()
    if args.list:
        list_models(args.max_input_price)
        return
    if not (args.cheap_model and args.strong_model):
        raise SystemExit("Provide --cheap-model and --strong-model (or use --list).")
    key = os.environ.get("EVAL_API_KEY")
    if not key:
        raise SystemExit("Set EVAL_API_KEY (the admin evaluation key) first.")
    results = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "cheap": measure(args.cheap_model, key, model_prices(args.cheap_model)),
        "strong": measure(args.strong_model, key, model_prices(args.strong_model)),
    }
    # provisional reference values: ~2x the strong model's median per-call cost / p90 latency
    strong = results["strong"]
    c_ref = (strong["cost_usd_per_call_median"] or 0.0) * 2 or None
    l_ref = strong["latency_ms"]["p90"]
    results["provisional_reference"] = {"c_ref_usd": c_ref, "l_ref_ms": l_ref}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    if args.write_reward and c_ref:
        path = Path("configs/reward.yaml")
        text = path.read_text(encoding="utf-8")
        import re

        text = re.sub(r"c_ref_usd:.*", f"c_ref_usd: {c_ref:.6f}", text)
        text = re.sub(r"l_ref_ms:.*", f"l_ref_ms: {l_ref:.0f}", text)
        path.write_text(text, encoding="utf-8")
        print("updated configs/reward.yaml (review, then set frozen: true before final tests)")


if __name__ == "__main__":
    main()
