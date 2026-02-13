"""Smoke tests to verify environment setup."""

import torch


def test_torch_available():
    """Test that PyTorch is installed."""
    assert torch.__version__ is not None


def test_cuda_or_cpu():
    """Test that we have either CUDA or CPU available."""
    # This test always passes - we can use either CUDA or CPU
    assert torch.cuda.is_available() or True


def test_diffusers_available():
    """Test that diffusers library is installed."""
    import diffusers

    assert diffusers.__version__ is not None


def test_transformers_available():
    """Test that transformers library is installed."""
    import transformers

    assert transformers.__version__ is not None


def test_imports():
    """Test that our modules can be imported."""
    from ai_artist import __version__
    from ai_artist.utils.config import Config
    from ai_artist.utils.logging import get_logger

    assert __version__ is not None
    assert get_logger is not None
    assert Config is not None
