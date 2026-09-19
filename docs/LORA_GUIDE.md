# LoRA Training & Management Guide

Complete guide for training and using custom LoRA styles with Lumira.

---

## 📚 Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Specialized Styles](#specialized-styles)
4. [Training Parameters](#training-parameters)
5. [Management Tools](#management-tools)
6. [Advanced Usage](#advanced-usage)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### What is LoRA?

LoRA (Low-Rank Adaptation) enables lightweight fine-tuning of Stable Diffusion to create unique artistic styles. Instead of training the entire model, LoRA trains only 0.09-0.19% of parameters, making it:

- **Fast**: Train in 1.5-2 hours on Apple Silicon
- **Small**: Model files are ~3MB vs 4GB for full models
- **Flexible**: Switch between multiple styles instantly
- **Stackable**: Can be used with the base model at any strength

### How It Works

```
Base Stable Diffusion Model
    ↓
+ LoRA Style (optional, 0-100% strength)
    ↓
= Styled Output
```

**Key Concept**: LoRAs are style enhancers, not replacements. You can:

- Generate any subject with or without a LoRA active
- Control style strength with the `lora_scale` parameter (0.0-1.0)
- Switch between LoRAs anytime by changing config
- Use base model when you need maximum flexibility

---

## Quick Start

### Prerequisites

1. **Training data**: 20-50 images ([see sourcing guide](docs/TRAINING_DATA_SOURCING.md))
2. **Dependencies**: `pip install -e .` (includes peft, accelerate)
3. **Legal compliance**: Review [LEGAL.md](LEGAL.md) before sourcing data
4. **Disk space**: ~5GB per LoRA for models and training data

### Basic Training (5 minutes to start)

```bash
# 1. Download a dataset (30 professional images)
python scripts/download_specialized_datasets.py webhero

# 2. Train LoRA (~1.5 hours)
python scripts/train_all_loras.py webhero

# 3. Activate the LoRA
python scripts/manage_loras.py set webhero_style

# 4. Generate images!
lumira
```

---

## Specialized Styles

Lumira provides three professionally configured LoRA profiles:

### 1. 🎨 Abstract Art

**Best for**: Creative projects, artistic designs, vibrant artwork

**Style**: Colorful, modern abstract compositions

- **Training**: 30 images, rank 16, 3000 steps
- **Time**: ~2 hours
- **Output**: Bold colors, geometric shapes, artistic flair

```bash
# Download dataset
python scripts/download_specialized_datasets.py abstract

# Train
python scripts/train_all_loras.py abstract

# Use
python scripts/manage_loras.py set abstract_style --scale 0.8
```

**Prompt examples**:

- "flowing colors and shapes"
- "geometric patterns in vibrant hues"
- "dreamlike composition with bold strokes"

### 2. 🏔️ Landscape Photography

**Best for**: Nature backgrounds, travel imagery, outdoor scenes

**Style**: Dramatic natural scenery, professional photography

- **Training**: 30 images, rank 8, 3000 steps
- **Time**: ~2 hours
- **Output**: Ansel Adams-style dramatic landscapes

```bash
# Download dataset
python scripts/download_specialized_datasets.py landscape

# Train
python scripts/train_all_loras.py landscape

# Use
python scripts/manage_loras.py set landscape_style --scale 0.7
```

**Prompt examples**:

- "mountain peak at golden hour"
- "misty forest in morning light"
- "dramatic coastal cliffs at sunset"

### 3. 💼 Web Hero Images ⭐

**Best for**: Website headers, landing pages, marketing materials

**Style**: Professional, clean, modern compositions (16:9 format)

- **Training**: 30 images, rank 8, 2500 steps, 768px resolution
- **Time**: ~1.5 hours
- **Output**: Professional website hero images

```bash
# Download dataset
python scripts/download_specialized_datasets.py webhero

# Train
python scripts/train_all_loras.py webhero

# Use
python scripts/manage_loras.py set webhero_style --scale 0.8
```

**Prompt examples** (perfect for web dev!):

- "modern tech office with computers"
- "professional business team working together"
- "sleek product on minimalist background"
- "laptop on wooden desk with coffee cup"
- "futuristic digital interface"

---

## Training Parameters

### Essential Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--instance_data_dir` | Required | Directory with training images |
| `--output_dir` | `models/lora` | Where to save trained LoRA |
| `--rank` | 4 | LoRA rank (4-128, lower=faster) |
| `--max_train_steps` | 2000 | Training iterations |

### Parameter Tuning

**LoRA Rank**:

- `rank=4`: Fast, subtle style (general use)
- `rank=8`: Balanced quality/speed (recommended)
- `rank=16`: Strong style (abstract/artistic)
- `rank=32+`: Very strong, risk of overfitting

**Training Steps**:

- `2000`: Quick iteration (1 hour on Apple Silicon)
- `2500-3000`: Standard quality (1.5-2 hours)
- `5000+`: Maximum quality, watch for overfitting

**Learning Rate**:

- `5e-5`: Slower, better for abstract/artistic (rank 16)
- `1e-4`: Standard (rank 4-8)
- `5e-4`: Faster, risk of instability

**Resolution**:

- `512`: Standard for most cases
- `768`: Better for hero images, requires more memory

### Advanced Training

```bash
python -m ai_artist.training.train_lora \
    --instance_data_dir datasets/training_custom \
    --output_dir models/lora/custom_style \
    --rank 8 \
    --learning_rate 1e-4 \
    --max_train_steps 3000 \
    --train_batch_size 1 \
    --gradient_accumulation_steps 4 \
    --resolution 512 \
    --mixed_precision no  # Use 'fp16' on GPU
```

---

## Management Tools

### List Available LoRAs

```bash
python scripts/manage_loras.py list
```

Output:

```
🎨 Available LoRA Models:
============================================================
1. abstract_style
   Status: ✅ Ready
   Path: models/lora/abstract_style

2. landscape_style
   Status: ✅ Ready
   Path: models/lora/landscape_style

3. webhero_style
   Status: ✅ Ready
   Path: models/lora/webhero_style
```

### Check Current LoRA

```bash
python scripts/manage_loras.py status
```

Output:

```
🎨 Current LoRA Status:
============================================================
Status: ✅ LoRA active
Model: webhero_style
Scale: 0.8
Path: models/lora/webhero_style
```

### Switch LoRA

```bash
# Activate a LoRA
python scripts/manage_loras.py set webhero_style --scale 0.8

# Change strength
python scripts/manage_loras.py set abstract_style --scale 0.3  # Subtle
python scripts/manage_loras.py set abstract_style --scale 0.9  # Strong

# Disable LoRA (use base model)
python scripts/manage_loras.py set none
```

### LoRA Scale Guide

The `--scale` parameter controls style strength:

| Scale | Effect | Use Case |
|-------|--------|----------|
| 0.0 | No effect | (Same as disabled) |
| 0.3 | Subtle hint | Gentle style influence |
| 0.5 | Balanced | Mix of style and flexibility |
| 0.7 | Strong | Clear style, some flexibility |
| 0.8 | Very strong | **Recommended default** |
| 1.0 | Maximum | Full style, may overpower |

---

## Advanced Usage

### Multiple LoRA Workflow

Switch between LoRAs for different project needs:

```bash
# Morning: Create abstract art
python scripts/manage_loras.py set abstract_style
lumira  # Generates abstract images

# Afternoon: Design website heroes
python scripts/manage_loras.py set webhero_style
lumira  # Generates professional heroes

# Evening: Create landscape backgrounds
python scripts/manage_loras.py set landscape_style
lumira  # Generates dramatic landscapes

# Night: General exploration
python scripts/manage_loras.py set none
lumira  # Full flexibility
```

### Manual Configuration

Edit `config/config.yaml` directly:

```yaml
model:
  base_model: "runwayml/stable-diffusion-v1-5"
  device: "mps"  # or "cuda" or "cpu"
  dtype: "float32"

  # LoRA settings
  lora_path: "models/lora/webhero_style"  # or null to disable
  lora_scale: 0.8  # 0.0-1.0
```

### Training Your Own Style

1. **Collect images** (20-50 similar style/subject)
2. **Organize dataset**:

   ```bash
   mkdir -p datasets/training_mystyle
   cp my_images/*.jpg datasets/training_mystyle/
   ```

3. **Document sources** in `datasets/licenses.txt`

4. **Train**:

   ```bash
   python -m ai_artist.training.train_lora \
       --instance_data_dir datasets/training_mystyle \
       --output_dir models/lora/mystyle \
       --rank 8 \
       --max_train_steps 3000
   ```

5. **Use**:

   ```bash
   python scripts/manage_loras.py set mystyle
   ```

### Train All Styles at Once

```bash
# Download all datasets (90 images)
python scripts/download_specialized_datasets.py all

# Train all styles (run overnight, ~5-6 hours)
python scripts/train_all_loras.py all
```

---

## Troubleshooting

### Training Issues

**Problem**: Training crashes with memory error
**Solution**: Reduce batch size or resolution:

```bash
--train_batch_size 1 --resolution 512
```

**Problem**: Loss not decreasing
**Solution**:

- Check learning rate (try 1e-4)
- Ensure images are similar style
- Increase training steps

**Problem**: Training very slow
**Solution**:

- Reduce rank (try 4 instead of 8)
- Reduce resolution (512 instead of 768)
- Use GPU if available

### LoRA Not Working

**Problem**: LoRA has no effect on output
**Solution**:

- Increase scale: `--scale 0.9`
- Check LoRA is active: `python scripts/manage_loras.py status`
- Verify training completed successfully

**Problem**: Style too strong
**Solution**: Reduce scale: `--scale 0.5` or `--scale 0.3`

**Problem**: Can't switch LoRA
**Solution**:

- Check path exists: `ls models/lora/`
- Verify permissions
- Check for typos in LoRA name

### Quality Issues

**Problem**: Generated images are low quality
**Solution**:

- Use base model to verify it works: `python scripts/manage_loras.py set none`
- Retrain with better dataset
- Check training loss decreased during training

**Problem**: LoRA produces artifacts
**Solution**:

- Dataset may have low-quality images
- Try lower rank (4 or 8)
- Reduce scale strength

---

## Best Practices

### Dataset Quality

✅ **Good**:

- 20-50 high-resolution images
- Consistent style/subject
- Good lighting, sharp focus
- Diverse compositions

❌ **Bad**:

- Mixed styles in one LoRA
- Low resolution or blurry
- Watermarks or text
- Too similar/duplicate images

### Training Tips

- Start with rank 8 for most cases
- Use 2500-3000 steps initially
- Monitor training loss (should decrease)
- Test at different scales (0.5, 0.7, 0.9)

### Usage Tips

- Start with scale 0.8
- Lower scale for subtle style
- Use base model for maximum flexibility
- Combine different LoRAs for varied outputs

---

## Resources

- **Data Sourcing**: [docs/TRAINING_DATA_SOURCING.md](docs/TRAINING_DATA_SOURCING.md)
- **Legal Guidelines**: [LEGAL.md](LEGAL.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Architecture**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

**Ready to create your custom styles!** 🎨

Start with: `python scripts/download_specialized_datasets.py webhero`
