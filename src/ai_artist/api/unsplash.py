"""Unsplash API client with retry logic."""

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..utils.logging import get_logger

logger = get_logger(__name__)


class RateLimitError(Exception):
    """Rate limit exceeded."""

    pass


class UnsplashClient:
    """Async Unsplash API client."""

    def __init__(self, access_key: str, app_name: str = "lumira"):
        self.access_key = access_key
        self.app_name = app_name
        self.base_url = "https://api.unsplash.com"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=30.0,
        )

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
    )
    async def search_photos(
        self,
        query: str,
        per_page: int = 10,
        orientation: str | None = None,
    ) -> dict[str, Any]:
        """Search photos with retry logic."""
        params: dict[str, str | int] = {"query": query, "per_page": per_page}
        if orientation:
            params["orientation"] = orientation

        logger.info("searching_photos", query=query, per_page=per_page)

        response = await self.client.get("/search/photos", params=params)

        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")

        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def download_image(self, url: str) -> bytes:
        """Download image data from URL."""
        # Use a temporary client for external URLs
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            # Cast to bytes to satisfy mypy
            content: bytes = response.content
            return content

    async def get_random_photo(self, query: str | None = None) -> dict[str, Any]:
        """Get a random photo."""
        params = {}
        if query:
            params["query"] = query

        response = await self.client.get("/photos/random", params=params)

        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")

        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def trigger_download(self, download_location: str):
        """Track download (required by Unsplash guidelines)."""
        await self.client.get(download_location)
        logger.info("download_tracked", location=download_location)

    def get_attribution(self, photo: dict) -> str:
        """Generate attribution HTML."""
        user = photo["user"]
        utm = f"utm_source={self.app_name}&utm_medium=referral"
        return (
            f'Photo by <a href="{user["links"]["html"]}?{utm}">'
            f"{user['name']}</a> on "
            f'<a href="https://unsplash.com/?{utm}">Unsplash</a>'
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
