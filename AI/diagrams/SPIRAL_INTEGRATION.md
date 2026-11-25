# Spiral Integration - Decision Record

Written 2026-11-25, replacing the Magica integration (Magica API shuts down 2026-12-01).
Snapshot; verify against code if HEAD moved.

## What Spiral is

Hosted multi-provider generative-media API (https://api.spiral.ai). One run endpoint
takes a `(provider, model)` pair plus an `input` object validated against that model's
schema. Unknown input fields are rejected (`INVALID_INPUT`), so each model family has its
own input builder. There is no sub-model parameter: the model id selects the variant.

## REST contract (verified against the OpenAPI spec and `inspect`, 2026-11-25)

- Auth: `Authorization: Bearer $SPIRAL_API_KEY`
- Start: `POST /v1/runs` body `{provider, model, input}` + `Idempotency-Key` header (fresh uuid4
  per run) -> run object, id at `.id`
- Poll: `GET /v1/runs/{id}?wait_seconds=N` (long-poll, 0-60) until `status` is
  `completed` / `failed` / `canceled` (lowercase)
- Outputs: `output.items[]` of `{type, url, mime_type, ...}`; links expire after 30 days, so
  the runtime downloads and stores the bytes
- Errors: `application/problem+json` with `code` and `retryable`; `402 INSUFFICIENT_BALANCE`
  when the account balance is empty

## Model mapping (Magica node -> Spiral provider/model)

| Old Magica node | Spiral provider/model | Note |
|---|---|---|
| `nano_banana_pro` | `fal/fal-ai/nano-banana-pro` | default image model |
| `nano_banana_2` | `fal/fal-ai/nano-banana-2` | |
| `flux_2_max` | `fal/fal-ai/flux-2-max` | no `num_images`: one run per image |
| `gpt_image_2` | `fal/openai/gpt-image-2` | |
| `grok_imagine_image` | `fal/xai/grok-imagine-image` | no `seed` |
| `elevenlabs_music` | `elevenlabs/music` | `music_length_ms`, `force_instrumental`; no `seed` with a prompt |
| `lyria3_pro` | `fal/fal-ai/lyria3/pro` | prompt only; no duration or seed |
| `kling_v3_pro` | `fal/fal-ai/kling-video/v3/pro/text-to-video` | `duration` is a string; no `seed` |
| `veo_3_1` | `gemini/gemini-omni-1.2-flash` | GAP: Spiral has no Veo 3.1; closest Google video model |
| `sora_2` | `fal/bytedance/seedance-2.0/text-to-video` | GAP: Spiral has no Sora 2; closest cinematic model |

## Code

- `core/spiral_client.py` - REST client (start run, long-poll, download, problem+json errors)
- `core/spiral_generator.py` - `SpiralGenerator`, `SPIRAL_MODELS`, `SPIRAL_MOOD_MODELS`,
  per-family `_build_model_input`, spend guard key `spiral`
- `core/spiral_media.py` - `SpiralAudioGenerator` / `SpiralVideoGenerator`, spend guard keys
  `spiral_audio` / `spiral_video`
- `core/generator_factory.py` - backend `spiral` (preferred when `SPIRAL_API_KEY` is set and
  config still says `local`)
- Studio APIs: `POST /api/lumira/soundtrack`, `POST /api/lumira/video`

## Env vars

`SPIRAL_API_KEY`, `SPIRAL_BASE_URL` (default `https://api.spiral.ai`),
`LUMIRA_SPIRAL_DAILY_MAX_{IMAGES,AUDIO,VIDEO}`, `LUMIRA_SPIRAL_COST_PER_IMAGE_USD`,
`LUMIRA_SPIRAL_{AUDIO,VIDEO}_COST_PER_ITEM_USD`.

## Status

- [x] Client, generators, factory, config literal, routes, tests migrated.
- [ ] Live validation: NOT done. The Spiral balance was $0 when this landed, so only mocked
      HTTP tests cover the run path. Run one image, one audio, and one video before relying on it.
- [ ] Confirm output item `type` values (`image` / `audio` / `video`) on a live run. The client
      also matches on `mime_type` prefix as a backstop.

## Repo hygiene (flagged, NOT changed — your call)

`data/*.json` (memory, mood_history, adaptive_learning, thematic_series) and
`data/vector_memory/*/data_level0.bin` are **runtime state, git-tracked, and churn every
run**. `.gitignore` only ignores `data/*.db`. Decide: keep versioned (seed state) or
untrack via `git rm --cached` + add to `.gitignore`. Not changed here — untracking committed
files is a versioning decision for you, not a silent edit. Also one staged deletion:
`.claude/cache/agents/research-agent/latest-output.md` (cache file, safe to drop).
