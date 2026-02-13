"""Tests for Unsplash API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_artist.api.unsplash import UnsplashClient


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_search_photos_success():
    """Test successful photo search."""
    with patch("httpx.AsyncClient") as mock_client_class:
        # Setup mock
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"id": "123"}]}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Test
        client = UnsplashClient(access_key="test_key")
        result = await client.search_photos(query="sunset")

        assert "results" in result
        assert len(result["results"]) == 1
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_random_photo():
    """Test getting random photo."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "random123"}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = UnsplashClient(access_key="test_key")
        result = await client.get_random_photo(query="landscape")

        assert result["id"] == "random123"


def test_get_attribution():
    """Test attribution HTML generation."""
    client = UnsplashClient(access_key="test_key")
    photo = {
        "user": {
            "name": "Test User",
            "links": {"html": "https://unsplash.com/@testuser"},
        }
    }

    attribution = client.get_attribution(photo)
    assert "Test User" in attribution
    assert "Unsplash" in attribution
    assert "utm_source=ai-artist" in attribution
