# 📦 Detailed Setup Guide

Complete installation and configuration instructions for Lumira.

---

## Table of Contents

- [System Requirements](#system-requirements)
- [Installation Methods](#installation-methods)
- [Configuration](#configuration)
- [GPU Setup](#gpu-setup)
- [API Keys Setup](#api-keys-setup)
- [Database Setup](#database-setup)
- [Web Interface Setup](#web-interface-setup)
- [Development Setup](#development-setup)
- [Troubleshooting](#troubleshooting)

---

## System Requirements

### Minimum Requirements

- **OS:** macOS 11+, Ubuntu 20.04+, Windows 10+
- **Python:** 3.11 or higher
- **RAM:** 8GB
- **Storage:** 10GB free space
- **GPU:** Optional but recommended

### Recommended Requirements

- **RAM:** 16GB+
- **Storage:** 50GB+ (for models and gallery)
- **GPU:**
  - NVIDIA RTX 3060+ (12GB VRAM) with CUDA 11.8+, OR
  - Apple M1/M2/M3 (8GB+ unified memory)

### Supported Devices

- **NVIDIA GPU:** CUDA 11.8 or 12.1
- **Apple Silicon:** MPS (Metal Performance Shaders)
- **CPU:** Works but slower (not recommended for production)

---

## Installation Methods

### Method 1: Standard Installation (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/yourusername/lumira.git
cd lumira

# 2. Create virtual environment
python3.11 -m venv venv

# 3. Activate environment
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# 4. Install PyTorch (choose based on your system)

# For NVIDIA GPU (CUDA 11.8):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# For NVIDIA GPU (CUDA 12.1):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# For Apple Silicon (M1/M2/M3):
pip install torch torchvision torchaudio

# For CPU only:
pip install torch torchvision torchaudio

# 5. Install project dependencies
pip install -r requirements-full.txt

# 6. Install in editable mode
pip install -e .
```

### Method 2: Development Installation

```bash
# Follow steps 1-5 from Method 1, then:

# Install development dependencies
pip install -r requirements-full.txt
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests to verify installation
pytest
```

### Method 3: Docker Installation (Coming Soon)

```bash
# Build and run with Docker Compose
docker-compose up -d

# Access web interface at http://localhost:8000
```

---

## Configuration

### Basic Configuration

1. **Copy example config:**

```bash
cp config/config.example.yaml config/config.yaml
```

2. **Edit configuration:**

```yaml
# Model settings
model:
  base_model: "stabilityai/stable-diffusion-xl-base-1.0"
  device: "cuda"  # "cuda", "mps", or "cpu"
  dtype: "float16"  # "float16" or "float32"

  # LoRA settings (optional)
  lora_path: null  # Path to trained LoRA
  lora_scale: 0.8  # LoRA strength (0.0-1.0)

# Generation parameters
generation:
  width: 1024
  height: 1024
  num_inference_steps: 30
  guidance_scale: 7.5
  num_variations: 3
  negative_prompt: "blurry, low quality, distorted"

# API keys
api_keys:
  unsplash_access_key: "YOUR_KEY_HERE"
  unsplash_secret_key: "YOUR_SECRET_HERE"
  pexels_api_key: "YOUR_KEY_HERE"  # Optional
  hf_token: "YOUR_TOKEN_HERE"  # Optional for private models

# Database
database:
  url: "sqlite:///./data/lumira.db"

# Scheduling
scheduling:
  enabled: true
  timezone: "America/Los_Angeles"
  daily_creation:
    enabled: true
    hour: 9
    minute: 0

# Curation
curation:
  enabled: true
  quality_threshold: 0.6
  keep_top_n: 2
```

### Environment Variables

Create a `.env` file for sensitive data:

```bash
# Copy template
cp .env.example .env
```

Edit `.env`:

```env
# API Keys
UNSPLASH_ACCESS_KEY=your_unsplash_access_key
UNSPLASH_SECRET_KEY=your_unsplash_secret_key
PEXELS_API_KEY=your_pexels_api_key
HF_TOKEN=your_huggingface_token

# Database
DATABASE_URL=sqlite:///./data/lumira.db

# Application
LOG_LEVEL=INFO
DEVICE=cuda
```

---

## GPU Setup

### NVIDIA GPU (CUDA)

1. **Install NVIDIA drivers** (latest)

2. **Install CUDA Toolkit:**

- CUDA 11.8: <https://developer.nvidia.com/cuda-11-8-0-download-archive>
- CUDA 12.1: <https://developer.nvidia.com/cuda-downloads>

3. **Verify installation:**

```bash
nvidia-smi
nvcc --version
```

4. **Install PyTorch with CUDA:**

```bash
# CUDA 11.8
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

5. **Update config:**

```yaml
model:
  device: "cuda"
  dtype: "float16"
```

### Apple Silicon (MPS)

1. **Ensure macOS 12.3+**

2. **Install PyTorch:**

```bash
pip install torch torchvision torchaudio
```

3. **Update config:**

```yaml
model:
  device: "mps"
  dtype: "float16"  # or "float32" if issues
```

**Known Issues:**

- Some operations may have NaN outputs (fixed in code)
- Attention slicing disabled on MPS
- VAE uses float32 to avoid dtype issues

### CPU Only

```yaml
model:
  device: "cpu"
  dtype: "float32"
```

**Note:** CPU generation is 10-20x slower than GPU.

---

## API Keys Setup

### Unsplash API

1. Go to <https://unsplash.com/developers>
2. Click "Register as a developer"
3. Create a new application
4. Copy your **Access Key** and **Secret Key**
5. Add to `config/config.yaml`:

```yaml
api_keys:
  unsplash_access_key: "YOUR_ACCESS_KEY"
  unsplash_secret_key: "YOUR_SECRET_KEY"
```

**Rate Limits:**

- Free tier: 50 requests/hour
- Plus tier: 100 requests/hour

### Pexels API (Optional)

1. Go to <https://www.pexels.com/api/>
2. Sign up and get your API key
3. Add to config:

```yaml
api_keys:
  pexels_api_key: "YOUR_PEXELS_KEY"
```

**Rate Limits:**

- Free tier: 200 requests/hour

### Hugging Face Token (Optional)

Only needed for private models or gated models.

1. Go to <https://huggingface.co/settings/tokens>
2. Create a new token
3. Add to config:

```yaml
api_keys:
  hf_token: "hf_YOUR_TOKEN"
```

---

## Database Setup

### SQLite (Default)

No setup required. Database is created automatically:

```bash
# Database location
data/lumira.db
```

### PostgreSQL (Production)

1. **Install PostgreSQL**

2. **Create database:**

```sql
CREATE DATABASE lumira;
CREATE USER lumira_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE lumira TO lumira_user;
```

3. **Update config:**

```yaml
database:
  url: "postgresql://lumira_user:secure_password@localhost/lumira"
```

4. **Run migrations:**

```bash
alembic upgrade head
```

---

## Web Interface Setup

### Development Server

```bash
# Start web server
lumira-web

# Or with uvicorn directly
uvicorn ai_artist.web.app:app --reload --host 0.0.0.0 --port 8000
```

Access at: <http://localhost:8000>

### Production Server

```bash
# Install production server
pip install gunicorn

# Run with Gunicorn
gunicorn ai_artist.web.app:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### Nginx Configuration (Optional)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias /path/to/lumira/static;
    }
}
```

---

## Development Setup

### Install Development Tools

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Development Tools Included

- **pytest** - Testing framework
- **pytest-cov** - Coverage reporting
- **black** - Code formatting
- **ruff** - Fast linting
- **mypy** - Type checking
- **pre-commit** - Git hooks

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_generator.py

# Run with verbose output
pytest -v
```

### Code Quality Checks

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type check
mypy src/

# Run all checks
pre-commit run --all-files
```

---

## Troubleshooting

### Installation Issues

**Problem:** `pip install` fails

**Solution:**

```bash
# Upgrade pip
pip install --upgrade pip setuptools wheel

# Try again
pip install -r requirements-full.txt
```

**Problem:** CUDA out of memory

**Solution:**

```yaml
# Reduce image size or use CPU
model:
  device: "cpu"
generation:
  width: 768
  height: 768
```

**Problem:** MPS backend errors

**Solution:**

```yaml
# Use float32 instead of float16
model:
  dtype: "float32"
```

### Runtime Issues

**Problem:** "No module named 'ai_artist'"

**Solution:**

```bash
pip install -e .
```

**Problem:** Database locked error

**Solution:**

```bash
# Close other connections and restart
rm data/lumira.db-journal
```

**Problem:** Web interface not loading

**Solution:**

```bash
# Check if port is in use
lsof -i :8000

# Use different port
lumira-web --port 8080
```

### Model Issues

**Problem:** Model download fails

**Solution:**

```bash
# Download manually
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0
```

**Problem:** Out of memory during generation

**Solution:**

```yaml
# Enable memory optimizations
model:
  enable_attention_slicing: true
  enable_vae_slicing: true
```

---

## Verification

After installation, verify everything works:

```bash
# 1. Check installation
python -c "import ai_artist; print('✓ Package installed')"

# 2. Check GPU
python -c "import torch; print(f'✓ GPU available: {torch.cuda.is_available()}')"

# 3. Run tests
pytest tests/test_smoke.py

# 4. Generate test image
lumira --theme "test image"

# 5. Check web interface
lumira-web
```

---

## Next Steps

- Read [QUICKSTART.md](QUICKSTART.md) for quick usage
- Check [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system
- See [LORA_TRAINING.md](LORA_TRAINING.md) for custom style training
- Review [SECURITY.md](SECURITY.md) for security best practices

---

**Need more help?**

- 📖 Full documentation: `docs/`
- 🐛 Report issues: GitHub Issues
- 💬 Discussions: GitHub Discussions
- 📧 Contact: [your-email@example.com]
