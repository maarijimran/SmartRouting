# Rating rubric (blind; 1 = poor … 5 = excellent)

Raters see the question, the supplied evidence and one response. They do **not** see which model
produced it. Rate each dimension independently.

| Dimension | Ask yourself | 1 | 3 | 5 |
|---|---|---|---|---|
| Correctness | Is every claim supported by the evidence / true? | mostly wrong | partly right, some errors | fully correct |
| Relevance | Does it answer the question that was asked? | off-topic | partly on target | directly on target |
| Completeness | Does it cover what the question needs? | misses the point | covers the main point only | complete, nothing material missing |
| Usefulness | Would it help a student study or decide? | not usable | usable with effort | clear and directly usable |

Rules: do not reward length or confident tone; "the paper does not say" is correct when the
evidence does not say it; if the response refuses or is empty, score 1 on all four.

## Automatic rubric (summaries / explanations)
Each task item lists `key_points`. A key point counts as covered when ≥ 60% of its content words
appear in the response (`app.feedback.scoring.rubric_coverage`); the score is the covered fraction.
For QA the automatic score is token-F1 against the best reference, plus a small evidence-overlap
term. These are cheap proxies: validate them against the human ratings before relying on them.
