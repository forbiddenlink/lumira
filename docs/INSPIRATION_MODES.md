# Inspiration Modes

Lumira has two primary modes for generating artwork:

## 1. Autonomous Mode (Default)

**What it is:** Lumira creates completely original artwork from her own imagination, using her built-in `AutonomousInspiration` system.

**How it works:**

- Combines 91 subjects, 47 artistic styles, 25 moods, and 20 lighting conditions
- Uses 4 generation modes:
  - **Surprise**: Completely random creative combinations
  - **Exploration**: Variations on a theme
  - **Style Fusion**: Blending two artistic styles
  - **Concept Mashup**: Combining unexpected subjects

**Features:**

- ✅ **Original artwork** - Not derivative of existing photos
- ✅ **Diversity checking** - Avoids painting the same subject repeatedly
- ✅ **Mood-influenced** - Her emotional state guides style and color choices
- ✅ **No attribution needed** - These are Lumira's own creations

**Example prompts generated:**

```
dragon, cyberpunk style, dramatic mood, golden hour lighting
mountain landscape meets ocean waves, impressionist interpretation
serene forest, watercolor style, pastel palette, soft morning light
```

**When to use:**

- Default for all autonomous creations
- When you want truly original artwork
- When variety and surprise are desired
- For Lumira's natural creative expression

## 2. Unsplash Reference Mode (Optional)

**What it is:** Uses Unsplash API to find reference photos that inspire the generation.

**How it works:**

- Fetches a random photo matching a query
- Uses the photo's description to build prompts
- Can use ControlNet to guide composition from the photo

**Features:**

- ✅ **Specific themes** - Great for precise subject requests
- ✅ **Real-world reference** - Based on actual photography
- ✅ **ControlNet compatible** - Can use photo structure as guide
- ⚠️ **Derivative work** - Artwork is inspired by existing photos
- ⚠️ **Requires attribution** - Must credit Unsplash photographers

**When to use:**

- User explicitly requests inspiration from photos
- Specific themed requests (e.g., "paint a photo of Paris")
- When using ControlNet for composition guidance
- For photorealistic interpretations

## Current Implementation

**Default behavior:**

```python
# Lumira generates her own original vision
base_prompt = self.autonomous_inspiration.generate_surprise()
# or
base_prompt = self.autonomous_inspiration.generate_exploration(theme="nature")
```

**Unsplash still available:**

```python
# Can be enabled for specific use cases
if use_reference_photo:
    photo = await self.unsplash.get_random_photo(query=query)
    # Use photo description as inspiration
```

## Diversity & Variety

The autonomous mode includes built-in diversity checking:

```python
# Tracks last 5 creations
recent_episodes = self.enhanced_memory.episodic.get_recent_episodes(5, "creation")
recent_subjects = [ep["details"]["subject"] for ep in recent_episodes]

# Avoids painting same subject 3 times in a row
if subject in recent_subjects[-3:]:
    # Pick something different
    subject = get_alternative_subject()
```

This prevents the issue of generating "4 women in a row" or any repetitive subjects.

## Configuration

Future enhancement: Add to `config.yaml`:

```yaml
inspiration:
  mode: "autonomous"  # or "unsplash" or "hybrid"
  diversity_window: 5  # Track last N creations
  avoid_repetition: true
  unsplash:
    enabled: true  # Keep available as option
    use_for_controlnet: true
```

## Summary

| Feature | Autonomous Mode | Unsplash Mode |
|---------|----------------|---------------|
| **Originality** | 100% original | Derivative |
| **Variety** | Built-in diversity checking | Depends on query |
| **Attribution** | Not needed | Required |
| **Mood-influenced** | Yes | Limited |
| **ControlNet support** | Future enhancement | Yes |
| **Speed** | Fast (no API calls) | Slower (API latency) |
| **Use case** | Default creative mode | Reference/themed work |

**Recommendation:** Use autonomous mode by default for Lumira's natural creative expression, and reserve Unsplash for specific cases where photo reference is explicitly desired.
