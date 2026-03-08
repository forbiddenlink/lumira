# Architecture Documentation

## System Overview

Lumira is built as a modular pipeline with five core components:

```text
┌─────────────────┐
│  Inspiration    │ ──> Fetches random images from APIs
│     Engine      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Generation    │ ──> Creates art using Stable Diffusion + LoRA
│     Pipeline    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Curation      │ ──> Rates and selects best works
│     System      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Gallery      │ ──> Stores and organizes artwork
│   Management    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Scheduler     │ ──> Automates the entire process
│                 │
└─────────────────┘
```

## Component Details

### 1. Inspiration Engine

**Purpose**: Autonomously discover interesting subjects to paint

**Components**:

- `UnsplashClient`: Fetches random high-quality images
- `PexelsClient`: Alternative image source
- `TopicGenerator`: Generates search queries (animals, landscapes, etc.)
- `ImagePreprocessor`: Crops, resizes, enhances source images

**Flow**:

1. Generate random search query or use predefined topic
2. Fetch image from API with retry logic (3 attempts)
3. Handle rate limits gracefully (fallback to Pexels)
4. Preprocess for optimal SD input
5. Save to inspiration cache with metadata
6. Log all operations for debugging

**Error Handling**:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def fetch_image(query: str) -> Dict:
    """Fetch with automatic retry on failure."""
    try:
        response = unsplash_client.get(query)
        return response
    except RateLimitError:
        # Fallback to Pexels
        return pexels_client.get(query)
```

**APIs Used**:

- Unsplash API (Free: 50 requests/hour)
- Pexels API (Free: 200 requests/hour)

### 2. Generation Pipeline

**Purpose**: Transform inspiration into unique artwork

**Components**:

- `StableDiffusionPipeline`: Core image generation
- `LoRAManager`: Loads and applies style weights
- `PromptBuilder`: Constructs effective prompts
- `ControlNetProcessor`: Preserves structure (optional)

**Model Architecture**:

```text
Base Model: Stable Diffusion 1.5 or SDXL
    ↓
+ LoRA Weights (trained style)
    ↓
+ ControlNet (optional, for structure preservation)
    ↓
= Unique Styled Output
```

**Generation Process**:

1. Load base SD model + LoRA weights
2. Analyze source image (color palette, composition)
3. Build prompt: "[subject] in the style of [artist name], [style keywords]"
4. Generate with optimal settings (steps=30-50, cfg_scale=7-9)
5. Post-process (upscaling, enhancement)

### 3. Style Training System

**Purpose**: Create unique artistic voice through LoRA fine-tuning

**Training Data Sources**:

- Curated art datasets (WikiArt, OpenImages)
- Hand-selected reference images
- AI-generated training set with specific style

**Training Pipeline**:

```python
# LoRA Training Parameters (Updated Best Practices)
{
    "rank": 16,                    # LoRA rank (4-32, higher = more params)
    "alpha": 32,                   # LoRA alpha (typically 2x rank)
    "learning_rate": 5e-4,         # Can be higher for LoRA (1e-4 to 1e-3)
    "steps": 2000-5000,            # Training iterations
    "batch_size": 1-4,             # Based on VRAM
    "resolution": 512x512,         # Training resolution
    "gradient_checkpointing": True, # Save memory
    "validation_epochs": 100,      # Validate during training
    "save_checkpoints": 500,       # Save every 500 steps
}
```

**Important Notes**:

- Use `accelerate` library for distributed training
- Validate during training to catch overfitting
- **Legal Compliance**: Only use public domain or CC-licensed training data
- Document all training data sources (see LEGAL.md)

**Style Consistency**:

- Train on 20-50 carefully selected images
- Use regularization images to prevent overfitting
- Test style transfer on diverse subjects
- Iterate until consistent results

### 4. Curation System

**Purpose**: AI self-evaluates and selects best works

**Evaluation Metrics** (Multi-dimensional):

1. **Aesthetic Score**: CLIP-based aesthetic predictor (0-100)
2. **Technical Quality**:
   - Blur detection
   - Artifact detection
   - Resolution quality
3. **Composition Analysis**:
   - Rule of thirds adherence
   - Visual balance
   - Color harmony
4. **Style Consistency**: Embedding similarity to training set
5. **Diversity Score**: Distance from recent works (prevent repetition)
6. **Human Feedback** (Optional): Thumbs up/down ratings

**CLIP-Based Rating**:

```python
# Encode image and style description
image_features = clip.encode_image(artwork)
style_features = clip.encode_text("high quality artistic painting")

