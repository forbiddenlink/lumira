# Railway Deployment Guide for Lumira

## Prerequisites

- Railway account with active subscription (trial expired)
- Your Unsplash API keys

## Quick Deploy to Railway

### 1. Add Payment Method to Railway

```bash
# Visit Railway dashboard and add payment method
open https://railway.app/account/billing
```

### 2. Initialize Project

```bash
cd /Volumes/LizsDisk/lumira
railway init
# Select: Elizabeth Stein's Projects
# Project name: lumira
```

### 3. Set Environment Variables

```bash
# Set Unsplash API keys
railway variables set UNSPLASH_ACCESS_KEY="your-access-key-here"
railway variables set UNSPLASH_SECRET_KEY="your-secret-key-here"

# Set device to CPU (Railway doesn't have GPU by default)
railway variables set MODEL_DEVICE="cpu"

# Optional: Set model cache location
railway variables set HF_HOME="/app/models/cache"
railway variables set PYTHONUNBUFFERED="1"
```

### 4. Deploy

```bash
railway up
```

### 5. Get Your URL

```bash
railway domain
# This will show your app URL, e.g., https://lumira-production-xxxx.up.railway.app
```

## What You Get

**Full Lumira Deployment:**

- ✅ Web gallery at `/`
- ✅ Image generation API at `/api/generate`
- ✅ All gallery endpoints
- ✅ WebSocket real-time updates
- ✅ Health checks at `/health`

**Endpoints:**

- `GET /` - Web gallery UI
- `POST /api/generate` - Generate new artwork
- `GET /api/gallery` - List all artworks
- `GET /api/gallery/{filename}` - Get specific image
- `GET /api/stats` - Gallery statistics
- `GET /health` - Health check
- `WS /ws` - WebSocket for real-time updates

## Performance Notes

**CPU Mode (Railway Default):**

- Generation time: ~2-3 minutes per image
- Memory: ~4GB RAM
- Cost: ~$5-10/month for hobby usage

**For GPU (Optional Upgrade):**

```bash
# Railway doesn't offer GPU by default
# For GPU, consider:
# - Render.com with GPU instances ($0.80/hr)
# - Modal.com (serverless GPU)
# - RunPod.io (GPU containers)
```

## Testing Deployment

```bash
# Check health
curl https://your-app.railway.app/health

# Check gallery
curl https://your-app.railway.app/api/gallery

# Generate artwork (takes 2-3 min on CPU)
curl -X POST https://your-app.railway.app/api/generate \
  -H "Content-Type: application/json" \
  -d '{"theme": "sunset landscape", "mood": "serene"}'
```

## Monitoring

```bash
# View logs
railway logs

# Check deployment status
railway status

# Open in browser
railway open
```

## Troubleshooting

**"Out of Memory" errors:**

```bash
# Increase memory limit in Railway dashboard
# Settings > Resources > Memory: 4GB → 8GB
```

**Slow generation:**

- CPU mode is slow (2-3 min per image)
- This is normal without GPU
- Consider scheduled generation instead of real-time

**Models not downloading:**

```bash
# Check logs for HuggingFace downloads
railway logs

# Models will download on first run (takes ~5-10 min)
# DreamShaper 8 model: ~2GB
```

## Cost Estimate

**Railway Hobby Plan:**

- Base: $5/month
- 500 hours compute included
- Additional: $0.01/hour

**For 24/7 operation:**

- ~$12/month (720 hours × $0.01 + $5 base)

**For scheduled generation (1hr/day):**

- ~$5/month (just base plan)

## Alternative: Local with Railway Database Only

If Railway costs are too high, you can:

1. Run Lumira locally (you already have MPS GPU)
2. Use Railway just for database/API endpoints
3. Push generated images to GitHub/S3
4. Deploy gallery-only to Vercel (free)

Let me know which approach you prefer!
