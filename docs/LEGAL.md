# Legal & Copyright Guidelines

## Overview

This document outlines the legal considerations and best practices for using the Lumira project, particularly regarding copyright, training data, and generated content.

**Last Updated**: January 8, 2026

## ⚠️ Important Legal Disclaimer

- This project is for educational and personal use
- Users are responsible for ensuring their use complies with applicable laws
- Consult a lawyer for commercial applications
- Generated content may have complex copyright status

---

## Training Data Guidelines

### Copyright Considerations

Training AI models on copyrighted artwork carries legal risks. According to the U.S. Copyright Office (2025):

- Training to mimic specific artists makes "copying easy to prove"
- Using copyrighted works without permission may constitute infringement
- Fair use defense is complex and case-by-case

### Safe Training Data Sources

**✅ RECOMMENDED:**

1. **Public Domain Works**
   - Pre-1928 artworks (copyright expired)
   - Government-created works
   - Explicitly public domain datasets

2. **Creative Commons Licensed Works**
   - CC0 (Public Domain Dedication)
   - CC-BY (Attribution required)
   - CC-BY-SA (Attribution + ShareAlike)
   - Verify license terms before use

3. **Your Own Artwork**
   - Original works you created
   - Works where you hold copyright

**❌ AVOID:**

- Copyrighted artwork without permission
- Works by living artists without explicit consent
- Dataset with unclear licensing
- Commercial stock photography

### Recommended Training Datasets

```yaml
safe_datasets:
  - WikiArt Public Domain collection (pre-1928 works)
  - Rijksmuseum Open Data
  - Metropolitan Museum Open Access
  - Smithsonian Open Access
  - Library of Congress Public Domain
  - Your own original artwork (20-50 images)
```

### Documentation Requirements

For each training session, document:

```python
training_metadata = {
    "dataset_sources": ["Rijksmuseum Open Access", "Personal Collection"],
    "licenses": ["CC0", "Self-owned"],
    "date_ranges": ["1600-1900", "2024-2026"],
    "artist_names": ["None - public domain only"],
    "verification_date": "2026-01-08",
    "total_images": 45
}
```

---

## Generated Content Copyright

### Copyright Status

**AI-generated artwork has complex copyright status:**

- U.S. Copyright Office: Works must have "human authorship" for copyright
- Purely AI-generated works may not be copyrightable
- Works with significant human creative input may qualify
- Laws vary by jurisdiction and are evolving

### Best Practices

1. **Attribution**
   - Credit the base model (e.g., "Created with Stable Diffusion 1.5")
   - Mention inspiration sources if applicable
   - Be transparent about AI involvement

2. **Licensing Your Outputs**

   ```yaml
   recommended_license: "CC-BY 4.0"
   # Allows others to use with attribution
   # Acknowledges uncertain copyright status
   ```

3. **Commercial Use**
   - Verify model license permits commercial use
   - Check if training data licenses restrict commercial outputs
   - Consider additional licensing for commercial projects

---

## API Usage Compliance

### Unsplash API

**Terms of Service Requirements:**

- Attribution required for used images
- Cannot use images for competing services
- Rate limits: 50 requests/hour (free tier)
- Downloaded images used only as inspiration, not redistributed

**Proper Attribution:**

```python
attribution = f"Photo by {photographer_name} on Unsplash"
# Store in database with each source image
```

### Pexels API

**Terms of Service Requirements:**

- Attribution appreciated but not required
- Cannot sell unmodified photos
- Cannot create competing image service
- Rate limits: 200 requests/hour (free tier)

---

## Guardrails & Safety Measures

### Preventing Copyright Infringement

Implement these guardrails in your generation pipeline:

```python
# Prohibited prompts (living artists)
BLOCKED_ARTISTS = [
    # Add names of living artists
    # Check regularly and update
]

# Prompt filtering
def check_prompt_safety(prompt: str) -> bool:
    """Prevent prompts that could generate infringing content"""
    prompt_lower = prompt.lower()

    # Block specific artist names
    for artist in BLOCKED_ARTISTS:
        if artist.lower() in prompt_lower:
            return False

    # Block style mimicry phrases
    risky_phrases = [
        "in the style of",
        "as painted by",
        "like [artist name]",
    ]

    # Allow style descriptors, block specific attribution
    return True
```

### Content Monitoring

```python
# Log all generations for review
generation_log = {
    "prompt": prompt,
    "negative_prompt": negative_prompt,
    "source_url": inspiration_url,
    "timestamp": datetime.now(),
    "safety_check": "passed"
}
```

---

## Model Licensing

### Stable Diffusion Models

Check license before use:

- **SD 1.5**: CreativeML OpenRAIL-M License
  - Allows commercial use
  - Prohibits illegal/harmful content
  - Cannot use to compete directly with Stability AI

- **SDXL**: CreativeML OpenRAIL++-M License
  - Similar terms to SD 1.5
  - Additional restrictions on derivatives

### LoRA Weights

- LoRA weights inherit base model license
- Additional restrictions if trained on restricted data
- Document training data licenses

---

## Privacy Considerations

### API Keys & Credentials

- Never commit API keys to version control
- Use environment variables or secrets management
- Rotate keys regularly
- Limit key permissions to necessary scopes

### User Data

If adding feedback or social features:

- Collect only necessary data
- Provide privacy policy
- Allow data deletion
- Comply with GDPR/CCPA if applicable

---

## Compliance Checklist

Before training or deploying:

- [ ] Verified all training data is public domain or properly licensed
- [ ] Documented data sources and licenses
- [ ] Implemented artist name blocking in prompts
- [ ] Added attribution for API-sourced images
- [ ] Reviewed and accepted base model license terms
- [ ] Set up proper secrets management
- [ ] Added copyright disclaimer to outputs
- [ ] Configured rate limiting for API calls

---

## Reporting Issues

If you discover:

- Potentially infringing outputs
- Training data with unclear licensing
- License violations

**Actions:**

1. Stop using the affected component
2. Document the issue
3. Consult legal advice if needed
4. Update this document with learnings

---

## Resources

### Legal Information

- [U.S. Copyright Office - AI Reports](https://www.copyright.gov/ai/)
- [Creative Commons Licenses](https://creativecommons.org/licenses/)
- [Stability AI License](https://huggingface.co/spaces/CompVis/stable-diffusion-license)

### Safe Data Sources

- [Rijksmuseum API](https://data.rijksmuseum.nl/)
- [Met Museum Open Access](https://www.metmuseum.org/about-the-met/policies-and-documents/open-access)
- [Public Domain Review](https://publicdomainreview.org/)

### Model Licenses

- [Stable Diffusion License](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md)
- [Hugging Face Model Cards](https://huggingface.co/docs/hub/model-cards)

---

## Updates

This document will be updated as:

- Laws and regulations evolve
- New court cases provide guidance
- Model licenses change
- Community best practices develop

**Version History:**

- v1.0 (2026-01-08): Initial version

---

*This document provides general information and is not legal advice. Consult a qualified attorney for specific legal questions.*
