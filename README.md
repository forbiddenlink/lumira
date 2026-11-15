# Lumira - Autonomous AI Artist

**Live gallery:** [lumira-gallery-production.up.railway.app](https://lumira-gallery-production.up.railway.app)

An autonomous AI artist with personality, moods, memory, and creative independence. A
lightweight "gallery + cloud-generation" build (`Dockerfile.gallery`, no local ML/GPU,
generation via Replicate/Magica) deploys to Railway; see `docs/DEPLOYMENT.md`.

## What makes Lumira different

Lumira isn't a tool - she's an **artist** you collaborate with:

- **Has Moods**: 10 emotional states that influence her art
- **Remembers**: Episodic + semantic memory learns what works
- **Reflects**: Journals her thoughts after each creation (visible thinking with ReAct pattern)
- **Chooses**: Makes autonomous decisions about what to paint
- **Evolves**: Artistic style develops through experience and adaptive learning
- **Bias mitigation**: prompt-level bias mitigation (see `docs/BIAS_MITIGATION.md`)

## Performance and delivery

- **Model pool**: pre-warmed diffusion pipelines (`src/ai_artist/core/model_pool.py`).
- **Batch curation**: CLIP quality scoring in batches.
- **Adaptive learning**: a multi-armed bandit learns from user feedback.
- **Progressive Web App**: installable, with a service worker and three caches (static, dynamic, images; `static/service-worker.js`).
- **Real-time preview**: WebSocket streaming of generation progress.
- **Monitoring**: Prometheus metrics (`src/ai_artist/monitoring/metrics.py`) and health checks for Kubernetes.

## Quick start

Prerequisites: Python 3.11 or newer (`requires-python` in `pyproject.toml`; `.python-version` pins 3.14). The full install pulls in PyTorch and is meant for a machine with a GPU.

```bash
# Clone and setup
git clone https://github.com/forbiddenlink/lumira.git
cd lumira
python -m venv venv
source venv/bin/activate
pip install -r requirements-full.txt
pip install -e .

# Configure
cp config/config.example.yaml config/config.yaml

# Let Lumira create (she chooses based on mood)
python -m ai_artist.main

# Or suggest a theme
python -m ai_artist.main --theme "twilight dreams"

# Web gallery
python -m ai_artist.web.app
```

If you only want the web gallery (no ML generation), use:

```bash
pip install -r requirements.txt
pip install -e .
```

## Project structure

```text
lumira/
├── src/ai_artist/
│   ├── personality/    # Moods, memory, identity
│   ├── core/           # Image generation
│   ├── curation/       # CLIP-based quality scoring
│   ├── scheduling/     # Autonomous creation
│   └── web/            # FastAPI gallery
├── config/             # Configuration
├── gallery/            # Generated artwork
└── docs/               # Documentation
```

## Documentation

| Document | Purpose |
|----------|---------|
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | System architecture and design choices |
| **[docs/QUICKSTART.md](docs/QUICKSTART.md)** | Step-by-step setup guide |
| **[docs/SETUP.md](docs/SETUP.md)** | Detailed installation |
| **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** | Common issues |
| **[docs/LORA_GUIDE.md](docs/LORA_GUIDE.md)** | Custom style training |
| **[docs/WEBSOCKET.md](docs/WEBSOCKET.md)** | Real-time updates guide |
| **[docs/API.md](docs/API.md)** | API documentation |
| **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** | Production deployment |
| **[docs/ROADMAP.md](docs/ROADMAP.md)** | What's next |
| **[docs/](docs/)** | Full technical documentation |

## Current status

See `CLAUDE.md` for the maintained current-state summary (stack, commands, gotchas). Highlights:

- 10-mood personality system with dynamic state
- 3-layer memory (episodic/semantic/working)
- Visible thinking process (ReAct pattern - observe/reflect/decide/express/create)
- Adaptive learning from user feedback (multi-armed bandit)
- Critique system for iterative improvement

**Performance and scale:**

- Model pool with pre-warming
- Batch curation
- Kubernetes-ready health checks (liveness/readiness)
- Prometheus metrics

**User experience:**

- Progressive Web App (PWA) with offline support
- Real-time generation preview via WebSocket
- Modern, accessible dark UI with animations
- Autonomous scheduling
- FastAPI web gallery with WebSocket
- Service worker caching (3-tier strategy)

**Quality and safety:**

- CLIP-based quality curation
- Ensemble curation framework
- Bias mitigation in prompt generation
- Intelligent prompt filtering
- Advanced prompt features (Matrix, Emphasis, Style Presets)
- A large pytest suite (over 1,400 test functions under `tests/`)

See [docs/ROADMAP.md](docs/ROADMAP.md) for what's actively planned, and
[docs/ADVANCED_PROMPTS.md](docs/ADVANCED_PROMPTS.md) for prompt utilities.

## Tech stack

**Core:**

- Stable Diffusion XL and FLUX (diffusers; xFormers is an optional dependency); cloud generation through Replicate or Magica
- LoRA for style training
- PyTorch

**Backend:**

- FastAPI + WebSocket for real-time updates
- SQLite + SQLAlchemy
- CLIP for quality curation
- Multi-armed bandit for adaptive learning

**Frontend:**

- Progressive Web App (PWA)
- Service worker with three caches (static, dynamic, images)
- Modern responsive UI with WebSocket streaming

**Production:**

- Prometheus metrics
- Kubernetes health checks
- Sentry error tracking
- Comprehensive logging (structlog)

## License

MIT. See [LICENSE](LICENSE).
