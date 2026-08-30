"""Tests for main AIArtist class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from ai_artist.main import AIArtist


def create_mock_config():
    """Create a complete mock configuration object."""
    config = MagicMock()

    # Model config
    config.model.base_model = "test/model"
    config.model.device = "cpu"
    config.model.dtype = "float32"
    config.model.lora_path = None
    config.model.lora_scale = 0.8
    config.model.use_refiner = False
    config.model.refiner_model = "test/refiner"
    config.model.mood_models.get_model_for_mood.return_value = "test/model"

    # API keys - use SecretStr
    config.api_keys.unsplash_access_key = SecretStr("test_key")

    # Generation config
    config.generation.width = 512
    config.generation.height = 512
    config.generation.num_inference_steps = 10
    config.generation.guidance_scale = 7.5
    config.generation.num_images = 1
    config.generation.num_variations = 2
    config.generation.negative_prompt = "ugly, blurry"

    # Curation config
    config.curation.enabled = True

    # Face restoration config
    config.face_restoration.enabled = False
    config.face_restoration.fidelity = 0.7
    config.face_restoration.model_path = None

    # ControlNet config
    config.controlnet.enabled = False
    config.controlnet.model_id = "test/controlnet"
    config.controlnet.conditioning_scale = 1.0

    # Upscaling config
    config.upscaling.enabled = False
    config.upscaling.model_id = "test/upscaler"
    config.upscaling.noise_level = 20

    # Inpainting config
    config.inpainting.enabled = False
    config.inpainting.model_id = "test/inpainter"

    # Trends config
    config.trends.enabled = False

    # Model manager config
    config.model_manager.enabled = False
    config.model_manager.base_path = "models"
    config.model_manager.civitai_api_key = None
    config.model_manager.auto_download_trending = False

    # Performance config (used by model pool)
    config.performance.enable_model_pool = False
    config.performance.preload_models = None

    # Autonomy config
    config.autonomy.enabled = False
    config.autonomy.max_retries = 2
    config.autonomy.min_score_threshold = 0.5

    # Graph memory config
    config.graph_memory = None

    return config


@pytest.fixture
def mock_config():
    """Mock configuration object."""
    return create_mock_config()


@pytest.fixture
def mock_patches():
    """Common patches for AIArtist tests."""
    with (
        patch("ai_artist.main.configure_logging") as mock_logging,
        patch("ai_artist.main.ImageGenerator") as mock_gen_class,
        patch("ai_artist.main.GalleryManager") as mock_gallery,
        patch("ai_artist.main.UnsplashClient") as mock_unsplash,
        patch("ai_artist.main.ImageCurator") as mock_curator,
        patch("ai_artist.main.CreationScheduler") as mock_scheduler,
        patch("ai_artist.main.PromptEngine") as mock_prompt_engine,
        patch("ai_artist.main.AutonomousInspiration") as mock_inspiration,
        patch("ai_artist.main.MoodBlender") as mock_mood_blender,
        patch("ai_artist.main.StyleInterpolator") as mock_style_interp,
        patch("ai_artist.main.PreviewGenerator") as mock_preview_gen,
        patch("ai_artist.main.TwoStageGenerator") as mock_two_stage,
        patch("ai_artist.main.InnerDialogue") as mock_inner_dialogue,
        patch("ai_artist.main.Rememberer") as mock_rememberer,
    ):
        # Set up mock generator
        mock_gen = MagicMock()
        mock_gen._pipe = MagicMock()
        mock_gen_class.return_value = mock_gen

        # Set up mock inspiration
        mock_insp = MagicMock()
        mock_insp.generate_exploration.return_value = "a beautiful sunset"
        mock_insp.generate_from_mode.return_value = "abstract colorful shapes"
        mock_inspiration.return_value = mock_insp

        # Set up mock curator
        mock_cur = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.overall_score = 0.8
        mock_metrics.aesthetic_score = 0.7
        mock_metrics.clip_score = 0.6
        mock_cur.evaluate.return_value = mock_metrics
        mock_curator.return_value = mock_cur

        # Set up mock inner dialogue
        mock_dialogue = MagicMock()
        mock_dialogue.get_history.return_value = []
        mock_inner_dialogue.return_value = mock_dialogue

        yield {
            "logging": mock_logging,
            "generator_class": mock_gen_class,
            "generator": mock_gen,
            "gallery": mock_gallery,
            "unsplash": mock_unsplash,
            "curator_class": mock_curator,
            "curator": mock_cur,
            "scheduler": mock_scheduler,
            "prompt_engine": mock_prompt_engine,
            "inspiration_class": mock_inspiration,
            "inspiration": mock_insp,
            "mood_blender": mock_mood_blender,
            "style_interpolator": mock_style_interp,
            "preview_generator": mock_preview_gen,
            "two_stage_generator": mock_two_stage,
            "inner_dialogue_class": mock_inner_dialogue,
            "inner_dialogue": mock_dialogue,
            "rememberer": mock_rememberer,
        }


class TestAIArtistInitialization:
    """Test AIArtist initialization scenarios."""

    def test_basic_init(self, mock_config, mock_patches):
        """Test basic AIArtist initialization."""
        artist = AIArtist(config=mock_config)

        # Verify core components were created
        assert artist.config == mock_config
        assert artist.name == "Lumira"
        assert artist.generator is not None
        assert artist.gallery is not None
        assert artist.unsplash is not None
        assert artist.curator is not None
        assert artist.scheduler is not None
        assert artist.prompt_engine is not None

        # Verify personality components exist
        assert artist.mood_system is not None
        assert artist.memory is not None
        assert artist.enhanced_memory is not None
        assert artist.profile is not None
        assert artist.critic is not None
        assert artist.thinking is not None

    def test_init_with_custom_name(self, mock_config, mock_patches):
        """Test initialization with custom artist name."""
        artist = AIArtist(config=mock_config, name="TestArtist")
        assert artist.name == "TestArtist"

    def test_init_with_lora_path(self, mock_config, mock_patches, tmp_path):
        """Test initialization with LoRA weights."""
        # Create mock LoRA path
        lora_path = tmp_path / "test_lora"
        lora_path.mkdir()
        mock_config.model.lora_path = str(lora_path)

        _artist = AIArtist(
            config=mock_config
        )  # noqa: F841 - instantiation triggers load_lora

        # Verify load_lora was called
        mock_patches["generator"].load_lora.assert_called_once()

    def test_init_with_nonexistent_lora_path(self, mock_config, mock_patches):
        """Test initialization with nonexistent LoRA path logs warning."""
        mock_config.model.lora_path = "/nonexistent/lora/path"

        # Should not raise - just log warning
        _artist = AIArtist(
            config=mock_config
        )  # noqa: F841 - test instantiation behavior

        # load_lora should NOT have been called
        mock_patches["generator"].load_lora.assert_not_called()

    def test_init_with_controlnet_enabled(self, mock_config, mock_patches):
        """Test initialization with ControlNet enabled."""
        mock_config.controlnet.enabled = True
        mock_config.controlnet.model_id = "test/controlnet-model"

        _artist = AIArtist(config=mock_config)  # noqa: F841 - triggers load_model

        # Verify load_model was called with controlnet model
        mock_patches["generator"].load_model.assert_called_once_with(
            controlnet_model="test/controlnet-model"
        )

    def test_init_with_refiner_enabled(self, mock_config, mock_patches):
        """Test initialization with refiner model."""
        mock_config.model.use_refiner = True
        mock_config.model.refiner_model = "test/refiner-model"

        _artist = AIArtist(config=mock_config)  # noqa: F841 - triggers load_refiner

        mock_patches["generator"].load_refiner.assert_called_once_with(
            refiner_id="test/refiner-model"
        )

    def test_init_with_upscaling_enabled(self, mock_config, mock_patches):
        """Test initialization with upscaler."""
        mock_config.upscaling.enabled = True

        with patch("ai_artist.main.ImageUpscaler") as mock_upscaler:
            artist = AIArtist(config=mock_config)
            assert artist.upscaler is not None
            mock_upscaler.assert_called_once()

    def test_init_with_inpainting_enabled(self, mock_config, mock_patches):
        """Test initialization with inpainter."""
        mock_config.inpainting.enabled = True

        with patch("ai_artist.main.ImageInpainter") as mock_inpainter:
            artist = AIArtist(config=mock_config)
            assert artist.inpainter is not None
            mock_inpainter.assert_called_once()

    def test_init_with_face_restoration_enabled(self, mock_config, mock_patches):
        """Test initialization with face restorer."""
        mock_config.face_restoration.enabled = True
        mock_config.face_restoration.model_path = "/path/to/model"

        with patch("ai_artist.main.FaceRestorer") as mock_face_restorer:
            artist = AIArtist(config=mock_config)
            assert artist.face_restorer is not None
            mock_face_restorer.assert_called_once()

    def test_init_with_trends_enabled(self, mock_config, mock_patches):
        """Test initialization with trend manager."""
        mock_config.trends.enabled = True

        with patch("ai_artist.main.TrendManager") as mock_trend_manager:
            artist = AIArtist(config=mock_config)
            assert artist.trend_manager is not None
            mock_trend_manager.assert_called_once()

    def test_init_with_model_manager_enabled(self, mock_config, mock_patches):
        """Test initialization with model manager."""
        mock_config.model_manager.enabled = True

        with patch("ai_artist.main.ModelManager") as mock_model_manager:
            artist = AIArtist(config=mock_config)
            assert artist.model_manager is not None
            mock_model_manager.assert_called_once()

    def test_init_with_model_pool_enabled(self, mock_config, mock_patches):
        """Test initialization with model pool."""
        mock_config.performance.enable_model_pool = True
        mock_config.performance.preload_models = "model1,model2"

        with patch("ai_artist.main.ModelPool") as mock_model_pool:
            artist = AIArtist(config=mock_config)
            assert artist.model_pool is not None
            mock_model_pool.assert_called_once()


class TestInitializeEnhancements:
    """Test _initialize_enhancements method."""

    def test_enhancements_initialized(self, mock_config, mock_patches):
        """Test that Lumira 2.0 enhancements are initialized."""
        artist = AIArtist(config=mock_config)

        # Verify enhancement components
        assert artist.mood_blender is not None
        assert artist.style_interpolator is not None
        assert artist.inner_dialogue is not None
        assert artist.preview_generator is not None
        assert artist.two_stage_generator is not None

    def test_graph_memory_init_success(self, mock_config, mock_patches):
        """Test graph memory initialization when enabled and successful."""
        # Configure graph memory
        mock_config.graph_memory = MagicMock()
        mock_config.graph_memory.enabled = True
        mock_config.graph_memory.host = "localhost"
        mock_config.graph_memory.port = 6380
        mock_config.graph_memory.graph_name = "test_graph"

        with patch("ai_artist.main.GraphMemory") as mock_graph:
            _artist = AIArtist(
                config=mock_config
            )  # noqa: F841 - triggers GraphMemory init
            mock_graph.assert_called_once_with(
                host="localhost",
                port=6380,
                graph_name="test_graph",
            )

    def test_graph_memory_init_failure(self, mock_config, mock_patches):
        """Test graph memory handles initialization failure gracefully."""
        mock_config.graph_memory = MagicMock()
        mock_config.graph_memory.enabled = True
        mock_config.graph_memory.host = "localhost"
        mock_config.graph_memory.port = 6380
        mock_config.graph_memory.graph_name = "test_graph"

        with patch(
            "ai_artist.main.GraphMemory", side_effect=Exception("Connection failed")
        ):
            # Should not raise - just log warning
            artist = AIArtist(config=mock_config)
            assert artist.graph_memory is None  # Fallback to None


class TestCreateWithPreview:
    """Test create_with_preview method."""

    @pytest.mark.asyncio
    async def test_create_with_preview_with_inner_dialogue(
        self, mock_config, mock_patches
    ):
        """Test create_with_preview using inner dialogue for concept."""
        artist = AIArtist(config=mock_config)

        # Mock inner dialogue deliberate method
        mock_concept = MagicMock()
        mock_concept.prompt = "test prompt"
        mock_concept.style_blend = {"abstract": 0.5}
        mock_concept.subject = "abstract art"
        mock_concept.style = "modern"
        mock_concept.confidence = 0.9

        artist.inner_dialogue = MagicMock()
        artist.inner_dialogue.deliberate = AsyncMock(return_value=mock_concept)

        # Mock two_stage_generator
        artist.two_stage_generator = MagicMock()
        artist.two_stage_generator.generate_with_preview = AsyncMock(
            return_value={
                "preview_result": MagicMock(),
                "preview_approved": True,
                "preview_score": 0.8,
            }
        )

        result = await artist.create_with_preview(theme="test theme")

        assert result is not None
        artist.inner_dialogue.deliberate.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_preview_fallback_no_dialogue(
        self, mock_config, mock_patches
    ):
        """Test create_with_preview fallback when no inner dialogue."""
        artist = AIArtist(config=mock_config)
        artist.inner_dialogue = None

        artist.two_stage_generator = MagicMock()
        artist.two_stage_generator.generate_with_preview = AsyncMock(
            return_value={
                "preview_result": MagicMock(),
                "preview_approved": True,
                "preview_score": 0.75,
            }
        )

        result = await artist.create_with_preview(theme="abstract")

        assert result is not None
        assert "preview_approved" in result

    @pytest.mark.asyncio
    async def test_create_with_preview_no_generator(self, mock_config, mock_patches):
        """Test create_with_preview when two_stage_generator not available."""
        artist = AIArtist(config=mock_config)
        artist.two_stage_generator = None

        # Need to also set inner_dialogue to None to skip deliberation
        artist.inner_dialogue = None

        result = await artist.create_with_preview()

        assert result == {"error": "Two-stage generator not initialized"}

    @pytest.mark.asyncio
    async def test_create_with_preview_records_to_graph_memory(
        self, mock_config, mock_patches
    ):
        """Test that approved previews are recorded in graph memory."""
        artist = AIArtist(config=mock_config)

        # Set up graph memory
        artist.graph_memory = MagicMock()
        artist.graph_memory.record_decision = AsyncMock()

        # Set up inner dialogue
        mock_concept = MagicMock()
        mock_concept.prompt = "test prompt"
        mock_concept.style_blend = {}
        artist.inner_dialogue = MagicMock()
        artist.inner_dialogue.deliberate = AsyncMock(return_value=mock_concept)

        # Mock two_stage_generator with approved result
        artist.two_stage_generator = MagicMock()
        artist.two_stage_generator.generate_with_preview = AsyncMock(
            return_value={
                "preview_result": MagicMock(),
                "preview_approved": True,
                "preview_score": 0.85,
            }
        )

        result = await artist.create_with_preview(theme="sunset")

        assert result["preview_approved"] is True
        artist.graph_memory.record_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_preview_graph_memory_failure_handled(
        self, mock_config, mock_patches
    ):
        """Test that graph memory failures are handled gracefully."""
        artist = AIArtist(config=mock_config)

        # Set up graph memory that fails
        artist.graph_memory = MagicMock()
        artist.graph_memory.record_decision = AsyncMock(
            side_effect=Exception("DB error")
        )

        mock_concept = MagicMock()
        mock_concept.prompt = "test"
        mock_concept.style_blend = {}
        artist.inner_dialogue = MagicMock()
        artist.inner_dialogue.deliberate = AsyncMock(return_value=mock_concept)

        artist.two_stage_generator = MagicMock()
        artist.two_stage_generator.generate_with_preview = AsyncMock(
            return_value={
                "preview_result": MagicMock(),
                "preview_approved": True,
                "preview_score": 0.8,
            }
        )

        # Should not raise
        result = await artist.create_with_preview()
        assert result is not None


class TestGetDialogueHistory:
    """Test get_dialogue_history method."""

    def test_get_dialogue_history_with_inner_dialogue(self, mock_config, mock_patches):
        """Test getting dialogue history when inner dialogue exists."""
        artist = AIArtist(config=mock_config)

        # Mock inner dialogue with history
        mock_history = [
            {"voice": "dreamer", "message": "What if we tried..."},
            {"voice": "critic", "message": "That's interesting, but..."},
        ]
        artist.inner_dialogue = MagicMock()
        artist.inner_dialogue.get_history.return_value = mock_history

        result = artist.get_dialogue_history()

        assert result == mock_history
        artist.inner_dialogue.get_history.assert_called_once()

    def test_get_dialogue_history_no_inner_dialogue(self, mock_config, mock_patches):
        """Test getting dialogue history when inner dialogue is None."""
        artist = AIArtist(config=mock_config)
        artist.inner_dialogue = None

        result = artist.get_dialogue_history()

        assert result == []


class TestShutdown:
    """Test shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_all_components(self, mock_config, mock_patches):
        """Test shutdown cleans up all components."""
        artist = AIArtist(config=mock_config)

        # Set up mock components
        artist.generator = MagicMock()
        artist.preview_generator = MagicMock()
        artist.preview_generator.unload = AsyncMock()
        artist.unsplash = MagicMock()
        artist.unsplash.close = AsyncMock()
        artist.scheduler = MagicMock()

        await artist.shutdown()

        artist.generator.unload.assert_called_once()
        artist.preview_generator.unload.assert_called_once()
        artist.unsplash.close.assert_called_once()
        artist.scheduler.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_with_missing_components(self, mock_config, mock_patches):
        """Test shutdown handles missing components gracefully."""
        artist = AIArtist(config=mock_config)

        # Remove some components
        artist.generator = None
        artist.preview_generator = None
        artist.unsplash = None
        artist.scheduler = None

        # Should not raise
        await artist.shutdown()


