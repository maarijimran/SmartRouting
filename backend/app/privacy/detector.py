from dataclasses import dataclass
from typing import Callable

from app.privacy.patterns import PatternFinding, find_pattern_entities


@dataclass(frozen=True)
class Finding:
    entity_type: str
    count: int
    scope: str
    detector_version: str = "patterns-v1"


@dataclass(frozen=True)
class ScanResult:
    findings: tuple[Finding, ...]
    error: str | None = None

    @property
    def sensitive(self) -> bool:
        return bool(self.findings)


class PrivacyScanner:
    def __init__(
        self,
        detector: Callable[[str], list[PatternFinding]] = find_pattern_entities,
        version: str = "patterns-v1",
    ) -> None:
        self.detector = detector
        self.version = version

    def scan(self, text: str, scope: str) -> ScanResult:
        try:
            findings = self.detector(text)
        except Exception as exc:
            return ScanResult((), f"scanner failure: {exc}")
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.entity_type] = counts.get(finding.entity_type, 0) + 1
        return ScanResult(
            tuple(Finding(kind, count, scope, self.version) for kind, count in counts.items())
        )
