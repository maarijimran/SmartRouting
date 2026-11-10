from dataclasses import dataclass, field

from app.registry.models import ModelSpec, PriceSnapshot


@dataclass(frozen=True)
class Features:
    """Coarse routing features. No prompt, document or response text lives here."""

    task: str
    input_tokens: int
    evidence_chunks: int
    evidence_spread: bool
    mode: str
    cost_preference: str
    estimated_cost_usd: float
    estimated_latency_ms: float | None
    retrieval_margin: float
    # Optional extras (defaults keep older call sites valid).
    estimated_output_tokens: int = 0
    evidence_tokens: int = 0
    retrieval_top_score: float = 0.0
    doc_pages: int = 0
    history_turns: int = 0
    # slug -> "local" | "cheap" | "strong"; filled by the pipeline from the candidates.
    tiers: dict[str, str] = field(default_factory=dict)
    # slug -> (recent latency EWMA ms, recent failure rate); filled by the gateway service.
    stats: dict[str, tuple[float, float]] = field(default_factory=dict)

    def is_local(self, slug: str) -> bool:
        tier = self.tiers.get(slug)
        return tier == "local" if tier else slug.startswith("local")

    def to_log(self) -> dict:
        """JSON-safe, text-free view stored with routing events."""
        return {
            "task": self.task,
            "input_tokens": self.input_tokens,
            "evidence_chunks": self.evidence_chunks,
            "evidence_spread": self.evidence_spread,
            "mode": self.mode,
            "cost_preference": self.cost_preference,
            "estimated_output_tokens": self.estimated_output_tokens,
            "evidence_tokens": self.evidence_tokens,
            "retrieval_top_score": round(self.retrieval_top_score, 4),
            "retrieval_margin": round(self.retrieval_margin, 4),
            "doc_pages": self.doc_pages,
            "history_turns": self.history_turns,
            "stats": {k: [round(v[0], 1), round(v[1], 4)] for k, v in self.stats.items()},
        }


@dataclass(frozen=True)
class CandidateEstimate:
    model: ModelSpec
    input_tokens: int
    reserved_output: int
    cost_usd: float | None
    latency_ms: float | None
    context_fits: bool


def estimate_candidate(
    model: ModelSpec,
    price: PriceSnapshot | None,
    *,
    input_tokens: int,
    reserved_output: int,
    latency_ms: float | None = None,
) -> CandidateEstimate:
    cost = None
    if model.kind == "local":
        cost = 0.0  # no API cost; local compute is reported separately
    elif price is not None:
        cost = (
            input_tokens * price.input_per_mtok + reserved_output * price.output_per_mtok
        ) / 1_000_000
    return CandidateEstimate(
        model,
        input_tokens,
        reserved_output,
        cost,
        latency_ms,
        input_tokens + reserved_output <= model.context_limit,
    )
