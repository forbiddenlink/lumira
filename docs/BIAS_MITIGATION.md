# Bias Mitigation in Lumira

## Overview

Lumira includes built-in bias mitigation strategies to ensure fair, diverse, and ethical image generation. This document explains how bias is addressed throughout the system.

## The Problem

Stable Diffusion models are trained on large datasets scraped from the internet, which contain inherent biases:

- **Gender Bias**: When prompts mention "person" or "people" without specifying gender, models often default to generating women due to training data imbalances
- **Stereotype Reinforcement**: Certain professions, settings, or activities may be associated with specific genders, races, or age groups
- **Cultural Bias**: Western-centric imagery may dominate over diverse cultural representations

## Our Solution

### 1. Prompt Filtering

When Lumira receives inspiration from external sources (like Unsplash), the system automatically filters out ambiguous person references:

```python
# Filters applied when user hasn't explicitly requested portraits
person_keywords = ["person", "people", "man", "woman", "men", "women", "human", "portrait"]

# Description: "A person standing in a forest"
# Filtered to: "standing in a forest"
```

**Why it matters**: This prevents unintended human figure generation and avoids triggering model biases.

### 2. Negative Prompts

When people aren't explicitly requested, Lumira adds negative prompts to discourage human generation:

```yaml
# Automatically added when avoid_people=True
negative_prompt: "person, people, human, portrait, face, man, woman"
```

**Configuration**:

```python
generator.generate(
    prompt="mountain landscape at sunset",
    avoid_people=True  # Default: True
)
```

### 3. Explicit Intent Detection

Lumira only generates human figures when users explicitly request them:

```python
# Triggers people generation:
python -m ai_artist.main --theme "portrait of an artist"
python -m ai_artist.main --theme "street photography with people"

# Avoids people generation:
python -m ai_artist.main --theme "mountain landscape"
python -m ai_artist.main --theme "abstract art"
```

## Best Practices

### For Users

1. **Be Explicit**: If you want people in your images, say so clearly
   - Good: "portrait of a scientist in a laboratory"
   - Bad: "laboratory" (might accidentally generate people)

2. **Specify Diversity**: When requesting people, include diverse attributes
   - "diverse group of people collaborating"
   - "person of color in traditional attire"

3. **Review Settings**: Check your `config.yaml` for generation settings

### For Developers

1. **Test with Diverse Prompts**: Always test with various demographic descriptors
2. **Monitor Outputs**: Regularly review generated images for bias patterns
3. **Update Filters**: Add new person-related keywords as needed
4. **Provide Feedback**: Report bias issues through GitHub

## Technical Implementation

### Files Modified

1. **src/ai_artist/main.py**
   - Added prompt filtering logic
   - Detects user intent for person generation
   - Removes ambiguous person references from descriptions

2. **src/ai_artist/core/generator.py**
   - Added `avoid_people` parameter
   - Implements negative prompt injection
   - Logs bias mitigation actions

### Configuration

```yaml
# config/config.yaml
generation:
  # Add global negative prompts
  negative_prompt: "low quality, blurry, distorted"

  # Bias mitigation is automatic, but you can disable per-request
  # via code: generator.generate(..., avoid_people=False)
```

## Limitations

1. **Model Dependency**: Bias mitigation can't completely eliminate biases present in the base model
2. **Context Sensitivity**: Some prompts may require nuanced interpretation
3. **False Positives**: Occasionally, legitimate requests might be filtered

## Future Improvements

- [ ] Add diversity score to curation metrics
- [ ] Implement fairness auditing for generated content
- [ ] Provide bias dashboard in web UI
- [ ] Support for more granular demographic controls
- [ ] Integration with debiasing techniques like prompt rewriting

## Resources

- [Diffusers Safe Stable Diffusion](https://github.com/huggingface/diffusers/blob/main/docs/source/en/api/pipelines/stable_diffusion/stable_diffusion_safe.md)
- [Semantic Guidance for Bias Reduction](https://github.com/huggingface/diffusers/blob/main/docs/source/en/api/pipelines/semantic_stable_diffusion.md)
- [Ethical AI Guidelines](https://www.unesco.org/en/artificial-intelligence/recommendation-ethics)

## Reporting Issues

If you observe biased output:

1. Create a GitHub issue with:
   - The prompt used
   - Generated image (if appropriate)
   - Expected vs actual output
   - Your configuration settings

2. Tag with `bias` label

3. We'll review and update mitigation strategies accordingly

## License Note

Bias mitigation features are part of Lumira's core ethics framework and are MIT licensed like the rest of the project.
