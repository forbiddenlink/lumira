# Magica Integration — Decision Record

Written against: `90005dd` (main, 2026-07-28). Snapshot; verify against code if HEAD moved.

## What Magica is

Hosted multi-model generative-media service (Galaxy AI). Models span:

- **image**: `flux_2_max`, `nano_banana_pro`, `nano_banana_2`, `gpt_image_2`, faceswap, `topaz_upscale`, bg-remover
- **video**: `sora_2` / `sora_2_pro`, `veo_3_1`, `kling_v3_pro`, `seedance_2_0`
- **audio**: `elevenlabs` (music / tts / sfx / dubbing), `lyria3_pro`, `minimax` tts / voice-clone
- **llm**: claude / gpt / gemini / grok

Node-graph workflows + one-shot `execute_tool`. Account has an active subscription and
large credit balance as of 2026-07-28.

## Two access paths (both real)

Magica exposes **two parallel surfaces**, confirmed 2026-07-28:

1. **Claude-side MCP server** (`/api/mcp`) — what this Claude session drives. Auth rides the
   MCP session. Playbook rule #1: *never invent a modelId / schema field / voice_id* — pin
   ids via `get_model_schema` / `search_media`.
2. **Public REST developer API** (`https://api.magica.com/api`, version `/v1`) — Bearer
   `MAGICA_API_KEY`, docs at magica.com/docs. This is what the Lumira runtime calls.
   Verified endpoints:
   - `POST /v1/nodes/{nodeType}/run`  body `{"input": {...}}`  -> `{"runId": ...}`
   - `GET  /v1/nodes/runs/{runId}`  -> poll to `COMPLETED` / `FAILED` / `CANCELED`
   - `GET  /v1/credits/balance`  (budget)
   - OpenAPI 3.1 spec published (import for a typed SDK).

The `nodeType` is the same id the MCP uses (e.g. `nano_banana_pro`) — the MCP
`execute_tool` response even returns `"nodeType"`. So the two surfaces line up: pin/verify
models via MCP, run in production via REST.

### Pattern A — Claude-orchestrated asset pipeline (available now)

Claude (this MCP session) drives Magica as Lumira's "hands": generate mood-themed images /
video / music via `search_tools -> get_model_schema -> get_pricing -> execute_tool ->
poll_run_status`, download the assets, drop them into the gallery. Good for batch art drops,
mood explorations, and adding video/audio media Lumira cannot make itself. Runs offline /
interactively, not inside the autonomous loop.

Proven 2026-07-28: generated a real gallery-quality Lumira "melancholic" oil painting via
`nano_banana_pro` (2400x1792) end-to-end through the MCP — `execute_tool` -> `poll_run_status`
-> download. Note: keyword `search_tools` did not surface the image catalog headlessly, but
`get_model_schema("nano_banana_pro")` + `execute_tool` worked directly with the node id.

### Pattern B — runtime backend (BUILT, gated behind MAGICA_API_KEY)

`core/magica_generator.py` — a third backend behind the factory, calling the REST API
above. Signature-compatible with `ImageGenerator`/`ReplicateGenerator`. With no
`MAGICA_API_KEY` it raises (same as Replicate). End-to-end REST run is untested until a key
is set; request/response shapes follow the documented contract + MCP-verified node schemas.
Enable with `config.model.backend = "magica"`.

## What was built (2026-07-28)

The "do it right, not by import-alias" seam the runtime was missing, plus the Magica backend:

- `core/generator_factory.py` — `get_image_generator(backend, model_id, device, dtype)`.
  Routes `config.model.backend` -> `local` / `replicate` / `magica`. Unknown/empty ->
  local with a warning.
- `core/magica_generator.py` — `MagicaGenerator` REST client (start-run -> poll ->
  download -> PIL), `MAGICA_MODELS` name->nodeType map, `_check_magica_budget()` daily
  backstop, `MAGICA_API_KEY` gate.
