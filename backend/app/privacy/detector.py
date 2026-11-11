from dataclasses import dataclass
from functools import lru_cache
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

    def warm_up(self) -> None:
        """Load heavy detector resources now (e.g. the PII model) instead of on first scan."""
        warm = getattr(self.detector, "warm_up", None)
        if warm is not None:
            warm()


def _unknown_detector(name: str) -> Callable[[str], list[PatternFinding]]:
    def detector(_: str) -> list[PatternFinding]:
        raise RuntimeError(f"unknown PII_DETECTOR {name!r}")

    return detector


@lru_cache(maxsize=1)
def default_scanner() -> PrivacyScanner:
    """The configured scanner (``PII_DETECTOR``): ``patterns`` (default) or ``piiranha``.

    An unknown detector name yields a scanner that always errors, so cloud is blocked
    (fail closed) rather than silently falling back to weaker detection.
    """
    from app.core.config import get_settings

    settings = get_settings()
    name = settings.pii_detector.strip().lower()
    if name == "patterns":
        return PrivacyScanner()
    if name == "piiranha":
        from app.privacy.ner import HybridDetector, PiiModelDetector

        model = PiiModelDetector(
            settings.pii_model_path,
            threshold=settings.pii_threshold,
            ignore=[t.strip() for t in settings.pii_ignore_types.split(",") if t.strip()],
            device=settings.pii_device,
        )
        return PrivacyScanner(HybridDetector(model), version="piiranha-v1+patterns-v1")
    return PrivacyScanner(_unknown_detector(name), version="unknown")
