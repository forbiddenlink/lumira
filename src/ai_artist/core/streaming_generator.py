"""
Real-time streaming image generator with WebSocket progress updates.

Streams generation progress to clients via WebSocket for live preview.
"""

import asyncio
import base64
from collections.abc import Callable
from io import BytesIO
from typing import Any, cast

import structlog
import torch
from diffusers import DiffusionPipeline
from PIL import Image

from ai_artist.utils.config import Config

logger = structlog.get_logger(__name__)


class StreamingCallback:
    """
    Callback handler for streaming generation progress.

    Captures intermediate latents and converts them to preview images.
    """

    def __init__(
        self,
        pipeline: DiffusionPipeline,
        on_progress: Callable[[int, int, Image.Image], None],
        preview_interval: int = 5,
    ):
        """
        Initialize streaming callback.

        Args:
            pipeline: Diffusion pipeline for decoding latents
            on_progress: Callback(step, total_steps, preview_image)
            preview_interval: Generate preview every N steps
        """
        self.pipeline = pipeline
        self.on_progress = on_progress
        self.preview_interval = preview_interval
        self.step_count = 0

    def __call__(
        self, step: int, timestep: torch.Tensor, latents: torch.Tensor
    ) -> None:
        """
        Called during generation to capture progress.

        Args:
            step: Current step number
            timestep: Current timestep tensor
            latents: Current latent representation
        """
        self.step_count = step

        # Only generate preview at intervals
        if step % self.preview_interval != 0 and step != 0:
            return

        try:
            # Decode latents to image for preview
            preview = self._decode_latents(latents)

            # Send to WebSocket
            if self.on_progress is not None:
                # Get total steps from pipeline config
                total_steps = getattr(self.pipeline, "num_inference_steps", 50)
                self.on_progress(step, total_steps, preview)

        except Exception as e:
            logger.warning("preview_generation_failed", step=step, error=str(e))

    def _decode_latents(self, latents: torch.Tensor) -> Image.Image:
        """
        Decode latents to preview image.

        Args:
            latents: Latent tensor from diffusion process

        Returns:
            PIL Image preview
        """
        # Scale latents back to image space
        latents = 1 / 0.18215 * latents

        # Decode with VAE
        with torch.no_grad():
            pipeline_obj = cast(Any, self.pipeline)
            image = pipeline_obj.vae.decode(latents).sample

        # Convert to PIL
        image = (image / 2 + 0.5).clamp(0, 1)
        image = image.cpu().permute(0, 2, 3, 1).float().numpy()

        # Take first image from batch
        image = (image[0] * 255).round().astype("uint8")
        pil_image = Image.fromarray(image)

        return pil_image


class StreamingGenerator:
    """
    Image generator with real-time progress streaming.

    Sends preview images via WebSocket during generation.
    """

    def __init__(self, config: Config):
        """Initialize streaming generator."""
        self.config = config
        logger.info("streaming_generator_initialized")

    async def generate_with_streaming(
        self,
        pipeline: DiffusionPipeline,
        prompt: str,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        width: int = 1024,
        height: int = 1024,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        preview_interval: int = 5,
        **kwargs: Any,
    ) -> Image.Image:
        """
        Generate image with streaming progress updates.

        Args:
            pipeline: Diffusion pipeline to use
            prompt: Text prompt
            num_inference_steps: Number of inference steps
            guidance_scale: Guidance scale
            width: Image width
            height: Image height
            on_progress: Callback for progress updates
            preview_interval: Preview every N steps
            **kwargs: Additional pipeline arguments

        Returns:
            Final generated image
        """
        logger.info(
            "streaming_generation_started",
            prompt=prompt[:50],
            steps=num_inference_steps,
        )

        # Create progress callback
        def progress_callback(step: int, total: int, preview: Image.Image) -> None:
            if on_progress:
                # Convert preview to base64 for WebSocket
                buffered = BytesIO()
                preview.save(buffered, format="JPEG", quality=80)
                img_b64 = base64.b64encode(buffered.getvalue()).decode()

                on_progress(
                    {
                        "type": "progress",
                        "step": step,
                        "total_steps": total,
                        "progress_percent": int((step / total) * 100),
                        "preview": f"data:image/jpeg;base64,{img_b64}",
                        "prompt": prompt[:100],
                    }
                )

        # Create callback handler
        callback = StreamingCallback(
            pipeline=pipeline,
            on_progress=progress_callback,
            preview_interval=preview_interval,
        )

        # Set pipeline steps
        pipeline_obj = cast(Any, pipeline)
        pipeline_obj.num_inference_steps = num_inference_steps

        # Generate with callback
        try:
            # Run in thread to not block event loop
            result: Any = await asyncio.to_thread(
                pipeline_obj,
                prompt=prompt,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                callback=callback,
                callback_steps=1,  # Call on every step
                **kwargs,
            )

            image: Image.Image = result.images[0]

            # Send completion
            if on_progress:
                on_progress(
                    {
                        "type": "complete",
                        "message": "Generation complete!",
                        "total_steps": num_inference_steps,
                    }
                )

            logger.info(
                "streaming_generation_complete",
                steps=num_inference_steps,
            )

            final_image: Image.Image = image
            return final_image

        except Exception as e:
            logger.error("streaming_generation_failed", error=str(e))
            if on_progress is not None:
                on_progress(
                    {
                        "type": "error",
                        "message": f"Generation failed: {str(e)}",
                    }
                )
            raise


async def stream_generation_to_websocket(
    generator: StreamingGenerator,
    pipeline: DiffusionPipeline,
    prompt: str,
    websocket_manager: Any,
    client_id: str,
    **generation_params: Any,
) -> Image.Image:
    """
    Helper to stream generation progress to specific WebSocket client.

    Args:
        generator: StreamingGenerator instance
        pipeline: Diffusion pipeline
        prompt: Generation prompt
        websocket_manager: WebSocket manager instance
        client_id: Client connection ID
        **generation_params: Generation parameters

    Returns:
        Final generated image
    """

    # Create event loop for async calls from sync callback
    def send_progress(progress_data: dict[str, Any]) -> None:
        """Send progress update via WebSocket (sync wrapper for async)."""
        try:
            # Schedule async call in event loop
            asyncio.create_task(
                websocket_manager.send_personal_message(progress_data, client_id)
            )
        except Exception as e:
            logger.warning("websocket_send_failed", client_id=client_id, error=str(e))

    # Generate with streaming
    image = await generator.generate_with_streaming(
        pipeline=pipeline,
        prompt=prompt,
        on_progress=send_progress,
        **generation_params,
    )

    return image
