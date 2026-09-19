# Available Scripts

This document lists all available scripts in the `scripts/` directory and how to use them.

## Generation Scripts

### `generate.py`

Basic image generation script.

```bash
python scripts/generate.py
```

### `generate_collection.py`

**Unified collection generator** - replaces the separate collection scripts.

Available collections:

- `artistic` - Creative styles and abstract concepts (impressionist, cubist, surrealist, etc.)
- `artistic2` - Modern art movements and experimental techniques (renaissance, photo-realism, op-art)
- `expanded` - Fresh creative prompts (cinematic moments, emotional portraits, nature spectacles)
- `ultimate` - Comprehensive diverse prompts across many themes (cosmic, mythological, retro, fantasy)
- `all` - All collections combined

```bash
# Generate 10 images from artistic collection
python scripts/generate_collection.py --collection artistic -n 10

# Generate all prompts from ultimate collection
python scripts/generate_collection.py --collection ultimate --all

# Generate from all collections combined
python scripts/generate_collection.py --collection all -n 50

# List available collections
python scripts/generate_collection.py --list-collections

# List categories in a collection
python scripts/generate_collection.py --collection expanded --list-categories

# Generate specific categories only
python scripts/generate_collection.py --collection ultimate -c cosmic_wonders mythological_beings -n 20

# Generate without randomization
python scripts/generate_collection.py --collection artistic -n 30 --no-randomize

# Generate with fixed parameters (no variation)
python scripts/generate_collection.py --collection expanded -n 10 --no-vary
```

Options:

- `--collection {artistic,artistic2,expanded,ultimate,all}` - Collection to use (default: ultimate)
- `-n, --num-images N` - Number of images to generate (default: 10)
- `--all` - Generate all prompts in the collection
- `-c, --categories` - Specific categories to generate from
- `--no-randomize` - Don't randomize prompt order
- `--no-vary` - Don't vary generation parameters
- `--list-categories` - List all categories and exit
- `--list-collections` - List all collections and exit

### `test_generation.py`

Test image generation pipeline.

```bash
python scripts/test_generation.py
```

### Legacy Scripts

The following scripts have been moved to `scripts/legacy/`:

- `generate_artistic_collection.py` - Replaced by `generate_collection.py --collection artistic`
- `generate_artistic_collection_2.py` - Replaced by `generate_collection.py --collection artistic2`
- `generate_expanded_collection.py` - Replaced by `generate_collection.py --collection expanded`
- `generate_ultimate_collection.py` - Replaced by `generate_collection.py --collection ultimate`

## Gallery Management

### `cleanup_gallery.py`

Clean up invalid, blank, or corrupted images from gallery.

```bash
# Dry run (show what would be deleted)
python scripts/cleanup_gallery.py --dry-run

# Actually delete invalid images
python scripts/cleanup_gallery.py
```

### `optimize_gallery_for_web.py`

Optimize gallery images for web delivery (resize, compress).

```bash
python scripts/optimize_gallery_for_web.py
```

### `upload_to_railway.py`

**NEW!** Upload images from local gallery to Railway deployment.

```bash
# Upload images from last 7 days
python scripts/upload_to_railway.py

# Upload all images
python scripts/upload_to_railway.py --all

# Upload specific directory
python scripts/upload_to_railway.py --directory gallery/2026/01

# Dry run (show what would be uploaded)
python scripts/upload_to_railway.py --dry-run

# Set API key
export RAILWAY_API_KEY="your-api-key-here"
python scripts/upload_to_railway.py
```

## Training & Model Management

### `train_all_loras.py`

Train all LoRA models.

```bash
python scripts/train_all_loras.py
```

### `manage_loras.py`

Manage LoRA model configurations.

```bash
python scripts/manage_loras.py
```

### `download_training_data.py`

Download training datasets.

```bash
python scripts/download_training_data.py
```

### `download_specialized_datasets.py`

Download specialized training datasets.

