"""Inter-rater agreement: Cohen's kappa (unweighted and quadratic-weighted)."""


def cohen_kappa(a: list[int], b: list[int], weights: str = "quadratic", levels: int = 5) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("rating lists must be non-empty and equal length")
    n = len(a)
    observed = [[0.0] * levels for _ in range(levels)]
    for x, y in zip(a, b, strict=True):
        observed[x - 1][y - 1] += 1
    row = [sum(r) for r in observed]
    col = [sum(observed[i][j] for i in range(levels)) for j in range(levels)]

    def weight(i: int, j: int) -> float:
        if weights == "quadratic":
            return ((i - j) / (levels - 1)) ** 2
        return 0.0 if i == j else 1.0

    num = sum(weight(i, j) * observed[i][j] for i in range(levels) for j in range(levels)) / n
    den = sum(weight(i, j) * row[i] * col[j] for i in range(levels) for j in range(levels)) / (
        n * n
    )
    if den == 0:
        return 1.0  # both raters used a single identical level
    return 1 - num / den
