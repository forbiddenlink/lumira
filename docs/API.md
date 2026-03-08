# API Specifications

Complete API documentation for all Lumira modules.

---

## Table of Contents

- [Core Modules](#core-modules)
  - [Image Generator](#image-generator)
  - [Image Curator](#image-curator)
- [API Clients](#api-clients)
  - [Unsplash Client](#unsplash-client)
  - [Pexels Client (Future)](#pexels-client)
- [Database](#database)
  - [Models](#database-models)
  - [Repositories](#repositories)
- [Utilities](#utilities)
  - [Configuration](#configuration)
  - [Logging](#logging)

---

## Core Modules

### Image Generator

**Module:** `src/ai_artist/core/generator.py`

#### Class: `ImageGenerator`

Stable Diffusion image generation with LoRA support.

**Constructor:**

```python
ImageGenerator(
    model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
    device: Literal["cuda", "mps", "cpu"] = "cuda",
    dtype: torch.dtype = torch.float16,
)
```

**Parameters:**

- `model_id` (str): HuggingFace model identifier
- `device` (Literal): Device to run model on
- `dtype` (torch.dtype): Data type for model weights

**Methods:**

##### `load_model() -> None`

Load the diffusion pipeline.

**Raises:**

- `RuntimeError`: If model fails to load

**Example:**

```python
generator = ImageGenerator()
generator.load_model()
```

---

##### `load_lora(lora_path: Path, lora_scale: float = 0.8) -> None`

Load LoRA weights into the pipeline.

**Parameters:**

- `lora_path` (Path): Path to LoRA safetensors file
- `lora_scale` (float): LoRA influence strength (0.0-1.0)

**Raises:**

- `RuntimeError`: If model not loaded first
- `FileNotFoundError`: If LoRA file doesn't exist

**Example:**

```python
generator.load_lora(Path("models/lora/my_style.safetensors"), lora_scale=0.8)
```

---

##### `generate() -> list[Image.Image]`

Generate images from prompt.

**Parameters:**

- `prompt` (str): Text prompt for generation
- `negative_prompt` (str, optional): Negative prompt. Default: ""
- `width` (int, optional): Image width. Default: 1024
- `height` (int, optional): Image height. Default: 1024
- `num_inference_steps` (int, optional): Diffusion steps. Default: 30
- `guidance_scale` (float, optional): CFG scale. Default: 7.5
- `num_images` (int, optional): Number to generate. Default: 1
- `seed` (int | None, optional): Random seed. Default: None

**Returns:**

- `list[Image.Image]`: Generated images

**Raises:**

- `RuntimeError`: If model not loaded
- `torch.cuda.OutOfMemoryError`: If GPU OOM

**Example:**

```python
images = generator.generate(
    prompt="a beautiful sunset over mountains",
    num_images=3,
    num_inference_steps=30,
    seed=42,
)
```

---

##### `unload() -> None`

Unload model from memory and clear CUDA cache.

**Example:**

```python
generator.unload()
```

---

### Image Curator

**Module:** `src/ai_artist/curation/curator.py`

#### Class: `QualityMetrics`

Dataclass for image quality scores.

**Attributes:**

- `aesthetic_score` (float): Aesthetic quality (0-1)
- `clip_score` (float): Text-image alignment (0-1)
- `technical_score` (float): Technical quality (0-1)

**Properties:**

- `overall_score` (float): Weighted average of all scores

---

#### Class: `ImageCurator`

CLIP-based image quality evaluation.

**Constructor:**

```python
ImageCurator(device: str = "cuda")
```

**Parameters:**

- `device` (str): Device for CLIP model

**Methods:**

##### `evaluate(image: Image.Image, prompt: str) -> QualityMetrics`

Evaluate image quality metrics.

**Parameters:**

- `image` (PIL.Image.Image): Image to evaluate
- `prompt` (str): Original generation prompt

**Returns:**

- `QualityMetrics`: Quality scores

**Example:**

```python
curator = ImageCurator()
metrics = curator.evaluate(image, prompt="a sunset")
print(f"Overall score: {metrics.overall_score:.2f}")
```

---

##### `should_keep(metrics: QualityMetrics, threshold: float = 0.6) -> bool`

Determine if image meets quality threshold.

**Parameters:**

- `metrics` (QualityMetrics): Image quality metrics
- `threshold` (float): Minimum acceptable score

**Returns:**

- `bool`: True if image should be kept

**Example:**

```python
if curator.should_keep(metrics, threshold=0.7):
    gallery.save_image(image, prompt, metadata)
```

---

## API Clients

### Unsplash Client

**Module:** `src/ai_artist/api/unsplash.py`

#### Class: `UnsplashClient`

Async HTTP client for Unsplash API with retry logic.

**Constructor:**

```python
UnsplashClient(
    access_key: str,
    app_name: str = "lumira",
)
```

**Parameters:**

- `access_key` (str): Unsplash API access key
- `app_name` (str): Application name for attribution

**Methods:**

##### `async search_photos() -> dict`

Search for photos.

**Parameters:**

- `query` (str): Search query
- `per_page` (int, optional): Results per page. Default: 10
- `orientation` (str | None, optional): Image orientation. Options: "landscape", "portrait", "squarish"

**Returns:**

- `dict`: Search results with "results" key containing photo objects

**Raises:**

- `RateLimitError`: If API rate limit exceeded
- `httpx.HTTPStatusError`: On HTTP errors

**Example:**

```python
async with UnsplashClient(access_key="...") as client:
    results = await client.search_photos(
        query="sunset mountains",
        per_page=5,
        orientation="landscape",
    )
    for photo in results["results"]:
        print(photo["urls"]["regular"])
```

---

##### `async get_random_photo(query: str | None = None) -> dict`

Get a random photo.

**Parameters:**

- `query` (str | None, optional): Filter by topic

**Returns:**

- `dict`: Photo object

**Example:**

```python
photo = await client.get_random_photo(query="nature")
```

---

##### `async trigger_download(download_location: str) -> None`

Track download (required by Unsplash API guidelines).

**Parameters:**

- `download_location` (str): Download URL from photo object

**Example:**

```python
await client.trigger_download(photo["links"]["download_location"])
```

---

##### `get_attribution(photo: dict) -> str`

Generate proper attribution HTML.

**Parameters:**

- `photo` (dict): Photo object from API

**Returns:**

- `str`: HTML attribution string

**Example:**

```python
attribution = client.get_attribution(photo)
# Output: 'Photo by <a href="...">John Doe</a> on <a href="...">Unsplash</a>'
```

---

##### `async close() -> None`

Close HTTP client connection.

**Example:**

```python
await client.close()
```

---

## Database

### Database Models

**Module:** `src/ai_artist/db/models.py`

#### Class: `GeneratedImage`

SQLAlchemy model for generated artwork.

**Table:** `generated_images`

**Columns:**

- `id` (Integer, PK): Auto-increment ID
- `filename` (String, unique, indexed): Image filename
- `prompt` (String): Generation prompt
- `negative_prompt` (String): Negative prompt
- `source_url` (String, nullable): Inspiration source URL
- `source_query` (String, nullable): Search query used
- `model_id` (String, indexed): Model identifier
- `generation_params` (JSON): Full generation parameters
- `seed` (Integer, nullable): Random seed
- `aesthetic_score` (Float, nullable): CLIP aesthetic score
- `clip_score` (Float, nullable): Text-image alignment
- `technical_score` (Float, nullable): Technical quality
- `final_score` (Float, indexed, nullable): Overall score
- `created_at` (DateTime, indexed): Creation timestamp
- `status` (String, indexed): Status ("pending", "curated", "rejected")
- `is_featured` (Boolean): Featured flag
- `tags` (JSON): Tag list

**Example:**

```python
image = GeneratedImage(
    filename="20260108_120000_sunset.png",
    prompt="a beautiful sunset",
    model_id="sdxl-1.0",
    generation_params={"steps": 30, "cfg": 7.5},
    seed=42,
    aesthetic_score=7.2,
    status="curated",
    is_featured=True,
)
session.add(image)
session.commit()
```

---

#### Class: `TrainingSession`

SQLAlchemy model for LoRA training sessions.

**Table:** `training_sessions`

**Columns:**

- `id` (Integer, PK): Auto-increment ID
- `name` (String): Session name
- `model_path` (String): Path to saved model
- `config` (JSON): Training configuration
- `dataset_size` (Integer): Number of training images
- `final_loss` (Float, nullable): Final training loss
- `training_time_seconds` (Float, nullable): Training duration
- `metrics` (JSON): Training metrics
- `started_at` (DateTime): Start timestamp
- `completed_at` (DateTime, nullable): Completion timestamp
- `status` (String): Status ("running", "completed", "failed")

---

#### Class: `CreationSession`

SQLAlchemy model for automated creation sessions.

**Table:** `creation_sessions`

**Columns:**

- `id` (Integer, PK): Auto-increment ID
- `theme` (String, nullable): Session theme
- `images_created` (Integer): Total images generated
- `images_kept` (Integer): Images that passed curation
- `avg_score` (Float, nullable): Average quality score
- `started_at` (DateTime): Session start
- `completed_at` (DateTime, nullable): Session end

---

### Repositories

#### Class: `ImageRepository`

Repository pattern for database operations on images.

**Constructor:**

```python
ImageRepository(session_factory: sessionmaker)
```

**Methods:**

##### `add(image: GeneratedImage) -> GeneratedImage`

Add new image record.

##### `get_by_id(image_id: int) -> GeneratedImage | None`

Get image by ID.

##### `get_uncurated(limit: int = 100) -> list[GeneratedImage]`

Get pending images for curation.

##### `update_quality_scores(image_id: int, aesthetic_score: float, clip_score: float) -> None`

Update quality scores.

##### `mark_curated(image_id: int, accepted: bool) -> None`

Mark image as curated or rejected.

---

## Utilities

### Configuration

**Module:** `src/ai_artist/utils/config.py`

#### Class: `Config`

Pydantic model for application configuration.

**Attributes:**

- `model` (ModelConfig): Model configuration
- `generation` (GenerationConfig): Generation parameters
- `api_keys` (APIKeysConfig): API credentials

**Function:** `load_config(config_path: Path) -> Config`

Load configuration from YAML file.

**Example:**

```python
config = load_config(Path("config/config.yaml"))
print(config.model.base_model)
print(config.generation.num_inference_steps)
```

---

### Logging

**Module:** `src/ai_artist/utils/logging.py`

#### Function: `configure_logging()`

Configure structured logging with structlog.

**Parameters:**

- `log_level` (str, optional): Log level. Default: "INFO"
- `log_file` (Path | None, optional): Log file path. Default: None

**Example:**

```python
configure_logging(log_level="DEBUG", log_file=Path("logs/app.log"))
```

---

#### Function: `get_logger(name: str) -> structlog.BoundLogger`

Get a structured logger instance.

**Parameters:**

- `name` (str): Logger name (typically `__name__`)

**Returns:**

- `structlog.BoundLogger`: Logger instance

**Example:**

```python
logger = get_logger(__name__)
logger.info("processing_image", image_id=123, score=7.5)
```

---

## Error Handling

### Custom Exceptions

**Module:** `src/ai_artist/api/unsplash.py`

#### Exception: `RateLimitError`

Raised when API rate limit is exceeded.

**Usage:**

```python
try:
    await client.search_photos("sunset")
except RateLimitError:
    # Fallback to cache or Pexels
    pass
```

---

## Type Hints

All modules use comprehensive type hints compatible with Python 3.11+:

```python
from typing import Literal
from collections.abc import Sequence
from pathlib import Path
from PIL import Image

type ImageBatch = list[Image.Image]
type Device = Literal["cuda", "mps", "cpu"]
```

---

## Async Patterns

### Context Manager Usage

```python
async with UnsplashClient(access_key="...") as client:
    photo = await client.get_random_photo()
    # Client automatically closed
```

### Database Sessions

```python
from src.ai_artist.db.session import get_db_session

with get_db_session(session_factory) as session:
    image = GeneratedImage(...)
    session.add(image)
    # Auto-commit on success, rollback on error
```

---

## Rate Limiting

All API clients implement retry logic with exponential backoff:

```python
@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(3),
)
async def api_call():
    ...
```

---

## Testing

### Mocking Examples

**Mock Unsplash Client:**

```python
@pytest.fixture
def mock_unsplash(mocker):
    client = AsyncMock()
    client.get_random_photo.return_value = {
        "id": "test123",
        "urls": {"regular": "https://..."},
        "user": {"name": "Test User"},
    }
    return client
```

**Mock Image Generator:**

```python
@pytest.fixture
def mock_generator(mocker):
    gen = mocker.Mock()
    gen.generate.return_value = [Image.new("RGB", (512, 512))]
    return gen
```

---

**Document Version:** 1.0
**Last Updated:** 2026-01-08
