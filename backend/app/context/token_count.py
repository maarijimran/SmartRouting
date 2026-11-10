from collections.abc import Sequence


def count_text(text: str, tokenizer: str = "fallback") -> int:
    if tokenizer == "fallback":
        return len(text.split())
    return max(1, round(len(text.split()) * 1.1))


def count_messages(messages: Sequence[dict[str, str]], tokenizer: str = "fallback") -> int:
    return sum(count_text(message.get("content", ""), tokenizer) for message in messages)


def fits_context(
    input_tokens: int, reserved_output: int, context_limit: int, margin: int = 64
) -> bool:
    return input_tokens + reserved_output + margin <= context_limit