# Compute similarity score (0-100)
aesthetic_score = cosine_similarity(image_features, style_features) * 100
```

**Multi-Metric Evaluation**:

```python
final_score = (
    aesthetic_score * 0.35 +
    technical_score * 0.25 +
    composition_score * 0.20 +
    diversity_score * 0.15 +
    style_consistency * 0.05
)
```

**Selection Process**:

- Generate 3-5 variations per session
- Rate all outputs with multiple metrics
- Keep only top 1-2 (score > threshold)
- Store rejected works in archive for analysis
- Track score distributions over time

### 5. Gallery Management

**Purpose**: Organize and track artwork portfolio

**Database Schema** (SQLite):

```sql
CREATE TABLE artworks (
    id INTEGER PRIMARY KEY,
    filename TEXT UNIQUE,
    created_at TIMESTAMP,

    -- Source tracking
    source_url TEXT,
    source_query TEXT,
    source_license TEXT,  -- Track for legal compliance

    -- Generation parameters
    prompt TEXT,
    negative_prompt TEXT,
    model_version TEXT,
    lora_version TEXT,
    seed INTEGER,
    cfg_scale REAL,
    steps INTEGER,

    -- Quality metrics
    aesthetic_score REAL,
    technical_score REAL,
    composition_score REAL,
    diversity_score REAL,
    style_consistency REAL,
    final_score REAL,

    -- Metadata
    file_size_bytes INTEGER,
    generation_time_seconds REAL,
    clip_embedding BLOB,  -- For similarity search

    -- User interaction
    user_rating INTEGER,
    user_feedback TEXT,
    views INTEGER DEFAULT 0,

    -- Organization
    style_name TEXT,
    is_featured BOOLEAN,
    session_theme TEXT,
    tags JSON,
    metadata JSON
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    date TIMESTAMP,
    theme TEXT,
    artworks_created INTEGER,
    artworks_kept INTEGER,
    avg_score REAL,
    duration_seconds REAL
);

CREATE TABLE training_history (
    id INTEGER PRIMARY KEY,
    style_name TEXT,
    trained_at TIMESTAMP,
    training_images INTEGER,
    steps INTEGER,
    final_loss REAL,
    data_sources JSON,  -- Legal compliance
    lora_path TEXT
);

-- Indexes for performance
CREATE INDEX idx_created_at ON artworks(created_at);
CREATE INDEX idx_final_score ON artworks(final_score);
CREATE INDEX idx_session_theme ON artworks(session_theme);
CREATE INDEX idx_style_name ON artworks(style_name);
```

**File Organization**:

```plaintext
gallery/
├── 2026/
│   ├── 01-January/
│   │   ├── 2026-01-01_morning_session/
│   │   │   ├── featured/
│   │   │   │   └── artwork_001.png
│   │   │   └── archive/
│   │   │       ├── artwork_001_v1.png
│   │   │       └── artwork_001_v2.png
│   │   └── metadata.json
```

### 6. Scheduling System

**Purpose**: Automate creation on regular basis

**Schedule Types**:

- **Daily**: One art piece per day at specific time
- **Weekly**: Multiple pieces on certain days
- **Session-based**: Burst creation (e.g., 10 pieces per session)
- **Event-triggered**: Create on external triggers

**Job Configuration**:

```yaml
schedules:
  daily_creation:
    time: "09:00"
    timezone: "America/Los_Angeles"
    theme: "random"

  weekend_series:
    days: ["Saturday", "Sunday"]
    time: "14:00"
    theme: "series"  # Creates themed collections
```

## Data Flow

### Complete Creation Cycle

```text
1. SCHEDULER triggers creation job
        ↓
2. INSPIRATION finds source image
        ↓
3. TOPIC GENERATOR creates prompt
        ↓
4. GENERATION PIPELINE creates 3-5 variations
        ↓
5. CURATION evaluates all outputs
        ↓
6. GALLERY saves top pieces
        ↓
7. DATABASE records metadata
        ↓
