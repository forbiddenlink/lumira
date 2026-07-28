"""Regression tests for ReplicateGenerator's caller-facing contract."""

from __future__ import annotations

import pytest

from ai_artist.core.replicate_generator import ReplicateGenerator

pytestmark = pytest.mark.unit


def test_generate_tolerates_extra_kwargs(monkeypatch):
    """The RQ worker passes ``use_refiner`` (a local-only param) to every backend.

    ReplicateGenerator must ignore unknown kwargs via ``**kwargs`` rather than raise
    ``TypeError: unexpected keyword argument``. With no token, ``generate`` should reach
    its token check and raise ``ValueError`` — proving the kwargs were accepted first.
    """
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    gen = ReplicateGenerator(model_id="flux-schnell")
    with pytest.raises(ValueError, match="REPLICATE_API_TOKEN"):
        gen.generate("a prompt", use_refiner=True, num_images=1)