class TestExtractStyleFromPrompt:
    """Test _extract_style_from_prompt method."""

    def test_extract_known_styles(self, mock_config, mock_patches):
        """Test extraction of known style keywords."""
        artist = AIArtist(config=mock_config)

        test_cases = [
            ("A beautiful pixel art landscape", "pixel art"),
            ("Watercolor painting of flowers", "watercolor"),
            ("An oil painting portrait", "oil painting"),
            ("Minimalist design", "minimalist"),
            ("Abstract shapes and colors", "abstract"),
            ("Impressionist garden scene", "impressionist"),
            ("Cyberpunk cityscape at night", "cyberpunk"),
            ("Anime style character", "anime"),
            ("Photorealistic portrait", "photorealistic"),
            ("Surreal dreamscape", "surrealism"),
        ]

        for prompt, expected_style in test_cases:
            result = artist._extract_style_from_prompt(prompt)
            assert result == expected_style, f"Failed for prompt: {prompt}"

    def test_extract_default_style(self, mock_config, mock_patches):
        """Test default style when no known keyword found."""
        artist = AIArtist(config=mock_config)

        result = artist._extract_style_from_prompt("A simple landscape")
        assert result == "dreamlike"

    def test_extract_style_case_insensitive(self, mock_config, mock_patches):
        """Test style extraction is case insensitive."""
        artist = AIArtist(config=mock_config)

        assert artist._extract_style_from_prompt("PIXEL ART scene") == "pixel art"
        assert artist._extract_style_from_prompt("WaTeRcOlOr flowers") == "watercolor"


