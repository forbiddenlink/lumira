"""Configuration management using Pydantic."""

from pathlib import Path
from typing import Literal

import torch
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Model constants to avoid string duplication
MODEL_SDXL = "stabilityai/stable-diffusion-xl-base-1.0"
MODEL_SD15 = "runwayml/stable-diffusion-v1-5"
MODEL_DREAMSHAPER = "Lykon/dreamshaper-8"


class MoodModelConfig(BaseModel):
    """Mood-to-model mapping configuration."""

    # Default model used when mood not found in mapping
    default_model: str = MODEL_SDXL

    # Mood-specific model assignments
    mood_models: dict[str, str] = {
        "contemplative": MODEL_SDXL,
        "chaotic": MODEL_SD15,  # More experimental
        "serene": MODEL_DREAMSHAPER,  # Softer rendering
        "melancholic": MODEL_SDXL,
        "joyful": MODEL_DREAMSHAPER,
        "rebellious": MODEL_SD15,
        "curious": MODEL_SDXL,
        "nostalgic": MODEL_DREAMSHAPER,
        "playful": MODEL_DREAMSHAPER,
        "introspective": MODEL_SDXL,
    }

    def get_model_for_mood(self, mood: str) -> str:
        """Get the model ID for a given mood."""
        return self.mood_models.get(mood.lower(), self.default_model)


class ModelConfig(BaseModel):
    """Model configuration."""

    base_model: str = MODEL_SDXL
    device: Literal["cuda", "mps", "cpu"] = "cuda"
    dtype: Literal["float16", "float32"] = "float16"
    enable_attention_slicing: bool = True
    enable_vae_slicing: bool = True
    lora_path: str | None = None  # Path to trained LoRA weights
    lora_scale: float = 0.8  # LoRA strength (0.0-1.0)
    use_refiner: bool = False
    refiner_model: str = "stabilityai/stable-diffusion-xl-refiner-1.0"
    # type: ignore[arg-type]
    mood_models: MoodModelConfig = Field(default_factory=MoodModelConfig)


class GenerationConfig(BaseModel):
    """Generation parameters."""

    width: int = Field(1024, ge=512, le=2048)
    height: int = Field(1024, ge=512, le=2048)
    num_inference_steps: int = Field(30, ge=10, le=100)
    guidance_scale: float = Field(7.5, ge=1.0, le=20.0)
    num_variations: int = Field(3, ge=1, le=10)
    negative_prompt: str = "blurry, low quality, distorted, ugly, deformed"


class UpscalingConfig(BaseModel):
    """Upscaling configuration."""

    enabled: bool = False
    model_id: str = "stabilityai/stable-diffusion-x4-upscaler"
    noise_level: int = 20  # 0-100 (20 is good for faithful upscaling)


class ControlNetConfig(BaseModel):
    """ControlNet configuration."""

    enabled: bool = False
    model_id: str = "lllyasviel/sd-controlnet-canny"
    conditioning_scale: float = 1.0
    low_threshold: int = 100  # Canny edge detection low threshold
    high_threshold: int = 200  # Canny edge detection high threshold


class InpaintingConfig(BaseModel):
    """Inpainting configuration."""

    enabled: bool = False
    model_id: str = "runwayml/stable-diffusion-inpainting"


class FaceRestorationConfig(BaseModel):
    """Face restoration configuration."""

    enabled: bool = False
    # CodeFormer is now the only option
    model: Literal["codeformer"] = "codeformer"
    model_path: str | None = None  # Custom model path (optional)
    fidelity: float = 0.7  # Balance between quality (0) and fidelity (1)


class AutonomyConfig(BaseModel):
    """Autonomy / Feedback Loop configuration."""

    enabled: bool = False
    min_score_threshold: float = (
        0.22  # Minimum CLIP score (0.22 is decent for pure CLIP)
    )
    max_retries: int = 2
    feedback_mode: Literal["simple_retry", "refine_prompt"] = "simple_retry"


class TrendsConfig(BaseModel):
    """Trend analysis configuration."""

    enabled: bool = False
    update_interval_hours: int = 24
    sources: list[str] = ["civitai", "artstation"]


class CacheConfig(BaseModel):
    """Redis caching configuration."""

    enabled: bool = False
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    generation_ttl: int = 3600  # 1 hour
    curation_ttl: int = 7200  # 2 hours


class GraphMemoryConfig(BaseModel):
    """FalkorDB graph memory configuration."""

    enabled: bool = True
    host: str = "localhost"
    port: int = 6380  # Different from Redis (6379)
    graph_name: str = "lumira"


