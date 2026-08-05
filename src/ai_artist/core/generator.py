"""Image generation using Stable Diffusion + LoRA."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import torch
from diffusers import (
    ControlNetModel,
    DiffusionPipeline,
    DPMSolverMultistepScheduler,
    StableDiffusionControlNetPipeline,
    StableDiffusionXLControlNetPipeline,
    StableDiffusionXLImg2ImgPipeline,
)
from PIL import Image

from ..curation.curator import is_black_or_blank
from ..utils.logging import get_logger
from .controlnet import SDXL_CONTROLNET_MODELS, ControlNetLoader, ControlNetType
from .ip_adapter import IPAdapterManager, get_ip_adapter_manager

logger = get_logger(__name__)


def _is_sdxl_model(model_id: str) -> bool:
    """Check if a model ID is an SDXL-based model.

    Args:
        model_id: HuggingFace model ID or local path

    Returns:
        True if model is SDXL-based, False otherwise
    """
    sdxl_indicators = ["sdxl", "stable-diffusion-xl", "sd-xl"]
    model_lower = model_id.lower()
    return any(indicator in model_lower for indicator in sdxl_indicators)


def _is_sdxl_controlnet(controlnet_model: str) -> bool:
    """Check if a ControlNet model is SDXL-compatible.

    Args:
        controlnet_model: HuggingFace ControlNet model ID

    Returns:
        True if ControlNet is SDXL-compatible, False otherwise
    """
    # Check if it's one of the known SDXL ControlNet models
    sdxl_controlnets = set(SDXL_CONTROLNET_MODELS.values())
    if controlnet_model in sdxl_controlnets:
        return True

    # Check common naming patterns
    sdxl_indicators = ["sdxl", "xl", "sd-xl"]
    model_lower = controlnet_model.lower()
    return any(indicator in model_lower for indicator in sdxl_indicators)


class ImageGenerator:
    """Stable Diffusion image generator with LoRA support.

    Can be used as a context manager for automatic cleanup:
        with ImageGenerator() as generator:
            generator.load_model()
            images = generator.generate("a beautiful landscape")

    Supports multi-model caching for mood-based model selection.
    """

    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
        device: Literal["cuda", "mps", "cpu"] = "cuda",
        dtype: torch.dtype = torch.float16,
    ):
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.pipeline: Any | None = None
        self.refiner: Any | None = None

        # Cache for loaded models to avoid reloading
        self._model_cache: dict[str, DiffusionPipeline] = {}
        self._current_model_id: str | None = None

        # IP-Adapter manager for reference image conditioning
        self._ip_adapter_manager: IPAdapterManager | None = None

        # ControlNet state
        self._controlnet_loaded: bool = False
        self._controlnet_models: list[ControlNetModel] | None = None

        # MPS + float16 can produce black/NaN images - warn and suggest float32
        if device == "mps" and dtype == torch.float16:
            logger.warning(
                "mps_float16_instability",
                message="MPS with float16 may produce black images. "
                "Consider using float32 for more stable results.",
                hint="Set dtype: 'float32' in config or use DEVICE=cuda if available",
            )

        logger.info(
            "initializing_generator", model=model_id, device=device, dtype=str(dtype)
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically cleanup resources."""
        self.unload()
        return False

    def get_model_for_mood(
        self, mood: str, mood_models: dict[str, str] | None = None
    ) -> str:
        """Get the appropriate model ID for a given mood.

        Args:
            mood: The current mood (e.g., "contemplative", "chaotic")
            mood_models: Optional mood-to-model mapping dict

        Returns:
            The model ID to use for this mood
        """
        if mood_models is None:
            return self.model_id

        model_id = mood_models.get(mood.lower(), self.model_id)
        logger.debug("model_for_mood", mood=mood, model=model_id)
        return model_id

    def switch_model(
        self, new_model_id: str, controlnet_model: str | None = None
    ) -> bool:
        """Switch to a different model, using cache if available.

        Args:
            new_model_id: The model ID to switch to
            controlnet_model: Optional ControlNet model

        Returns:
            True if model was switched, False if already using this model
        """
        if new_model_id == self._current_model_id and self.pipeline is not None:
            logger.debug("model_already_loaded", model=new_model_id)
            return False

        # Check cache first
        if new_model_id in self._model_cache:
            logger.info("switching_to_cached_model", model=new_model_id)
            self.pipeline = self._model_cache[new_model_id]
            self._current_model_id = new_model_id
            return True

        # Load new model (will be cached)
        old_model_id = self.model_id
        self.model_id = new_model_id
        self.load_model(controlnet_model=controlnet_model)
        self.model_id = old_model_id  # Restore original default

        return True

    def load_model(
        self,
        controlnet_model: str | list[str] | None = None,
        model_override: str | None = None,
    ):
        """Load the diffusion pipeline.

        Args:
            controlnet_model: Optional ControlNet model(s) to load. Can be a single
                model ID string or a list of model IDs for multi-ControlNet.
            model_override: Optional model ID to load instead of self.model_id
        """
        model_to_load = model_override or self.model_id
        is_sdxl = _is_sdxl_model(model_to_load)

        logger.info(
            "loading_model",
            model=model_to_load,
            controlnet=controlnet_model,
            is_sdxl=is_sdxl,
        )

        try:
            if controlnet_model:
                # Normalize to list for consistent handling
                controlnet_models = (
                    [controlnet_model]
                    if isinstance(controlnet_model, str)
                    else controlnet_model
                )

                logger.info(
                    "initializing_controlnet_pipeline",
                    num_controlnets=len(controlnet_models),
                )

                # Load ControlNet model(s)
                if len(controlnet_models) == 1:
                    controlnet = ControlNetModel.from_pretrained(
                        controlnet_models[0],
                        torch_dtype=self.dtype,
                        use_safetensors=True,
                    )
                else:
                    # Multi-ControlNet: load all models
                    controlnet = ControlNetLoader.load_multiple(
                        controlnet_models, dtype=self.dtype
                    )

                # Determine if we should use SDXL pipeline
                # Use SDXL if either the base model or ControlNet is SDXL
                use_sdxl_pipeline = is_sdxl or any(
                    _is_sdxl_controlnet(cn) for cn in controlnet_models
                )

                if use_sdxl_pipeline:
                    logger.info("using_sdxl_controlnet_pipeline")
                    pipeline = StableDiffusionXLControlNetPipeline.from_pretrained(
                        model_to_load,
                        controlnet=controlnet,
                        torch_dtype=self.dtype,
                        variant="fp16" if self.dtype == torch.float16 else None,
                        use_safetensors=True,
                    )
                else:
                    logger.info("using_sd15_controlnet_pipeline")
                    pipeline = StableDiffusionControlNetPipeline.from_pretrained(
                        model_to_load,
                        controlnet=controlnet,
                        torch_dtype=self.dtype,
                        variant="fp16" if self.dtype == torch.float16 else None,
                        use_safetensors=True,
                        safety_checker=None,
                    )

                self._controlnet_loaded = True
                self._controlnet_models = (
                    controlnet if isinstance(controlnet, list) else [controlnet]
                )
            else:
                pipeline = DiffusionPipeline.from_pretrained(
                    model_to_load,
                    torch_dtype=self.dtype,
                    variant="fp16" if self.dtype == torch.float16 else None,
                    use_safetensors=True,
                )
                self._controlnet_loaded = False
                self._controlnet_models = None

            # Move pipeline to device
            pipeline = pipeline.to(self.device)

            # Use better scheduler (if compatible)
            try:
                pipeline.scheduler = DPMSolverMultistepScheduler.from_config(
                    pipeline.scheduler.config
                )
            except ValueError as e:
                # Some models have incompatible scheduler configs - use their default
                logger.warning("scheduler_override_skipped", reason=str(e))

            # Device-specific optimizations
            if self.device == "mps":
                logger.info(
                    "applying_mps_optimizations",
                    action="configuring_for_apple_silicon",
                    dtype=str(self.dtype),
                )
                # Don't use attention/VAE slicing on MPS - it's slower than direct computation

                # Log actual device placement
                logger.info(
                    "verifying_device_placement",
                    unet_device=(
                        str(pipeline.unet.device)
                        if hasattr(pipeline.unet, "device")
                        else "unknown"
                    ),
                    vae_device=(
                        str(pipeline.vae.device)
                        if hasattr(pipeline.vae, "device")
                        else "unknown"
                    ),
                    unet_dtype=(
                        str(pipeline.unet.dtype)
                        if hasattr(pipeline.unet, "dtype")
                        else "unknown"
                    ),
                    vae_dtype=(
                        str(pipeline.vae.dtype)
                        if hasattr(pipeline.vae, "dtype")
                        else "unknown"
                    ),
                )
            else:
                # Enable memory-efficient optimizations for CUDA/CPU
                logger.info("applying_memory_optimizations", device=self.device)

                # Try optimizations in order of performance (best to fallback)
                attention_enabled = False

                # 1. Try xFormers (fastest, requires separate install)
                try:
                    pipeline.enable_xformers_memory_efficient_attention()
                    logger.info(
                        "xformers_enabled",
                        benefit="30-50% faster inference, 20% memory reduction",
                    )
                    attention_enabled = True
                except Exception:
                    pass

                # 2. Try PyTorch 2.0+ SDPA (fast, built-in)
                if not attention_enabled:
                    try:
                        if hasattr(torch.nn.functional, "scaled_dot_product_attention"):
                            # SDPA is available in PyTorch 2.0+
                            # Diffusers automatically uses it if available
                            logger.info(
                                "sdpa_available",
                                benefit="20-30% faster than standard attention",
                                pytorch_version=torch.__version__,
                            )
                            attention_enabled = True
                    except Exception:
                        pass

                # 3. Fallback to attention slicing (slower but memory efficient)
                if not attention_enabled:
                    try:
                        pipeline.enable_attention_slicing(1)
                        logger.info(
                            "attention_slicing_enabled",
                            note="Install xformers for better performance: pip install xformers",
                        )
                    except Exception as e:
                        logger.warning("attention_slicing_failed", error=str(e))

                # Enable VAE slicing for large images (always beneficial)
                try:
                    pipeline.enable_vae_slicing()
                    logger.debug("vae_slicing_enabled")
                except Exception as e:
                    logger.warning("vae_slicing_failed", error=str(e))

                # Try torch.compile() for PyTorch 2.0+ (10-20% speedup)
                if hasattr(torch, "compile") and torch.__version__ >= "2.0":
                    try:
                        # Compile UNet for faster inference
                        pipeline.unet = torch.compile(
                            pipeline.unet,
                            mode="reduce-overhead",
                            fullgraph=True,
                        )
                        logger.info(
                            "torch_compile_enabled",
                            benefit="10-20% faster inference after warmup",
                            target="unet",
                        )
                    except Exception as e:
                        logger.debug("torch_compile_unavailable", error=str(e))

            # Assign to instance attribute after all setup is complete
            self.pipeline = pipeline

            # Cache the loaded model for future use
            self._model_cache[model_to_load] = pipeline
            self._current_model_id = model_to_load

            logger.info(
                "model_loaded",
                model=model_to_load,
                device=self.device,
                controlnet_enabled=self._controlnet_loaded,
            )
        except Exception as e:
            logger.error("model_load_failed", model=model_to_load, error=str(e))
            raise

    def load_controlnet(
        self,
        controlnet_type: ControlNetType | str,
        use_sdxl: bool = True,
    ):
        """Load a ControlNet model by type.

        This is a convenience method to load a ControlNet with proper SDXL/SD1.5
        model selection based on the controlnet_type.

        Args:
            controlnet_type: Type of ControlNet (canny, depth, pose, lineart, softedge)
            use_sdxl: Whether to use SDXL ControlNet models (default: True)
        """
        if isinstance(controlnet_type, str):
            controlnet_type = ControlNetType(controlnet_type.lower())

        if use_sdxl:
            model_id = ControlNetLoader.get_sdxl_model_id(controlnet_type)
        else:
            model_id = ControlNetLoader.get_sd15_model_id(controlnet_type)

        logger.info(
            "loading_controlnet_by_type",
            type=controlnet_type.value,
            model=model_id,
            use_sdxl=use_sdxl,
        )

        # Reload the pipeline with ControlNet
        self.load_model(controlnet_model=model_id)

    def load_refiner(
        self, refiner_id: str = "stabilityai/stable-diffusion-xl-refiner-1.0"
    ):
        """Load the refiner pipeline."""
        logger.info("loading_refiner", model=refiner_id)

        try:
            # Get text_encoder_2 and vae from pipeline if available
            text_encoder_2 = None
            vae = None
            if self.pipeline is not None:
                if hasattr(self.pipeline, "text_encoder_2"):
                    text_encoder_2 = self.pipeline.text_encoder_2
                if hasattr(self.pipeline, "vae"):
                    vae = self.pipeline.vae

            refiner = StableDiffusionXLImg2ImgPipeline.from_pretrained(
                refiner_id,
                text_encoder_2=text_encoder_2,
                vae=vae,
                torch_dtype=self.dtype,
                use_safetensors=True,
                variant="fp16" if self.dtype == torch.float16 else None,
            )

            # Move refiner to device and assign to instance
            self.refiner = refiner.to(self.device)

            logger.info("refiner_loaded", model=refiner_id)
        except Exception as e:
            logger.error("refiner_load_failed", model=refiner_id, error=str(e))
            raise

    def load_lora(self, lora_path: Path, lora_scale: float = 0.8):
        """Load LoRA weights from trained model."""
        if not self.pipeline:
            raise RuntimeError("Load model first using load_model()")

        logger.info("loading_lora", path=str(lora_path), scale=lora_scale)

        try:
            # Load LoRA weights using diffusers method
            self.pipeline.load_lora_weights(str(lora_path))

            # Apply LoRA scale
            self.pipeline.fuse_lora(lora_scale=lora_scale)

            logger.info("lora_loaded", path=str(lora_path), scale=lora_scale)
        except Exception as e:
            logger.error("lora_load_failed", path=str(lora_path), error=str(e))
            raise

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        num_images: int = 1,
        seed: int | None = None,
        use_refiner: bool = False,
        control_image: Image.Image | list[Image.Image] | None = None,
        controlnet_conditioning_scale: float | list[float] = 1.0,
        on_progress: "Callable[[int, int, str], None] | None" = None,
        avoid_people: bool = True,
        reference_image: Image.Image | None = None,
        ip_adapter_scale: float = 0.6,
    ) -> list[Image.Image]:
        """Generate images from prompt.

        Args:
            prompt: The text prompt for generation
            negative_prompt: What to avoid in the generation
            width: Image width in pixels
            height: Image height in pixels
            num_inference_steps: Number of denoising steps
            guidance_scale: How closely to follow the prompt (7-9 recommended)
            num_images: Number of images to generate
            seed: Random seed for reproducibility
            use_refiner: Whether to use the refiner model (if loaded)
            control_image: Optional PIL Image(s) for ControlNet guidance.
                For multi-ControlNet, pass a list of images matching the number
                of loaded ControlNet models.
            controlnet_conditioning_scale: Strength of ControlNet guidance (0.0-1.0).
                For multi-ControlNet, pass a list of scales matching the number
                of loaded ControlNet models.
            on_progress: Optional callback(step, total_steps, message) for progress updates
            avoid_people: If True, adds negative prompts to avoid generating people when not explicitly requested
            reference_image: Optional reference image for IP-Adapter style transfer
            ip_adapter_scale: Strength of reference image influence (0.0-1.0, default 0.6)
                             0.3-0.6 recommended when combining with text prompts

        Returns:
            List of generated PIL images
        """
        if not self.pipeline:
            raise RuntimeError("Load model first using load_model()")

        # Add people avoidance to negative prompt if not explicitly wanted
        person_keywords = [
            "person",
            "people",
            "man",
            "woman",
            "men",
            "women",
            "human",
            "portrait",
            "face",
            "selfie",
        ]
        prompt_lower = prompt.lower()
        has_people_in_prompt = any(kw in prompt_lower for kw in person_keywords)

        if avoid_people and not has_people_in_prompt:
            # Add to negative prompt to avoid unwanted human generation
            people_negative = "person, people, human, portrait, face, man, woman"
            if negative_prompt:
                negative_prompt = f"{negative_prompt}, {people_negative}"
            else:
                negative_prompt = people_negative

        logger.info(
            "generating_images",
            prompt=prompt[:100],
            num_images=num_images,
            steps=num_inference_steps,
            use_refiner=use_refiner,
            has_control_image=bool(control_image),
            controlnet_enabled=self._controlnet_loaded,
            has_reference_image=bool(reference_image),
            avoid_people=avoid_people,
        )

        # Set seed for reproducibility
        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(seed)

        # Progress callback using modern API (callback_on_step_end)
        def progress_callback_modern(pipeline, step_index, timestep, callback_kwargs):
            step = step_index + 1  # Make it 1-based for display
            progress_pct = int((step / num_inference_steps) * 100)
            logger.debug(
                "generation_progress",
                step=step,
                total=num_inference_steps,
                percent=progress_pct,
            )
            # Call external progress callback if provided (for WebSocket updates).
            # Every 5 steps (and final), try to decode latents into a preview image
            # so the studio can show real paint-as-you-watch frames.
            if on_progress is not None:
                preview: Any = f"Generating: step {step}/{num_inference_steps}"
                try:
                    if step % 5 == 0 or step == num_inference_steps:
                        latents = callback_kwargs.get("latents")
                        if latents is not None and hasattr(pipeline, "vae"):
                            import torch

                            with torch.no_grad():
                                scaled = latents / getattr(
                                    pipeline.vae.config, "scaling_factor", 0.18215
                                )
                                decoded = pipeline.vae.decode(
                                    scaled[:1].to(dtype=pipeline.vae.dtype),
                                    return_dict=False,
                                )[0]
                                decoded = (decoded / 2 + 0.5).clamp(0, 1)
                                arr = (
                                    decoded[0]
                                    .detach()
                                    .cpu()
                                    .permute(1, 2, 0)
                                    .float()
                                    .numpy()
                                )
                                from PIL import Image as PILImage

                                preview = PILImage.fromarray(
                                    (arr * 255).round().astype("uint8")
                                )
                except Exception:
                    pass
                on_progress(step, num_inference_steps, preview)
            return callback_kwargs

        # If using refiner, we need to output latents from base
        output_type = "pil"
        if use_refiner and self.refiner:
            output_type = "latent"

        # Prepare kwargs with modern callback API
        call_kwargs = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "num_images_per_prompt": num_images,
            "generator": generator,
            "callback_on_step_end": progress_callback_modern,
            "output_type": output_type,
        }

        # Add ControlNet arguments if applicable
        if control_image is not None:
            # Check if pipeline supports controlnet
            if (
                hasattr(self.pipeline, "controlnet")
                or "ControlNet" in self.pipeline.__class__.__name__
            ):
                call_kwargs["image"] = control_image
                call_kwargs["controlnet_conditioning_scale"] = (
                    controlnet_conditioning_scale
                )
            else:
                logger.warning("control_image_ignored_pipeline_no_support")

        # Refiner denoising end
        if use_refiner and self.refiner:
            call_kwargs["denoising_end"] = 0.8

        # Add IP-Adapter for reference image conditioning
        if reference_image is not None:
            # Initialize IP-Adapter manager if needed
            if self._ip_adapter_manager is None:
                self._ip_adapter_manager = get_ip_adapter_manager()

            # Load IP-Adapter if not already loaded
            self._ip_adapter_manager.load_ip_adapter(self.pipeline)

            # Set influence scale
            self._ip_adapter_manager.set_ip_adapter_scale(
                self.pipeline, ip_adapter_scale
            )

            # Prepare reference image
            ref_image = self._ip_adapter_manager.prepare_reference_image(
                reference_image
            )
            call_kwargs["ip_adapter_image"] = ref_image

            logger.info(
                "using_ip_adapter",
                scale=ip_adapter_scale,
                adapter=self._ip_adapter_manager._loaded_adapter,
            )

        result = self.pipeline(**call_kwargs)

        images = result.images

        # Run Refiner if requested
        if use_refiner and self.refiner:
            logger.info("running_refiner")
            images = self.refiner(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=max(10, int(num_inference_steps * 0.2)),
                denoising_start=0.8,
                image=images,
                generator=generator,
            ).images

        # Filter out black/blank/NaN images (common MPS issue)
        valid_images = []
        for i, img in enumerate(images):
            is_invalid, reason = is_black_or_blank(img)
            if is_invalid:
                logger.warning(
                    "rejecting_invalid_image",
                    index=i,
                    reason=reason,
                    device=self.device,
                )
            else:
                valid_images.append(img)

        # If all images were invalid, log error but return empty list
        if not valid_images and images:
            logger.error(
                "all_generated_images_invalid",
                original_count=len(images),
                device=self.device,
                hint="Try using float32 dtype on MPS or check model configuration",
            )

        logger.info(
            "images_generated",
            total=len(images),
            valid=len(valid_images),
            rejected=len(images) - len(valid_images),
        )

        # Return only valid images
        images = valid_images

        # Clear GPU cache after generation to prevent memory buildup
        self.clear_vram()

        return cast(list[Image.Image], images)

    def generate_img2img(
        self,
        prompt: str,
        image: Image.Image,
        strength: float = 0.75,
        guidance_scale: float = 7.5,
        negative_prompt: str = "",
        num_inference_steps: int = 30,
        seed: int | None = None,
    ) -> dict:
        """Generate an image based on an existing image (img2img).

        This method transforms an existing image based on a text prompt,
        allowing partial modifications while preserving the original structure.

        Args:
            prompt: The text prompt describing the desired output
            image: Source PIL Image to transform
            strength: How much to transform the image (0.0 = identical, 1.0 = completely different)
                     0.75 is a good default for balanced transformation
            guidance_scale: How closely to follow the prompt (7.5 is standard)
            negative_prompt: What to avoid in the generation
            num_inference_steps: Number of denoising steps
            seed: Random seed for reproducibility

        Returns:
            Dict with 'image' key containing the generated PIL Image, or empty dict on failure
        """
        if not self.pipeline:
            raise RuntimeError("Load model first using load_model()")

        logger.info(
            "generating_img2img",
            prompt=prompt[:100],
            strength=strength,
            guidance_scale=guidance_scale,
            steps=num_inference_steps,
        )

        try:
            # Create img2img pipeline from the loaded base pipeline
            img2img_pipeline = StableDiffusionXLImg2ImgPipeline.from_pipe(
                self.pipeline,
                torch_dtype=self.dtype,
            )
            img2img_pipeline.to(self.device)

            # Set seed for reproducibility
            generator = None
            if seed is not None:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            # Ensure image is in RGB mode and appropriate size
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Resize to standard dimensions if needed (maintaining aspect ratio)
            max_dim = 1024
            if image.width > max_dim or image.height > max_dim:
                ratio = min(max_dim / image.width, max_dim / image.height)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                # Ensure dimensions are multiples of 8
                new_size = (
                    new_size[0] - new_size[0] % 8,
                    new_size[1] - new_size[1] % 8,
                )
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            # Generate
            result = img2img_pipeline(
                prompt=prompt,
                image=image,
                strength=strength,
                guidance_scale=guidance_scale,
                negative_prompt=negative_prompt
                or "blurry, low quality, distorted, deformed",
                num_inference_steps=num_inference_steps,
                generator=generator,
            )

            if result.images and len(result.images) > 0:
                generated_image = result.images[0]

                # Validate output
                if not is_black_or_blank(generated_image):
                    logger.info("img2img_generation_complete")
                    return {"image": generated_image}
                else:
                    logger.warning("img2img_produced_black_image")
                    return {}

            logger.error("img2img_no_output")
            return {}

        except Exception as e:
            logger.error("img2img_generation_failed", error=str(e))
            raise
        finally:
            # Cleanup
            self.clear_vram()

    def clear_vram(self):
        """Clear GPU memory cache to prevent memory leaks in long-running sessions.

        Should be called after each generation cycle, especially in 24/7 operation.
        This helps prevent VRAM fragmentation and out-of-memory errors.
        """
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.debug("cuda_vram_cleared")
        elif torch.backends.mps.is_available():
            torch.mps.empty_cache()
            logger.debug("mps_vram_cleared")

    def unload(self):
        """Unload model from memory and cleanup resources."""
        if self.refiner:
            logger.info("unloading_refiner")
            del self.refiner
            self.refiner = None

        # Clear ControlNet models
        if self._controlnet_models:
            logger.info("unloading_controlnets")
            self._controlnet_models = None
            self._controlnet_loaded = False

        # Clear model cache
        if self._model_cache:
            logger.info("clearing_model_cache", num_models=len(self._model_cache))
            for model_id in list(self._model_cache.keys()):
                del self._model_cache[model_id]
            self._model_cache.clear()
            self._current_model_id = None

        if self.pipeline:
            logger.info("unloading_model")
            del self.pipeline
            self.pipeline = None

            # Clear GPU cache
            self.clear_vram()

            logger.info("model_unloaded")