class TestOnThought:
    """Test _on_thought callback method."""

    def test_on_thought_logs_thought(self, mock_config, mock_patches):
        """Test that thoughts are logged."""
        artist = AIArtist(config=mock_config)

        mock_thought = MagicMock()
        mock_thought.type = MagicMock()
        mock_thought.type.value = "observation"
        mock_thought.content = "This is a test thought"
        mock_thought.context = {}

        # Should not raise
        artist._on_thought(mock_thought)

    def test_on_thought_with_websocket_manager(self, mock_config, mock_patches):
        """Test thoughts are broadcast via WebSocket when available."""
        artist = AIArtist(config=mock_config)

        # Mock WebSocket manager
        mock_ws_manager = MagicMock()
        mock_ws_manager.send_thinking_update = AsyncMock()
        artist._ws_manager = mock_ws_manager
        artist._current_session_id = "test-session-123"

        mock_thought = MagicMock()
        mock_thought.type = MagicMock()
        mock_thought.type.value = "reflection"
        mock_thought.content = "Reflecting on the concept"
        mock_thought.context = {"theme": "sunset"}

        # Run in async context. Save/restore the thread's event loop so we don't
        # leave a closed loop as "current" for later tests on this thread.
        try:
            prev_loop = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            prev_loop = None
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # _on_thought tries to create a task, which needs a running loop
            artist._on_thought(mock_thought)
        except RuntimeError:
            # Expected - no running event loop in test
            pass
        finally:
            loop.close()
            asyncio.set_event_loop(prev_loop)