- `config.py` — `ModelConfig.backend: Literal["local","replicate","magica"] = "local"`
  (default preserves prior hardwired-local behavior).
- `queue/worker.py` — the RQ image job now constructs via the factory (was hardwired
  `ImageGenerator`). This is the natural remote ride-along point: remote calls are
  I/O-bound and the queue already handles priority / backpressure / progress meta.
- Tests: `test_generator_factory.py` (7) + `test_magica_generator.py` (7) = 14, passing.
  Cover routing/fallback/dtype + node-type resolution, key gate, budget guard, aspect/res
  mapping, and mocked start-run -> poll -> download happy/fail paths.

`main.py:127` (autonomous loop) intentionally left on local `ImageGenerator`: it does
local-only post-construct setup (refiner / LoRA / ControlNet). Remote generation belongs on
the async queue path, not the GPU loop.

## Pattern B checklist — status

- [x] REST base URL + auth contract confirmed (magica.com/docs).
- [x] `core/magica_generator.py` (REST client, MAGICA_MODELS, budget guard, key gate).
- [x] `"magica"` in `ModelConfig.backend` Literal + factory routing branch.
- [x] Unit tests: routing + key-refusal + budget-refusal (the intent-test half).
- [x] Per-model input adapter (`_build_model_input`): Nano Banana uses
      `resolution`+`aspect_ratio`, FLUX 2 uses `image_size`; verified via `get_model_schema`.
- [x] Per-mood model diversity: `MAGICA_MOOD_MODELS` + `model_for_mood()` (nano/flux/gpt/grok).
- [x] `sub_model_id` plumbing (top-level in the run request) for multi-mode nodes.
- [x] **Live REST validation** (2026-07-28) — `MAGICA_API_KEY` set in `~/.secrets` + `.env`;
      a real `backend=magica` gen returned a 1024×1024 image. Caught + fixed a real bug: run
      status returns URLs at `output.result`, not top-level `assets[]` (see `_extract_urls`).
      To use: `config.model.backend = "magica"` (or pass `backend` in the RQ job params).
- [ ] Optional: add `MAGICA_API_KEY` to `APIKeysConfig` as `SecretStr` (currently read from
      env like `ReplicateGenerator`, deliberately consistent).
- [ ] Consider a live routing-test matrix before enabling in prod (per agent-intent-tests rule).

## New modalities (video / audio)

Lumira is image-only in-runtime; video exists only as moviepy slideshow assembly
(`utils/video.py`), no audio generation anywhere. Magica adds both:
**video** (`sora_2`/`veo_3_1`/`kling_v3_pro`) and **music/sfx** (`elevenlabs_music`/`lyria3_pro`).

- **Proven via Pattern A (Claude-driven MCP):** generated a mood-matched melancholic
  instrumental (`elevenlabs_music`, 30s) to accompany the demo painting — see
  `gallery/magica_demo/`. Note: `lyria3_pro` (Google Vertex) 400'd on a policy block for the
  same prompt; `elevenlabs_music` is the more permissive default.
- **Runtime wire is a separate workstream:** `MagicaGenerator` returns `list[PIL.Image]`, so
  audio/video need a sibling class (e.g. `MagicaAudioGenerator` returning file bytes/paths)
  and a non-image call path — not the image factory. Scope on its own.

## Repo hygiene (flagged, NOT changed — your call)

`data/*.json` (memory, mood_history, adaptive_learning, thematic_series) and
`data/vector_memory/*/data_level0.bin` are **runtime state, git-tracked, and churn every
run**. `.gitignore` only ignores `data/*.db`. Decide: keep versioned (seed state) or
untrack via `git rm --cached` + add to `.gitignore`. Not changed here — untracking committed
files is a versioning decision for you, not a silent edit. Also one staged deletion:
`.claude/cache/agents/research-agent/latest-output.md` (cache file, safe to drop).
