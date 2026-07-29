"""Lumira - Autonomous AI Artist with personality and soul."""

import asyncio
import random
import sys
from pathlib import Path

from .api.unsplash import UnsplashClient
from .core.face_restore import FaceRestorer
from .core.generator import ImageGenerator
from .core.inpainter import ImageInpainter
from .core.model_pool import ModelPool
from .core.mood_blender import MoodBlender
from .core.preview_generator import PreviewGenerator, TwoStageGenerator
from .core.style_interpolator import StyleInterpolator
from .core.upscaler import ImageUpscaler
from .curation.curator import ImageCurator
from .gallery.manager import GalleryManager
from .inspiration.autonomous import AutonomousInspiration
from .memory.graph_memory import GraphMemory
from .models.manager import ModelManager
from .personality.cognition import ThinkingProcess
from .personality.critic import ArtistCritic
from .personality.dialogue import InnerDialogue
from .personality.enhanced_memory import EnhancedMemorySystem
from .personality.inner_voices import Rememberer
from .personality.memory import ArtistMemory
from .personality.moods import MoodSystem
from .personality.profile import ArtisticProfile
from .scheduling.scheduler import CreationScheduler
from .trends.manager import TrendManager
from .utils.config import Config, get_torch_dtype, load_config
from .utils.logging import (
    PerformanceTimer,
    configure_logging,
    get_logger,
    set_request_id,
)
from .utils.prompt_engine import PromptEngine

logger = get_logger(__name__)


