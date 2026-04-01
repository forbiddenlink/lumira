# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Lumira is an autonomous AI artist — a Python system with personality, moods, memory, and creative independence. It generates artwork via Stable Diffusion XL/FLUX pipelines, curates output with CLIP scoring, and learns from experience using a multi-armed bandit algorithm. Python 3.11+ required.

## Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements-full.txt && pip install -e .
alembic upgrade head

# Gallery-only mode (no ML dependencies)
pip install -r requirements.txt && pip install -e .

# Run
python -m ai_artist.main                        # Autonomous (mood-based)
python -m ai_artist.main --theme "twilight"     # Themed
python -m ai_artist.main --mode auto            # Scheduled
uvicorn ai_artist.web.app:app --reload --port 8000  # Web server

# CLI entry points (registered in pyproject.toml [project.scripts])
lumira             # Main CLI
lumira-web         # Web server
lumira-worker      # Redis job queue worker
lumira-gallery     # Gallery viewer
lumira-schedule    # Scheduling

# Tests
pytest                                    # All tests
pytest tests/unit/test_moods.py           # Single file
pytest -k "test_critic"                   # Pattern match
pytest --cov=src/ai_artist tests/         # With coverage
pytest -m "not slow"                      # Skip slow tests
pytest tests/e2e -v --browser chromium    # E2E (needs playwright install)

# Lint & format
black src/ tests/
ruff check src/ --fix
mypy src/ai_artist --ignore-missing-imports
pre-commit run --all-files

# Database migrations (Alembic + SQLite, WAL mode)
alembic revision --autogenerate -m "description"
alembic upgrade head

# Docker
docker-compose up -d
docker-compose -f docker-compose.gpu.yml up   # GPU support
```

## Architecture

### Core Pipeline

```
MoodSystem → ThinkingProcess (ReAct) → PromptEngine → ImageGenerator → Curator → GalleryManager
                                                                         ↓
                                                                    CLIP scoring
                                                                    + ensemble
