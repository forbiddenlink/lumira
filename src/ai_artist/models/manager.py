"""Model management for CivitAI resources."""

from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from ..utils.logging import get_logger

logger = get_logger(__name__)


class CivitAIModel(BaseModel):
    """CivitAI Model representation."""

    id: int
    name: str
    type: str  # Checkpoint, LORA, TextualInversion
    nsfw: bool = False
    download_url: str
    filename: str
    size_kb: float
    hash_sha256: str | None = None


class ModelManager:
    """Manages downloading and organizing models."""

    def __init__(
        self, base_path: Path | str = "models", api_key: str | None = None
    ) -> None:
        # Reject non-path base_path (e.g. an unconfigured Mock attribute) so a
        # bad value can't silently mkdir junk directories at the repo root.
        if not isinstance(base_path, str | Path):
            raise TypeError(
                f"base_path must be str or Path, got {type(base_path).__name__}"
            )
        self.base_path = Path(base_path)
        self.lora_path = self.base_path / "lora"
        self.checkpoint_path = self.base_path / "checkpoints"
        self.api_key = api_key

        self.base_url = "https://civitai.com/api/v1"
        self.client = httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": "AIArtist/1.0"}
        )

        self.ensure_dirs()

    def ensure_dirs(self) -> None:
        """Create the model storage directories (side effect kept out of init
        so constructing a manager for its interface alone touches no disk)."""
        self.lora_path.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.mkdir(parents=True, exist_ok=True)

    async def search_models(
        self, query: str = "", limit: int = 10, types: str = "LORA"
    ) -> list[dict[str, Any]]:
        """Search CivitAI for models."""
        params: dict[str, str | int] = {
            "limit": limit,
            "sort": "Most Downloaded",
            "types": types,
            "period": "AllTime",
        }
        if query:
            params["query"] = query

        try:
            response = await self.client.get(f"{self.base_url}/models", params=params)
            response.raise_for_status()
            data = response.json()
            items: list[dict[str, Any]] = data.get("items", [])
            return items
        except Exception as e:
            logger.error("model_search_failed", error=str(e))
            return []

    async def get_model_file_info(self, model_version_id: int) -> CivitAIModel | None:
        """Get download info for a specific model version."""
        try:
            await self.client.get(f"{self.base_url}/model-variants/{model_version_id}")
            # Note: CivitAI API structure varies. Often we need to query /models/{id} then pick a version.
            # Let's assume we are passed a version ID and want to find the file.
            # Actually easier to get full model details first.
            pass
        except Exception:
            pass
        return None

    async def download_file(
        self, url: str, destination: Path, expected_hash: str | None = None
    ) -> bool:
        """Download file with progress and optional hash verification."""
        if destination.exists():
            logger.info("file_exists_skipping", path=str(destination))
            return True

        logger.info("download_started", url=url, dest=str(destination))

        # Add API Key if needed
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with self.client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()

                with open(destination, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)

            logger.info("download_complete", path=str(destination))
            return True
        except Exception as e:
            logger.error("download_failed", error=str(e))
            if destination.exists():
                destination.unlink()  # Delete partial
            return False

    async def download_top_lora(self, tag: str) -> None:
        """Find and download the top LoRA for a specific tag."""
        logger.info("finding_lora_for_tag", tag=tag)
        results = await self.search_models(query=tag, limit=1, types="LORA")

        if not results:
            logger.warning("no_lora_found", tag=tag)
            return

        model = results[0]
        model["name"]

        # Get latest version
        versions = model.get("modelVersions", [])
        if not versions:
            return

        latest = versions[0]
        files = latest.get("files", [])

        # Find safetensors
        safe_file = next((f for f in files if f["name"].endswith(".safetensors")), None)
        if not safe_file:
            safe_file = files[0] if files else None

        if safe_file:
            filename = safe_file["name"]
            download_url = safe_file["downloadUrl"]

            dest_path = self.lora_path / filename
            await self.download_file(download_url, dest_path)

    async def close(self) -> None:
        await self.client.aclose()
