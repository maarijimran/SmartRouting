from app.core.logging_scrub import scrub


def test_scrub_removes_secret_fields_and_inline_tokens() -> None:
    payload = {
        "api_key": "canary-secret",
        "message": "Authorization: Bearer abcdefghijklmnop",
        "nested": {"password": "another-secret"},
    }

    result = scrub(payload)

    assert result == {
        "api_key": "[REDACTED]",
        "message": "Authorization: [REDACTED]",
        "nested": {"password": "[REDACTED]"},
    }
    assert payload["api_key"] == "canary-secret"
