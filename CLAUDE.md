# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lumira is an autonomous AI artist system - not a tool, but an artist with personality, moods, memory, and creative independence. Built with Python 3.11+, FastAPI, and Stable Diffusion XL, it creates artwork based on emotional states, learns from experience, and evolves its artistic style.

## Common Commands

```bash
# Development setup
python -m venv venv && source venv/bin/activate
pip install -r requirements-full.txt && pip install -e .
alembic upgrade head

# Run Lumira
python -m ai_artist.main                    # Autonomous creation (mood-based)
python -m ai_artist.main --theme "twilight" # Themed creation
python -m ai_artist.main --mode auto        # Scheduled mode

# Web server
uvicorn ai_artist.web.app:app --reload --port 8000
# Visit: http://localhost:8000/lumira (creative studio)

# Worker for async jobs
lumira-worker

# Testing
pytest                                      # All tests
pytest tests/unit/test_moods.py             # Single file
pytest -k "test_critic"                     # Pattern match
pytest --cov=src/ai_artist tests/           # With coverage

# Linting & formatting
black src/ tests/
ruff check src/ --fix
mypy src/ai_artist --ignore-missing-imports
pre-commit run --all-files

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Docker
docker-compose up -d                        # Standard
docker-compose -f docker-compose.gpu.yml up # GPU support
```

## Architecture

### Core Pipeline Flow

```
MoodSystem → ThinkingProcess → PromptEngine → ImageGenerator → Curator → GalleryManager
    ↓              ↓                                              ↓
Enhanced       ReAct pattern                                 CLIP scoring
Memory         (observe/reflect/                             + ensemble
(3-layer)      decide/express)                               evaluation
```

### Key Modules (`src/ai_artist/`)

| Module | Purpose |
|--------|---------|
| `personality/` | Moods (10 states), memory (episodic/semantic/working), cognition (ReAct), critic |
| `core/` | Image generation: SDXL, FLUX.2, LoRA, ControlNet, IP-Adapter, model pool |
| `web/` | FastAPI app (`app.py`), routes (`lumira_routes.py`, `gallery_routes.py`), WebSocket |
| `curation/` | CLIP curator, AGIQA scorer, ensemble evaluation |
| `intelligence/` | Creative mind, desire engine, narrative generation |
| `scheduling/` | APScheduler-based autonomous creation |
| `learning/` | Multi-armed bandit adaptive learning |
| `queue/` | Redis job queue and workers |

### Central Class: `AIArtist` (main.py)

Orchestrates all subsystems:
- `mood_system` - Current emotional state influencing art
- `thinking` - Visible reasoning process
- `critic` - Self-evaluation before generation
- `enhanced_memory` - Learning from past creations
- `generator` - Diffusion pipeline
- `curator` - Quality scoring
- `gallery` - Artwork storage

### Web Application Structure

FastAPI routers mounted at:
- `/api/lumira` - Personality & generation endpoints
- `/api/gallery` - Gallery management
- `/api/health` - Kubernetes probes
- `/api/metrics` - Prometheus metrics
- `/ws` - WebSocket for real-time updates

### Database

SQLAlchemy models in `db/models.py`. Primary tables:
- `GeneratedImage` - Artwork metadata, scores, generation params
- `TrainingSession` - LoRA training records
- `GalleryLike/Comment/Share` - User engagement

## Code Patterns

### Async Convention
All FastAPI routes are async. File I/O uses `aiofiles`:
```python
async with aiofiles.open(path, "r") as f:
    content = await f.read()
```

### Pydantic V2
Configuration and API models use Pydantic V2:
```python
from pydantic import BaseModel
class LumiraEvolveResponse(BaseModel):
    prompt: str
    mood: str
    creativity: float
```

### Type Hints
Target 100% coverage. Use Google-style docstrings.

### Tenacity for Retries
API calls use `@retry` decorator with exponential backoff.

### Commit Messages
Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Configuration

- **Environment**: `.env` (copy from `.env.example`, 182 documented vars)
- **YAML config**: `config/config.yaml`
- **Style presets**: `config/style_presets.json`
- **Wildcards**: `config/wildcards/*.txt`
- **LoRA registry**: `config/lora_models.json`

Key env vars:
```
MODEL_ID=stabilityai/stable-diffusion-xl-base-1.0
DEVICE=cuda|mps|cpu
HF_TOKEN=<for gated models>
DATABASE_URL=sqlite:///./data/lumira.db
```

## Testing

- **Markers**: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`
- **Async**: `asyncio_mode = "auto"` in pytest.ini
- **Fixtures**: See `tests/conftest.py`
- **Redis mocking**: Uses `fakeredis` for queue tests

## Personality System

The 10-mood system influences model selection, prompt generation, and artistic decisions:
- Contemplative, Playful, Melancholic, Euphoric, Serene
- Anxious, Nostalgic, Curious, Rebellious, Transcendent

Memory is 3-layered:
- **Episodic**: Recent creation history
- **Semantic**: Learned patterns and preferences
- **Working**: Current session context

## Entry Points

```
lumira          # Main CLI (ai_artist.main:main)
lumira-gallery  # Gallery viewer CLI
lumira-schedule # Scheduling CLI
lumira-web      # Web server CLI
lumira-worker   # Queue worker
```
