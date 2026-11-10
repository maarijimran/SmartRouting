"""Executors that turn (item, model) into a measured outcome, with a result cache and budget.

* ``SimulatedExecutor``: deterministic, offline. Its numbers are NOT scientific results;
  it exists to exercise and test the pipeline, learner and statistics end to end.
* ``LiveExecutor``: real models. Needs ``configs/models.yaml`` filled in after the Phase 0
  pilots and an admin evaluation key in ``EVAL_API_KEY``. Cached, and hard-stopped at the
  configured USD cap.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from eval.common import CACHE, CHEAP, LOCAL, ROOT, STRONG, EvalItem, stable_hash, stable_unit


class BudgetExceeded(RuntimeError):
    """Raised before a billable call that would pass the evaluation cap."""


@dataclass(frozen=True)
class ModelProfile:
    slug: str
    kind: str  # local | cloud
    tier: str  # local | cheap | strong
    strength: float
    price_in: float  # USD per million input tokens
    price_out: float
    latency_ms: float
    per_token_ms: float
    fail_rate: float
    context_limit: int
    max_output: int
    # live-only
    provider_model: str | None = None
    base_url: str | None = None


SIM_PROFILES: dict[str, ModelProfile] = {
    LOCAL: ModelProfile(LOCAL, "local", "local", 0.45, 0.0, 0.0, 450, 22, 0.04, 4096, 512),
    CHEAP: ModelProfile(CHEAP, "cloud", "cheap", 0.62, 0.15, 0.60, 700, 9, 0.02, 16384, 1024),
    STRONG: ModelProfile(STRONG, "cloud", "strong", 0.86, 3.00, 15.00, 1200, 11, 0.01, 32768, 1024),
}


@dataclass
class Result:
    text: str
    status: str  # ok | fail
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    ttft_ms: float | None
    cached: bool = False
    simulated: bool = False


class ResultCache:
    """Disk cache keyed by (item, model, prompt hash, config hash). Reruns cost nothing."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def key(self, item_id: str, model: str, prompt_hash: str, config_hash: str) -> str:
        return stable_hash(item_id, model, prompt_hash, config_hash)

    def get(self, key: str) -> Result | None:
        path = self.dir / f"{key}.json"
        if not path.exists():
            self.misses += 1
            return None
        self.hits += 1
        data = json.loads(path.read_text(encoding="utf-8"))
        return Result(**{**data, "cached": True})

    def put(self, key: str, result: Result) -> None:
        payload = asdict(result)
        payload["cached"] = False
        (self.dir / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


class BudgetGuard:
    """Hard stop at ``cap_usd``; spend is persisted so the cap survives restarts."""

    def __init__(self, cap_usd: float, ledger: Path) -> None:
        self.cap = cap_usd
        self.ledger = ledger
        ledger.parent.mkdir(parents=True, exist_ok=True)
        self.spent = (
            sum(float(line.split(",")[1]) for line in ledger.read_text().splitlines() if line)
            if ledger.exists()
            else 0.0
        )

    def check(self, estimate_usd: float) -> None:
        if self.spent + estimate_usd > self.cap:
            raise BudgetExceeded(
                f"evaluation cap USD {self.cap:.2f} would be exceeded "
                f"(spent {self.spent:.4f}, next call ~{estimate_usd:.4f})"
            )

    def record(self, item_id: str, usd: float) -> None:
        self.spent += usd
        with self.ledger.open("a", encoding="utf-8") as handle:
            handle.write(f"{item_id},{usd}\n")


def prompt_hash(messages: list[dict[str, str]]) -> str:
    return stable_hash(json.dumps(messages, sort_keys=True))


def _corrupt(text: str, u: float) -> str:
    """Plausible wrong answer: change digits, or fall back to a hedge."""
    changed = re.sub(r"\d", lambda m: str((int(m.group()) + 3) % 10), text)
    return changed if changed != text else "The paper does not clearly state this."


class SimulatedExecutor:
    simulated = True

    def __init__(self, seed: int = 0, cache: ResultCache | None = None) -> None:
        self.seed = seed
        self.cache = cache
        self.latency_factor: dict[str, float] = {}  # controlled latency shift (replay)

    def config_hash(self, profile: ModelProfile) -> str:
        return stable_hash("sim-v1", self.seed, json.dumps(asdict(profile), sort_keys=True))

    def run(
        self,
        item: EvalItem,
        profile: ModelProfile,
        messages: list[dict[str, str]],
        input_tokens: int,
    ) -> Result:
        factor = self.latency_factor.get(profile.slug, 1.0)
        key = None
        if self.cache is not None:
            key = self.cache.key(
                item.item_id, profile.slug, prompt_hash(messages), self.config_hash(profile)
            )
            hit = self.cache.get(key)
            if hit is not None:
                return Result(**{**asdict(hit), "latency_ms": hit.latency_ms * factor})
        u = lambda tag: stable_unit(self.seed, item.item_id, profile.slug, tag)  # noqa: E731
        base_latency = profile.latency_ms * (0.85 + 0.3 * u("lat"))
        if u("fail") < profile.fail_rate or input_tokens + 64 > profile.context_limit:
            result = Result(
                "",
                "fail",
                input_tokens,
                0,
                input_tokens * profile.price_in / 1e6,
                base_latency,
                None,
                simulated=True,
            )
        else:
            p_correct = 1 / (1 + math.exp(-6 * (profile.strength - item.difficulty)))
            correct = u("q") < p_correct
            if item.references:
                ref = item.references[0]
                text = ref if correct else _corrupt(ref, u("c"))
            else:
                points = item.key_points or ["no key points"]
                keep = len(points) if correct else max(1, int(len(points) * profile.strength * 0.6))
                text = "The paper discusses " + "; ".join(points[:keep]) + "."
            out_tokens = max(1, len(text.split()))
            result = Result(
                text,
                "ok",
                input_tokens,
                out_tokens,
                (input_tokens * profile.price_in + out_tokens * profile.price_out) / 1e6,
                base_latency + profile.per_token_ms * out_tokens,
                base_latency * 0.35,
                simulated=True,
            )
        if self.cache is not None and key is not None:
            self.cache.put(key, result)
        return Result(**{**asdict(result), "latency_ms": result.latency_ms * factor})


class LiveExecutor:
    simulated = False

    def __init__(self, profiles: dict[str, ModelProfile], cache: ResultCache, budget: BudgetGuard):
        self.profiles = profiles
        self.cache = cache
        self.budget = budget
        self.api_key = os.environ.get("EVAL_API_KEY", "")

    @classmethod
    def from_config(cls, cache_name: str = "live") -> tuple[LiveExecutor, dict[str, ModelProfile]]:
        import yaml

        raw = yaml.safe_load((ROOT / "configs" / "models.yaml").read_text(encoding="utf-8"))
        budget_cfg = yaml.safe_load((ROOT / "configs" / "budget.yaml").read_text(encoding="utf-8"))
        profiles: dict[str, ModelProfile] = {}
        for entry in raw.get("local", []) + raw.get("cloud", []):
            if not entry.get("enabled", True) and entry.get("kind") == "cloud":
                continue
            if not entry.get("provider_model"):
                raise SystemExit(
                    f"configs/models.yaml: '{entry['slug']}' has no provider_model. Run the "
                    "hardware/pricing pilots (SETUP.md) and fill in the real model IDs and prices."
                )
            price = entry.get("price") or {}
            tier = "local" if entry["kind"] == "local" else entry.get("tier", "cheap")
            profiles[entry["slug"]] = ModelProfile(
                entry["slug"],
                entry["kind"],
                tier,
                0.0,
                float(price.get("input_per_mtok", 0.0)),
                float(price.get("output_per_mtok", 0.0)),
                0,
                0,
                0,
                int(entry["context_limit"]),
                int(entry["max_output"]),
                provider_model=entry["provider_model"],
                base_url=entry.get("endpoint"),
            )
        cap = float(budget_cfg.get("benchmark_cap_usd", 55)) + float(
            budget_cfg.get("adaptive_cap_usd", 15)
        )
        executor = cls(
            profiles,
            ResultCache(CACHE / cache_name),
            BudgetGuard(cap, CACHE / cache_name / "ledger.csv"),
        )
        if any(p.kind == "cloud" for p in profiles.values()) and not executor.api_key:
            raise SystemExit("Set EVAL_API_KEY (the admin evaluation key) to run live cloud calls.")
        return executor, profiles

    def config_hash(self, profile: ModelProfile) -> str:
        return stable_hash("live-v1", profile.provider_model, profile.max_output, 0.0)

    def run(
        self,
        item: EvalItem,
        profile: ModelProfile,
        messages: list[dict[str, str]],
        input_tokens: int,
    ) -> Result:
        from app.gateway.live import live_generate

        key = self.cache.key(
            item.item_id, profile.slug, prompt_hash(messages), self.config_hash(profile)
        )
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        estimate = (input_tokens * profile.price_in + profile.max_output * profile.price_out) / 1e6
        if profile.kind == "cloud":
            self.budget.check(estimate)
        try:
            live = asyncio.run(
                live_generate(
                    kind=profile.kind,
                    base_url=profile.base_url or "",
                    model_id=profile.provider_model or "",
                    api_key=self.api_key,
                    messages=messages,
                    max_tokens=profile.max_output,
                    context_limit=profile.context_limit,
                )
            )
        except Exception:
            result = Result("", "fail", input_tokens, 0, 0.0, 0.0, None)
        else:
            in_tok = live.input_tokens if live.input_tokens is not None else input_tokens
            out_tok = (
                live.output_tokens if live.output_tokens is not None else len(live.text.split())
            )
            cost = live.cost_usd or (in_tok * profile.price_in + out_tok * profile.price_out) / 1e6
            if profile.kind == "local":
                cost = 0.0
            result = Result(
                live.text,
                "ok" if live.text.strip() else "fail",
                in_tok,
                out_tok,
                cost,
                live.latency_ms,
                live.ttft_ms,
            )
        if profile.kind == "cloud":
            self.budget.record(item.item_id, result.cost_usd)
        self.cache.put(key, result)
        return result
