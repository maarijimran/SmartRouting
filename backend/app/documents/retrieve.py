import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.documents.chunk import DocumentChunk


@dataclass(frozen=True)
class Evidence:
    chunk: DocumentChunk
    score: float
    margin: float


class Retriever:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = chunks
        self._bm25 = BM25Okapi([self._tokens(chunk.text) for chunk in chunks])

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def search(self, query: str, top_k: int = 3) -> list[Evidence]:
        if not query.strip() or not self.chunks:
            return []
        scores = self._bm25.get_scores(self._tokens(query))
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k]
        result = []
        for position, (index, score) in enumerate(ranked):
            next_score = ranked[position + 1][1] if position + 1 < len(ranked) else 0.0
            result.append(Evidence(self.chunks[index], float(score), float(score - next_score)))
        return result