8. (Optional) SOCIAL MEDIA posts featured work
```

## Technology Choices

### Why Stable Diffusion?

- Open source and highly customizable
- Excellent LoRA support for style transfer
- Large community and resources
- Can run locally (privacy, cost)

### Why LoRA over DreamBooth?

- **Faster training**: 1-2 hours vs 8-12 hours
- **Smaller files**: 3-50MB vs 2-4GB
- **Better flexibility**: Switch styles easily
- **Less overfitting**: More generalizable

### Why Unsplash?

- High-quality curated images
- Free tier sufficient for project
- Good API documentation
- Diverse subject matter

### Why SQLite?

- No server setup required
- Fast for this use case
- Built into Python
- Easy backup and portability

## Performance Considerations

### GPU Requirements

**Minimum**:

- 6GB VRAM (RTX 2060, M1 Max)
- SD 1.5 at 512x512

**Recommended**:

- 12GB+ VRAM (RTX 3060, RTX 4070)
- SDXL at 1024x1024

**Optimization Techniques**:

- Half-precision (fp16) for memory
- Attention slicing for large images
- Model offloading to CPU when needed
- Batch size = 1 for memory efficiency

### Speed Estimates

**Per Image Generation**:

- SD 1.5 (512px): 5-15 seconds
- SDXL (1024px): 20-60 seconds
- With LoRA: +10-20% time

**Training**:

- LoRA training: 1-3 hours (2000-5000 steps)
- Dataset preparation: 30-60 minutes

## Security & Privacy

- API keys stored in environment variables
- Source images not permanently stored (optional)
- No user data collected
- Generated art is local by default
- Social media integration opt-in only

## Extensibility

### Adding New Features

**New Image Sources**:

1. Implement `ImageSourceInterface`
2. Add client to `inspiration/sources/`
3. Register in config

**New Styles**:

1. Collect training images
2. Run training script
3. Save LoRA weights to `models/lora/`
4. Update config

**New Curation Metrics**:

1. Implement scorer in `curation/scorers/`
2. Register in evaluation pipeline
3. Configure weight in settings

## Web Application Architecture

### FastAPI Async Patterns

The web application uses FastAPI with fully async request handling.
All file I/O uses `aiofiles` to avoid blocking the event loop.

**Async File I/O with aiofiles**:

```python
import aiofiles

# Reading files (templates, config, etc.)
async with aiofiles.open(file_path, "r") as f:
    content = await f.read()

# Writing files (uploads, cache)
async with aiofiles.open(file_path, "wb") as f:
    await f.write(data)

# JSON loading
async def load_json_async(path: Path) -> dict:
    async with aiofiles.open(path, "r") as f:
        return json.loads(await f.read())
```

**Why aiofiles over sync I/O**:

- Non-blocking: Doesn't freeze other requests during file operations
- Consistency: All endpoints remain async, no thread pool overhead
- Scalability: Better performance under concurrent load

**Response Models with Pydantic V2**:

All LUMIRA API endpoints use typed response models for:

- OpenAPI documentation generation
- Runtime validation
- Type safety

```python
from pydantic import BaseModel

class LumiraEvolveResponse(BaseModel):
    prompt: str
    seed: int | None
    guidance_scale: float
    steps: int
    image_path: str
    mood: str
    creativity: float

@app.post("/lumira/evolve", response_model=LumiraEvolveResponse)
async def evolve(request: EvolveRequest) -> LumiraEvolveResponse:
    ...
```

**mypy Configuration for aiofiles**:

Even with `types-aiofiles` installed, add explicit override in `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "aiofiles.*"
ignore_missing_imports = true
```

### Prompt Collections Module

All generation prompts are centralized in `src/ai_artist/prompts/`:

```text
prompts/
├── __init__.py      # get_collection_prompts(), get_all_collections()
├── artistic.py      # Impressionist, cubist, surrealist styles
├── artistic2.py     # Renaissance, photo-realism, op-art
├── expanded.py      # Cinematic, emotional, nature themes
└── ultimate.py      # Cosmic, mythological, fantasy themes
```

**Usage**:

```python
from ai_artist.prompts import get_collection_prompts, get_collection_names

# Get specific collection
prompts = get_collection_prompts("artistic")

# List available collections
names = get_collection_names()  # ["artistic", "artistic2", "expanded", "ultimate"]
```
