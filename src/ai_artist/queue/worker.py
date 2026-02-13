"""Worker functions for the Redis job queue.

These functions are executed by RQ workers in separate processes.
Each function handles a specific type of job (e.g., image generation).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


def generate_image(prompt: str, params: dict[str, Any]) -> dict[str, Any]:
    """Worker function for image generation.

    This function is executed by RQ workers. It loads the model,
    generates images, and saves them to the gallery.

    Args:
        prompt: The generation prompt
        params: Generation parameters including:
            - width: Image width (default: 1024)
            - height: Image height (default: 1024)
            - num_inference_steps: Number of steps (default: 30)
            - guidance_scale: Guidance scale (default: 7.5)
            - num_images: Number of images to generate (default: 1)
            - seed: Random seed (optional)
            - negative_prompt: Negative prompt (optional)
            - use_refiner: Whether to use refiner (default: False)
            - model_id: Model to use (optional)

    Returns:
        Dictionary with generation results:
            - paths: List of saved image paths
            - count: Number of images generated
            - prompt: The prompt used
            - seed: The seed used
            - duration_seconds: Time taken
    """
    import time

    # Try to import RQ for job context
    try:
        from rq import get_current_job

        job = get_current_job()
    except ImportError:
        job = None

    start_time = time.time()

    # Update progress
    def update_progress(step: int, total: int, message: str = "") -> None:
        if job:
            progress = int((step / total) * 100)
            job.meta["progress"] = progress
            job.meta["current_step"] = step
            job.meta["total_steps"] = total
            job.meta["message"] = message
            job.save_meta()
            logger.debug(
                "progress_updated",
                job_id=job.id,
                progress=progress,
                step=step,
                total=total,
            )

    generator = None  # Initialize for cleanup in finally block

    try:
        # Import here to avoid loading torch until needed
        import torch

        from ..core.generator import ImageGenerator
        from ..curation.curator import is_black_or_blank
        from ..utils.config import load_config

        logger.info(
            "worker_starting_generation",
            job_id=job.id if job else "direct",
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
        )

        # Update initial progress
        update_progress(0, 100, "Loading configuration...")

        # Load configuration
        config_path = Path("config/config.yaml")
        if config_path.exists():
            config = load_config(config_path)
            model_id = params.get("model_id", config.model.base_model)
            device = config.model.device
            dtype = torch.float32 if config.model.dtype == "float32" else torch.float16
        else:
            # Use defaults
            model_id = params.get(
                "model_id", "stabilityai/stable-diffusion-xl-base-1.0"
            )
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "mps"
                if torch.backends.mps.is_available()
                else "cpu"
            )
            dtype = torch.float16 if device == "cuda" else torch.float32

        update_progress(5, 100, "Loading model...")

        # Create and load generator
        generator = ImageGenerator(
            model_id=model_id,
            device=device,
            dtype=dtype,
        )
        generator.load_model()

        update_progress(20, 100, "Model loaded, generating images...")

        # Extract generation parameters
        width = params.get("width", 1024)
        height = params.get("height", 1024)
        num_inference_steps = params.get("num_inference_steps", 30)
        guidance_scale = params.get("guidance_scale", 7.5)
        num_images = params.get("num_images", 1)
        seed = params.get("seed")
        negative_prompt = params.get("negative_prompt", "")
        use_refiner = params.get("use_refiner", False)

        # Progress callback for generation steps
        def on_generation_progress(step: int, total: int, message: str) -> None:
            # Map generation steps to 20-90% of total progress
            progress_pct = 20 + int((step / total) * 70)
            update_progress(progress_pct, 100, f"Generating: step {step}/{total}")

        # Generate images
        images = generator.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            num_images=num_images,
            seed=seed,
            use_refiner=use_refiner,
            on_progress=on_generation_progress,
        )

        update_progress(90, 100, "Saving images...")

        # Save images to gallery
        gallery_path = Path("gallery")
        now = datetime.now()
        date_path = gallery_path / now.strftime("%Y/%m/%d")
        date_path.mkdir(parents=True, exist_ok=True)

        saved_paths: list[str] = []
        job_id = job.id if job else f"direct_{now.strftime('%H%M%S')}"

        for i, img in enumerate(images):
            # Double-check validity before saving
            is_invalid, reason = is_black_or_blank(img)
            if is_invalid:
                logger.warning(
                    "skipping_invalid_image",
                    job_id=job_id,
                    index=i,
                    reason=reason,
                )
                continue

            # Generate filename
            filename = f"{job_id}_{i}.png"
            save_path = date_path / filename

            # Save image
            img.save(save_path)
            saved_paths.append(str(save_path))

            # Save metadata
            metadata = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "model_id": model_id,
                "created_at": now.isoformat(),
                "job_id": job_id,
            }
            metadata_path = save_path.with_suffix(".json")
            metadata_path.write_text(json.dumps(metadata, indent=2))

            logger.info(
                "image_saved",
                job_id=job_id,
                path=str(save_path),
                index=i,
            )

        update_progress(100, 100, "Complete!")

        duration = time.time() - start_time

        result = {
            "paths": saved_paths,
            "count": len(saved_paths),
            "prompt": prompt,
            "seed": seed,
            "duration_seconds": round(duration, 2),
            "model_id": model_id,
        }

        logger.info(
            "worker_generation_complete",
            job_id=job_id,
            count=len(saved_paths),
            duration_seconds=duration,
        )

        return result

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        logger.error(
            "worker_generation_failed",
            job_id=job.id if job else "direct",
            error=str(e),
            traceback=error_details,
        )

        # Update job meta with error
        if job:
            job.meta["error"] = str(e)
            job.meta["progress"] = -1
            job.save_meta()

        raise

    finally:
        # Always cleanup GPU resources
        if generator is not None:
            try:
                generator.unload()
                logger.debug(
                    "worker_generator_unloaded", job_id=job.id if job else "direct"
                )
            except Exception as cleanup_error:
                logger.warning(
                    "worker_cleanup_failed",
                    job_id=job.id if job else "direct",
                    error=str(cleanup_error),
                )


def cleanup_stale_jobs(max_age_hours: int = 24) -> dict[str, Any]:
    """Cleanup stale jobs from the registry.

    This is a maintenance function that can be scheduled periodically.

    Args:
        max_age_hours: Maximum age of jobs to keep

    Returns:
        Statistics about cleaned jobs
    """
    from datetime import timedelta

    try:
        from redis import Redis  # type: ignore[import-untyped]
        from rq import Queue
        from rq.job import Job
    except ImportError:
        return {"error": "RQ not installed"}

    import os

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    try:
        redis = Redis.from_url(redis_url)
        stats: dict[str, int] = {"cleaned": 0, "errors": 0}

        for queue_name in ["generation", "generation-high", "generation-low"]:
            queue = Queue(queue_name, connection=redis)

            # Clean failed jobs
            for job_id in queue.failed_job_registry.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=redis)
                    if job.ended_at:
                        age = datetime.now() - job.ended_at.replace(tzinfo=None)
                        if age > timedelta(hours=max_age_hours):
                            job.delete()
                            stats["cleaned"] += 1
                except Exception as e:
                    logger.warning("cleanup_job_failed", job_id=job_id, error=str(e))
                    stats["errors"] += 1

            # Clean finished jobs beyond TTL
            for job_id in queue.finished_job_registry.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=redis)
                    if job.ended_at:
                        age = datetime.now() - job.ended_at.replace(tzinfo=None)
                        if age > timedelta(hours=max_age_hours):
                            job.delete()
                            stats["cleaned"] += 1
                except Exception as e:
                    logger.warning("cleanup_job_failed", job_id=job_id, error=str(e))
                    stats["errors"] += 1

        logger.info("stale_jobs_cleaned", **stats)
        return stats

    except Exception as e:
        logger.error("cleanup_failed", error=str(e))
        return {"error": str(e)}