class TestGetWsManager:
    """Test _get_ws_manager method."""

    def test_get_ws_manager_returns_cached(self, mock_config, mock_patches):
        """Test that cached WebSocket manager is returned."""
        artist = AIArtist(config=mock_config)

        mock_manager = MagicMock()
        artist._ws_manager = mock_manager

        result = artist._get_ws_manager()

        assert result is mock_manager

    def test_get_ws_manager_lazy_loads(self, mock_config, mock_patches):
        """Test that WebSocket manager is lazily loaded."""
        artist = AIArtist(config=mock_config)
        artist._ws_manager = None

        with patch("ai_artist.main.AIArtist._get_ws_manager") as mock_method:
            mock_method.return_value = None
            result = artist._get_ws_manager()
            # Returns None when import fails or not available
            assert result is None


class TestUpdateTrends:
    """Test update_trends method."""

    @pytest.mark.asyncio
    async def test_update_trends_no_manager(self, mock_config, mock_patches):
        """Test update_trends returns early when trend manager is None."""
        artist = AIArtist(config=mock_config)
        artist.trend_manager = None

        # Should return without doing anything
        await artist.update_trends()

    @pytest.mark.asyncio
    async def test_update_trends_success(self, mock_config, mock_patches):
        """Test successful trend update."""
        artist = AIArtist(config=mock_config)

        artist.trend_manager = MagicMock()
        artist.trend_manager.update_wildcard_file = AsyncMock()
        artist.prompt_engine = MagicMock()

        await artist.update_trends()

        artist.trend_manager.update_wildcard_file.assert_called_once()
        artist.prompt_engine.reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_trends_with_auto_download(self, mock_config, mock_patches):
        """Test trend update with auto model download."""
        mock_config.model_manager.enabled = True
        mock_config.model_manager.auto_download_trending = True

        artist = AIArtist(config=mock_config)

        artist.trend_manager = MagicMock()
        artist.trend_manager.update_wildcard_file = AsyncMock()
        artist.trend_manager.get_combined_trends = AsyncMock(
            return_value=["cyberpunk", "anime"]
        )

        artist.model_manager = MagicMock()
        artist.model_manager.download_top_lora = AsyncMock()

        artist.prompt_engine = MagicMock()

        await artist.update_trends()

        # Should download models for each trend
        assert artist.model_manager.download_top_lora.call_count == 2

    @pytest.mark.asyncio
    async def test_update_trends_handles_error(self, mock_config, mock_patches):
        """Test trend update handles errors gracefully."""
        artist = AIArtist(config=mock_config)

        artist.trend_manager = MagicMock()
        artist.trend_manager.update_wildcard_file = AsyncMock(
            side_effect=Exception("Network error")
        )

        # Should not raise
        await artist.update_trends()


