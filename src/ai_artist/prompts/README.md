# Prompt Collections Module

This module contains pre-defined prompt collections for Lumira image generation.

## Status: Unused / Future Feature

⚠️ **This module is currently not integrated into the main application.**

It was created as a potential prompt library but is not currently used by the autonomous
generation system, which creates prompts dynamically based on:

- Trends analysis
- Mood/personality states
- Previous artwork feedback
- Creative cognition

## Collections Available

- **artistic**: Creative styles and abstract concepts (impressionist, cubist, etc.)
- **artistic2**: Modern art movements and experimental techniques
- **expanded**: Fresh creative prompts (cinematic, emotional, nature)
- **ultimate**: Comprehensive diverse prompts across many themes

## Potential Future Uses

1. **Inspiration Source**: Could be integrated into the cognition module as an additional
   inspiration source when creativity is low
2. **Batch Generation**: Could be used for generating test/sample artwork collections
3. **User-Initiated Generation**: Could be exposed via API for users to select from
   pre-defined artistic styles
4. **Training Data**: Could be used to generate training data for LoRA models

## Integration Example

```python
from ai_artist.prompts import get_collection_prompts, COLLECTION_METADATA

# Get all artistic prompts
prompts = get_collection_prompts("artistic")

# Use in autonomous system
if inspiration_needed:
    collection = random.choice(list(COLLECTIONS.keys()))
    prompts = get_collection_prompts(collection)
    # Mix with current mood/trends...
```

## Decision: Keep or Remove?

**Recommendation**: Keep for now as a well-structured future feature.

- Total size: ~500 lines across 5 files
- Well-documented and organized
- Could be valuable for future features
- No maintenance burden (static data)

If you want to remove it to simplify the codebase, it can be safely deleted as it has
no dependencies and nothing imports it.
