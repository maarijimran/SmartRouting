import re
from collections.abc import Mapping
from typing import Any

_SECRET_KEYS = {"api_key", "authorization", "password", "token", "key_ciphertext"}
_SECRET_PATTERN = re.compile(r"(?i)(bearer\s+|(?:sk|or)-)[A-Za-z0-9._~+/=-]{8,}")


def scrub(value: Any) -> Any:
    """Return a log-safe copy without mutating application data."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SECRET_KEYS else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub(item) for item in value)
    if isinstance(value, str):
        return _SECRET_PATTERN.sub("[REDACTED]", value)
    return value
