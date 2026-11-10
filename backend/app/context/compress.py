from dataclasses import dataclass


@dataclass(frozen=True)
class CompressionNotice:
    compressed_turns: int
    label: str
    text: str


def compress_history(
    history: list[dict[str, str]], summarizer, label: str = "public"
) -> tuple[list[dict[str, str]], CompressionNotice | None]:
    if len(history) <= 4:
        return history, None
    old = history[:-4]
    summary = summarizer(old)
    notice = CompressionNotice(len(old), label, summary)
    return [{"role": "system", "content": summary, "label": label}, *history[-4:]], notice
