from dataclasses import dataclass
from typing import Protocol

from app.routing.config import routing_config
from app.routing.features import Features


@dataclass(frozen=True)
class Decision:
    action: str
    probability: float
    rule_id: str
    explanation: str
    # slug -> probability over the eligible set (sums to 1); used for off-policy evaluation
    distribution: dict[str, float] | None = None


class Policy(Protocol):
    name: str
    version: str

    def select(self, features: Features, eligible: list[str]) -> Decision: ...


class FixedRules:
    """Ordered, explainable rule baseline (docs/01). Version 0 is the rollback target."""

    name = "fixed_rules"
    version = "0"

    def __init__(self, config: dict | None = None) -> None:
        rules = (config or routing_config()).get("rules", {})
        self.local_context_tokens = int(rules.get("local_context_tokens", 4096))
        self.simple_tasks = set(
            rules.get("simple_tasks", ["definition", "short_explanation", "explain"])
        )
        self.simple_max_chunks = int(rules.get("simple_max_evidence_chunks", 2))
        self.spread_min_chunks = int(rules.get("spread_min_chunks", 3))

    def select(self, features: Features, eligible: list[str]) -> Decision:
        if not eligible:
            raise ValueError("Cannot select from an empty eligible set")
        local = [item for item in eligible if features.is_local(item)]
        cloud = [item for item in eligible if not features.is_local(item)]
        strong = [item for item in cloud if features.tiers.get(item) == "strong"] or cloud
        cheap = [item for item in cloud if features.tiers.get(item) == "cheap"] or cloud

        if features.mode == "local_only":
            return self._pick(local or eligible, "label_forbids_cloud", "Local-only mode")
        if features.input_tokens > self.local_context_tokens and cloud:
            return self._pick(cloud, "context_exceeds_local", "Prompt exceeds local context budget")
        if (
            features.task in self.simple_tasks
            and features.evidence_chunks <= self.simple_max_chunks
        ):
            return self._pick(
                local or eligible, "simple_task_local", "Short task with focused evidence"
            )
        if (
            features.task == "cross_section_qa"
            or features.evidence_spread
            or features.evidence_chunks >= self.spread_min_chunks
        ):
            return self._pick(
                strong or eligible, "distributed_evidence_strong", "Evidence spans sections"
            )
        if features.cost_preference == "lowest":
            return self._pick(
                local or eligible, "cost_preference_local", "Lowest-cost eligible route"
            )
        return self._pick(
            cheap or local or eligible, "default_cheap_cloud", "Default eligible route"
        )

    @staticmethod
    def _pick(actions: list[str], rule_id: str, explanation: str) -> Decision:
        return Decision(actions[0], 1.0, rule_id, explanation, {actions[0]: 1.0})


class LocalOnly(FixedRules):
    name = "local_only"

    def select(self, features: Features, eligible: list[str]) -> Decision:
        local = [item for item in eligible if features.is_local(item)]
        if not local:
            raise ValueError("No eligible local model")
        return self._pick(local, "local_only_policy", "Local-only baseline")


class StrongCloudOnly(FixedRules):
    name = "strong_cloud_only"

    def select(self, features: Features, eligible: list[str]) -> Decision:
        cloud = [item for item in eligible if not features.is_local(item)]
        strong = [item for item in cloud if features.tiers.get(item) == "strong"] or cloud
        if not strong:
            raise ValueError("No eligible cloud model")
        return self._pick(strong, "strong_cloud_only_policy", "Strong-cloud baseline")
