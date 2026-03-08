"""Integration tests for the full artwork creation flow.

Tests the complete pipeline: mood -> critic -> thinking -> generation
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from pydantic import SecretStr

from ai_artist.main import AIArtist
from ai_artist.personality.cognition import ThoughtType
from ai_artist.personality.moods import Mood
from ai_artist.utils.config import Config


@pytest.fixture
def mock_config():
    """Create a mock configuration with all required attributes."""
    config = MagicMock(spec=Config)

    # Configure model settings
    model = MagicMock()
    model.base_model = "runwayml/stable-diffusion-v1-5"
    model.device = "cpu"
    model.dtype = "float32"
    model.lora_path = None
    model.lora_scale = 0.8
    model.use_refiner = False
    model.refiner_model = "stabilityai/stable-diffusion-xl-refiner-1.0"
    config.model = model

    # Configure generation settings
    generation = MagicMock()
    generation.width = 256
    generation.height = 256
    generation.num_inference_steps = 5
    generation.guidance_scale = 7.5
    generation.num_variations = 2
    generation.negative_prompt = "blurry"
    config.generation = generation

    # Configure API keys with SecretStr
    api_keys = MagicMock()
    api_keys.unsplash_access_key = SecretStr("test_key")
    api_keys.unsplash_secret_key = SecretStr("test_secret")
    config.api_keys = api_keys

    # Configure optional features (disabled by default)
    config.controlnet = MagicMock(enabled=False)
    config.upscaling = MagicMock(enabled=False)
    config.inpainting = MagicMock(enabled=False)
    config.face_restoration = MagicMock(enabled=False)
    config.autonomy = MagicMock(enabled=False, max_retries=0)
    config.trends = MagicMock(enabled=False)
    config.model_manager = MagicMock(enabled=False)
    config.performance = MagicMock(enable_model_pool=False, preload_models="")

    return config


@pytest.fixture
def mock_generator():
    """Create a mock image generator."""
    generator = MagicMock()
    # Create a simple test image
    test_image = Image.new("RGB", (256, 256), color="blue")
    generator.generate.return_value = [test_image, test_image]
    generator.load_model = MagicMock()
    generator.unload = MagicMock()
    return generator


@pytest.fixture
def mock_unsplash():
    """Create a mock Unsplash client."""
    client = AsyncMock()
    client.get_random_photo.return_value = {
        "id": "test_photo_123",
        "description": "A beautiful landscape",
        "alt_description": "mountain sunset",
        "urls": {"regular": "https://example.com/photo.jpg"},
        "links": {"download_location": "https://api.unsplash.com/download/123"},
    }
    client.trigger_download = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_curator():
    """Create a mock image curator."""
    curator = MagicMock()
    metrics = MagicMock()
    metrics.overall_score = 0.75
    metrics.aesthetic_score = 0.8
    metrics.clip_score = 0.7
    curator.evaluate.return_value = metrics
    return curator


@pytest.fixture
def mock_gallery(tmp_path):
    """Create a mock gallery manager."""
    gallery = MagicMock()
    saved_path = tmp_path / "test_artwork.png"
    gallery.save_image.return_value = saved_path
    return gallery


class TestFullCreationFlow:
    """Test the complete artwork creation pipeline."""

    @pytest.mark.asyncio
    async def test_creation_flow_with_theme(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test full creation flow when theme is provided."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            result = await app.create_artwork(theme="sunset over ocean")

            # Verify the flow - autonomous inspiration is now used instead of Unsplash
            # mock_unsplash is no longer called since we use autonomous mode
            mock_generator.generate.assert_called()
            mock_curator.evaluate.assert_called()
            mock_gallery.save_image.assert_called()

            # Should return saved path
            assert result is not None

    @pytest.mark.asyncio
    async def test_creation_flow_autonomous(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test creation flow when Lumira chooses the subject autonomously."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # No theme - Lumira chooses based on mood
            result = await app.create_artwork(theme=None)

            assert result is not None
            # Autonomous inspiration is used - no Unsplash calls
            # The autonomous system generates original concepts instead


class TestMoodToCriticPipeline:
    """Test the mood to critic pipeline."""

    @pytest.mark.asyncio
    async def test_mood_influences_critic(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that mood influences the critic's evaluation."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # Set specific mood
            app.mood_system.current_mood = Mood.SERENE
            app.mood_system.energy_level = 0.7

            await app.create_artwork(theme="calm lake")

            # The critic should have been consulted (internal to create_artwork)
            # We verify the overall flow completed
            mock_gallery.save_image.assert_called()


class TestThinkingToGenerationPipeline:
    """Test the thinking process leading to generation."""

    @pytest.mark.asyncio
    async def test_thinking_process_emits_thoughts(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that thinking process emits thoughts during creation."""
        thoughts_emitted = []

        def capture_thought(thought):
            thoughts_emitted.append(thought)

        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)
            app.thinking.on_thought = capture_thought

            await app.create_artwork(theme="test")

            # Should have emitted thoughts
            assert len(thoughts_emitted) > 0

            # Should have at least an observation
            thought_types = [t.type for t in thoughts_emitted]
            assert ThoughtType.OBSERVE in thought_types

    @pytest.mark.asyncio
    async def test_thinking_session_stored_in_memory(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that thinking session is stored in memory."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            initial_episode_count = len(app.enhanced_memory.episodic.episodes)

            await app.create_artwork(theme="test")

            # Should have added episodes (creation + thinking session)
            assert len(app.enhanced_memory.episodic.episodes) > initial_episode_count


class TestCriticIterationFlow:
    """Test the critic iteration loop."""

    @pytest.mark.asyncio
    async def test_critic_approves_good_concept(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test critic approves when concept is good."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # Force critic to always approve
            with patch.object(app.critic, "critique_concept") as mock_critique:
                mock_critique.return_value = {
                    "approved": True,
                    "confidence": 0.9,
                    "critique": "Excellent concept!",
                    "suggestions": [],
                    "analysis": {"overall_score": 0.9},
                }

                await app.create_artwork(theme="test")

                # Should have called critique only once since approved
                assert mock_critique.call_count == 1

    @pytest.mark.asyncio
    async def test_critic_retries_on_rejection(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test critic retries when concept is rejected."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # First two calls reject, third approves
            call_count = [0]

            def mock_critique_func(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    return {
                        "approved": False,
                        "confidence": 0.4,
                        "critique": "Try again",
                        "suggestions": ["fresh angle"],
                        "analysis": {"overall_score": 0.4},
                    }
                return {
                    "approved": True,
                    "confidence": 0.8,
                    "critique": "Good!",
                    "suggestions": [],
                    "analysis": {"overall_score": 0.8},
                }

            with patch.object(
                app.critic, "critique_concept", side_effect=mock_critique_func
            ):
                await app.create_artwork(theme="test")

                # Should have iterated through critique loop
                assert call_count[0] >= 2


class TestWebSocketEventsDuringCreation:
    """Test WebSocket events during creation (mocked)."""

    @pytest.mark.asyncio
    async def test_websocket_manager_not_required(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test creation works without WebSocket manager."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)
            # Explicitly ensure no ws manager
            app._ws_manager = None

            # Should complete without error
            result = await app.create_artwork(theme="test")
            assert result is not None


class TestMemoryIntegrationInCreation:
    """Test memory system integration during creation."""

    @pytest.mark.asyncio
    async def test_creation_recorded_in_memory(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that creation is recorded in both memory systems."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            initial_simple_count = len(app.memory.memory["paintings"])
            initial_enhanced_count = len(app.enhanced_memory.episodic.episodes)

            await app.create_artwork(theme="memorable sunset")

            # Both memory systems should have new entries
            assert len(app.memory.memory["paintings"]) > initial_simple_count
            assert len(app.enhanced_memory.episodic.episodes) > initial_enhanced_count

    @pytest.mark.asyncio
    async def test_style_effectiveness_updated(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that style effectiveness is updated after creation."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # Create multiple artworks
            await app.create_artwork(theme="test1")
            await app.create_artwork(theme="test2")

            # Semantic memory should have learned about styles
            effectiveness = app.enhanced_memory.semantic.knowledge[
                "style_effectiveness"
            ]
            # Should have at least one style recorded
            assert len(effectiveness) > 0


class TestMoodUpdatesAfterCreation:
    """Test mood updates after creation."""

    @pytest.mark.asyncio
    async def test_mood_updates_after_creation(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that mood is updated after creation."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # Track mood update calls
            update_count = [0]
            original_update = app.mood_system.update_mood

            def tracking_update(*args, **kwargs):
                update_count[0] += 1
                return original_update(*args, **kwargs)

            app.mood_system.update_mood = tracking_update

            await app.create_artwork(theme="test")

            # Mood should be updated (at least once at start, possibly after)
            assert update_count[0] >= 1


class TestErrorHandlingInFlow:
    """Test error handling in the creation flow."""

    @pytest.mark.asyncio
    async def test_autonomous_inspiration_works(
        self, mock_config, mock_generator, mock_curator, mock_gallery
    ):
        """Test that autonomous inspiration generates artwork without external APIs."""
        # No Unsplash mock needed - we use autonomous inspiration
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # Should succeed without external API calls
            result = await app.create_artwork(theme="test")

            assert result is not None
            # Verify autonomous generation was used
            mock_generator.generate.assert_called()
            mock_curator.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_generator_failure_propagates(
        self, mock_config, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that generator failure is properly propagated."""
        mock_generator = MagicMock()
        mock_generator.generate.side_effect = Exception("Generation failed")
        mock_generator.load_model = MagicMock()
        mock_generator.unload = MagicMock()

        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            with pytest.raises(Exception, match="Generation failed"):
                await app.create_artwork(theme="test")


class TestReflectionAfterCreation:
    """Test Lumira's reflection after creation."""

    @pytest.mark.asyncio
    async def test_reflection_generated(
        self, mock_config, mock_generator, mock_unsplash, mock_curator, mock_gallery
    ):
        """Test that Lumira generates a reflection after creation."""
        with (
            patch("ai_artist.main.ImageGenerator", return_value=mock_generator),
            patch("ai_artist.main.UnsplashClient", return_value=mock_unsplash),
            patch("ai_artist.main.ImageCurator", return_value=mock_curator),
            patch("ai_artist.main.GalleryManager", return_value=mock_gallery),
            patch("ai_artist.main.configure_logging"),
        ):
            app = AIArtist(mock_config)

            # Track reflection calls
            reflection_called = [False]
            original_reflect = app.mood_system.reflect_on_work

            def tracking_reflect(*args, **kwargs):
                reflection_called[0] = True
                return original_reflect(*args, **kwargs)

            app.mood_system.reflect_on_work = tracking_reflect

            await app.create_artwork(theme="test")

            assert reflection_called[0], "Reflection should be generated after creation"
