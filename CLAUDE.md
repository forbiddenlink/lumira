# Lumira

Autonomous AI artist system -- not a tool, an artist with personality, moods, memory, and
creative independence. Python 3.11+, FastAPI, Stable Diffusion XL/FLUX; creates artwork based
on emotional states, learns from experience, evolves its style. A lightweight "gallery +
cloud-generation" build (`Dockerfile.gallery`, no local ML/GPU, generation via Replicate/Magica)
deploys to Railway (`railway.toml`).

## Stack

- Python >=3.11, package manager `uv` (`uv.lock`); `pip install -e .` also works
- FastAPI (`>=0.115.0,<0.142.0`) + Uvicorn; SQLAlchemy 2 + Alembic; SQLite (WAL mode)
- Pydantic V2 + pydantic-settings for config (`.env` support, nested delimiter `__`)
- Local generation: torch, diffusers, transformers, accelerate, peft (SDXL, FLUX)
- Cloud generation: Replicate API, Magica/Galaxy AI; `anthropic` SDK; `chromadb` (vector memory)
- Redis + RQ (async job queue); structlog (logging); `tenacity` (retry/backoff)
- Jinja2 templates + plain CSS custom properties for the web UI (not Next.js/Tailwind)
- Optional extras (`pyproject.toml [project.optional-dependencies]`): training (wandb, xformers), monitoring (Sentry, Prometheus), social (Twitter/X, Instagram, Bluesky), graph memory (FalkorDB), C2PA provenance, e2e (Playwright)

## Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements-full.txt && pip install -e .
alembic upgrade head
# or: uv sync --dev

# Run
python -m ai_artist.main                        # Autonomous (mood-based)
python -m ai_artist.main --theme "twilight"      # Themed
python -m ai_artist.main --mode auto             # Scheduled
uvicorn ai_artist.web.app:app --reload --port 8000

# CLI entry points (pyproject.toml [project.scripts])
lumira / lumira-web / lumira-worker / lumira-gallery / lumira-schedule

# Tests
pytest                                    # All tests (testpaths = tests, pytest.ini)
pytest tests/unit/test_moods.py           # Single file
pytest -k "test_critic"                   # Pattern match
pytest --cov=src/ai_artist tests/         # With coverage
pytest -m "not slow"                      # Skip slow tests
pytest tests/e2e -v --browser chromium    # E2E (needs playwright install)

# Lint & format -- ruff/black are not project deps in the venv; uvx fetches them
uvx ruff check src/ tests/ --fix
uvx black src/ tests/
uv run mypy src/ --ignore-missing-imports   # mypy IS a dev dependency
pre-commit run --all-files

# Migrations
alembic revision --autogenerate -m "description" && alembic upgrade head