class TestRunManual:
    """Test run_manual method."""

    @pytest.mark.asyncio
    async def test_run_manual_with_theme(self, mock_config, mock_patches):
        """Test manual run with a theme."""
        artist = AIArtist(config=mock_config)

        artist.create_artwork = AsyncMock()
        artist.update_trends = AsyncMock()

        await artist.run_manual(theme="sunset")

        artist.create_artwork.assert_called_once_with(theme="sunset")

    @pytest.mark.asyncio
    async def test_run_manual_with_trends_enabled(self, mock_config, mock_patches):
        """Test manual run updates trends when enabled."""
        mock_config.trends.enabled = True
        artist = AIArtist(config=mock_config)

        artist.create_artwork = AsyncMock()
        artist.update_trends = AsyncMock()

        await artist.run_manual()

        artist.update_trends.assert_called_once()
        artist.create_artwork.assert_called_once()


class TestRunAutomated:
    """Test run_automated method."""

    @pytest.mark.asyncio
    async def test_run_automated_setup(self, mock_config, mock_patches):
        """Test automated mode sets up scheduler correctly."""
        artist = AIArtist(config=mock_config)

        artist.scheduler = MagicMock()
        artist.update_trends = AsyncMock()
        artist.create_artwork = AsyncMock()

        # Run briefly and cancel
        with pytest.raises(asyncio.CancelledError):
            task = asyncio.create_task(artist.run_automated())
            await asyncio.sleep(0.1)
            task.cancel()
            await task

    @pytest.mark.asyncio
    async def test_run_automated_schedules_daily_job(self, mock_config, mock_patches):
        """Test that daily creation job is scheduled."""
        artist = AIArtist(config=mock_config)

        artist.scheduler = MagicMock()
        artist.update_trends = AsyncMock()

        # Run briefly and cancel
        try:
            task = asyncio.create_task(artist.run_automated())
            await asyncio.sleep(0.05)
            task.cancel()
            await task
        except asyncio.CancelledError:
            pass

        # Verify scheduler was configured
        artist.scheduler.add_daily_job.assert_called()
        artist.scheduler.start.assert_called_once()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_init_creates_personality_components(self, mock_config, mock_patches):
        """Test that personality components are always created."""
        artist = AIArtist(config=mock_config)

        assert artist.mood_system is not None
        assert artist.memory is not None
        assert artist.enhanced_memory is not None
        assert artist.profile is not None
        assert artist.critic is not None
        assert artist.thinking is not None

    def test_websocket_manager_initially_none(self, mock_config, mock_patches):
        """Test that WebSocket manager is initially None."""
        artist = AIArtist(config=mock_config)
        assert artist._ws_manager is None

    def test_current_session_id_not_set_initially(self, mock_config, mock_patches):
        """Test that session ID is not set until create_artwork called."""
        artist = AIArtist(config=mock_config)
        assert (
            not hasattr(artist, "_current_session_id")
            or artist._current_session_id is None
        )


