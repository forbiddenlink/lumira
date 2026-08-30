"""Style interpolation for Lumira's artistic expression.

The StyleInterpolator enables:
1. Runtime LoRA blending - mix multiple trained styles
2. Latent space exploration - navigate between concepts
3. Style discovery - find interesting combinations
"""

import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..utils.logging import get_logger

if TYPE_CHECKING:
    import torch
    from diffusers import DiffusionPipeline
    from PIL import Image

logger = get_logger(__name__)


@dataclass
class StyleBlend:
    """A blend of multiple styles."""

    styles: dict[str, float]  # {"impressionist": 0.6, "cyberpunk": 0.4}
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name and self.styles:
            # Auto-generate name
            sorted_styles = sorted(self.styles.items(), key=lambda x: -x[1])
            self.name = "+".join(s for s, _ in sorted_styles if _ > 0.1)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "styles": self.styles,
            "name": self.name,
            "description": self.description,
        }


@dataclass
class ExplorationResult:
    """Result from latent space exploration."""

    images: list["Image.Image"] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    interpolation_values: list[float] = field(default_factory=list)


# Curated style combinations that work well together
RECOMMENDED_BLENDS = [
    StyleBlend(
        styles={"impressionist": 0.6, "cyberpunk": 0.4},
        name="impressionist+cyberpunk",
        description="Impressionist brushwork meets neon circuitry",
    ),
    StyleBlend(
        styles={"zen": 0.7, "glitch": 0.3},
        name="zen+glitch",
        description="Meditative disruption - peace with digital artifacts",
    ),
    StyleBlend(
        styles={"baroque": 0.5, "minimalist": 0.5},
        name="baroque+minimalist",
        description="Ornate simplicity - dramatic restraint",
    ),
    StyleBlend(
        styles={"romantic": 0.6, "brutalist": 0.4},
        name="romantic+brutalist",
        description="Tender concrete - emotion in harsh forms",
    ),
    StyleBlend(
        styles={"art-nouveau": 0.6, "synthwave": 0.4},
        name="art-nouveau+synthwave",
        description="Organic neon - natural curves with electronic glow",
    ),
    StyleBlend(
        styles={"surrealist": 0.5, "photorealist": 0.5},
        name="surrealist+photorealist",
        description="Impossible clarity - dreamlike precision",
    ),
]


class StyleInterpolator:
    """Manages runtime style blending via LoRA adapters.

    Enables Lumira to combine multiple trained styles at inference time
    without retraining.
    """

    def __init__(
        self,
        pipeline: "DiffusionPipeline | None" = None,
        lora_registry: dict[str, str] | None = None,
    ):
        """Initialize the style interpolator.

        Args:
            pipeline: Diffusion pipeline with LoRA support
            lora_registry: Map of style names to LoRA file paths
        """
        self.pipe: Any = pipeline
        self.registry = lora_registry or {}
        self.loaded_loras: set[str] = set()
        self.current_blend: StyleBlend | None = None

        logger.info(
            "style_interpolator_initialized",
            registered_styles=len(self.registry),
        )

    def register_style(self, name: str, lora_path: str) -> bool:
        """Register a new style.

        Args:
            name: Style name for reference
            lora_path: Path to LoRA weights file

        Returns:
            True if registered successfully
        """
        path = Path(lora_path)
        if not path.exists():
            logger.warning("lora_path_not_found", path=lora_path)
            return False

        self.registry[name] = str(path)
        logger.info("style_registered", name=name, path=lora_path)
        return True

    async def load_styles(self, styles: list[str]) -> list[str]:
        """Load required LoRA adapters.

        Args:
            styles: List of style names to load

        Returns:
            List of successfully loaded styles
        """
        if self.pipe is None:
            logger.warning("no_pipeline", action="load_styles")
            return []

        loaded = []
        for style in styles:
            if style in self.loaded_loras:
                loaded.append(style)
                continue

            if style not in self.registry:
                logger.debug("style_not_registered", style=style)
                continue

            try:
                path = self.registry[style]
                self.pipe.load_lora_weights(path, adapter_name=style)
                self.loaded_loras.add(style)
                loaded.append(style)
                logger.debug("lora_loaded", style=style)
            except Exception as e:
                logger.error("lora_load_failed", style=style, error=str(e))

        return loaded

    async def set_blend(self, weights: dict[str, float]) -> bool:
        """Set the active style blend.

        Args:
            weights: Style weights, e.g., {"impressionist": 0.6, "zen": 0.4}

        Returns:
            True if blend was set successfully
        """
        if self.pipe is None:
            logger.warning("no_pipeline", action="set_blend")
            return False

        if not weights:
            return False

        # Load any unloaded styles
        styles = list(weights.keys())
        loaded = await self.load_styles(styles)

        if not loaded:
            logger.warning("no_styles_loaded")
            return False

        # Filter to only loaded styles and renormalize
        active_weights = {s: w for s, w in weights.items() if s in loaded}
        total = sum(active_weights.values())
        if total > 0:
            active_weights = {s: w / total for s, w in active_weights.items()}

        try:
            self.pipe.set_adapters(
                adapter_names=list(active_weights.keys()),
                adapter_weights=list(active_weights.values()),
            )
            self.current_blend = StyleBlend(styles=active_weights)
            logger.info(
                "blend_set",
                styles=list(active_weights.keys()),
                weights=list(active_weights.values()),
            )
            return True
        except Exception as e:
            logger.error("set_blend_failed", error=str(e))
            return False

    async def clear_blend(self) -> None:
        """Clear the current style blend."""
        if self.pipe is not None:
            with contextlib.suppress(Exception):
                self.pipe.disable_lora()
        self.current_blend = None

    def get_recommended_blends(self) -> list[StyleBlend]:
        """Get curated style blend recommendations.

        Returns:
            List of recommended StyleBlend objects
        """
        # Filter to only blends where we have the styles registered
        available = []
        for blend in RECOMMENDED_BLENDS:
            if all(s in self.registry for s in blend.styles):
                available.append(blend)

        return available

    def suggest_blend_for_mood(self, mood: str) -> StyleBlend:
        """Suggest a style blend for a given mood.

        Args:
            mood: Current mood state

        Returns:
            Suggested StyleBlend
        """
        mood_blends = {
            "contemplative": {"impressionist": 0.7, "minimalist": 0.3},
            "playful": {"pop-art": 0.6, "cartoon": 0.4},
            "melancholic": {"romantic": 0.6, "atmospheric": 0.4},
            "euphoric": {"psychedelic": 0.5, "radiant": 0.5},
            "serene": {"zen": 0.7, "naturalist": 0.3},
            "anxious": {"expressionist": 0.6, "glitch": 0.4},
            "nostalgic": {"vintage": 0.7, "film-grain": 0.3},
            "curious": {"surrealist": 0.6, "experimental": 0.4},
            "rebellious": {"punk": 0.5, "street-art": 0.5},
            "transcendent": {"ethereal": 0.6, "cosmic": 0.4},
        }

        blend_weights = mood_blends.get(mood, {"atmospheric": 1.0})
        return StyleBlend(styles=blend_weights)


