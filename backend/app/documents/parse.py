from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 100


class DocumentParseError(ValueError):
    """Raised when an uploaded document cannot be safely parsed."""


@dataclass(frozen=True)
class ParsedPage:
    page: int
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    media_type: str
    pages: tuple[ParsedPage, ...]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def parse_document(filename: str, content: bytes, media_type: str | None = None) -> ParsedDocument:
    if len(content) > MAX_BYTES:
        raise DocumentParseError("Document exceeds the 10 MB limit")
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "txt" or media_type == "text/plain":
        text = content.decode("utf-8", errors="replace").strip()
        if not text:
            raise DocumentParseError("Text document is empty")
        return ParsedDocument(filename, "text/plain", (ParsedPage(1, text),))
    if suffix != "pdf" and media_type != "application/pdf":
        raise DocumentParseError("Unsupported document type; upload a PDF or TXT file")
    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise DocumentParseError("PDF is corrupt or unreadable") from exc
    if len(reader.pages) > MAX_PAGES:
        raise DocumentParseError("PDF exceeds the 100-page limit")
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(ParsedPage(index, text))
    if not pages:
        raise DocumentParseError("PDF has no extractable text; scanned PDFs are unsupported")
    return ParsedDocument(filename, "application/pdf", tuple(pages))
