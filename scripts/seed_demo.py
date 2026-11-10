"""Seed demo models so the app works on a laptop with no GPU and no provider keys.

Run with FAKE_PROVIDERS=true (see SETUP.md). Creates one local and two cloud registry
entries with example prices. These are placeholders, not measured prices.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.models import Model, ModelPrice  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.routing.policy_store import ensure_rules_version  # noqa: E402

DEMO = [
    ("local-demo", "local", "ollama", 4096, 512, None),
    ("cloud-cheap-demo", "cloud", "openrouter", 16384, 1024, (0.15, 0.60)),
    ("cloud-strong-demo", "cloud", "openrouter", 32768, 1024, (3.00, 15.00)),
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        for slug, kind, provider, ctx, out, price in DEMO:
            if db.query(Model).filter_by(slug=slug).one_or_none():
                continue
            model = Model(
                slug=slug,
                kind=kind,
                provider=provider,
                endpoint="http://localhost:11434"
                if kind == "local"
                else "https://openrouter.ai/api/v1",
                context_limit=ctx,
                max_output=out,
            )
            db.add(model)
            db.flush()
            if price:
                db.add(
                    ModelPrice(
                        model_id=model.id,
                        input_per_mtok=price[0],
                        output_per_mtok=price[1],
                        source="demo placeholder (not measured)",
                    )
                )
        db.commit()
        ensure_rules_version(db)
    print("seeded demo models: local-demo, cloud-cheap-demo, cloud-strong-demo")


if __name__ == "__main__":
    main()