class SocialConfig(BaseModel):
    """Social media sharing configuration."""

    enabled: bool = False
    platforms: list[str] = ["twitter", "instagram", "pinterest"]
    auto_share: bool = False
    share_threshold: float = 0.3  # Only share artworks above this score


class ModelManagerConfig(BaseModel):
    """Model management configuration."""

    enabled: bool = False
    base_path: str = "models"
    auto_download_trending: bool = False
    max_models: int = 50
    civitai_api_key: str | None = None
    # Model preloading for instant generation
    preload_models: list[str] = []  # Models to preload on startup
    enable_model_pool: bool = True  # Use model pooling for performance


class APIKeysConfig(BaseModel):
    """API keys configuration.

    Uses SecretStr to prevent accidental logging of sensitive values.
    Access the actual value with .get_secret_value() method.
    """

    unsplash_access_key: SecretStr | None = None
    unsplash_secret_key: SecretStr | None = None
    pexels_api_key: SecretStr | None = None
    hf_token: SecretStr | None = None
    civitai_api_key: SecretStr | None = None


class DatabaseConfig(BaseModel):
    """Database configuration."""

    url: str = "sqlite:///./data/ai_artist.db"


class WebConfig(BaseModel):
    """Web server configuration."""

    # API key authentication - empty list means no auth required (dev mode)
    # Can be set via RAILWAY_API_KEY environment variable
    api_keys: list[SecretStr] = []

    # CORS origins - empty list uses secure localhost defaults
    cors_origins: list[str] = []

    # Rate limiting
    rate_limit_generate: str = "5/minute"  # For /api/generate endpoint
    rate_limit_api: str = "60/minute"  # For other API endpoints

    @classmethod
    def from_env(cls) -> "WebConfig":
        """Create WebConfig from environment variables."""
        import os

        api_keys = []
        if api_key := os.getenv("RAILWAY_API_KEY"):
            api_keys = [SecretStr(api_key)]

        return cls(api_keys=api_keys)


class ObservabilityConfig(BaseModel):
    """Observability and monitoring configuration."""

    # Sentry error tracking
    sentry_dsn: SecretStr | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1  # 10% of transactions
    sentry_profiles_sample_rate: float = 0.1  # 10% of transactions

    # Metrics export
    enable_prometheus: bool = False
    prometheus_port: int = 9090

    # Performance monitoring
    enable_performance_logging: bool = True
    log_slow_operations_threshold: float = 1.0  # seconds


class Config(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        extra="allow",
        env_file=".env",
        env_nested_delimiter="__",
        protected_namespaces=("settings_",),
    )  # type: ignore[misc]

    model: ModelConfig = Field(default_factory=lambda: ModelConfig())
    generation: GenerationConfig = Field(default_factory=lambda: GenerationConfig())
    upscaling: UpscalingConfig = Field(default_factory=lambda: UpscalingConfig())
    controlnet: ControlNetConfig = Field(default_factory=lambda: ControlNetConfig())
    inpainting: InpaintingConfig = Field(default_factory=lambda: InpaintingConfig())
    face_restoration: FaceRestorationConfig = Field(
        default_factory=lambda: FaceRestorationConfig()
    )
    autonomy: AutonomyConfig = Field(default_factory=lambda: AutonomyConfig())
    trends: TrendsConfig = Field(default_factory=lambda: TrendsConfig())
    cache: CacheConfig = Field(default_factory=lambda: CacheConfig())
    graph_memory: GraphMemoryConfig = Field(
        default_factory=lambda: GraphMemoryConfig()
    )
    social: SocialConfig = Field(default_factory=lambda: SocialConfig())
    model_manager: ModelManagerConfig = Field(
        default_factory=lambda: ModelManagerConfig()
    )
    api_keys: APIKeysConfig = Field(default_factory=lambda: APIKeysConfig())
    database: DatabaseConfig = Field(default_factory=lambda: DatabaseConfig())
    web: WebConfig = Field(default_factory=lambda: WebConfig())
    observability: ObservabilityConfig = Field(
        default_factory=lambda: ObservabilityConfig()
    )


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None or file doesn't exist,
                    returns default config (gallery-only mode).

    Raises:
        ValueError: If config file exists but is invalid
    """
    # If no config path or file doesn't exist, use defaults
    if config_path is None or not config_path.exists():
        return Config()

    with open(config_path) as f:
        data = yaml.safe_load(f)
    config = Config(**data)

    return config


def get_torch_dtype(dtype_str: str) -> torch.dtype:
    """Convert dtype string to torch dtype."""
    return torch.float16 if dtype_str == "float16" else torch.float32
