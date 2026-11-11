import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PatternFinding:
    entity_type: str
    start: int
    end: int
    score: float = 1.0


PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "pk_phone": re.compile(r"(?<!\d)(?:03\d{2}[- ]?\d{7}|\+92[- ]?\d{10})(?!\d)"),
    "cnic": re.compile(r"(?<!\d)\d{5}-\d{7}-\d(?!\d)"),
    "student_id": re.compile(r"(?<![A-Z0-9])\d{2}K-\d{4}(?![A-Z0-9])", re.I),
    "iban": re.compile(r"(?<![A-Z0-9])PK\d{2}[A-Z]{4}\d{16}(?![A-Z0-9])", re.I),
    "card": re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    # Passport numbers (1-2 letters + 6-8 digits, e.g. PK "AB1234567") are only flagged near
    # the word "passport", so ordinary codes are not. Group 1 is the reported span. The PII
    # model has no passport label and misses these.
    "passport": re.compile(r"\b(?i:passport)\b[^\n]{0,30}?(?<![A-Z0-9])([A-Z]{1,2}\d{6,8})(?!\d)"),
}


def _luhn(value: str) -> bool:
    digits = [int(char) for char in re.sub(r"\D", "", value)]
    if len(digits) < 13:
        return False
    checksum = sum(
        digit if index % 2 == 0 else (digit * 2 - 9 if digit * 2 > 9 else digit * 2)
        for index, digit in enumerate(reversed(digits))
    )
    return checksum % 10 == 0


def find_pattern_entities(text: str) -> list[PatternFinding]:
    findings = []
    for entity_type, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            if entity_type == "card" and not _luhn(match.group()):
                continue
            start, end = match.span(1) if pattern.groups else match.span()
            findings.append(PatternFinding(entity_type, start, end))
    return findings