# Docker
docker-compose up -d                          # Standard
docker-compose -f docker-compose.gpu.yml up   # GPU support
```

Three requirements files, deliberately different subsets of `pyproject.toml` (issue #59, closed,
fixed the original drift; keep them in sync manually going forward): `requirements-full.txt`
(full ML install, mirrors pyproject exactly), `requirements-gallery.txt` (web + DB + cloud
generation, no ML -- what Railway's `Dockerfile.gallery` installs), `requirements.txt` (minimal
web/API only, no DB, no generation).

## Layout (`src/ai_artist/`)

- `personality/` -- mood system (10 states), 3-layer memory (episodic/semantic/working), ReAct
  cognition, inner critic/dialogue, vector memory (ChromaDB)
- `core/` -- generation backends: SDXL (`generator.py`), FLUX (`flux_generator.py`), Replicate
  (`replicate_generator.py`), ControlNet, IP-Adapter, inpainting, upscaling, face restoration;
  `model_pool.py` for pre-warmed model caching
- `curation/` -- CLIP scoring (`curator.py`), AGIQA perceptual scoring, ensemble evaluation
- `intelligence/` -- creative mind, desire engine, narrative generation
- `web/` -- FastAPI app; `app.py` is the entrypoint and mounts every router (see Routes);
  WebSocket in `websocket.py`; middleware in `middleware.py`
- `db/` -- SQLAlchemy models (`GeneratedImage`, `TrainingSession`, `GalleryLike/Comment/Share`, `GalleryCollection`) and `session.py`
- `queue/` -- Redis job queue (RQ); worker in `worker.py`, CLI in `cli.py`
- `learning/` -- multi-armed bandit adaptive learning; `scheduling/` -- APScheduler cycles
- `prompts/`, `utils/` (config, logging, prompt engine, presets), `training/` (LoRA), `memory/` (FalkorDB graph), `social/`, `monitoring/`
- `config/` -- `config.yaml`, `style_presets.json`, `lora_models.json`, `wildcards/*.txt`
- `alembic/` -- migrations (`alembic.ini`); `tests/` -- `unit/`, `integration/`, `e2e/`

## Web routes (verified against `app.py` router mounts)

`/api/lumira` (personality & generation), `/api/gallery`, `/api/prompt`, `/api/feedback`,
`/admin` (gated by `require_api_key`), `/ws` (WebSocket), `/static`. **Not** under `/api`:
`/health`, `/health/live`, `/health/ready` (Kubernetes probes) and `/metrics` (gated by
`require_api_key`) -- both are mounted bare, unlike every other router.

## Conventions

- Async: all FastAPI routes are async; file I/O uses `aiofiles`
- Pydantic V2 for config/API models; `pydantic-settings` loads `config.Config` from `.env` +
  `config/config.yaml` (nested delimiter `__`)
- Type hints targeted at 100% coverage, Google-style docstrings, `disallow_untyped_defs = true`
- `tenacity` `@retry` with exponential backoff for external API calls
- Secrets held as `SecretStr` -- access via `.get_secret_value()`, never logged directly
- structlog throughout (`get_logger(__name__)`); gallery manager via `dependencies.py`
  (`GalleryManagerDep`); DB sessions via `db/session.py` (`get_db`)
- Formatting: Black (line-length 88), Ruff (`select = ["E","W","F","I","B","C4","UP","SIM"]`,
  ignores `E501`/`B008`/`UP042`; `web/app.py` also ignores `E402`), isort (black profile)
- Pre-commit: Black, Ruff, isort, mypy, bandit, pip-audit, markdownlint
- Commits: Conventional commits; branches: `feature/`, `fix/`, `docs/`, `refactor/`, `test/`
- `src/` layout (`[tool.setuptools] package-dir`)
- Before editing any UI/template: read `design-system.txt` (CSS custom-property token index for
  the Jinja templates; philosophy in `.impeccable.md`). Reuse the named CSS vars, never
  introduce an ad-hoc hex value.

## Testing

pytest with `pytest-asyncio` (`asyncio_mode = auto`), `pytest-mock`, `pytest-cov`,
`pytest-timeout`. Config lives in `pytest.ini` (single source of truth -- `pyproject.toml`
deliberately has no `[tool.pytest.ini_options]`). Markers: `slow`, `integration`, `unit`, `e2e`.
Layout mirrors `tests/unit/`, `tests/integration/`, `tests/e2e/`; root `conftest.py` adds `src/`
to `sys.path`. Redis mocked via `fakeredis`. CI (GitHub Actions, `uv sync --dev`) runs lint ->
test (matrix: Python 3.11/3.12 x ubuntu/macos, excludes slow+e2e) -> integration/e2e (main only)
-> security (Safety + Bandit) -> build.

## Env vars

Names confirmed via `os.getenv`/`os.environ` in source plus deploy vars documented in
`railway.toml`:

- `RAILWAY_API_KEY` -- fail-closed auth on generation/admin routes (gallery browsing stays public without it; those routes return 503)
- `MAGICA_API_KEY`, `MAGICA_BASE_URL`, `REPLICATE_API_TOKEN`, `ANTHROPIC_API_KEY` -- generation and AI providers
- `ALLOWED_ORIGINS`, `UNSPLASH_ACCESS_KEY`, `UNSPLASH_SECRET_KEY`, `REDIS_URL`, `FALKORDB_PASSWORD` -- infra/service config
- `LUMIRA_AUTO_SOUNDTRACK`, `LUMIRA_AUTO_VIDEO` -- pair new artwork with generated audio/video
- `TWITTER_API_KEY`/`TWITTER_API_SECRET`/`TWITTER_ACCESS_TOKEN`/`TWITTER_ACCESS_SECRET`/`TWITTER_BEARER_TOKEN`, `INSTAGRAM_USERNAME`/`INSTAGRAM_PASSWORD`/`INSTAGRAM_SESSION_FILE`, `BLUESKY_HANDLE`/`BLUESKY_PASSWORD` -- social posting
- `LUMIRA_DEV_MODE`, `DEBUG` -- local-dev auth bypass, never enable in production
- `LUMIRA_AI_KILL_SWITCH`, `LUMIRA_DAILY_SPEND_USD_MAX`, `LUMIRA_MAGICA_COST_PER_IMAGE_USD`, `LUMIRA_MAGICA_DAILY_MAX_IMAGES`, `LUMIRA_REPLICATE_COST_PER_IMAGE_USD`, `LUMIRA_REPLICATE_DAILY_MAX_IMAGES` -- spend guards
- `LUMIRA_PORT`/`PORT`, `WS_MAX_CONNECTIONS`, `LUMIRA_MAX_CONCURRENT_GENERATIONS`, `LUMIRA_MAX_QUEUE_DEPTH`, `LUMIRA_JOB_MAX_RETRIES`, `LUMIRA_MIN_FREE_DISK_MB`, `LUMIRA_SCHEDULER_PERSIST`, `LUMIRA_SESSION_RETRY`, `LUMIRA_AUTONOMOUS_CREATE`, `LUMIRA_AUTONOMOUS_INTERVAL_MIN`, `LUMIRA_FORCE_LOCAL_WEB`, `LUMIRA_MODERATION_ENABLED`, `TESTING` -- runtime tuning

Most non-secret settings (model backend, device, generation defaults, database URL) live in
`config/config.yaml` loaded through the nested `Config` (pydantic-settings, delimiter `__`), not
as flat env vars -- verify against `src/ai_artist/utils/config.py` before assuming a bare
`MODEL_ID`/`DEVICE`/`DATABASE_URL` env var controls something.

## Gotchas

- `AIArtist` (`main.py`) is the central orchestrator: mood, thinking, critic, memory, generator,
  curator, gallery. 10 moods (Contemplative, Chaotic, Melancholic, Energized, Rebellious,
  Serene, Restless, Playful, Introspective, Bold) drive model selection and prompts.
- `uvx` fetches ruff/black on demand -- they are not installed in the project venv, so a bare
  `ruff`/`black` reports "command not found" there. mypy IS a dev dependency and runs against
  the project environment instead.
- Health/metrics routes are NOT under `/api`, unlike every other router -- a past version of
  this doc had this backwards; verify route prefixes in the router files, not from memory.
- `requirements-gallery.txt`, not `requirements.txt`, is the Railway-parity "gallery-only" file.
- `[tool.uv] override-dependencies` in `pyproject.toml` pins several packages ahead of their
  direct dependents for stated CVE/compatibility reasons -- read the inline comments before
  changing what looks like a conflicting pin.
- Railway deploy uses `Dockerfile.gallery` specifically; the full-ML `Dockerfile`/`Dockerfile.gpu`
  don't fit Railway's no-GPU, size-limited environment. Health check path is `/health`.
