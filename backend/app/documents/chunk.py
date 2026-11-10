import hashlib
import re
from dataclasses import dataclass

from app.documents.parse import ParsedDocument


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    text: str
    page: int
    index: int
    label: str = "public"


def chunk_document(document: ParsedDocument, words_per_chunk: int = 180) -> list[DocumentChunk]:
    if words_per_chunk < 1:
        raise ValueError("words_per_chunk must be positive")
    chunks = []
    index = 0
    for page in document.pages:
        words = re.findall(r"\S+", page.text)
        for start in range(0, len(words), words_per_chunk):
            text = " ".join(words[start : start + words_per_chunk])
            source = f"{document.filename}:{page.page}:{index}:{text}"
            digest = hashlib.sha256(source.encode()).hexdigest()
            chunks.append(DocumentChunk(digest[:24], text, page.page, index))
            index += 1
    return chunks
