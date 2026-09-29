# Development Roadmap

The phase descriptions and counts below are historical milestones. For current
priorities and verification status, see **Next Immediate Steps**.

## Project Vision

Build an autonomous AI artist that creates unique artwork with style consistency, automated scheduling, and continuous improvement through LoRA fine-tuning.

---

## ✅ Completed Phases

### Phase 0: Foundation

**Status**: Complete | **Completed**: January 2026

- [x] Project structure and configuration
- [x] Core documentation
- [x] Git version control with pre-commit hooks
- [x] Legal and security guidelines

### Phase 0.5: Quick Wins

**Status**: Complete | **Completed**: January 2026

**Features**:

- [x] CLIP-based curation (generate 3, save best)
- [x] Enhanced prompts with artistic style modifiers
- [x] Progress indicators during generation
- [x] Gallery viewer CLI tool
- [x] Testing framework (38 passing tests, 45% coverage)
- [x] Structured logging with structlog

### Phase 2: LoRA Training Infrastructure

**Status**: Complete | **Completed**: January 2026

**Features**:

- [x] Full LoRA training script with accelerate/peft
- [x] Comprehensive documentation (LORA_TRAINING.md)
- [x] Legal data sourcing guide
- [x] Auto-load trained LoRA from config
- [x] DreamBooth dataset implementation

**Performance**:

- Apple Silicon: 20-40 min for 2000 steps
- NVIDIA GPU: 10-20 min for 2000 steps

### Phase 3: Automation System

**Status**: Complete | **Completed**: January 2026

**Features**:

- [x] CreationScheduler with AsyncIOScheduler
- [x] Topic rotation (8 themes)
- [x] CLI tool: `lumira-schedule`
- [x] Multiple schedule types (daily, interval, weekly, cron)
- [x] Batch creation support
- [x] Job management (add, list, remove)

**Test Coverage**: 16/17 tests passing (94%)

---

## 🔄 Current Phase

### Phase 1: Enhanced Logging & Observability

**Status**: Complete | **Completed**: January 2026

**Features**:

- [x] Replaced all print() statements with structured logs
- [x] Request ID tracking with contextvars
- [x] Performance metrics with PerformanceTimer
- [x] JSON logging for production
- [x] Log rotation (10MB max, 5 backups)
- [x] Comprehensive logging across all modules

**Technical Stack**: structlog (already installed)

**Success Criteria**:

- All modules use structured logging
- Performance metrics tracked
- JSON logs in production mode
- Request IDs in all operations

### Phase 1.5: Testing Improvements

**Status**: Complete | **Completed**: January 2026

**Goals**:

- [x] Increase test coverage from 52% to 58%
- [x] Add comprehensive tests for generator.py (19% → 84%)
- [x] Add tests for main.py initialization (16% → 62%)
- [x] Improve code quality and reliability

**Results**:

- Total test coverage: 58% (856 lines, 362 missing)
- Generator coverage: 84% (was 19%)
- Main coverage: 62% (was 16%)
- 51 tests passing (1 skipped: CLIP download)

**Files with High Coverage**:

- models.py: 100%
- gallery/manager.py: 100%
- config.py: 100%
- logging.py: 96%
- scheduler.py: 88%
- generator.py: 84%
- unsplash.py: 83%

---

## ✅ Recently Completed

### Phase 5: Web Gallery Interface

**Status**: Complete | **Completed**: January 2026

**Note**: Skipped Phase 4 (Social Media) - moved directly to Web Gallery

**Features**:

- [x] FastAPI backend for artwork browsing
- [x] Modern HTML/CSS frontend with dark theme
- [x] Gallery grid with filtering
- [x] Responsive design
- [x] Search by prompt keywords
- [x] Featured filter
- [x] Download functionality
- [x] Modal image viewer
- [x] WebSocket real-time updates
- [x] Modern middleware (error handling, logging, CORS)
- [x] Health check endpoints (/health, /health/ready, /health/live)
- [x] Dependency injection system
- [x] Exception handlers

**Technical Stack**: FastAPI, Jinja2 templates, vanilla JS, modern CSS

