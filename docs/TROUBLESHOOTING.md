# 🔧 Troubleshooting Guide

Common issues and their solutions for Lumira.

---

## Table of Contents

- [Installation Issues](#installation-issues)
- [GPU & Memory Issues](#gpu--memory-issues)
- [Generation Problems](#generation-problems)
- [API & Network Issues](#api--network-issues)
- [Database Issues](#database-issues)
- [Web Interface Issues](#web-interface-issues)
- [LoRA Training Issues](#lora-training-issues)
- [Performance Issues](#performance-issues)

---

## Installation Issues

### ❌ "No module named 'ai_artist'"

**Cause:** Package not installed in editable mode

**Solution:**

```bash
pip install -e .
```

### ❌ pip install fails with "No matching distribution"

**Cause:** Python version too old

**Solution:**

```bash
# Check Python version
python --version  # Should be 3.11+

# If too old, install Python 3.11+
# macOS: brew install python@3.11
# Ubuntu: sudo apt install python3.11
# Windows: Download from python.org
```

### ❌ "error: Microsoft Visual C++ 14.0 or greater is required" (Windows)

**Cause:** Missing C++ build tools

**Solution:**

1. Download Visual Studio Build Tools
2. Install "Desktop development with C++"
3. Retry pip install

### ❌ PyTorch installation fails

**Cause:** Wrong installation command for your system

**Solution:**

```bash
# NVIDIA GPU (CUDA 11.8)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# NVIDIA GPU (CUDA 12.1)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Apple Silicon
pip install torch torchvision torchaudio

# CPU only
pip install torch torchvision torchaudio
```

---

## GPU & Memory Issues

### ❌ "CUDA out of memory"

**Cause:** GPU VRAM insufficient

**Solutions:**

**Option 1: Reduce image size**

```yaml
# config.yaml
generation:
  width: 768  # Instead of 1024
  height: 768
```

**Option 2: Enable memory optimizations**

```yaml
model:
  enable_attention_slicing: true
  enable_vae_slicing: true
```

**Option 3: Use CPU**

```yaml
model:
  device: "cpu"
```

**Option 4: Reduce batch size**

```yaml
generation:
  num_variations: 1  # Instead of 3
```

### ❌ Images are black or have NaN values (MPS/Apple Silicon)

**Cause:** Known MPS backend issues with float16

**Solutions:**

**Option 1: Use float32** (Already implemented as fallback)

```yaml
model:
  dtype: "float32"
```

**Option 2: Check code has MPS fixes**

```python
# generator.py should have:
if self.device == "mps":
    self.pipeline.vae = self.pipeline.vae.to(dtype=torch.float32)
```

**Option 3: Update PyTorch**

```bash
pip install --upgrade torch torchvision torchaudio
```

### ❌ "RuntimeError: CUDA error: device-side assert triggered"

**Cause:** GPU driver issue or memory corruption

**Solution:**

```bash
# Reset GPU state
nvidia-smi --gpu-reset

# Update drivers
# Windows: GeForce Experience
# Linux: sudo apt update && sudo apt install nvidia-driver-535
```

---

## Generation Problems

### ❌ Generation is very slow

**Expected Times:**

- NVIDIA RTX 3060: 15-30 seconds per image
- Apple M1/M2: 30-60 seconds per image
- CPU: 5-15 minutes per image

**Solutions:**

**1. Check device:**

```python
import torch
print(f"CUDA: {torch.cuda.is_available()}")
print(f"MPS: {torch.backends.mps.is_available()}")
```

**2. Reduce steps:**

```yaml
generation:
  num_inference_steps: 20  # Instead of 30
```

**3. Use smaller model:**

```yaml
model:
  base_model: "stabilityai/stable-diffusion-v1-5"  # Smaller than XL
```

### ❌ Generated images have poor quality

**Solutions:**

**1. Increase steps:**

```yaml
generation:
  num_inference_steps: 50
  guidance_scale: 9.0
```

**2. Improve prompt:**

```bash
# Bad prompt
lumira --theme "dog"

# Good prompt
lumira --theme "a majestic golden retriever, professional photography, detailed fur, natural lighting, 8k"
```

**3. Use negative prompts:**

```yaml
generation:
  negative_prompt: "blurry, low quality, distorted, ugly, deformed, watermark, text, amateur"
```

### ❌ Images don't match the prompt

**Cause:** Weak guidance or poor prompt

**Solution:**

```yaml
generation:
  guidance_scale: 9.0  # Higher = more prompt adherence
```

---

## API & Network Issues

### ❌ "Unsplash API rate limit exceeded"

**Cause:** Too many requests (50/hour on free tier)

**Solutions:**

**1. Wait for rate limit reset**

```bash
# Check when limit resets (shown in error message)
```

**2. Use Pexels as fallback**

```yaml
api_keys:
  pexels_api_key: "YOUR_KEY"
```

**3. Upgrade Unsplash tier**

- Plus: 100 requests/hour
- Enterprise: Unlimited

### ❌ "API key invalid"

**Solution:**

```bash
# Check config.yaml has correct keys
cat config/config.yaml | grep unsplash_access_key

# Regenerate keys at https://unsplash.com/developers
```

### ❌ "Connection timeout"

**Cause:** Network issues or API down

**Solution:**

```bash
# Check internet connection
ping api.unsplash.com

# Check API status
curl -I https://api.unsplash.com

# Try with increased timeout (in code)
timeout = 30  # seconds
```

---

## Database Issues

### ❌ "Database is locked"

**Cause:** Another process using database

**Solution:**

```bash
# Find processes using the database
lsof data/lumira.db

# Kill the process
kill -9 <PID>

# Remove journal file
rm data/lumira.db-journal

# Restart application
```

### ❌ "No such table"

**Cause:** Migrations not run

**Solution:**

```bash
# Run migrations
alembic upgrade head
```

### ❌ Database corruption

**Solution:**

```bash
# Backup first
cp data/lumira.db data/lumira.db.backup

# Try to repair
sqlite3 data/lumira.db "PRAGMA integrity_check"

# If corrupted, restore from backup or recreate
rm data/lumira.db
alembic upgrade head
```

---

## Web Interface Issues

### ❌ "Address already in use"

**Cause:** Port 8000 already taken

**Solutions:**

**Option 1: Use different port**

```bash
lumira-web --port 8080
```

**Option 2: Kill process using port**

```bash
# macOS/Linux
lsof -ti:8000 | xargs kill -9

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### ❌ Gallery not showing images

**Cause:** Incorrect paths or permissions

**Solutions:**

**1. Check gallery directory exists:**

```bash
ls -la gallery/
```

**2. Check permissions:**

```bash
chmod -R 755 gallery/
```

**3. Check metadata files:**

```bash
# Each image should have .json metadata
ls gallery/2026/01/09/*.json
```

### ❌ 404 errors on static files

**Cause:** Static files not found

**Solution:**

```bash
# Check static directory structure
ls src/ai_artist/web/static/
ls src/ai_artist/web/templates/
```

---

## LoRA Training Issues

### ❌ Training crashes with OOM

**Solutions:**

**1. Reduce batch size:**

```bash
--train_batch_size 1
```

**2. Reduce gradient accumulation:**

```bash
--gradient_accumulation_steps 1
```

**3. Use smaller rank:**

```bash
--rank 4  # Instead of 16
```

### ❌ Loss not decreasing

**Causes & Solutions:**

**1. Learning rate too high/low:**

```bash
# Try different learning rates
--learning_rate 1e-4  # Start here
--learning_rate 5e-5  # If loss spikes
--learning_rate 2e-4  # If loss flat
```

**2. Not enough training data:**

- Minimum: 15 images
- Recommended: 30+ images

**3. Poor quality training data:**

- Images should be similar style/subject
- Resolution should match target (1024x1024)
- Diverse poses/angles

### ❌ Trained LoRA has no effect

**Causes & Solutions:**

**1. LoRA scale too low:**

```yaml
model:
  lora_scale: 1.0  # Try higher
```

**2. Wrong LoRA path:**

```bash
# Check path exists
ls models/lora/my_style/

# Verify in config
cat config/config.yaml | grep lora_path
```

**3. Undertrained:**

```bash
# Train longer
--max_train_steps 3000  # Instead of 2000
```

---

## Performance Issues

### ❌ High CPU usage when GPU available

**Cause:** Using CPU despite GPU available

**Solution:**

```python
# Check what device is being used
import torch
from ai_artist.utils.config import load_config

config = load_config()
print(f"Config device: {config.model.device}")
print(f"CUDA available: {torch.cuda.is_available()}")
```

### ❌ Model loading is slow

**Cause:** Downloading model on every run

**Solution:**

```bash
# Models cached in:
ls ~/.cache/huggingface/hub/

# Or set custom cache dir
export HF_HOME=/path/to/cache
```

### ❌ Disk space running out

**Solution:**

```bash
# Check space
df -h

# Clean up old cache
rm -rf ~/.cache/huggingface/hub/models--*

# Clean up old gallery (backup first!)
# Only keep last 30 days:
find gallery/ -type f -mtime +30 -delete
```

---

## Still Having Issues?

### 1. Check Logs

```bash
# View recent logs
tail -n 100 logs/lumira.log

# Watch logs in real-time
tail -f logs/lumira.log

# Search for errors
grep ERROR logs/lumira.log
```

### 2. Enable Debug Mode

```yaml
# config.yaml or .env
LOG_LEVEL: DEBUG
```

### 3. Run Tests

```bash
# Run smoke test
pytest tests/test_smoke.py -v

# Run all tests
pytest -v
```

### 4. Get Help

- 🐛 **GitHub Issues:** Report bugs
- 💬 **Discussions:** Ask questions
- 📧 **Email:** [your-email@example.com]
- 📖 **Documentation:** Check other guides

### 5. Include This Info When Reporting

```bash
# System info
python --version
pip list | grep torch
uname -a  # or `systemd` on Windows

# Error message (full traceback)
# Steps to reproduce
# Config (redact API keys!)
```

---

## Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Installation fails | `pip install --upgrade pip && pip install -e .` |
| CUDA OOM | Reduce `width`/`height` in config |
| Black images (MPS) | Set `dtype: "float32"` |
| Rate limit | Wait or use Pexels |
| Port in use | Use `--port 8080` |
| Database locked | `rm data/lumira.db-journal` |
| Slow generation | Check device with `torch.cuda.is_available()` |
| LoRA not working | Increase `lora_scale` to 1.0 |

---

**Pro Tip:** Always backup your gallery and config before major changes!

```bash
# Backup gallery
cp -r gallery/ gallery_backup_$(date +%Y%m%d)/

# Backup config
cp config/config.yaml config/config.yaml.backup
```
