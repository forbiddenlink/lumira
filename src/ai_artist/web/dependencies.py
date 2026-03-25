"""FastAPI dependency injection functions for shared resources."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from ..gallery.manager import GalleryManager
from ..utils.config import WebConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Global instances (initialized in lifespan)
_gallery_manager: GalleryManager | None = None
_gallery_path: str | None = None

# API key header for authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Web configuration (set during app initialization)
_web_config: WebConfig | None = None


def set_web_config(config: WebConfig) -> None:
    """Set the web configuration for authentication and rate limiting."""
    global _web_config
    _web_config = config


def get_web_config() -> WebConfig:
    """Get the current web configuration."""
    if _web_config is None:
        return WebConfig()
    return _web_config


def require_api_key(
    api_key: str | None = Depends(api_key_header),
) -> str:
    """Require API key for admin endpoints.

    If no API keys are configured, allow access (dev mode).
    """
    config = get_web_config()

    if not config.api_keys:
        return "dev-mode"

    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "API key required"},
        )

    valid_keys = [k.get_secret_value() for k in config.api_keys]
    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return api_key


def set_gallery_manager(manager: GalleryManager, path: str) -> None:
    """Set global gallery manager instance (called during app startup)."""
    global _gallery_manager, _gallery_path
    _gallery_manager = manager
    _gallery_path = path


def get_gallery_manager() -> Generator[GalleryManager, None, None]:
    """Dependency that provides gallery manager instance."""
    if _gallery_manager is None:
        raise HTTPException(status_code=503, detail="Gallery not initialized")
    yield _gallery_manager


def get_gallery_path() -> str:
    """Dependency that provides gallery path."""
    if _gallery_path is None:
        raise HTTPException(status_code=503, detail="Gallery not initialized")
    return _gallery_path


# Type annotations for cleaner dependency injection
GalleryManagerDep = Annotated[GalleryManager, Depends(get_gallery_manager)]
GalleryPathDep = Annotated[str, Depends(get_gallery_path)]
