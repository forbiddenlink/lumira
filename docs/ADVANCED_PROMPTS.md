# New Features: Advanced Prompt Control

Three powerful new features inspired by AUTOMATIC1111 and InvokeAI to give you more control over image generation.

## 1. Prompt Matrix 🎲

Generate multiple variations automatically using `{option1|option2}` syntax.

### Basic Usage

```python
from ai_artist.utils.prompt_matrix import PromptMatrix

pm = PromptMatrix()

# Simple example
prompts = pm.parse_prompt("a {red|blue} cat")
# Result: ["a red cat", "a blue cat"]

# Complex example
prompts = pm.parse_prompt("{portrait|landscape} of a {young|old} {man|woman}")
# Result: 8 combinations
```

### Real-World Examples

```python
# Art styles
"portrait in {impressionist|baroque|renaissance} style"

# Moods and lighting
"{bright cheerful|dark moody|ethereal dreamy} atmosphere"

# Subjects with variations
"{majestic|playful|sleeping} {tiger|lion|panther} in {jungle|savanna|mountains}"
```

### Validation

```python
is_valid, error = pm.validate_syntax("{option1|option2} prompt")
count = pm.count_combinations(prompt)  # Know how many images will be generated
```

## 2. Prompt Emphasis ⚡

Control the importance of specific words using `(word:weight)` syntax.

### Basic Usage

```python
from ai_artist.utils.prompt_emphasis import PromptEmphasis

pe = PromptEmphasis()

# Emphasize (>1.0) or de-emphasize (<1.0)
prompt = "(beautiful:1.5) woman, (cluttered:0.5) background"

# Convert to Compel format (for diffusers)
compel_prompt = pe.apply_emphasis_to_compel(prompt)
```

### Weight Guidelines

- **1.0** = Normal (default)
- **1.1-1.3** = Mild emphasis
- **1.4-1.7** = Strong emphasis
- **1.8-2.0** = Very strong (use sparingly)
- **0.5-0.9** = De-emphasis (reduce importance)

### Examples

```python
# Portrait with strong focus on eyes
"(detailed eyes:1.6) portrait, face, (background:0.6)"

# Landscape with emphasis on lighting
"(golden hour lighting:1.4) mountain landscape, (foreground:0.8)"

# Style with reduced unwanted elements
"abstract art, (colorful:1.3) shapes, (realistic:0.4) elements"
```

### Without Explicit Weight

Use `()` without a number for default 1.1x emphasis:

```python
"(masterpiece) artwork"  # 1.1x emphasis
```

## 3. Style Presets 🎨

Reusable style templates with positive and negative prompts.

### Using Presets

```python
from ai_artist.utils.style_presets import StylePresetsManager

manager = StylePresetsManager()

# List available presets
presets = manager.list_presets()
for preset in presets:
    print(f"{preset.name}: {preset.description}")

# Apply a preset
positive, negative = manager.apply_preset("Cinematic", "portrait of a woman")
# positive: "portrait of a woman, cinematic lighting, dramatic shadows..."
# negative: "flat lighting, overexposed, amateur"
```

### Default Presets

1. **Cinematic** - Movie-quality with dramatic lighting
2. **Dreamy** - Soft, ethereal, pastel aesthetic
3. **Vibrant** - Bold colors and high contrast
4. **Minimalist** - Clean, simple composition
5. **Oil Painting** - Traditional painting style
6. **Studio Portrait** - Professional photography
7. **Watercolor** - Soft watercolor aesthetic
8. **Dark Moody** - Atmospheric, dramatic shadows
9. **Anime** - Japanese animation style
10. **Retro Vintage** - 1970s nostalgic feel

### Creating Custom Presets

```python
from ai_artist.utils.style_presets import StylePreset

# Create a custom preset
custom = StylePreset(
    name="Cyberpunk",
    positive="neon lights, futuristic, cyberpunk aesthetic, {prompt}, high tech",
    negative="natural, organic, vintage, low tech",
    description="Futuristic cyberpunk aesthetic",
    category="art",
    tags=["scifi", "neon", "futuristic"]
)

# Save it
manager.add_preset(custom)
```

### Using {prompt} Placeholder

Presets can use `{prompt}` to control where your base prompt appears:

```python
# Without {prompt} - appends to end
positive: "cinematic, dramatic lighting"
# Result: "portrait, cinematic, dramatic lighting"

# With {prompt} - inserts in specific location
positive: "oil painting of {prompt}, masterpiece quality"
# Result: "oil painting of portrait, masterpiece quality"
```

## Combining Features 🚀

You can combine all three features for maximum control:

```python
# 1. Start with a matrix
base = "portrait of a {young|old} woman"

# 2. Apply emphasis
emphasized = "(detailed face:1.5) portrait of a {young|old} woman, (background:0.6)"

# 3. Apply a style preset
positive, negative = manager.apply_preset("Cinematic", emphasized)

# Now generate all combinations with the style applied!
```

## API Integration

These features are designed to integrate with Lumira's main workflow:

```python
from ai_artist.main import AIArtist

# In your generation code:
# 1. Parse matrix to get all variations
variations = prompt_matrix.parse_prompt(user_prompt)

# 2. Apply emphasis to each
for prompt in variations:
    emphasized = prompt_emphasis.apply_emphasis_to_compel(prompt)

    # 3. Apply style if requested
    if style_name:
        positive, negative = style_manager.apply_preset(style_name, emphasized)

    # 4. Generate!
    await artist.create_artwork(theme=positive)
```

## Best Practices

### Prompt Matrix

- Start small (2-3 options) to avoid generating too many images
- Use descriptive options that meaningfully change the output
- Validate syntax before batch processing

### Prompt Emphasis

- Don't over-emphasize (>2.0 can cause artifacts)
- Balance emphasis - if everything is emphasized, nothing is
- Use de-emphasis to remove unwanted elements

### Style Presets

- Browse categories to find the right aesthetic
- Combine presets with custom prompts for unique results
- Create custom presets for your favorite styles

## Performance Tips

- **Prompt Matrix**: Count combinations first with `count_combinations()`
- **Prompt Emphasis**: Use `validate_syntax()` before processing
- **Style Presets**: Presets are cached in memory for fast access

## Examples

### Generate Seasonal Portraits

```python
prompt = "{spring|summer|autumn|winter} portrait, (seasonal colors:1.4)"
positive, negative = manager.apply_preset("Cinematic", prompt)
variations = prompt_matrix.parse_prompt(positive)
# Creates 4 seasonal portraits with cinematic style
```

### Art Style Exploration

```python
base = "mountain landscape"
styles = ["Oil Painting", "Watercolor", "Anime", "Minimalist"]

for style in styles:
    positive, negative = manager.apply_preset(style, base)
    # Generate with each style
```

### Controlled Experimentation

```python
prompt = "(detailed:1.5) portrait, {neutral|happy|sad} expression"
# Generates 3 variations with strong detail emphasis
```

## Testing

Run tests with:

```bash
pytest tests/test_prompt_utilities.py -v
```

All features include comprehensive test coverage and validation.
