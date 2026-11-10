"""Synthetic fail-closed privacy regression suite (CI job ``privacy-gate``).

The cases live in ``app.privacy.suite`` so the router can also check them at runtime.
Exits non-zero on any privacy decision that violates the outbound contract.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from app.privacy.suite import run_suite  # noqa: E402


def main() -> None:
    failures = run_suite()
    if failures:
        for name, actual, expected in failures:
            print(f"FAIL {name}: expected {expected!r}, got {actual!r}")
        raise SystemExit(1)
    print("privacy suite passed")


if __name__ == "__main__":
    main()
