"""Measure a local Ollama model on the machine that actually runs it.

Run this on the Ollama machine (or point --url at it). It records only values
reported by Ollama itself; if Ollama or the model is unreachable it exits with
an error and writes nothing, so no hardware numbers are ever invented.

Example:
    python scripts/profile_local.py --model llama3.1:8b-instruct-q4_K_M --model qwen2.5:7b
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

PROMPT = (
    "Explain in three sentences why a student might prefer to keep a confidential "
    "draft on a local model instead of sending it to a cloud service."
)


def _get(client: httpx.Client, url: str, path: str) -> dict:
    response = client.get(f"{url}{path}")
    response.raise_for_status()
    return response.json()


def profile_model(client: httpx.Client, url: str, model: str, num_ctx: int) -> dict:
    # Unload anything resident so load_duration reflects a cold start.
    client.post(f"{url}/api/generate", json={"model": model, "keep_alive": 0})
    started = time.perf_counter()
    response = client.post(
        f"{url}/api/generate",
        json={
            "model": model,
            "prompt": PROMPT,
            "stream": False,
            "options": {"num_ctx": num_ctx, "temperature": 0.0},
        },
    )
    wall_s = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()
    eval_s = body.get("eval_duration", 0) / 1e9
    resident = _get(client, url, "/api/ps").get("models", [])
    entry = next((m for m in resident if m.get("name", "").startswith(model.split(":")[0])), {})
    return {
        "model": model,
        "num_ctx_tested": num_ctx,
        "load_seconds": round(body.get("load_duration", 0) / 1e9, 2),
        "prompt_tokens": body.get("prompt_eval_count"),
        "output_tokens": body.get("eval_count"),
        "tokens_per_second": round(body["eval_count"] / eval_s, 1) if eval_s else None,
        "wall_seconds": round(wall_s, 2),
        "model_size_gb": round(entry.get("size", 0) / 1e9, 2) or None,
        "vram_gb": round(entry.get("size_vram", 0) / 1e9, 2) if entry else None,
        "fully_on_gpu": bool(entry) and entry.get("size_vram") == entry.get("size"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--model", action="append", required=True, help="repeat per model")
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--output", type=Path, default=Path("docs/pilot-hardware.json"))
    args = parser.parse_args()
    url = args.url.rstrip("/")

    with httpx.Client(timeout=600) as client:
        try:
            installed = {m["name"] for m in _get(client, url, "/api/tags").get("models", [])}
        except httpx.HTTPError as exc:
            raise SystemExit(f"Cannot reach Ollama at {url}: {exc}") from exc
        missing = [m for m in args.model if m not in installed]
        if missing:
            raise SystemExit(
                f"Not installed on {url}: {', '.join(missing)}. "
                f"Run `ollama pull <model>` first. Installed: {sorted(installed) or 'none'}"
            )
        results = []
        for model in args.model:
            print(f"Profiling {model} ...", flush=True)
            result = profile_model(client, url, model, args.num_ctx)
            print(json.dumps(result, indent=2))
            results.append(result)

    record = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "ollama_url": url,
        "host": platform.node(),
        "os": platform.platform(),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}. Copy the numbers into docs/pilot-hardware.md.")
    if any(not r["fully_on_gpu"] for r in results):
        print("WARNING: a model did not fully fit in VRAM; try a smaller one.", file=sys.stderr)


if __name__ == "__main__":
    main()
