# Lumira - Autonomous AI Artist

An autonomous AI artist with personality, moods, memory, and creative independence.

## ✨ What Makes Lumira Different

Lumira isn't a tool - she's an **artist** you collaborate with:

- **Has Moods**: 10 emotional states that influence her art
- **Remembers**: Episodic + semantic memory learns what works
- **Reflects**: Journals her thoughts after each creation (visible thinking with ReAct pattern)
- **Chooses**: Makes autonomous decisions about what to paint
- **Evolves**: Artistic style develops through experience and adaptive learning
- **Ethical AI**: Built-in bias mitigation to ensure fair and diverse output
- **Production-Ready**: 10x faster generation, PWA support, real-time monitoring

## 🚀 Performance Highlights

- ⚡ **10x Faster**: First generation in 3-5s (was 35s) with model pool preloading
- 🎯 **Smart Curation**: GPU-parallel batch processing (3x faster quality scoring)
- 🧠 **Adaptive Learning**: Multi-armed bandit algorithm learns from user feedback
- 📱 **Progressive Web App**: Install as native app, works offline
- 🔴 **Real-time Preview**: WebSocket streaming shows generation progress
- 📊 **Production Monitoring**: Prometheus metrics + health checks for Kubernetes

## Quick Start

```bash
# Clone and setup
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

## Project Structure

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

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **[LUMIRA.md](LUMIRA.md)** | Full personality system & roadmap |
| **[QUICKSTART.md](QUICKSTART.md)** | Step-by-step setup guide |
| **[SETUP.md](SETUP.md)** | Detailed installation |
| **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** | Common issues |
| **[LORA_GUIDE.md](LORA_GUIDE.md)** | Custom style training |
| **[docs/PHASE1_IMPLEMENTATION_SUMMARY.md](docs/PHASE1_IMPLEMENTATION_SUMMARY.md)** | ⭐ **All 4 enhancement phases complete** |
| **[docs/EXTERNAL_TOOLS_EVALUATION.md](docs/EXTERNAL_TOOLS_EVALUATION.md)** | External tool recommendations |
| **[docs/WEBSOCKET.md](docs/WEBSOCKET.md)** | Real-time updates guide |
| **[docs/API.md](docs/API.md)** | API documentation |
| **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** | Production deployment |
| **[docs/](docs/)** | Full technical documentation |

## 📊 Current Status

**✅ Completed (76% - Production Ready):**

**Personality & Intelligence:**

- 10-mood personality system with dynamic state
- 3-layer memory (episodic/semantic/working)
- Visible thinking process (ReAct pattern - observe/reflect/decide/express/create)
- Adaptive learning from user feedback (multi-armed bandit)
- Critique system for iterative improvement

**Performance & Scale:**

- Model pool with pre-warming (10x faster first generation)
- GPU-parallel batch curation (3x faster quality scoring)
- Kubernetes-ready health checks (liveness/readiness)
- Prometheus metrics (15+ production metrics)

**User Experience:**

- Progressive Web App (PWA) with offline support
- Real-time generation preview via WebSocket
- Modern, accessible dark UI with animations
- Autonomous scheduling
- FastAPI web gallery with WebSocket
- Service worker caching (3-tier strategy)

**Quality & Safety:**

- CLIP-based quality curation
- Ensemble curation framework
- Bias mitigation in prompt generation
- Intelligent prompt filtering
- Advanced prompt features (Matrix, Emphasis, Style Presets)
- Comprehensive test coverage (400+ tests)

**📈 In Progress (24%):**

- Type annotations to 100% (currently 85%)
- Redis caching layer,
[docs/PHASE1_IMPLEMENTATION_SUMMARY.md](docs/PHASE1_IMPLEMENTATION_SUMMARY.md) for all enhancements,
and [docs/ADVANCED_PROMPTS.md](docs/ADVANCED_PROMPTS.md) for prompt utilities.

## 🛠️ Tech Stack

**Core:**

- Stable Diffusion XL (diffusers + xFormers + SDPA)
- LoRA for style training
- PyTorch with torch.compile optimization

**Backend:**

- FastAPI + WebSocket for real-time updates
- SQLite + SQLAlchemy
- CLIP for quality curation
- Multi-armed bandit for adaptive learning

**Frontend:**

- Progressive Web App (PWA)
- Service Worker with 3-tier caching
- Modern responsive UI with WebSocket streaming

**Production:**

- Prometheus metrics
- Kubernetes health checks
- Sentry error tracking
- Comprehensive logging (structlog)
- Stable Diffusion (diffusers)
- LoRA for style training
- FastAPI + WebSocket
- SQLite
- CLIP for curation

## License

MIT License