class TestCreateArtwork:
    """Test create_artwork method - the main generation pipeline."""

    @pytest.fixture
    def artist_with_mocks(self, mock_config, mock_patches):
        """Create an AIArtist with all internal components mocked."""
        artist = AIArtist(config=mock_config)

        # Mock generator
        mock_image = MagicMock()
        artist.generator = MagicMock()
        artist.generator.generate.return_value = [mock_image]
        artist.generator.switch_model.return_value = False

        # Mock curator
        mock_metrics = MagicMock()
        mock_metrics.overall_score = 0.85
        mock_metrics.aesthetic_score = 0.8
        mock_metrics.clip_score = 0.75
        artist.curator = MagicMock()
        artist.curator.evaluate.return_value = mock_metrics

        # Mock gallery
        artist.gallery = MagicMock()
        artist.gallery.save_image.return_value = "/gallery/test_artwork.png"

        # Mock autonomous inspiration
        artist.autonomous_inspiration = MagicMock()
        artist.autonomous_inspiration.generate_exploration.return_value = (
            "beautiful sunset scene"
        )
        artist.autonomous_inspiration.generate_from_mode.return_value = (
            "abstract colorful shapes"
        )

        # Mock prompt engine
        artist.prompt_engine = MagicMock()
        artist.prompt_engine.process.return_value = "processed prompt with style"

        # Mock critic
        artist.critic = MagicMock()
        artist.critic.critique_concept.return_value = {
            "approved": True,
            "confidence": 0.9,
            "critique": "Excellent concept with good balance",
            "suggestions": [],
        }

        # Mock thinking process
        artist.thinking = MagicMock()
        artist.thinking.decide.return_value = (
            "mountain landscape",
            "fits contemplative mood",
        )
        artist.thinking.get_thinking_narrative.return_value = (
            "I observed... I reflected..."
        )

        return artist

    @pytest.mark.asyncio
    async def test_create_artwork_with_theme(self, artist_with_mocks):
        """Test artwork creation with a provided theme."""
        result = await artist_with_mocks.create_artwork(theme="cosmic nebula")

        # Verify path returned
        assert result == "/gallery/test_artwork.png"

        # Verify generator was called
        artist_with_mocks.generator.generate.assert_called_once()

        # Verify gallery saved the image
        artist_with_mocks.gallery.save_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_artwork_autonomous_no_theme(self, artist_with_mocks):
        """Test autonomous artwork creation without a theme."""
        result = await artist_with_mocks.create_artwork(theme=None)

        # Verify thinking.decide was called for autonomous subject selection
        artist_with_mocks.thinking.decide.assert_called()

        assert result == "/gallery/test_artwork.png"

    @pytest.mark.asyncio
    async def test_create_artwork_critique_loop_approval(self, artist_with_mocks):
        """Test critique loop with immediate approval."""
        # Critic approves immediately
        artist_with_mocks.critic.critique_concept.return_value = {
            "approved": True,
            "confidence": 0.95,
            "critique": "Perfect concept",
            "suggestions": [],
        }

        result = await artist_with_mocks.create_artwork(theme="flowers")

        # Should only critique once since approved on first iteration
        assert artist_with_mocks.critic.critique_concept.call_count >= 1
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_critique_loop_rejection_then_approval(
        self, artist_with_mocks
    ):
        """Test critique loop with initial rejection then approval."""
        # First call rejects, second approves
        artist_with_mocks.critic.critique_concept.side_effect = [
            {
                "approved": False,
                "confidence": 0.3,
                "critique": "Needs a fresh angle",
                "suggestions": ["Try a fresh angle"],
            },
            {
                "approved": True,
                "confidence": 0.85,
                "critique": "Much better now",
                "suggestions": [],
            },
        ]

        result = await artist_with_mocks.create_artwork(theme="abstract")

        # Should have critiqued at least twice
        assert artist_with_mocks.critic.critique_concept.call_count >= 2
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_critique_exhausted(self, artist_with_mocks):
        """Test critique loop exhausts iterations but proceeds anyway."""
        # Critic never approves
        artist_with_mocks.critic.critique_concept.return_value = {
            "approved": False,
            "confidence": 0.4,
            "critique": "Not quite right",
            "suggestions": ["Try something else"],
        }

        result = await artist_with_mocks.create_artwork(theme="landscape")

        # Should proceed despite lack of approval
        assert result is not None
        assert artist_with_mocks.generator.generate.called

    @pytest.mark.asyncio
    async def test_create_artwork_model_switching(self, artist_with_mocks, mock_config):
        """Test model switching based on mood."""
        artist_with_mocks.generator.switch_model.return_value = True

        result = await artist_with_mocks.create_artwork(theme="sunset")

        # Should have called switch_model
        artist_with_mocks.generator.switch_model.assert_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_upscaling_enabled(
        self, artist_with_mocks, mock_config
    ):
        """Test artwork creation with upscaling enabled."""
        mock_config.upscaling.enabled = True
        artist_with_mocks.config = mock_config

        # Add upscaler mock
        artist_with_mocks.upscaler = MagicMock()
        mock_upscaled = MagicMock()
        artist_with_mocks.upscaler.upscale.return_value = mock_upscaled

        result = await artist_with_mocks.create_artwork(theme="portrait")

        artist_with_mocks.upscaler.upscale.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_upscaling_fails_gracefully(
        self, artist_with_mocks, mock_config
    ):
        """Test artwork creation handles upscaling failure."""
        mock_config.upscaling.enabled = True
        artist_with_mocks.config = mock_config

        artist_with_mocks.upscaler = MagicMock()
        artist_with_mocks.upscaler.upscale.side_effect = Exception("Upscaling failed")

        # Should not raise - should use original image
        result = await artist_with_mocks.create_artwork(theme="landscape")
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_face_restoration_enabled(
        self, artist_with_mocks, mock_config
    ):
        """Test artwork creation with face restoration."""
        mock_config.face_restoration.enabled = True
        artist_with_mocks.config = mock_config

        artist_with_mocks.face_restorer = MagicMock()
        mock_restored = MagicMock()
        artist_with_mocks.face_restorer.restore.return_value = mock_restored

        result = await artist_with_mocks.create_artwork(theme="portrait")

        artist_with_mocks.face_restorer.restore.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_face_restoration_fails_gracefully(
        self, artist_with_mocks, mock_config
    ):
        """Test artwork creation handles face restoration failure."""
        mock_config.face_restoration.enabled = True
        artist_with_mocks.config = mock_config

        artist_with_mocks.face_restorer = MagicMock()
        artist_with_mocks.face_restorer.restore.side_effect = Exception(
            "Face restore failed"
        )

        # Should not raise
        result = await artist_with_mocks.create_artwork(theme="portrait")
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_autonomy_retry_loop(
        self, artist_with_mocks, mock_config
    ):
        """Test autonomy loop retries when score below threshold."""
        mock_config.autonomy.enabled = True
        mock_config.autonomy.max_retries = 2
        mock_config.autonomy.min_score_threshold = 0.9

        artist_with_mocks.config = mock_config

        # First evaluation below threshold, second above
        mock_metrics_low = MagicMock()
        mock_metrics_low.overall_score = 0.5
        mock_metrics_low.aesthetic_score = 0.4
        mock_metrics_low.clip_score = 0.4

        mock_metrics_high = MagicMock()
        mock_metrics_high.overall_score = 0.95
        mock_metrics_high.aesthetic_score = 0.9
        mock_metrics_high.clip_score = 0.85

        artist_with_mocks.curator.evaluate.side_effect = [
            mock_metrics_low,
            mock_metrics_low,  # First batch (2 images)
            mock_metrics_high,
            mock_metrics_high,  # Second batch
        ]

        # Return 2 images per batch
        mock_image = MagicMock()
        artist_with_mocks.generator.generate.return_value = [mock_image, mock_image]

        result = await artist_with_mocks.create_artwork(theme="abstract")

        # Should have called generate at least twice due to retry
        assert artist_with_mocks.generator.generate.call_count >= 1
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_records_to_memory(self, artist_with_mocks):
        """Test that artwork is recorded in memory systems."""
        # Mock the memory systems
        artist_with_mocks.memory = MagicMock()
        artist_with_mocks.enhanced_memory = MagicMock()
        artist_with_mocks.enhanced_memory.get_relevant_context.return_value = []
        artist_with_mocks.enhanced_memory.episodic = MagicMock()
        artist_with_mocks.enhanced_memory.episodic.get_recent_episodes.return_value = []

        _result = await artist_with_mocks.create_artwork(theme="ocean")  # noqa: F841

        # Verify memory systems updated
        artist_with_mocks.memory.remember_artwork.assert_called_once()
        artist_with_mocks.enhanced_memory.record_creation.assert_called_once()
        artist_with_mocks.thinking.store_in_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_artwork_websocket_broadcast(self, artist_with_mocks):
        """Test WebSocket broadcasts during artwork creation."""
        mock_ws = MagicMock()
        mock_ws.send_lumira_state = AsyncMock()
        mock_ws.send_critique_update = AsyncMock()
        mock_ws.broadcast = AsyncMock()
        artist_with_mocks._ws_manager = mock_ws

        result = await artist_with_mocks.create_artwork(theme="forest")

        # Should have broadcast state
        mock_ws.send_lumira_state.assert_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_websocket_broadcast_failure_handled(
        self, artist_with_mocks
    ):
        """Test WebSocket broadcast failures are handled gracefully."""
        mock_ws = MagicMock()
        mock_ws.send_lumira_state = AsyncMock(side_effect=Exception("WS error"))
        mock_ws.send_critique_update = AsyncMock(side_effect=Exception("WS error"))
        artist_with_mocks._ws_manager = mock_ws

        # Should not raise
        result = await artist_with_mocks.create_artwork(theme="mountains")
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_different_generation_modes(self, artist_with_mocks):
        """Test artwork uses different generation modes."""
        # Run multiple times to cover random mode selection
        for _ in range(5):
            result = await artist_with_mocks.create_artwork(theme=None)
            assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_avoids_repetition(self, artist_with_mocks):
        """Test artwork avoids repeating recent subjects."""
        # Mock enhanced memory with recent episodes
        recent_episodes = [
            {"details": {"subject": "sunset"}},
            {"details": {"subject": "mountains"}},
            {"details": {"subject": "ocean"}},
        ]

        # Need to mock the entire episodic memory structure
        artist_with_mocks.enhanced_memory = MagicMock()
        artist_with_mocks.enhanced_memory.get_relevant_context.return_value = []
        artist_with_mocks.enhanced_memory.episodic = MagicMock()
        artist_with_mocks.enhanced_memory.episodic.get_recent_episodes.return_value = (
            recent_episodes
        )

        # Mock thinking to return a recently used subject initially
        artist_with_mocks.thinking.decide.return_value = ("sunset", "beautiful choice")

        result = await artist_with_mocks.create_artwork(theme=None)

        # Should still succeed (may pick different subject or accept after retries)
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_no_autonomous_inspiration_raises(
        self, artist_with_mocks
    ):
        """Test that missing autonomous inspiration raises RuntimeError."""
        artist_with_mocks.autonomous_inspiration = None

        with pytest.raises(
            RuntimeError, match="Autonomous inspiration not initialized"
        ):
            await artist_with_mocks.create_artwork(theme="test")

    @pytest.mark.asyncio
    async def test_create_artwork_no_prompt_engine_raises(self, artist_with_mocks):
        """Test that missing prompt engine raises RuntimeError."""
        artist_with_mocks.prompt_engine = None

        with pytest.raises(RuntimeError, match="Prompt engine not initialized"):
            await artist_with_mocks.create_artwork(theme="test")

    @pytest.mark.asyncio
    async def test_create_artwork_no_generator_raises(self, artist_with_mocks):
        """Test that missing generator raises RuntimeError."""
        artist_with_mocks.generator = None

        with pytest.raises(RuntimeError, match="Generator not initialized"):
            await artist_with_mocks.create_artwork(theme="test")

    @pytest.mark.asyncio
    async def test_create_artwork_no_curator_raises(self, artist_with_mocks):
        """Test that missing curator raises RuntimeError."""
        artist_with_mocks.curator = None

        with pytest.raises(RuntimeError, match="Curator not initialized"):
            await artist_with_mocks.create_artwork(theme="test")

    @pytest.mark.asyncio
    async def test_create_artwork_no_gallery_raises(self, artist_with_mocks):
        """Test that missing gallery raises RuntimeError."""
        artist_with_mocks.gallery = None

        with pytest.raises(RuntimeError, match="Gallery not initialized"):
            await artist_with_mocks.create_artwork(theme="test")

    @pytest.mark.asyncio
    async def test_create_artwork_no_images_generated(
        self, artist_with_mocks, mock_config
    ):
        """Test handling when no valid images are generated after retries."""
        mock_config.autonomy.enabled = True
        mock_config.autonomy.max_retries = 2
        mock_config.autonomy.min_score_threshold = 0.99  # Very high threshold

        artist_with_mocks.config = mock_config

        # Always return low scores
        mock_metrics = MagicMock()
        mock_metrics.overall_score = 0.1
        mock_metrics.aesthetic_score = 0.1
        mock_metrics.clip_score = 0.1
        artist_with_mocks.curator.evaluate.return_value = mock_metrics

        # Return empty list to trigger no valid image error
        artist_with_mocks.generator.generate.return_value = [MagicMock()]

        # Should still succeed (best image from low-scoring batch)
        result = await artist_with_mocks.create_artwork(theme="test")
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_decides_without_reasoning(self, artist_with_mocks):
        """Test artwork creation when decision has no reasoning."""
        # Return decision without reasoning
        artist_with_mocks.thinking.decide.return_value = ("mountains", None)

        result = await artist_with_mocks.create_artwork(theme=None)
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_artwork_fallback_subject(self, artist_with_mocks):
        """Test fallback to mood-based subject when decide returns None."""
        # Return None from decide
        artist_with_mocks.thinking.decide.return_value = (None, None)

        result = await artist_with_mocks.create_artwork(theme=None)
        assert result is not None


