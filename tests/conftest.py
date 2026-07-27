"""Pytest bootstrap configuration."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Run the API in dev-mode during tests so app-lifespan config (WebConfig.from_env,
# triggered by `with TestClient(app)`) allows unauthenticated requests. Production
# stays fail-closed; the fail-closed contract is asserted with explicit config in
# tests/unit/test_generation_auth.py.
os.environ.setdefault("LUMIRA_DEV_MODE", "1")

import pytest


@pytest.fixture(autouse=True)
def _default_dev_mode_web_config():
    """Run the API in explicit dev-mode by default so unauthenticated test
    requests are allowed. Auth requires fail-closed config in production
    (empty api_keys + dev_mode False -> 503); tests that assert that contract
    override this by calling set_web_config() in their own body/fixtures."""
    from ai_artist.utils.config import WebConfig
    from ai_artist.web.dependencies import set_web_config

    set_web_config(WebConfig(dev_mode=True))
    yield
