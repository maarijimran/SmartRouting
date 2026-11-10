"""Frozen supervised router baseline: ridge predictors trained once, never updated."""

import numpy as np

from app.routing.bandit import Outcome, Scaler, _RidgePolicy, phi, raw_vector, ridge_fit
from app.routing.features import Features
from app.routing.rules import Decision


class FrozenRouter(_RidgePolicy):
    kind = "frozen"
    name = "frozen_supervised"

    def select(self, features: Features, eligible: list[str]) -> Decision:
        if not eligible:
            raise ValueError("Cannot select from an empty eligible set")
        preds = {slug: self.predict(features, slug) for slug in eligible}
        best = max(eligible, key=lambda slug: (preds[slug], -eligible.index(slug)))
        probs = {slug: 1.0 if slug == best else 0.0 for slug in eligible}
        return Decision(
            best,
            1.0,
            "frozen_argmax",
            f"Frozen supervised router (predicted reward {preds[best]:.3f})",
            probs,
        )

    def update(self, batch: list[Outcome]) -> "FrozenRouter":
        return self  # frozen: no-op by definition

    @classmethod
    def train(
        cls,
        outcomes: list[Outcome],
        *,
        version: str,
        lam: float = 1.0,
        scaler: Scaler | None = None,
    ) -> "FrozenRouter":
        """Fit once on the TRAIN split (outcomes for every model on the same items)."""
        scaler = scaler or Scaler.fit(
            np.vstack([raw_vector(o.features, o.model) for o in outcomes])
        )
        thetas, counts = {}, {}
        for slug in sorted({o.model for o in outcomes}):
            rows = [o for o in outcomes if o.model == slug]
            x = np.vstack([phi(o.features, slug, scaler) for o in rows])
            thetas[slug] = ridge_fit(x, np.array([o.reward for o in rows]), lam)
            counts[slug] = len(rows)
        return cls(thetas, counts, scaler, version=version, lam=lam)

    def to_params(self) -> dict:
        return self._params()

    @classmethod
    def from_params(cls, params: dict, *, version: str) -> "FrozenRouter":
        models = params.get("models", {})
        return cls(
            {s: np.array(m["theta"]) for s, m in models.items()},
            {s: int(m["n"]) for s, m in models.items()},
            Scaler.from_params(params.get("scaler")),
            version=version,
            lam=params.get("lambda", 1.0),
            cold_start_min=0,
        )