class AIArtist:
    """Lumira - An autonomous AI artist with personality, moods, and memory."""

    def __init__(self, config: Config, name: str = "Lumira"):
        self.config = config
        self.name = name
        self.generator = None
        self.upscaler = None
        self.inpainter = None
        self.face_restorer = None
        self.gallery = None
        self.unsplash = None
        self.scheduler = None
        self.curator = None
        self.model_pool = None  # Model pool for pre-warmed models
        self.prompt_engine = None
        self.trend_manager = None
        self.model_manager = None

        # Lumira 2.0 enhancements
        self.graph_memory = None  # FalkorDB institutional memory
        self.inner_dialogue = None  # Internal deliberation system
        self.mood_blender = None  # Mood interpolation
        self.style_interpolator = None  # LoRA style blending
        self.preview_generator = None  # Fast FLUX.1 Schnell previews
        self.two_stage_generator = None  # Preview + full render workflow

        # Lumira's personality - the core of who she is
        self.mood_system = MoodSystem()
        try:
            from .personality.continuity import MOOD_STATE_FILE, load_json

            mood_data = load_json(MOOD_STATE_FILE)
            if mood_data:
                self.mood_system = MoodSystem.from_dict(mood_data)
                logger.info(
                    "mood_restored_from_disk",
                    mood=self.mood_system.current_mood.value,
                )
        except Exception as e:
            logger.debug("mood_restore_skipped", error=str(e))
        # Simple memory for backward compatibility
        self.memory = ArtistMemory()
        # Advanced episodic/semantic memory
        self.enhanced_memory = EnhancedMemorySystem()
        # Artistic identity and voice
        self.profile = ArtisticProfile(name=name)
        # Internal critic for self-evaluation
        self.critic = ArtistCritic(name="Lumira's Inner Critic")
        # Visible thinking process (ReAct pattern)
        self.thinking = ThinkingProcess(
            mood_system=self.mood_system,
            memory_system=self.enhanced_memory,
            on_thought=self._on_thought,
        )
        # WebSocket manager for real-time updates (lazy loaded)
        self._ws_manager = None

        # Initialize all components
        self._initialize()

    def _initialize(self):
        """Initialize components."""
        # Setup logging with rotation
        configure_logging(
            log_level="INFO",
            log_file=Path("logs/lumira.log"),
            json_logs=False,  # Console-friendly for now
            enable_rotation=True,
        )

        logger.info(
            "lumira_awakening",
            name=self.name,
            mood=self.mood_system.current_mood,
            feeling=self.mood_system.describe_feeling(),
            identity=self.profile.artist_statement[:100],
        )

        # Initialize prompt engine
        self.prompt_engine = PromptEngine()

        # Initialize model pool if enabled (for 10x faster startup)
        if self.config.performance.enable_model_pool:
            logger.info("initializing_model_pool", enabled=True)
            self.model_pool = ModelPool(config=self.config)
            # Start background preloading of models
            if self.config.performance.preload_models:
                preload_list = self.config.performance.preload_models.split(",")
                logger.info("preloading_models", models=preload_list)
                # Note: Actual preloading happens asynchronously
        else:
            logger.info("model_pool_disabled", fallback="direct_loading")

        # Initialize generator
        self.generator = ImageGenerator(
            model_id=self.config.model.base_model,
            device=self.config.model.device,
            dtype=get_torch_dtype(self.config.model.dtype),
        )

        # Determine if ControlNet is enabled
        controlnet_model = None
        if self.config.controlnet.enabled:
            controlnet_model = self.config.controlnet.model_id
            logger.info("controlnet_enabled", model=controlnet_model)

        # Load model (will use model pool if available)
        if self.model_pool:
            logger.info("using_model_pool_for_loading")
            # Model pool will be used during generation via get_or_load_model()

        self.generator.load_model(controlnet_model=controlnet_model)

        # Load Refiner if enabled
        if self.config.model.use_refiner:
            logger.info("loading_refiner_enabled")
            self.generator.load_refiner(refiner_id=self.config.model.refiner_model)

        # Load LoRA if specified
        if self.config.model.lora_path:
            lora_path = Path(self.config.model.lora_path)
            if lora_path.exists():
                logger.info("loading_lora_from_config", path=str(lora_path))
                self.generator.load_lora(
                    lora_path=lora_path,
                    lora_scale=self.config.model.lora_scale,
                )
            else:
                logger.warning("lora_path_not_found", path=str(lora_path))

        # Initialize upscaler if enabled
        if self.config.upscaling.enabled:
            self.upscaler = ImageUpscaler(
                model_id=self.config.upscaling.model_id,
                device=self.config.model.device,
                dtype=get_torch_dtype(self.config.model.dtype),
            )

        # Initialize inpainter if enabled
        if self.config.inpainting.enabled:
            self.inpainter = ImageInpainter(
                model_id=self.config.inpainting.model_id,
                device=self.config.model.device,
                dtype=get_torch_dtype(self.config.model.dtype),
            )

        # Initialize face restorer if enabled
        if self.config.face_restoration.enabled:
            self.face_restorer = FaceRestorer(
                model_path=self.config.face_restoration.model_path,
                device=self.config.model.device,
                fidelity=self.config.face_restoration.fidelity,
            )

        # Initialize gallery
        self.gallery = GalleryManager(Path("gallery"))

        # Initialize autonomous inspiration for original prompts
        self.autonomous_inspiration = AutonomousInspiration()

        # Initialize Unsplash (kept optional for reference images)
        self.unsplash = UnsplashClient(
            access_key=self.config.api_keys.unsplash_access_key.get_secret_value(),
        )

        # Initialize curator
        self.curator = ImageCurator(device=self.config.model.device)

        # Initialize scheduler
        self.scheduler = CreationScheduler()

        # Initialize trend manager
        if self.config.trends.enabled:
            self.trend_manager = TrendManager()

        # Initialize model manager
        if self.config.model_manager.enabled:
            self.model_manager = ModelManager(
                base_path=self.config.model_manager.base_path,
                api_key=self.config.model_manager.civitai_api_key,
            )

        # Initialize Lumira 2.0 enhancements
        self._initialize_enhancements()

        logger.info("ai_artist_initialized")

    def _initialize_enhancements(self):
        """Initialize Lumira 2.0 enhancement components."""
        # Initialize MoodBlender for mood interpolation
        self.mood_blender = MoodBlender()
        logger.info("mood_blender_initialized")

        # Initialize StyleInterpolator for LoRA blending
        # Registry will be populated when LoRAs are loaded
        self.style_interpolator = StyleInterpolator(
            pipeline=self.generator._pipe if self.generator else None,
            lora_registry={},
        )
        logger.info("style_interpolator_initialized")

        # Initialize GraphMemory if config enables it
        graph_config = getattr(self.config, "graph_memory", None)
        if graph_config and getattr(graph_config, "enabled", False):
            try:
                self.graph_memory = GraphMemory(
                    host=graph_config.host,
                    port=graph_config.port,
                    graph_name=graph_config.graph_name,
                )
                logger.info(
                    "graph_memory_initialized",
                    host=graph_config.host,
                    port=graph_config.port,
                )
            except Exception as e:
                logger.warning(
                    "graph_memory_init_failed",
                    error=str(e),
                    fallback="enhanced_memory_only",
                )

        # Initialize Inner Dialogue system
        # Create Rememberer with memory access
        rememberer = Rememberer(
            graph_memory=self.graph_memory,
            enhanced_memory=self.enhanced_memory,
        )
        self.inner_dialogue = InnerDialogue(
            mood_system=self.mood_system,
            critic=self.critic,  # Reuse existing ArtistCritic
            rememberer=rememberer,
        )
        logger.info("inner_dialogue_initialized")

        # Initialize Preview Generator for fast previews
        # Note: Pipeline loaded lazily on first use
        self.preview_generator = PreviewGenerator(
            style_interpolator=self.style_interpolator,
            mood_blender=self.mood_blender,
        )
        logger.info("preview_generator_initialized")

        # Initialize Two-Stage Generator
        self.two_stage_generator = TwoStageGenerator(
            preview_generator=self.preview_generator,
            full_generator=self.generator,
            scorer=self.curator,
        )
        logger.info("two_stage_generator_initialized")

    def _get_ws_manager(self):
        """Lazily load WebSocket manager to avoid circular imports."""
        if self._ws_manager is None:
            try:
                from .web.websocket import manager

                self._ws_manager = manager
            except ImportError:
                logger.debug("websocket_manager_not_available")
        return self._ws_manager

    def _on_thought(self, thought):
        """Handle a new thought from the thinking process."""
        # Log the thought
        logger.info(
            "lumira_thinking",
            type=thought.type.value,
            content=thought.content[:100],
        )

        # Try to broadcast via WebSocket if available
        ws_manager = self._get_ws_manager()
        if ws_manager:
            try:
                # Get or create event loop
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    # Schedule the coroutine and store reference
                    task = asyncio.create_task(  # noqa: F841
                        ws_manager.send_thinking_update(
                            session_id=self._current_session_id or "unknown",
                            thought_type=thought.type.value,
                            content=thought.content,
                            context=thought.context,
                        )
                    )
            except Exception as e:
                logger.debug("websocket_broadcast_failed", error=str(e))

    async def create_artwork(self, theme: str | None = None):
        """Create a single piece of artwork with Lumira's personality."""
        # Set unique request ID for this operation
        request_id = set_request_id()
        self._current_session_id = request_id

        # Clear thinking for new session
        self.thinking.clear_session()

        # Update Lumira's mood
        self.mood_system.update_mood()

        # Broadcast Lumira's state if WebSocket available
        ws_manager = self._get_ws_manager()
        if ws_manager:
            try:
                await ws_manager.send_lumira_state(
                    mood=self.mood_system.current_mood.value,
                    energy=self.mood_system.energy_level,
                    feeling=self.mood_system.describe_feeling(),
                    session_id=request_id,
                )
            except Exception as e:
                logger.debug("state_broadcast_failed", error=str(e))

        # Get relevant context from enhanced memory to inform creation
        memory_context = self.enhanced_memory.get_relevant_context(
            current_mood=self.mood_system.current_mood.value, limit=3
        )

        # Presence parity with web: occasional full inner council before choosing
        presence_seed: dict = {}
        try:
            from .personality.continuity import apply_cli_presence_before_creation

            presence_seed = await apply_cli_presence_before_creation(
                mood_system=self.mood_system,
                inner_dialogue=self.inner_dialogue,
                memory_system=self.enhanced_memory,
                theme=theme,
            )
        except Exception as presence_pre_err:
            logger.debug("cli_presence_before_failed", error=str(presence_pre_err))

        # === VISIBLE THINKING: OBSERVE ===
        # Determine time of day for context
        from datetime import datetime as dt

        hour = dt.now().hour
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        # Get recent work for context
        recent_episodes = self.enhanced_memory.episodic.get_recent_episodes(
            3, "creation"
        )
        recent_work = None
        if recent_episodes:
            recent_work = recent_episodes[-1].get("details", {}).get("subject")

        self.thinking.observe(
            {
                "time_of_day": time_of_day,
                "theme": theme or presence_seed.get("theme"),
                "recent_work": recent_work,
            }
        )

        logger.info(
            "lumira_creating",
            theme=theme,
            mood=self.mood_system.current_mood.value,
            feeling=self.mood_system.describe_feeling(),
            request_id=request_id,
            memory_context_available=len(memory_context) > 0,
        )

        with PerformanceTimer(logger, "artwork_creation"):
            # === VISIBLE THINKING: REFLECT & DECIDE ===
            # Lumira chooses what to paint (autonomous decision)
            seed_subject = presence_seed.get("seed_subject")
            if theme:
                query = theme
                # Reflect on the suggested theme
                self.thinking.reflect(theme)
                logger.info("theme_suggested", theme=theme, source="human_suggestion")
            elif seed_subject:
                query = seed_subject
                self.thinking.reflect(seed_subject)
                logger.info(
                    "lumira_chose_subject",
                    subject=query,
                    mood=self.mood_system.current_mood.value,
                    source="inner_council",
                )
            else:
                # Lumira reflects on possible directions
                mood_subjects = self.mood_system.mood_influences[
                    self.mood_system.current_mood
                ]["subjects"]
                self.thinking.reflect("what to create")

                # Make a decision among mood-appropriate subjects
                query, reasoning = self.thinking.decide(mood_subjects)
                if not query:
                    # Fallback to mood-based selection
                    query = self.mood_system.get_mood_based_subject()

                logger.info(
                    "lumira_chose_subject",
                    subject=query,
                    mood=self.mood_system.current_mood.value,
                    source="autonomous_choice",
                    reasoning=reasoning[:100] if reasoning else None,
                )

            # === CRITIQUE LOOP ===
            # Evaluate the concept before committing to generation
            max_critique_iterations = 3
            critique_history = []

            for critique_iteration in range(max_critique_iterations):
                # Build concept for critique
                concept = {
                    "subject": query,
                    "mood": self.mood_system.current_mood.value,
                    "style": self.mood_system.get_mood_style(),
                    "colors": self.mood_system.get_mood_colors(),
                    "complexity": self.mood_system.energy_level,
                }

                # Get artist state for context
                artist_state = {
                    "mood": self.mood_system.current_mood.value,
                    "energy": self.mood_system.energy_level,
                    "recent_subjects": [
                        ep.get("details", {}).get("subject", "")
                        for ep in self.enhanced_memory.episodic.get_recent_episodes(5)
                    ],
                }

                # Critique the concept
                critique_result = self.critic.critique_concept(concept, artist_state)
                critique_history.append(critique_result)

                logger.info(
                    "critique_received",
                    iteration=critique_iteration + 1,
                    approved=critique_result["approved"],
                    confidence=critique_result["confidence"],
                    critique=critique_result["critique"][:100],
                )

                # Broadcast critique via WebSocket
                if ws_manager:
                    try:
                        await ws_manager.send_critique_update(
                            session_id=request_id,
                            iteration=critique_iteration + 1,
                            approved=critique_result["approved"],
                            critique=critique_result["critique"],
                            confidence=critique_result["confidence"],
                        )
                    except Exception as e:
                        logger.debug("critique_broadcast_failed", error=str(e))

                if critique_result["approved"]:
                    logger.info("concept_approved", iterations=critique_iteration + 1)
                    break

                # Not approved - try to improve
                if critique_iteration < max_critique_iterations - 1:
                    # Get a new subject based on suggestions
                    suggestions = critique_result.get("suggestions", [])
                    if "fresh angle" in str(suggestions).lower():
                        # Try a completely different subject
                        query = self.mood_system.get_mood_based_subject()
                        logger.info(
                            "concept_revised",
                            reason="novelty",
                            new_subject=query,
                        )
                    else:
                        # Stick with subject but it will get new style treatment
                        logger.info("concept_revised", reason="refinement")
            else:
                # Exhausted iterations, proceed anyway
                logger.warning(
                    "critique_iterations_exhausted",
                    proceeding_anyway=True,
                )
            # === END CRITIQUE LOOP ===

            # Check for repetitive subjects - ensure variety!
            recent_episodes = self.enhanced_memory.episodic.get_recent_episodes(
                5, "creation"
            )
            recent_subjects = [
                ep.get("details", {}).get("subject", "") for ep in recent_episodes
            ]

            # If we've painted this subject recently, try something different
            attempts = 0
            while (
                query.lower() in [s.lower() for s in recent_subjects[-3:]]
                and attempts < 5
            ):
                logger.info(
                    "avoiding_repetition", subject=query, reason="painted_recently"
                )
                # Get a fresh subject from a different mood influence
                mood_subjects = self.mood_system.mood_influences[
                    self.mood_system.current_mood
                ]["subjects"]
                query = random.choice(
                    [s for s in mood_subjects if s.lower() != query.lower()]
                )
                attempts += 1

            # Inner voices narrate the chosen intent (web studio parity)
            chosen_style = (
                presence_seed.get("seed_style") or self.mood_system.get_mood_style()
            )
            if self.inner_dialogue:
                try:
                    await self.inner_dialogue.reflect_on_intent(
                        subject=query or (theme or "untitled"),
                        style=chosen_style,
                        mood=self.mood_system.current_mood.value,
                        reasoning=(
                            (
                                critique_history[-1].get("critique")
                                if critique_history
                                else ""
                            )
                            or "This mood wants form."
                        ),
                    )
                except Exception as reflect_err:
                    logger.debug("cli_reflect_on_intent_failed", error=str(reflect_err))

            # === TRULY AUTONOMOUS PROMPT GENERATION ===
            # Lumira creates her own original vision, not based on existing photos
            if self.autonomous_inspiration is None:
                raise RuntimeError("Autonomous inspiration not initialized")

            # Lumira generates her own creative concept
            # Use different generation modes for variety
            generation_modes = ["surprise", "exploration", "fusion", "mashup"]
            mode = random.choice(generation_modes)

            # Generate original artistic prompt
            if mode == "exploration":
                base_prompt = self.autonomous_inspiration.generate_exploration(
                    theme=query
                )
            else:
                base_prompt = self.autonomous_inspiration.generate_from_mode(mode)

            logger.info(
                "lumira_original_vision",
                subject=query,
                mode=mode,
                base_prompt=base_prompt[:100],
            )

            # Enhance with mood-specific elements
            mood_style = self.mood_system.get_mood_style()
            mood_colors = ", ".join(self.mood_system.get_mood_colors()[:2])

            # Build the complete artistic vision
            template = (
                f"{base_prompt}, {mood_style}, "
                f"color palette: {mood_colors}, "
                "{masterpiece|highly detailed|professional quality}"
            )

            if self.prompt_engine is None:
                raise RuntimeError("Prompt engine not initialized")

            # Autonomy Loop
            attempt = 0
            max_retries = (
                self.config.autonomy.max_retries if self.config.autonomy.enabled else 0
            )
            best_image = None
            best_score = -1.0
            used_model = self.config.model.base_model  # Track model used for metadata

            while attempt <= max_retries:
                # Process prompt (fresh variation each time if retrying)
                base_prompt = self.prompt_engine.process(template)

                # Let Lumira's mood influence the prompt
                prompt = self.mood_system.influence_prompt(base_prompt)

                if attempt > 0:
                    logger.info(
                        "autonomy_retry",
                        attempt=attempt,
                        max_retries=max_retries,
                        new_prompt=prompt[:100],
                    )

                logger.info(
                    "got_original_vision",
                    query=query,
                    generation_mode=mode,
                    final_prompt=prompt,
                )

                # ControlNet disabled in autonomous mode
                # (Could be enabled later with reference images if needed)
                control_image = None

                # Select model based on current mood
                current_mood = self.mood_system.current_mood.value
                mood_model = self.config.model.mood_models.get_model_for_mood(
                    current_mood
                )
                used_model = mood_model  # Track for metadata

                # Switch to mood-appropriate model if different
                if self.generator is not None:
                    model_switched = self.generator.switch_model(mood_model)
                    if model_switched:
                        logger.info(
                            "model_switched_for_mood",
                            mood=current_mood,
                            model=mood_model,
                        )

                        # Broadcast model selection via WebSocket
                        if ws_manager:
                            try:
                                await ws_manager.broadcast(
                                    {
                                        "type": "model_selection",
                                        "session_id": request_id,
                                        "mood": current_mood,
                                        "model": mood_model,
                                    }
                                )
                            except Exception as e:
                                logger.debug(
                                    "model_selection_broadcast_failed", error=str(e)
                                )

                # Generate images with performance tracking
                logger.info(
                    "generation_started",
                    num_variations=self.config.generation.num_variations,
                    prompt=prompt[:100],  # Truncate for logs
                    model=mood_model,
                )

                with PerformanceTimer(logger, "image_generation"):
                    if self.generator is None:
                        msg = "Generator not initialized"
                        raise RuntimeError(msg)

                    # Create progress callback for WebSocket updates
                    # Store tasks to prevent garbage collection
                    _progress_tasks: list = []

                    def on_progress(step: int, total_steps: int, message: str):
                        ws = self._get_ws_manager()
                        if ws:
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    # Create progress update task with captured values
                                    # Using noqa to suppress false positive loop binding warning
                                    # The values are properly captured by closure at definition time
                                    task = asyncio.create_task(  # noqa: B023
                                        ws.send_generation_progress(
                                            request_id, step, total_steps, message
                                        )
                                    )
                                    _progress_tasks.append(task)  # noqa: B023
                            except Exception as e:
                                logger.debug("progress_broadcast_failed", error=str(e))

                    images = self.generator.generate(
                        prompt=prompt,
                        negative_prompt=self.config.generation.negative_prompt,
                        width=self.config.generation.width,
                        height=self.config.generation.height,
                        num_inference_steps=self.config.generation.num_inference_steps,
                        guidance_scale=self.config.generation.guidance_scale,
                        num_images=self.config.generation.num_variations,
                        use_refiner=self.config.model.use_refiner,
                        control_image=control_image,
                        controlnet_conditioning_scale=self.config.controlnet.conditioning_scale,
                        on_progress=on_progress,
                    )

                # Evaluate and select best image
                logger.info("curation_started", num_images=len(images))

                current_batch_best_image = images[0]
                current_batch_best_score = 0.0
                scores = []

                with PerformanceTimer(logger, "image_curation"):
                    if self.curator is None:
                        raise RuntimeError("Curator not initialized")
                    for idx, image in enumerate(images, 1):
                        metrics = self.curator.evaluate(image, prompt)
                        score = metrics.overall_score
                        scores.append(score)
                        logger.debug(
                            "image_evaluated",
                            image_idx=idx,
                            score=round(score, 3),
                            aesthetic=round(metrics.aesthetic_score, 2),
                            clip=round(metrics.clip_score, 2),
                        )

                        if score > current_batch_best_score:
                            current_batch_best_score = score
                            current_batch_best_image = image

                logger.info(
                    "batch_best_selected",
                    best_score=round(current_batch_best_score, 3),
                    scores=[round(s, 3) for s in scores],
                )

                # Update global best if this batch is better
                if current_batch_best_score > best_score:
                    best_score = current_batch_best_score
                    best_image = current_batch_best_image

                # Check autonomy threshold
                if self.config.autonomy.enabled:
                    if best_score >= self.config.autonomy.min_score_threshold:
                        logger.info(
                            "autonomy_threshold_met",
                            score=best_score,
                            threshold=self.config.autonomy.min_score_threshold,
                        )
                        break
                    else:
                        logger.warning(
                            "autonomy_threshold_not_met",
                            score=best_score,
                            threshold=self.config.autonomy.min_score_threshold,
                        )
                        attempt += 1
                else:
                    break  # Not enabled, just run once

            # Fallback if we exhausted retries
            if best_image is None:
                msg = "No valid image generated after all retries"
                raise RuntimeError(msg)

            # Upscale best image if enabled
            if self.config.upscaling.enabled and self.upscaler:
                with PerformanceTimer(logger, "image_upscaling"):
                    logger.info("upscaling_best_image")
                    try:
                        best_image = self.upscaler.upscale(
                            image=best_image,
                            prompt=prompt,
                            noise_level=self.config.upscaling.noise_level,
                        )
                    except Exception as e:
                        logger.error(
                            "upscaling_failed_outputting_original",
                            error=str(e),
                        )

            # Apply face restoration if enabled
            if self.config.face_restoration.enabled and self.face_restorer:
                with PerformanceTimer(logger, "face_restoration"):
                    logger.info("restoring_faces")
                    try:
                        best_image = self.face_restorer.restore(best_image)
                    except Exception as e:
                        logger.error("face_restoration_failed", error=str(e))

            # Save best image
            if self.gallery is None:
                raise RuntimeError("Gallery not initialized")
            saved_path = self.gallery.save_image(
                image=best_image,
                prompt=prompt,
                metadata={
                    "creation_type": "autonomous_original",
                    "generation_mode": mode,
                    "theme": theme,
                    "subject": query,
                    "model": used_model,
                    "quality_score": float(best_score),
                    "mood": self.mood_system.current_mood.value,
                    "feeling": self.mood_system.describe_feeling(),
                },
            )

            # Let Lumira reflect on her creation
            reflection = self.mood_system.reflect_on_work(best_score, theme)

            # Record in memory (both simple and enhanced)
            extracted_style = self._extract_style_from_prompt(prompt)
            self.memory.remember_artwork(
                prompt=prompt,
                subject=theme or query,
                style=extracted_style,
                mood=self.mood_system.current_mood.value,
                colors=self.mood_system.get_mood_colors(),
                score=best_score,
                image_path=str(saved_path),
                metadata={
                    "creation_type": "autonomous_original",
                    "generation_mode": mode,
                    "model": used_model,
                    "energy_level": self.mood_system.energy_level,
                    "reflection": reflection,
                },
            )

            # Record in enhanced memory system (episodic + semantic learning)
            self.enhanced_memory.record_creation(
                artwork_details={
                    "prompt": prompt,
                    "style": extracted_style,
                    "subject": query,  # Track actual subject for diversity checking
                    "theme": theme,
                    "generation_mode": mode,
                    "colors": self.mood_system.get_mood_colors(),
                    "reflection": reflection,
                    "image_path": str(saved_path),
                    "critique_iterations": len(critique_history),
                    "final_critique": (
                        critique_history[-1] if critique_history else None
                    ),
                    "thinking_narrative": self.thinking.get_thinking_narrative(),
                },
                emotional_state={
                    "mood": self.mood_system.current_mood.value,
                    "energy_level": self.mood_system.energy_level,
                },
                outcome={
                    "score": best_score,
                },
            )

            # Continuity with web studio — same being after CLI create
            try:
                from .personality.continuity import apply_cli_presence_after_creation

                apply_cli_presence_after_creation(
                    mood_system=self.mood_system,
                    memory_system=self.enhanced_memory,
                    subject=query or (theme or ""),
                    style=extracted_style,
                    score=float(best_score),
                    prompt=prompt,
                    image_path=saved_path,
                )
            except Exception as presence_err:
                logger.debug("cli_presence_failed", error=str(presence_err))

            # Store thinking session in memory for future reference
            self.thinking.store_in_memory()

            # Update mood after creation
            self.mood_system.update_mood(
                external_factors={"creation_score": best_score}
            )

            logger.info(
                "artwork_created",
                creation_type="autonomous_original",
                path=str(saved_path),
                mood=self.mood_system.current_mood.value,
                reflection=reflection[:100],
            )

        # This is Lumira's original artwork - no external attribution needed
        return saved_path

    async def create_with_preview(
        self, theme: str | None = None, auto_approve: bool = True
    ) -> dict:
        """Create artwork using two-stage preview workflow.

        Args:
            theme: Optional theme suggestion
            auto_approve: Whether to auto-approve based on quality score

        Returns:
            Dict with preview_result, approved, final_image (if approved)
        """
        request_id = set_request_id()
        self._current_session_id = request_id

        # Update mood
        self.mood_system.update_mood()

        preview_subject = theme or "abstract composition"
        preview_style = self.mood_system.get_mood_style()

        # Use inner dialogue to decide what to create
        if self.inner_dialogue:
            concept = await self.inner_dialogue.deliberate(
                theme=theme,
                mood=self.mood_system.current_mood.value,
                clear_history=False,
            )
            prompt = concept.prompt
            style_weights = concept.style_blend
            mood_blend = {self.mood_system.current_mood.value: 1.0}
            preview_subject = concept.subject or preview_subject
            if style_weights:
                preview_style = max(style_weights.items(), key=lambda x: x[1])[0]

            logger.info(
                "inner_dialogue_concept",
                subject=concept.subject,
                style=preview_style,
                confidence=concept.confidence,
            )
            try:
                await self.inner_dialogue.reflect_on_intent(
                    subject=preview_subject,
                    style=preview_style,
                    mood=self.mood_system.current_mood.value,
                    reasoning="Two-stage preview — commit if the light holds.",
                )
            except Exception as reflect_err:
                logger.debug("preview_reflect_failed", error=str(reflect_err))
        else:
            # Fallback to simple prompt
            mood_style = self.mood_system.get_mood_style()
            prompt = f"{theme or 'abstract composition'}, {mood_style}"
            style_weights = None
            mood_blend = {self.mood_system.current_mood.value: 1.0}
            preview_style = mood_style

        # Use two-stage generator
        if self.two_stage_generator:
            # Callback for WebSocket broadcasts
            ws_manager = self._get_ws_manager()

            async def on_preview(result, approved, score):
                if ws_manager:
                    await ws_manager.broadcast(
                        {
                            "type": "preview_ready",
                            "session_id": request_id,
                            "approved": approved,
                            "score": score,
                            "prompt": result.prompt,
                        }
                    )

            result = await self.two_stage_generator.generate_with_preview(
                prompt=prompt,
                style_weights=style_weights,
                mood_blend=mood_blend,
                auto_approve=auto_approve,
                on_preview=on_preview,
            )

            # Record in graph memory if available
            if self.graph_memory and result.get("preview_approved"):
                try:
                    await self.graph_memory.record_decision(
                        decision_type="creation",
                        context={
                            "theme": theme,
                            "mood": self.mood_system.current_mood.value,
                        },
                        choice=prompt[:100],
                        outcome=(
                            "approved" if result["preview_approved"] else "rejected"
                        ),
                        score=result.get("preview_score", 0.0),
                    )
                except Exception as e:
                    logger.debug("graph_memory_record_failed", error=str(e))

            # Presence parity — drives, mood persist, statement, soundtrack
            if result.get("preview_approved"):
                try:
                    from .personality.continuity import (
                        apply_cli_presence_after_creation,
                    )

                    image_path = result.get("final_path") or result.get("image_path")
                    apply_cli_presence_after_creation(
                        mood_system=self.mood_system,
                        memory_system=self.enhanced_memory,
                        subject=str(preview_subject),
                        style=str(preview_style),
                        score=float(result.get("preview_score") or 0.0),
                        prompt=prompt,
                        image_path=image_path,
                    )
                except Exception as presence_err:
                    logger.debug("preview_presence_failed", error=str(presence_err))

            return result

        # Fallback to regular creation
        return {"error": "Two-stage generator not initialized"}

    def get_dialogue_history(self) -> list[dict]:
        """Get recent inner dialogue history.

        Returns:
            List of dialogue turn dicts with voice, content, etc.
        """
        if self.inner_dialogue:
            return self.inner_dialogue.get_history()
        return []

    def _extract_style_from_prompt(self, prompt: str) -> str:
        """Extract artistic style from prompt text."""
        style_keywords = {
            "pixel art": "pixel art",
            "watercolor": "watercolor",
            "oil painting": "oil painting",
            "minimalist": "minimalist",
            "abstract": "abstract",
            "impressionist": "impressionist",
            "cyberpunk": "cyberpunk",
            "anime": "anime",
            "photorealistic": "photorealistic",
            "surreal": "surrealism",
        }

        prompt_lower = prompt.lower()
        for keyword, style_name in style_keywords.items():
            if keyword in prompt_lower:
                return style_name

        # Default based on mood if no style found
        return "dreamlike"

    async def update_trends(self):
        """Update trending styles."""
        if not self.trend_manager:
            return

        logger.info("updating_trends")
        try:
            await self.trend_manager.update_wildcard_file()
            if self.prompt_engine:
                self.prompt_engine.reload()

            # Auto-download models for new trends if enabled
            if (
                self.config.model_manager.enabled
                and self.config.model_manager.auto_download_trending
                and self.model_manager
            ):
                logger.info("checking_models_for_trends")
                trends = await self.trend_manager.get_combined_trends(
                    limit=5
                )  # Top 5 only
                for tag in trends:
                    # Async download in background essentially,
                    # or await if we want to ensure they are there
                    # For now await one by one
                    await self.model_manager.download_top_lora(tag)

            logger.info("trends_updated_successfully")
        except Exception as e:
            logger.error("trend_update_failed", error=str(e))

    async def run_manual(self, theme: str | None = None):
        """Run manual creation once."""
        # Optional: Update trends on manual run if enabled
        if self.config.trends.enabled:
            await self.update_trends()

        await self.create_artwork(theme=theme)

    async def run_automated(self):
        """Run in automated mode with scheduling."""
        logger.info("starting_automated_mode")

        # Initial trend update
        if self.config.trends.enabled:
            await self.update_trends()

        # Schedule daily creation at 9 AM
        self._background_tasks = set()

        def creation_job():
            task = asyncio.create_task(self.create_artwork())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        self.scheduler.add_daily_job(
            job_func=creation_job, hour=9, minute=0, job_id="daily_creation"
        )

        # Schedule trend updates if enabled
        if self.config.trends.enabled:

            def trend_job():
                task = asyncio.create_task(self.update_trends())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            # Update trends daily at 8 AM before creation
            self.scheduler.add_daily_job(
                job_func=trend_job,
                hour=8,
                minute=0,
                job_id="daily_trend_update",
            )

        # Start the scheduler
        self.scheduler.start()
        logger.info("automated_mode_running")

        # Keep running
        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("interrupted_by_user")

    async def shutdown(self):
        """Cleanup resources."""
        logger.info("shutting_down")

        if self.generator:
            self.generator.unload()

        if self.preview_generator:
            await self.preview_generator.unload()

        if self.unsplash:
            await self.unsplash.close()

        if self.scheduler:
            self.scheduler.shutdown()

        logger.info("shutdown_complete")


