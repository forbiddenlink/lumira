# Generator Backends

Snapshot as of 2026-07-28. Source: `src/ai_artist/core/`, `web/lumira_routes.py`, `queue/worker.py`.

Lumira's generation stage is duck-typed: any class exposing
`generate(prompt, ...) -> list[PIL.Image]` (plus `load_model()` / cleanup) can stand in.
Two concrete backends exist today; a hosted multi-model backend (Magica) is the planned third.

```mermaid
flowchart TD
    subgraph Callers
        Main["main.py:127<br/>autonomous loop"]
        Worker["queue/worker.py:116<br/>RQ jobs"]
        Web["web/lumira_routes.py<br/>x5 import-alias swap"]
    end

    Factory{{"get_image_generator(config)<br/>NEW · keyed off config.model.backend"}}
    Main --> Factory
    Worker --> Factory
    Web -.today: import-alias.-> Factory

    Factory -->|local| Local["ImageGenerator<br/>generator.py:62<br/>diffusers SDXL / FLUX · GPU"]
    Factory -->|replicate| Rep["ReplicateGenerator<br/>replicate_generator.py:78<br/>hosted API · REPLICATE_MODELS registry"]
    Factory -->|magica| Mag["MagicaGenerator<br/>magica_generator.py<br/>REST · MAGICA_MODELS · image (+video/audio future)"]

    Local --> Pool["ModelPool<br/>model_pool.py:24<br/>pipeline cache"]

    Mag -.->|gated: MAGICA_API_KEY| Note["REST built; live run untested until key set.<br/>See MAGICA_INTEGRATION.md"]
```

## Backend interface (duck-typed — no ABC yet)

| Method | local `ImageGenerator` | `ReplicateGenerator` | `MagicaGenerator` |
|--------|------------------------|----------------------|-----------------------------|
| `generate(prompt, ...) -> list[Image]` | ✅ `generator.py:471` | ✅ `replicate_generator.py:142` | ✅ `magica_generator.py` |
| `load_model()` | ✅ | ✅ | ✅ no-op (remote) |
| budget guard | n/a (local) | `_check_replicate_budget:52` | `_check_magica_budget` |
| model registry | `MoodModelConfig` `config.py:26` | `REPLICATE_MODELS:20` | `MAGICA_MODELS` |

## Selection

`config.model.backend` (`local` \| `replicate` \| `magica`, added 2026-07-28, default
`"local"`) selects the backend via `get_image_generator()` in `core/generator_factory.py`.
Behavior-preserving: unset -> local, matching prior hardwired behavior at `main.py:127` and
`worker.py:116`. `magica` requires `MAGICA_API_KEY`; see MAGICA_INTEGRATION.md.
