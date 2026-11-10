from app.registry.models import PriceSnapshot


def estimate_cost(price: PriceSnapshot, input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
