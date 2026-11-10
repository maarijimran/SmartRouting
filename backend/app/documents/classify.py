def classify_task(prompt: str) -> str:
    lowered = prompt.lower()
    if any(word in lowered for word in ("summarize", "summary", "key points", "overview")):
        return "summary"
    if lowered.startswith(("explain ", "why ", "how does ")):
        return "explain"
    return "qa"
