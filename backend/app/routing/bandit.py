"""Eligibility-constrained epsilon-greedy contextual bandit with per-model ridge regressors.

Spec: docs/05. The policy only ever sees the eligible set (the pipeline passes it in),
logs the true action probability, learns only from the selected action's outcome and
is immutable: ``update`` returns a new policy and never mutates the old one.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from app.routing.features import Features
from app.routing.rules import Decision

TASKS = ("qa", "summary", "explain")
NUMERIC = (
    "input_tokens",
    "evidence_tokens",
    "estimated_output_tokens",
    "retrieval_top_score",
    "retrieval_margin",
    "doc_pages",
    "history_turns",
    "local_only",
    "cost_pref",
    "latency_ewma_s",
    "failure_rate",
)
COST_PREF = {"lowest": 0.0, "balanced": 0.5, "best": 1.0}
DIM = len(NUMERIC) + len(TASKS) + 1  # numerics + task one-hot + constant


@dataclass(frozen=True)
class Outcome:
    """A scored outcome of the SELECTED action (the only thing the learner may see)."""

    model: str
    features: Mapping  # Features.to_log() dict (or a Features object)
    reward: float


def _view(features: Features | Mapping) -> Mapping:
    return features.to_log() if isinstance(features, Features) else features


def raw_vector(features: Features | Mapping, slug: str) -> np.ndarray:
    f = _view(features)
    stats = f.get("stats", {}).get(slug, (0.0, 0.0))
    values = [
        f.get("input_tokens", 0),
        f.get("evidence_tokens", 0),
        f.get("estimated_output_tokens", 0),
        f.get("retrieval_top_score", 0.0),
        f.get("retrieval_margin", 0.0),
        f.get("doc_pages", 0),
        f.get("history_turns", 0),
        1.0 if f.get("mode") == "local_only" else 0.0,
        COST_PREF.get(f.get("cost_preference", "balanced"), 0.5),
        float(stats[0]) / 1000.0,
        float(stats[1]),
    ]
    return np.array(values, dtype=float)


class Scaler:
    """Standardiser. Fit on training data only; frozen afterwards."""

    def __init__(self, mean: np.ndarray | None = None, std: np.ndarray | None = None) -> None:
        self.mean = np.zeros(len(NUMERIC)) if mean is None else mean
        self.std = np.ones(len(NUMERIC)) if std is None else std

    @classmethod
    def fit(cls, rows: np.ndarray) -> "Scaler":
        std = rows.std(axis=0)
        return cls(rows.mean(axis=0), np.where(std < 1e-8, 1.0, std))

    def to_params(self) -> dict:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}

    @classmethod
    def from_params(cls, params: dict | None) -> "Scaler":
        if not params:
            return cls()
        return cls(np.array(params["mean"], dtype=float), np.array(params["std"], dtype=float))


def phi(features: Features | Mapping, slug: str, scaler: Scaler) -> np.ndarray:
    f = _view(features)
    numeric = (raw_vector(f, slug) - scaler.mean) / scaler.std
    task = np.array([1.0 if f.get("task") == t else 0.0 for t in TASKS])
    return np.concatenate([numeric, task, [1.0]])


def ridge_fit(x: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    """Closed-form ridge; the constant column is not regularised."""
    penalty = lam * np.eye(x.shape[1])
    penalty[-1, -1] = 0.0
    return np.linalg.solve(x.T @ x + penalty + 1e-9 * np.eye(x.shape[1]), x.T @ y)


def epsilon_at(decisions: int, initial: float, final: float, decay: int) -> float:
    if decay <= 0:
        return final
    return max(final, initial - (initial - final) * decisions / decay)


class _RidgePolicy:
    """Shared state/serialisation for the bandit and the frozen baseline."""

    kind = "bandit"
    name = "adaptive_bandit"

    def __init__(
        self,
        thetas: dict[str, np.ndarray],
        counts: dict[str, int],
        scaler: Scaler,
        *,
        version: str,
        lam: float = 1.0,
        cold_start_min: int = 50,
    ) -> None:
        self.thetas = {k: np.array(v, dtype=float) for k, v in thetas.items()}
        self.counts = dict(counts)
        self.scaler = scaler
        self.version = version
        self.lam = lam
        self.cold_start_min = cold_start_min

    @property
    def ready(self) -> bool:
        """Cold start: fixed rules serve until every model has enough scored examples."""
        return bool(self.counts) and all(n >= self.cold_start_min for n in self.counts.values())

    def predict(self, features: Features | Mapping, slug: str) -> float:
        theta = self.thetas.get(slug)
        if theta is None:
            return 0.0
        return float(theta @ phi(features, slug, self.scaler))

    def _params(self) -> dict:
        return {
            "lambda": self.lam,
            "cold_start_min": self.cold_start_min,
            "scaler": self.scaler.to_params(),
            "models": {
                slug: {"theta": theta.tolist(), "n": self.counts.get(slug, 0)}
                for slug, theta in self.thetas.items()
            },
        }


class EpsilonGreedyRidge(_RidgePolicy):
    kind = "bandit"
    name = "adaptive_bandit"

    def __init__(
        self,
        thetas,
        counts,
        scaler,
        *,
        version: str,
        decisions: int = 0,
        epsilon_initial: float = 0.10,
        epsilon_final: float = 0.02,
        epsilon_decay: int = 1000,
        seed: int = 0,
        lam: float = 1.0,
        cold_start_min: int = 50,
        window: int | None = None,
        cloud_exploration: bool = True,
    ) -> None:
        super().__init__(
            thetas, counts, scaler, version=version, lam=lam, cold_start_min=cold_start_min
        )
        self.decisions = decisions
        self.epsilon_initial, self.epsilon_final, self.epsilon_decay = (
            epsilon_initial,
            epsilon_final,
            epsilon_decay,
        )
        self.seed = seed
        self.window = window
        self.cloud_exploration = cloud_exploration
        self._rng = np.random.default_rng(seed)

    @property
    def epsilon(self) -> float:
        return epsilon_at(
            self.decisions, self.epsilon_initial, self.epsilon_final, self.epsilon_decay
        )

    def distribution(self, features: Features, eligible: list[str]) -> tuple[str, dict[str, float]]:
        """(greedy action, P(a|x)) over the eligible set; probabilities sum to 1."""
        preds = {slug: self.predict(features, slug) for slug in eligible}
        best = max(eligible, key=lambda slug: (preds[slug], -eligible.index(slug)))
        explore = [s for s in eligible if self.cloud_exploration or features.is_local(s)] or []
        eps = self.epsilon if explore else 0.0
        probs = {slug: 0.0 for slug in eligible}
        probs[best] += 1.0 - eps
        for slug in explore:
            probs[slug] += eps / len(explore)
        return best, probs

    def select(self, features: Features, eligible: list[str]) -> Decision:
        if not eligible:
            raise ValueError("Cannot select from an empty eligible set")
        best, probs = self.distribution(features, eligible)
        slugs = list(probs)
        action = slugs[int(self._rng.choice(len(slugs), p=[probs[s] for s in slugs]))]
        self.decisions += 1
        explored = action != best
        return Decision(
            action,
            probs[action],
            "bandit_explore" if explored else "bandit_exploit",
            f"Adaptive policy {'explored' if explored else 'exploited'} "
            f"(epsilon={self.epsilon:.3f}, predicted reward "
            f"{self.predict(features, action):.3f})",
            probs,
        )

    def update(self, batch: list[Outcome]) -> "EpsilonGreedyRidge":
        """Refit only the models that appear in ``batch``, on their own scored data."""
        by_model: dict[str, list[Outcome]] = {}
        for outcome in batch:
            by_model.setdefault(outcome.model, []).append(outcome)
        scaler = self.scaler
        if not self.thetas and batch:  # first fit: scaler learned from this (training) batch only
            scaler = Scaler.fit(np.vstack([raw_vector(o.features, o.model) for o in batch]))
        thetas, counts = dict(self.thetas), dict(self.counts)
        for slug, outcomes in by_model.items():
            data = outcomes[-self.window :] if self.window else outcomes
            x = np.vstack([phi(o.features, slug, scaler) for o in data])
            y = np.array([o.reward for o in data])
            thetas[slug] = ridge_fit(x, y, self.lam)
            counts[slug] = counts.get(slug, 0) + len(outcomes)
        return EpsilonGreedyRidge(
            thetas,
            counts,
            scaler,
            version=self.version,
            decisions=self.decisions,
            epsilon_initial=self.epsilon_initial,
            epsilon_final=self.epsilon_final,
            epsilon_decay=self.epsilon_decay,
            seed=self.seed,
            lam=self.lam,
            cold_start_min=self.cold_start_min,
            window=self.window,
            cloud_exploration=self.cloud_exploration,
        )

    def with_version(self, version: str) -> "EpsilonGreedyRidge":
        clone = self.update([])
        clone.version = version
        return clone

    def to_params(self) -> dict:
        return {
            **self._params(),
            "decisions": self.decisions,
            "epsilon": {
                "initial": self.epsilon_initial,
                "final": self.epsilon_final,
                "decay": self.epsilon_decay,
            },
            "seed": self.seed,
            "window": self.window,
        }

    @classmethod
    def from_params(
        cls, params: dict, *, version: str, cloud_exploration: bool = True
    ) -> "EpsilonGreedyRidge":
        eps = params.get("epsilon", {})
        models = params.get("models", {})
        return cls(
            {s: np.array(m["theta"]) for s, m in models.items()},
            {s: int(m["n"]) for s, m in models.items()},
            Scaler.from_params(params.get("scaler")),
            version=version,
            decisions=int(params.get("decisions", 0)),
            epsilon_initial=eps.get("initial", 0.10),
            epsilon_final=eps.get("final", 0.02),
            epsilon_decay=eps.get("decay", 1000),
            seed=int(params.get("seed", 0)),
            lam=params.get("lambda", 1.0),
            cold_start_min=params.get("cold_start_min", 50),
            window=params.get("window"),
            cloud_exploration=cloud_exploration,
        )
