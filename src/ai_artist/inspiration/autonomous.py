"""Autonomous inspiration generation - Let the AI choose what to create!"""

import random
from collections.abc import Callable
from typing import Any, Literal

from ..utils.logging import get_logger

logger = get_logger(__name__)


class AutonomousInspiration:
    """Generate truly autonomous inspiration without human input."""

    def __init__(self) -> None:
        # Concept categories for autonomous exploration
        self.subjects = [
            # Nature
            "mountain",
            "ocean",
            "forest",
            "desert",
            "waterfall",
            "canyon",
            "volcano",
            "aurora borealis",
            "thunderstorm",
            "rainbow",
            "coral reef",
            "cave",
            "glacier",
            "valley",
            "meadow",
            "beach",
            "cliff",
            "river",
            "lake",
            # Urban
            "cityscape",
            "street scene",
            "architecture",
            "bridge",
            "skyline",
            "alleyway",
            "marketplace",
            "cafe",
            "library",
            "museum",
            "train station",
            "skyscraper",
            "cathedral",
            "castle",
            "temple",
            "lighthouse",
            # Abstract
            "geometric patterns",
            "fluid dynamics",
            "fractals",
            "energy waves",
            "color explosion",
            "light and shadow",
            "textures",
            "gradients",
            "minimalism",
            "chaos theory",
            "sacred geometry",
            "spirals",
            # Creatures
            "dragon",
            "phoenix",
            "unicorn",
            "whale",
            "eagle",
            "wolf",
            "butterfly",
            "owl",
            "fox",
            "deer",
            "lion",
            "tiger",
            "peacock",
            "hummingbird",
            # Sci-fi
            "space station",
            "alien world",
            "future city",
            "robot",
            "spacecraft",
            "portal",
            "cyberpunk street",
            "hologram",
            "time machine",
            "crystal city",
            # Fantasy
            "enchanted forest",
            "magical castle",
            "wizard tower",
            "floating islands",
            "ancient ruins",
            "mystical portal",
            "elemental spirit",
            "dreamscape",
            # Emotions/Concepts
            "serenity",
            "chaos",
            "hope",
            "mystery",
            "wonder",
            "power",
            "freedom",
            "transformation",
            "journey",
            "discovery",
            "nostalgia",
            "euphoria",
        ]

        self.styles = [
            "impressionist",
            "expressionist",
            "surrealist",
            "abstract",
            "realistic",
            "minimalist",
            "maximalist",
            "cyberpunk",
            "vaporwave",
            "art nouveau",
            "art deco",
            "baroque",
            "renaissance",
            "modernist",
            "futuristic",
            "vintage",
            "retro",
            "steampunk",
            "gothic",
            "ethereal",
            "dreamlike",
            "cinematic",
            "dramatic",
            "whimsical",
            "elegant",
            "bold",
            "delicate",
            "atmospheric",
            "mysterious",
            "vibrant",
            "muted",
            "monochromatic",
            "psychedelic",
            "geometric",
            "organic",
            "stylized",
            "photorealistic",
            "painterly",
            "digital art",
            "oil painting",
            "watercolor",
            "ink wash",
            "pixel art",
            "low poly",
            "3D render",
            "concept art",
            "matte painting",
        ]

        self.moods = [
            "serene",
            "dramatic",
            "mysterious",
            "joyful",
            "melancholic",
            "powerful",
            "ethereal",
            "dark",
            "bright",
            "moody",
            "peaceful",
            "energetic",
            "contemplative",
            "epic",
            "intimate",
            "grand",
            "subtle",
            "intense",
            "calm",
            "stormy",
            "hopeful",
            "haunting",
            "magical",
            "raw",
            "refined",
        ]

        self.lighting = [
            "golden hour",
            "blue hour",
            "midday sun",
            "moonlight",
            "candlelight",
            "neon lights",
            "bioluminescence",
            "starlight",
            "dawn",
            "dusk",
            "overcast",
            "dramatic lighting",
            "soft diffused light",
            "harsh shadows",
            "rim lighting",
            "backlit",
            "volumetric lighting",
            "studio lighting",
            "natural light",
            "artificial light",
            "glowing",
            "luminous",
        ]

        self.techniques = [
            "palette knife",
            "loose brushwork",
            "fine detail",
            "textured",
            "smooth gradients",
            "bold strokes",
            "delicate lines",
            "mixed media",
            "layered",
            "transparent",
            "opaque",
            "glazed",
            "impasto",
            "pointillism",
            "stippling",
            "hatching",
            "wet on wet",
            "dry brush",
        ]

        logger.info(
            "autonomous_inspiration_initialized",
            subjects=len(self.subjects),
            styles=len(self.styles),
            moods=len(self.moods),
        )

    def generate_surprise(self) -> str:
        """Completely random surprise - the AI chooses everything!"""
        subject = random.choice(self.subjects)
        style = random.choice(self.styles)
        mood = random.choice(self.moods)
        lighting = random.choice(self.lighting)

        # Sometimes add technique, sometimes don't
        if random.random() > 0.3:
            technique = random.choice(self.techniques)
            prompt = f"{subject}, {style} style, {mood} mood, {lighting}, {technique}"
        else:
            prompt = f"{subject}, {style} style, {mood} mood, {lighting}"

        logger.info("surprise_generated", prompt=prompt)
        return prompt

    def generate_exploration(self, theme: str | None = None) -> str:
        """Explore variations on a theme or random exploration."""
        if theme:
            # Explore around a concept
            style = random.choice(self.styles)
            mood = random.choice(self.moods)
            prompt = f"{theme}, {style} style, {mood} mood"
        else:
            # Pure exploration
            subject = random.choice(self.subjects)
            style = random.choice(self.styles)
            prompt = f"{subject}, {style} style"

        logger.info("exploration_generated", prompt=prompt, theme=theme)
        return prompt

    def generate_style_fusion(self) -> str:
        """Mix multiple styles for unique results."""
        subject = random.choice(self.subjects)
        style1 = random.choice(self.styles)
        style2 = random.choice(self.styles)
        mood = random.choice(self.moods)

        prompt = f"{subject}, fusion of {style1} and {style2}, {mood} atmosphere"
        logger.info("style_fusion_generated", prompt=prompt)
        return prompt

    def generate_concept_mashup(self) -> str:
        """Mash up unexpected concepts for creative results."""
        subject1 = random.choice(self.subjects)
        subject2 = random.choice(self.subjects)
        style = random.choice(self.styles)

        # Avoid duplicate subjects
        while subject1 == subject2:
            subject2 = random.choice(self.subjects)

        prompt = f"{subject1} meets {subject2}, {style} interpretation"
        logger.info("concept_mashup_generated", prompt=prompt)
        return prompt

    def generate_from_mode(
        self, mode: Literal["surprise", "exploration", "fusion", "mashup"] = "surprise"
    ) -> str:
        """Generate based on autonomous mode."""
        modes: dict[str, Callable[[], str]] = {
            "surprise": self.generate_surprise,
            "exploration": self.generate_exploration,
            "fusion": self.generate_style_fusion,
            "mashup": self.generate_concept_mashup,
        }

        generator = modes.get(mode, self.generate_surprise)
        result: str = generator()
        return result

    def get_random_mode(self) -> str:
        """Pick a random generation mode."""
        return random.choice(["surprise", "exploration", "fusion", "mashup"])