**Test Coverage**: Web module implemented (0% coverage - needs tests)

---

## 📋 Upcoming Phases

### Phase 6: Cloud Deployment

**Duration**: 2 weeks | **Start**: Week 7

**Goals**:

- [x] Docker containerization (including the lightweight gallery image)
- [x] CI/CD pipeline (GitHub Actions)
- [ ] Infrastructure as Code (Terraform)
- [ ] Cloud deployment (AWS/GCP/Azure)
- [ ] CDN for image delivery
- [ ] Monitoring and alerting

---

## 🚀 Future Enhancements

### Phase 7: Advanced Features

- Multi-model support (SD 2.1, SDXL)
- Video generation
- Style mixing
- NFT minting
- Print-on-demand

### Phase 8: AI Improvements

- Fine-tune aesthetic predictor
- Custom CLIP for style consistency
- Automatic prompt optimization
- Style evolution tracking

### Phase 9: Analytics Dashboard

- Artwork analytics
- Style trend analysis
- Engagement metrics
- Recommendation engine

---

## Timeline Overview

| Phase | Duration | Status | Completion |
|-------|----------|--------|------------|
| Phase 0 | Week 0 | ✅ Complete | Jan 2026 |
| Phase 0.5 | Week 0.5 | ✅ Complete | Jan 2026 |
| Phase 1 | Week 1 | ✅ Complete | Jan 2026 |
| Phase 1.5 | Week 1.5 | ✅ Complete | Jan 2026 |
| Phase 2 | Week 2 | ✅ Complete | Jan 2026 |
| Phase 3 | Week 3 | ✅ Complete | Jan 2026 |
| Phase 5 | Week 4-5 | ✅ Complete | Jan 2026 |
| **Phase 6** | **Week 6** | **📋 Next** | **Jan 2026** |
| Phase 4 | Week 7+ | 📋 Optional | Feb 2026 |

---

## Next Immediate Steps

### Reliability work completed locally (2026-09-18)

- Daily image counts and dollar totals no longer reset one another in the
  in-memory fallback; Redis reads use the authoritative micro-dollar counter.
- LLM calls atomically reserve estimated cost before contacting the provider.
  Returned token usage adjusts the original reservation. Failed calls or missing
  usage retain the estimate; uncertain Redis reservations block the LLM call.
  Concurrent first requests wait for Redis initialization to finish instead of
  prematurely switching to independent local counters.
- Image scoring runs in worker threads, with serialized access to the shared
  curator, so model loading and scoring do not block the web request loop.
- Regression checks cover concurrent spending, usage reconciliation, UTC-day
  rollover, provider failures, and worker-thread scoring. Reservations and
  reconciliation were also checked against temporary real Redis with a mocked
  provider.

Budget figures remain estimates using the existing token pricing model, not
provider billing guarantees. Without Redis, limits are process-local and reset
when that process restarts. Actual usage can exceed the pre-call estimate.

### Remaining validation and release work

1. **Verify the intended live deployment**
   - Confirm the target environment and an explicit spending allowance before
     a paid generation check.
   - Check health, authenticated creation, saved artwork, and restart persistence.
   - Keep unattended creation opt-in while checking the spending ledger.

2. **Verify optional integrations when needed**
   - FalkorDB graph queries require a running graph service.
   - Local CLIP/FLUX checks require downloaded models and suitable hardware.
   - Magica audio/video paths exist; paid output quality is not yet validated by
     these local checks. 3D generation remains deferred.

3. **Prepare the release**
   - Review the accumulated uncommitted studio, gallery, and persistence changes.
   - Commit the verified changes and confirm CI before deployment.
   - Verify monitoring and alerts against the selected deployment.

---

## Success Metrics

### Technical

- Uptime: >99.5%
- Test Coverage: >60%
- Generation Success: >95%
- Avg Generation Time: <60s (MPS)

### Product

- Daily Creations: 1-3 artworks
- Gallery Growth: 30+ artworks/month
- Style Consistency: >0.7 CLIP score

---

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute to this roadmap.