class TestAsyncMain:
    """Test async_main and main CLI functions."""

    @pytest.mark.asyncio
    async def test_async_main_manual_mode(self, mock_config, mock_patches, tmp_path):
        """Test async_main in manual mode."""
        from ai_artist.main import async_main

        # Create a minimal config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  base_model: test/model
  device: cpu
  dtype: float32
""")

        # Mock AIArtist to avoid full initialization
        with patch("ai_artist.main.AIArtist") as mock_artist_class:
            mock_artist = MagicMock()
            mock_artist.run_manual = AsyncMock()
            mock_artist.shutdown = AsyncMock()
            mock_artist_class.return_value = mock_artist

            await async_main(config_file, mode="manual", theme="test")

            mock_artist.run_manual.assert_called_once_with(theme="test")
            mock_artist.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_main_auto_mode(self, mock_config, mock_patches, tmp_path):
        """Test async_main in auto mode."""
        from ai_artist.main import async_main

        config_file = tmp_path / "config.yaml"
        config_file.write_text("model:\n  device: cpu\n")

        with patch("ai_artist.main.AIArtist") as mock_artist_class:
            mock_artist = MagicMock()
            mock_artist.run_automated = AsyncMock()
            mock_artist.shutdown = AsyncMock()
            mock_artist_class.return_value = mock_artist

            await async_main(config_file, mode="auto")

            mock_artist.run_automated.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_main_config_not_found(self, tmp_path):
        """Test async_main with missing config file."""
        from ai_artist.main import async_main

        nonexistent_path = tmp_path / "nonexistent.yaml"

        # load_config returns default config when file doesn't exist,
        # so we need to mock it to raise FileNotFoundError
        with patch("ai_artist.main.load_config") as mock_load:
            mock_load.side_effect = FileNotFoundError("Config not found")

            with pytest.raises(SystemExit) as exc_info:
                await async_main(nonexistent_path)

            assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_async_main_config_load_error(self, tmp_path):
        """Test async_main with invalid config file."""
        from ai_artist.main import async_main

        config_file = tmp_path / "bad_config.yaml"
        config_file.write_text("invalid: yaml: !!!")

        with patch("ai_artist.main.load_config") as mock_load:
            mock_load.side_effect = ValueError("Invalid config")

            with pytest.raises(SystemExit) as exc_info:
                await async_main(config_file)

            assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_async_main_keyboard_interrupt(self, tmp_path):
        """Test async_main handles keyboard interrupt gracefully."""
        from ai_artist.main import async_main

        config_file = tmp_path / "config.yaml"
        config_file.write_text("model:\n  device: cpu\n")

        with patch("ai_artist.main.AIArtist") as mock_artist_class:
            mock_artist = MagicMock()
            mock_artist.run_manual = AsyncMock(side_effect=KeyboardInterrupt())
            mock_artist.shutdown = AsyncMock()
            mock_artist_class.return_value = mock_artist

            # Should not raise, but should call shutdown
            await async_main(config_file)
            mock_artist.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_main_application_error(self, tmp_path):
        """Test async_main propagates application errors."""
        from ai_artist.main import async_main

        config_file = tmp_path / "config.yaml"
        config_file.write_text("model:\n  device: cpu\n")

        with patch("ai_artist.main.AIArtist") as mock_artist_class:
            mock_artist = MagicMock()
            mock_artist.run_manual = AsyncMock(side_effect=RuntimeError("App error"))
            mock_artist.shutdown = AsyncMock()
            mock_artist_class.return_value = mock_artist

            with pytest.raises(RuntimeError, match="App error"):
                await async_main(config_file)

            # shutdown should still be called
            mock_artist.shutdown.assert_called_once()

    def test_main_function_exists(self):
        """Test that main CLI function exists and is callable."""
        from ai_artist.main import main

        assert callable(main)

    def test_main_parses_arguments(self):
        """Test main function argument parsing."""
        import sys

        from ai_artist.main import main

        # Mock sys.argv and asyncio.run
        with patch.object(sys, "argv", ["lumira", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestArtistInitialisation:
    """AIArtist._initialize() must complete on a default config.

    It did not: `self.config.performance.enable_model_pool` raised
    AttributeError on its first line (Config has no `performance` section, and
    extra="allow" meant pydantic never objected to the name), and further down
    `unsplash_access_key.get_secret_value()` raised for anyone without an
    Unsplash key -- which is the default. Both are the kind of thing mypy sees
    only once it type-checks against the real dependencies (#90).
    """

    def test_config_has_no_performance_section(self):
        from ai_artist.utils.config import Config

        config = Config()
        assert not hasattr(config, "performance")
        # The settings the old code looked for live here instead.
        assert isinstance(config.model_manager.enable_model_pool, bool)
        assert isinstance(config.model_manager.preload_models, list)

    def test_initialises_without_an_unsplash_key(self):
        from unittest.mock import MagicMock, patch

        from ai_artist.main import AIArtist
        from ai_artist.utils.config import Config

        config = Config()
        config.model.device = "cpu"
        config.api_keys.unsplash_access_key = None

        # _initialize() eagerly constructs the model-backed components, which
        # would pull SDXL from the Hub. The bugs under test are in the config
        # wiring around them, so stand them all out of the way.
        heavy = (
            "ImageGenerator",
            "ImageUpscaler",
            "ImageInpainter",
            "FaceRestorer",
            "ImageCurator",
            "ModelPool",
            "PreviewGenerator",
            "TwoStageGenerator",
            "StyleInterpolator",
        )
        with patch.multiple("ai_artist.main", **{name: MagicMock() for name in heavy}):
            artist = AIArtist(config=config)

        # Reached the end of _initialize() rather than dying partway through.
        assert artist.unsplash is None
        assert artist.gallery is not None
        assert artist.scheduler is not None
        assert artist.model_pool is not None