```bash
python scripts/download_specialized_datasets.py
```

## LUMIRA Integration

### `lumira_insights.py`

Get insights from LUMIRA's autonomous creative process.

```bash
python scripts/lumira_insights.py
```

### `check_lumira.py`

Check LUMIRA system status and configuration.

```bash
python scripts/check_lumira.py
```

## Setup & Installation

### `install.sh`

Install system dependencies (Linux/macOS).

```bash
bash scripts/install.sh
```

### `setup_project.sh`

Set up the project environment.

```bash
bash scripts/setup_project.sh
```

## Running the Web Application

### Local Development

```bash
# Using uvicorn directly
uvicorn ai_artist.web.app:app --host 0.0.0.0 --port 8000 --reload

# Or using the module
python -m ai_artist.web.app
```

**Features:**

- Full image generation capability (requires `config/config.yaml`)
- Gallery viewing at <http://localhost:8000>
- LUMIRA creative studio at <http://localhost:8000/lumira>
- API documentation at <http://localhost:8000/docs>

### Railway Deployment

```bash
# Deploy to Railway
railway up

# View logs
railway logs

# Check deployment status
curl https://lumira-production-3084.up.railway.app/health
```

**Railway Features:**

- Gallery-only mode (no image generation)
- Persistent storage via Railway Volume at `/app/gallery`
- Upload images via admin API endpoints

## Environment Setup

### Required Environment Variables

For **local development**:

```bash
# Create config/config.yaml with:
# - Model settings
# - API keys (if using external services)
```

For **Railway deployment**:

```bash
# Set in Railway dashboard:
RAILWAY_API_KEY=your-admin-api-key-here
```

## Common Workflows

### 1. Generate Images Locally and Upload to Railway

```bash
# Generate images locally
uvicorn ai_artist.web.app:app --host 0.0.0.0 --port 8000

# Upload to Railway
export RAILWAY_API_KEY="your-api-key"
python scripts/upload_to_railway.py --days 1
```

### 2. Clean Up Gallery

```bash
# Check what would be deleted
python scripts/cleanup_gallery.py --dry-run

# Remove invalid images
python scripts/cleanup_gallery.py
```

### 3. Generate and Optimize Images

```bash
# Generate ultimate collection
python scripts/generate_ultimate_collection.py

# Optimize for web
python scripts/optimize_gallery_for_web.py
```

### 4. Train Custom LoRA

```bash
# Download training data
python scripts/download_training_data.py

# Train all LoRAs
python scripts/train_all_loras.py
```

## API Endpoints

### Public Endpoints

- `GET /` - Gallery homepage
- `GET /api/images` - List all images
- `GET /api/images/file/{path}` - Get image file
- `GET /api/stats` - Gallery statistics
- `GET /health` - Health check

### Admin Endpoints (Require API Key)

- `POST /api/admin/upload-image` - Upload single image
- `POST /api/admin/upload-batch` - Upload multiple images
- `DELETE /api/images/{path}` - Delete image
- `PUT /api/images/{path}/featured` - Toggle featured status

### Using Admin Endpoints

```bash
# Set API key header
curl -X POST https://lumira-production-3084.up.railway.app/api/admin/upload-image \
  -H "X-API-Key: your-api-key" \
  -F "image=@/path/to/image.png" \
  -F "metadata={\"prompt\":\"A beautiful sunset\"}"
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'ai_artist'"

Make sure you're in the project root directory and the package is installed:

```bash
cd /Volumes/LizsDisk/lumira
pip install -e .
```

### "CUDA is not available"

Railway doesn't have GPU support. Use local machine for generation.

### "Gallery is empty on Railway"

Upload images using the upload script:

```bash
python scripts/upload_to_railway.py
```

### "Permission denied" on scripts

Make scripts executable:

```bash
chmod +x scripts/*.sh scripts/*.py
```

## Need Help?

- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
- Review [API.md](docs/API.md) for API documentation
- See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for deployment guide
