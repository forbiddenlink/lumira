"""init_sentry must actually initialize: a bad integration arg once made
every production boot log sentry_init_failed and report nothing."""

import pytest

sentry_sdk = pytest.importorskip("sentry_sdk")

from ai_artist.monitoring import sentry as sentry_module  # noqa: E402


def test_init_sentry_succeeds_with_dsn(monkeypatch):
    monkeypatch.setattr(sentry_module, "_sentry_initialized", False)
    # Syntactically valid DSN for an unroutable host; nothing is sent.
    ok = sentry_module.init_sentry(
        dsn="https://public@o0.ingest.invalid/0", environment="test"
    )
    try:
        assert ok is True
    finally:
        client = sentry_sdk.get_client()
        if client is not None:
            client.close(timeout=0)
        sentry_sdk.init(dsn=None)
        monkeypatch.setattr(sentry_module, "_sentry_initialized", False)
