# Lumira Major Enhancements Plan

**Created:** 2026-02-01
**Status:** Phases 1-4 Complete (Core Technical Enhancements Done)

## Overview

This plan implements the highest-impact improvements identified through codebase analysis and industry research. Focus areas: modern model support, reference image capabilities, enhanced ControlNet, and async job queue architecture.

---

## Phase 1: FLUX.2 Model Support

**Goal:** Add Black Forest Labs' FLUX.2 model as an option alongside SDXL.

**Why:** FLUX.2 is the 2025-2026 production standard with superior quality and text rendering.

### Tasks

- [x] 1.1 Add `flux` optional dependency group to pyproject.toml
- [x] 1.2 Create `src/ai_artist/core/flux_generator.py` with FluxGenerator class
- [x] 1.3 Update model_pool.py to support FLUX model preloading
- [x] 1.4 Add FLUX routing in mood-based model selection
- [x] 1.5 Create FLUX-specific prompt enhancement (FLUX prefers detailed prompts)
- [x] 1.6 Add unit tests for FluxGenerator

**Files to create/modify:**
- `pyproject.toml` - Add flux dependencies
- `src/ai_artist/core/flux_generator.py` - New file
- `src/ai_artist/core/model_pool.py` - Add FLUX support
- `src/ai_artist/personality/moods.py` - FLUX model routing
- `tests/unit/test_flux_generator.py` - New tests

---

## Phase 2: IP-Adapter Integration

**Goal:** Enable reference image-based style transfer without retraining.

**Why:** Essential for character/style consistency across generations.

### Tasks

- [x] 2.1 Add ip-adapter dependencies to pyproject.toml
- [x] 2.2 Create `src/ai_artist/core/ip_adapter.py` with IPAdapterMixin
- [x] 2.3 Integrate IP-Adapter into ImageGenerator
- [x] 2.4 Add reference image upload to web API
- [x] 2.5 Create memory integration (Aria remembers preferred styles)
- [x] 2.6 Add unit tests for IP-Adapter

**Files to create/modify:**
- `pyproject.toml` - Add ip-adapter
- `src/ai_artist/core/ip_adapter.py` - New file
- `src/ai_artist/core/generator.py` - Integration
- `src/ai_artist/web/aria_routes.py` - API endpoints
- `tests/unit/test_ip_adapter.py` - New tests

---

## Phase 3: Enhanced ControlNet for SDXL

**Goal:** Full ControlNet support with multiple preprocessors for SDXL.

**Why:** Current implementation is SD 1.5 only with just Canny edges.

### Tasks

- [x] 3.1 Add controlnet-aux dependency for preprocessors
- [x] 3.2 Expand ControlNetPreprocessor with depth, pose, lineart, softedge
- [x] 3.3 Create StableDiffusionXLControlNetPipeline integration
- [x] 3.4 Add multi-ControlNet support (combine pose + depth)
- [x] 3.5 Create web UI for ControlNet selection
- [x] 3.6 Add integration tests for ControlNet

**Files to create/modify:**
- `pyproject.toml` - Add controlnet-aux
- `src/ai_artist/core/controlnet.py` - Expand preprocessors
- `src/ai_artist/core/generator.py` - SDXL ControlNet
- `src/ai_artist/web/templates/*.html` - UI updates
- `tests/integration/test_controlnet.py` - New tests

---

## Phase 4: Redis Job Queue Architecture

**Goal:** Transform sync generation to async job queue for scalability.

**Why:** Enables horizontal scaling, 50ms API responses, better UX.

### Tasks

- [x] 4.1 Add rq (Redis Queue) dependency
- [x] 4.2 Create `src/ai_artist/queue/job_queue.py` with GenerationQueue
- [x] 4.3 Create `src/ai_artist/queue/worker.py` for GPU workers
- [x] 4.4 Create job status API endpoints
- [x] 4.5 Update WebSocket to stream job progress
- [x] 4.6 Add worker CLI command
- [x] 4.7 Add Docker compose for Redis + workers
- [x] 4.8 Add integration tests for queue

**Files to create/modify:**
- `pyproject.toml` - Add rq
- `src/ai_artist/queue/__init__.py` - New module
- `src/ai_artist/queue/job_queue.py` - Queue manager
- `src/ai_artist/queue/worker.py` - Worker process
- `src/ai_artist/web/aria_routes.py` - Job status API
- `docker-compose.yml` - Add Redis service
- `tests/integration/test_queue.py` - New tests

---

## Phase 5: Community Gallery

**Goal:** Public gallery with sharing, search, and social features.

**Why:** User engagement drives growth; AI art market projected $40.4B by 2033.

### Tasks

- [ ] 5.1 Create gallery database models (likes, comments, shares)
- [ ] 5.2 Create public gallery API endpoints
- [ ] 5.3 Add search/filtering by tags, mood, style
- [ ] 5.4 Create share functionality (unique URLs)
- [ ] 5.5 Add user profiles (optional, anonymous by default)
- [ ] 5.6 Create gallery web UI with infinite scroll
- [ ] 5.7 Add daily/weekly featured artwork

**Files to create/modify:**
- `src/ai_artist/models/gallery.py` - New models
- `src/ai_artist/web/gallery_routes.py` - New API
- `src/ai_artist/web/templates/gallery.html` - New UI
- `tests/unit/test_gallery.py` - New tests

---

## Implementation Order

1. **Phase 1** (FLUX) - Foundation for modern generation
2. **Phase 2** (IP-Adapter) - Style consistency
3. **Phase 3** (ControlNet) - Structural control
4. **Phase 4** (Job Queue) - Scalability
5. **Phase 5** (Gallery) - Community engagement

Each phase is independent and can be merged separately.

---

## Success Metrics

- [ ] FLUX.2 generates images with text rendering
- [ ] IP-Adapter maintains character consistency
- [ ] ControlNet works with SDXL + multiple preprocessors
- [ ] Job queue handles 100 concurrent requests
- [ ] Gallery loads in <2s with 1000+ images
