import base64
import os
from pathlib import Path

# Tests must never reach a real provider. Set before any app module is imported.
os.environ.setdefault("FAKE_PROVIDERS", "true")
os.environ.setdefault("KEY_VAULT_MASTER_KEY", base64.b64encode(b"t" * 32).decode())
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
# Unit tests use the regex detector even if a local .env enables the PII model; the model
# itself is covered by test_pii_model.py (skipped when the weights are not present).
os.environ["PII_DETECTOR"] = "patterns"


def pytest_configure(config) -> None:
    # Start every run from fresh SQLite files so schema changes never hit stale test DBs.
    for stale in Path.cwd().glob("test_*.db"):
        stale.unlink(missing_ok=True)