class LatentExplorer:
    """Explores the latent space between concepts.

    Enables Lumira to discover intermediate states between
    different artistic concepts through embedding interpolation.
    """

    def __init__(self, pipeline: "DiffusionPipeline | None" = None):
        """Initialize the latent explorer.

        Args:
            pipeline: Diffusion pipeline for generation
        """
        self.pipe: Any = pipeline
        logger.info("latent_explorer_initialized")

    def _get_text_encoder(self) -> Any:
        """Get the text encoder from pipeline."""
        if self.pipe is None:
            return None
        return getattr(self.pipe, "text_encoder", None)

    def _get_tokenizer(self) -> Any:
        """Get the tokenizer from pipeline."""
        if self.pipe is None:
            return None
        return getattr(self.pipe, "tokenizer", None)

    async def encode_prompt(self, prompt: str) -> "torch.Tensor | None":
        """Encode a prompt to embedding space.

        Args:
            prompt: Text prompt to encode

        Returns:
            Embedding tensor or None if failed
        """
        import torch

        text_encoder = self._get_text_encoder()
        tokenizer = self._get_tokenizer()

        if text_encoder is None or tokenizer is None:
            logger.warning("missing_encoder_or_tokenizer")
            return None

        try:
            tokens = tokenizer(
                prompt,
                padding="max_length",
                max_length=tokenizer.model_max_length,
                truncation=True,
                return_tensors="pt",
            )
            input_ids = tokens.input_ids.to(text_encoder.device)

            with torch.no_grad():
                embeddings = text_encoder(input_ids)[0]

            return cast("torch.Tensor", embeddings)
        except Exception as e:
            logger.error("encode_prompt_failed", error=str(e))
            return None

    def spherical_lerp(
        self,
        embed_a: "torch.Tensor",
        embed_b: "torch.Tensor",
        t: float,
    ) -> "torch.Tensor":
        """Spherical linear interpolation between embeddings.

        SLERP produces smoother transitions than linear interpolation
        for high-dimensional spaces.

        Args:
            embed_a: Starting embedding
            embed_b: Ending embedding
            t: Interpolation factor (0.0 to 1.0)

        Returns:
            Interpolated embedding
        """
        import torch

        # Flatten for computation
        a_flat = embed_a.view(-1)
        b_flat = embed_b.view(-1)

        # Normalize
        a_norm = a_flat / a_flat.norm()
        b_norm = b_flat / b_flat.norm()

        # Compute angle
        dot = torch.clamp(torch.dot(a_norm, b_norm), -1.0, 1.0)
        omega = torch.acos(dot)

        # If vectors are nearly parallel, use linear interpolation
        if omega.abs() < 1e-6:
            result = (1.0 - t) * a_flat + t * b_flat
        else:
            sin_omega = torch.sin(omega)
            s_a = torch.sin((1.0 - t) * omega) / sin_omega
            s_b = torch.sin(t * omega) / sin_omega
            result = s_a * a_flat + s_b * b_flat

        return result.view(embed_a.shape)

    def linear_lerp(
        self,
        embed_a: "torch.Tensor",
        embed_b: "torch.Tensor",
        t: float,
    ) -> "torch.Tensor":
        """Linear interpolation between embeddings.

        Simpler but can produce less smooth transitions.

        Args:
            embed_a: Starting embedding
            embed_b: Ending embedding
            t: Interpolation factor (0.0 to 1.0)

        Returns:
            Interpolated embedding
        """
        return (1.0 - t) * embed_a + t * embed_b

    async def explore_between(
        self,
        concept_a: str,
        concept_b: str,
        steps: int = 5,
        use_slerp: bool = True,
        **generation_kwargs: Any,
    ) -> ExplorationResult:
        """Generate images along the path from concept A to B.

        Args:
            concept_a: Starting concept/prompt
            concept_b: Ending concept/prompt
            steps: Number of interpolation steps
            use_slerp: Use spherical interpolation (recommended)
            **generation_kwargs: Additional args for generation

        Returns:
            ExplorationResult with images and metadata
        """
        if self.pipe is None:
            logger.warning("no_pipeline", action="explore_between")
            return ExplorationResult()

        # Encode both prompts
        embed_a = await self.encode_prompt(concept_a)
        embed_b = await self.encode_prompt(concept_b)

        if embed_a is None or embed_b is None:
            logger.error("encoding_failed")
            return ExplorationResult()

        result = ExplorationResult()
        interp_fn = self.spherical_lerp if use_slerp else self.linear_lerp

        for i in range(steps):
            t = i / (steps - 1) if steps > 1 else 0.0
            result.interpolation_values.append(t)

            # Interpolate embeddings
            blended_embed = interp_fn(embed_a, embed_b, t)

            # Generate image
            try:
                image = self.pipe(
                    prompt_embeds=blended_embed,
                    **generation_kwargs,
                ).images[0]
                result.images.append(image)

                # Create descriptive prompt for this point
                if t == 0:
                    prompt = concept_a
                elif t == 1:
                    prompt = concept_b
                else:
                    prompt = f"[{1 - t:.0%} {concept_a}] + [{t:.0%} {concept_b}]"
                result.prompts.append(prompt)

                logger.debug(
                    "exploration_step",
                    step=i + 1,
                    total=steps,
                    t=round(t, 2),
                )
            except Exception as e:
                logger.error("exploration_step_failed", step=i, error=str(e))

        return result

    async def explore_variations(
        self,
        concept: str,
        variation_strength: float = 0.3,
        count: int = 4,
        **generation_kwargs: Any,
    ) -> ExplorationResult:
        """Generate variations of a concept in latent space.

        Args:
            concept: Base concept
            variation_strength: How far to explore (0.0-1.0)
            count: Number of variations
            **generation_kwargs: Additional args for generation

        Returns:
            ExplorationResult with variation images
        """
        import torch

        if self.pipe is None:
            logger.warning("no_pipeline", action="explore_variations")
            return ExplorationResult()

        base_embed = await self.encode_prompt(concept)
        if base_embed is None:
            return ExplorationResult()

        result = ExplorationResult()

        for i in range(count):
            # Add random noise to embedding
            noise = torch.randn_like(base_embed) * variation_strength
            varied_embed = base_embed + noise

            try:
                image = self.pipe(
                    prompt_embeds=varied_embed,
                    **generation_kwargs,
                ).images[0]
                result.images.append(image)
                result.prompts.append(f"{concept} (variation {i + 1})")
                result.interpolation_values.append(variation_strength)
            except Exception as e:
                logger.error("variation_failed", index=i, error=str(e))

        return result

    async def find_midpoint(
        self,
        concept_a: str,
        concept_b: str,
        **generation_kwargs: Any,
    ) -> tuple["Image.Image | None", str]:
        """Find the aesthetic midpoint between two concepts.

        Args:
            concept_a: First concept
            concept_b: Second concept
            **generation_kwargs: Additional args for generation

        Returns:
            Tuple of (image, description) or (None, error)
        """
        result = await self.explore_between(
            concept_a=concept_a,
            concept_b=concept_b,
            steps=3,  # Just get start, middle, end
            **generation_kwargs,
        )

        if len(result.images) >= 2:
            # Return the middle image
            mid_idx = len(result.images) // 2
            return result.images[mid_idx], result.prompts[mid_idx]

        return None, "Failed to generate midpoint"