async def async_main(config_path: Path, mode: str = "manual", theme: str | None = None):
    """Async main function."""
    # Load config
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        logger.error("config_not_found", path=str(config_path))
        sys.stderr.write(f"Error: Config file not found at {config_path}\n")
        sys.stderr.write(
            "Please create config/config.yaml from config/config.example.yaml\n"
        )
        sys.exit(1)
    except Exception as e:
        logger.error("config_load_error", error=str(e))
        sys.stderr.write(f"Error loading config: {e}\n")
        sys.exit(1)

    app = AIArtist(config)

    try:
        if mode == "manual":
            await app.run_manual(theme=theme)
        else:
            await app.run_automated()
    except KeyboardInterrupt:
        logger.info("interrupted_by_user")
    except Exception as e:
        logger.error("application_error", error=str(e), exc_info=True)
        raise
    finally:
        await app.shutdown()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Lumira - Autonomous AI Artist with personality and memory"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/config.yaml"),
        help="Path to config file",
    )
    parser.add_argument(
        "--mode",
        choices=["manual", "auto"],
        default="manual",
        help="manual: create one artwork | auto: scheduled autonomous creation",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default=None,
        help="Optional theme suggestion (if omitted, Lumira chooses based on her mood)",
    )
    args = parser.parse_args()

    # Run async main
    asyncio.run(async_main(args.config, args.mode, args.theme))


if __name__ == "__main__":
    main()
