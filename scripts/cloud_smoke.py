"""Connectivity check for one OpenAI-compatible cloud endpoint (free tiers included).

Sends ONE short synthetic prompt. This is a standalone developer check, not the
gateway: never put real documents or personal data in --prompt. The API key is
read from an environment variable so it never appears in shell history or logs.

Examples (PowerShell):
    $env:OPENROUTER_API_KEY = "sk-or-..."
    python scripts/cloud_smoke.py --provider openrouter --model "<model-id>:free"
    $env:GROQ_API_KEY = "gsk_..."
    python scripts/cloud_smoke.py --provider groq --model llama-3.3-70b-versatile
"""

from __future__ import annotations

import argparse
import os
import time

import httpx

PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="openrouter")
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", help="override the provider base URL")
    parser.add_argument("--key-env", help="override the env var holding the key")
    parser.add_argument("--prompt", default="Reply with the single word: ready")
    args = parser.parse_args()

    default_url, default_env = PROVIDERS[args.provider]
    base_url = (args.base_url or default_url).rstrip("/")
    key_env = args.key_env or default_env
    api_key = os.environ.get(key_env)
    if not api_key:
        raise SystemExit(f"Set the {key_env} environment variable first.")

    started = time.perf_counter()
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": args.model,
            "messages": [{"role": "user", "content": args.prompt}],
            "max_tokens": 32,
            "temperature": 0,
        },
        timeout=60,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if response.status_code != 200:
        raise SystemExit(f"HTTP {response.status_code}: {response.text[:300]}")
    body = response.json()
    text = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    print(f"OK  model={body.get('model', args.model)}  latency={elapsed_ms:.0f} ms")
    print(f"reply: {text.strip()[:200]!r}")
    print(f"usage reported: {usage or 'none (record this for the pricing pilot)'}")


if __name__ == "__main__":
    main()