class WikipediaInspiration:
    """Get inspiration from random Wikipedia articles."""

    def __init__(self) -> None:
        self.api_url = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
        logger.info("wikipedia_inspiration_initialized")

    async def get_random_article_summary(self) -> dict:
        """Fetch a random Wikipedia article summary."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.api_url)
                response.raise_for_status()
                data = response.json()

                logger.info(
                    "wikipedia_article_fetched",
                    title=data.get("title"),
                    extract_length=len(data.get("extract", "")),
                )
                return {
                    "title": data.get("title", ""),
                    "extract": data.get("extract", ""),
                    "description": data.get("description", ""),
                }
        except Exception as e:
            logger.error("wikipedia_fetch_failed", error=str(e))
            return {"title": "", "extract": "", "description": ""}

    async def generate_from_article(self) -> str:
        """Generate artistic prompt from random Wikipedia article."""
        article = await self.get_random_article_summary()

        if not article["title"]:
            # Fallback to generic
            return "mysterious landscape, artistic interpretation"

        # Use title and description for prompt
        title = article["title"]
        desc = article.get("description", "")

        if desc:
            prompt = f"{title}, {desc}, artistic interpretation"
        else:
            prompt = f"{title}, creative artistic vision"

        logger.info("wikipedia_prompt_generated", prompt=prompt, article=title)
        return prompt


class TrendingInspiration:
    """Generate prompts based on trending topics."""

    def __init__(self) -> None:
        from ..trends.manager import ArtStationTrendProvider, CivitAITrendProvider

        self.civitai = CivitAITrendProvider()
        self.artstation = ArtStationTrendProvider()
        self.cached_trends: list[str] = []
        logger.info("trending_inspiration_initialized")

    async def fetch_trends(self) -> None:
        """Fetch and cache trending topics."""
        try:
            civitai_trends = await self.civitai.get_trending_tags(limit=15)
            artstation_trends = await self.artstation.get_trending_tags(limit=15)
            self.cached_trends = civitai_trends + artstation_trends
            logger.info("trends_cached", count=len(self.cached_trends))
        except Exception as e:
            logger.error("trend_fetch_failed", error=str(e))
            self.cached_trends = []

    async def generate_from_trends(self) -> str:
        """Generate prompt from trending topics."""
        if not self.cached_trends:
            await self.fetch_trends()

        if not self.cached_trends:
            logger.warning("no_trends_available", fallback=True)
            return "trending art style, contemporary vision"

        # Pick 1-2 trending tags
        num_tags = random.randint(1, 2)
        tags = random.sample(self.cached_trends, min(num_tags, len(self.cached_trends)))

        prompt = ", ".join(tags) + ", artistic interpretation"
        logger.info("trending_prompt_generated", prompt=prompt, tags=tags)
        return prompt

    async def close(self) -> None:
        """Cleanup resources."""
        await self.civitai.close()
        await self.artstation.close()


class EvolutionaryInspiration:
    """Learn from successful generations and evolve."""

    def __init__(self, gallery_manager: Any = None) -> None:
        self.gallery_manager = gallery_manager
        self.successful_themes: list[str] = []
        logger.info("evolutionary_inspiration_initialized")

    async def analyze_successes(self, min_score: float = 0.65) -> None:
        """Analyze highly-rated images to find successful patterns."""
        if not self.gallery_manager:
            return

        try:
            # Get all images with metadata
            all_images = self.gallery_manager.list_all_images()

            # Filter by score
            successful = []
            for img_info in all_images:
                metadata = self.gallery_manager.get_image_metadata(img_info["path"])
                if metadata and metadata.get("score", 0) >= min_score:
                    prompt = metadata.get("prompt", "")
                    if prompt:
                        successful.append(prompt)

            self.successful_themes = successful
            logger.info(
                "evolution_analyzed",
                total=len(all_images),
                successful=len(successful),
                min_score=min_score,
            )
        except Exception as e:
            logger.error("evolution_analysis_failed", error=str(e))

    def generate_evolution(self) -> str:
        """Generate variations based on successful themes."""
        if not self.successful_themes:
            logger.warning("no_successful_themes", fallback=True)
            return "artistic evolution, refined style"

        # Pick a successful prompt and vary it
        base = random.choice(self.successful_themes)

        # Extract key concepts and recombine
        # Simple approach: take base and add "variation" keywords
        variations = [
            "reimagined",
            "alternative perspective",
            "new interpretation",
            "evolution of",
            "inspired by",
            "creative take on",
        ]

        variation = random.choice(variations)
        prompt = f"{variation} {base}"

        logger.info("evolution_generated", prompt=prompt, base=base[:50])
        return prompt