```

The central orchestrator is `AIArtist` in `src/ai_artist/main.py`. It wires together all subsystems: mood, thinking, critic, memory, generator, curator, and gallery.

### Source Layout (`src/ai_artist/`)

- **`personality/`** — Mood system (10 states), 3-layer memory (episodic/semantic/working), ReAct cognition (`cognition.py`), inner critic, inner dialogue, vector memory (ChromaDB). The mood system is the creative driver — it influences model selection, prompt generation, and artistic decisions.
- **`core/`** — Image generation backends: SDXL (`generator.py`), FLUX (`flux_generator.py`), Replicate cloud (`replicate_generator.py`), ControlNet, IP-Adapter, inpainting, upscaling, face restoration. `model_pool.py` provides pre-warmed model caching for 10x faster startup.
- **`curation/`** — CLIP-based quality scoring (`curator.py`), AGIQA perceptual scoring, ensemble evaluation framework.
- **`intelligence/`** — Higher-level creative systems: creative mind, desire engine, narrative generation.
- **`web/`** — FastAPI application. `app.py` is the entrypoint; routes are split into `lumira_routes.py`, `gallery_routes.py`, `prompt_routes.py`, `health.py`, `metrics_routes.py`, `feedback.py`, `admin.py`. WebSocket support in `websocket.py`. Middleware in `middleware.py` (CORS, security headers, logging, error handling).
- **`db/`** — SQLAlchemy models (`models.py`) and session management (`session.py`). Primary tables: `GeneratedImage`, `TrainingSession`, `GalleryLike/Comment/Share`, `GalleryCollection`. Uses SQLite with WAL mode; Alembic for migrations.
- **`queue/`** — Redis-backed job queue (RQ) for async generation. Worker in `worker.py`, CLI in `cli.py`.
- **`learning/`** — Multi-armed bandit adaptive learning from user feedback.
- **`scheduling/`** — APScheduler-based autonomous creation cycles with resilience handling.
- **`prompts/`** — Prompt template libraries (artistic, expanded, ultimate).
- **`utils/`** — Config (`config.py` — Pydantic V2 + pydantic-settings), structured logging (structlog), prompt engine, style presets, negative prompts.
- **`training/`** — LoRA fine-tuning.
- **`memory/`** — FalkorDB graph memory for institutional knowledge.
- **`social/`** — Social media posting (Twitter/X, Instagram, Bluesky).
- **`monitoring/`** — Prometheus metrics and Sentry integration.

### Web API Routes

- `/api/lumira` — Personality & generation endpoints
- `/api/gallery` — Gallery management
- `/api/health` — Kubernetes liveness/readiness probes
- `/api/metrics` — Prometheus metrics
- `/ws` — WebSocket for real-time generation updates

### Configuration

- **Environment**: `.env` (copy from `.env.example`). Key vars: `MODEL_ID`, `DEVICE` (cuda/mps/cpu), `HF_TOKEN`, `DATABASE_URL`.
- **YAML**: `config/config.yaml` (copy from `config/config.example.yaml`).
- **Style presets**: `config/style_presets.json`
- **LoRA registry**: `config/lora_models.json`
- **Wildcards**: `config/wildcards/*.txt`
- Config is loaded via `utils/config.py` using Pydantic V2 `BaseSettings` with `.env` support and nested delimiter `__`.

## Code Patterns

- **Async**: All FastAPI routes are async. File I/O uses `aiofiles`.
- **Pydantic V2**: All config and API models. `pydantic-settings` for env loading.
- **Type hints**: Target 100% coverage. Google-style docstrings.
- **Retries**: `tenacity` with `@retry` and exponential backoff for external API calls.
- **Secrets**: Config uses `SecretStr` for API keys — access via `.get_secret_value()`.
- **Structured logging**: `structlog` throughout. Logger via `get_logger(__name__)`.
- **FastAPI dependencies**: Gallery manager injected via `dependencies.py` (`GalleryManagerDep`). DB sessions via `db/session.py` (`get_db`).

## Testing

- **Framework**: pytest with `pytest-asyncio` (auto mode), `pytest-mock`, `pytest-cov`.
- **Markers**: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`, `@pytest.mark.e2e`.
- **Layout**: `tests/unit/`, `tests/integration/`, `tests/e2e/`.
- **Fixtures**: Root `tests/conftest.py` adds `src/` to `sys.path`. E2E has its own `conftest.py`.
- **Redis mocking**: Uses `fakeredis` for queue tests.
- **CI excludes**: `tests/e2e` and `slow` marker are excluded from default PR test runs; they run only on main branch pushes.

## CI/CD

GitHub Actions (`ci.yml`):
1. **Lint** — ruff, black, mypy (runs first, gates all other jobs)
2. **Test** — pytest matrix: Python 3.11/3.12 × ubuntu/macos, excludes slow and e2e
3. **Integration/E2E** — run only on pushes to `main`
4. **Security** — Safety + Bandit scans with SARIF upload
5. **Build** — `pyproject-build` + `twine check`

CI uses `uv` for dependency management (`uv sync --dev`).

## Conventions

- **Commits**: Conventional commits — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- **Branches**: `feature/`, `fix/`, `docs/`, `refactor/`, `test/`.
- **Formatting**: Black (line-length 88), Ruff (see `pyproject.toml [tool.ruff]` for select/ignore), isort (black profile).
- **Ruff ignores**: `E501` (line length), `B008` (FastAPI Depends pattern), `UP042` (str/Enum).
- **Per-file**: `src/ai_artist/web/app.py` allows `E402` (path setup before imports).
- **Pre-commit**: Black, Ruff, isort, mypy, bandit, pip-audit, markdownlint.
- **Package source dir**: `src/` layout — packages found under `src/` via `[tool.setuptools] package-dir`.
