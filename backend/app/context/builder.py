from dataclasses import dataclass

from app.context.token_count import count_messages, fits_context


@dataclass(frozen=True)
class ContextResult:
    messages: list[dict[str, str]]
    input_tokens: int
    fits: bool


def build_context(
    prompt: str,
    evidence: list[str],
    history: list[dict[str, str]],
    *,
    tokenizer: str,
    reserved_output: int,
    context_limit: int,
    margin: int = 64,
) -> ContextResult:
    evidence_text = "\n\n".join(evidence)
    messages = [
        {"role": "system", "content": "Answer using the supplied evidence."},
        *history,
        {"role": "user", "content": f"Evidence:\n{evidence_text}\n\nQuestion: {prompt}"},
    ]
    input_tokens = count_messages(messages, tokenizer)
    return ContextResult(
        messages, input_tokens, fits_context(input_tokens, reserved_output, context_limit, margin)
    )
