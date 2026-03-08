# Web Gallery Guide

The Lumira Web Gallery provides a beautiful web interface to browse and explore your AI-generated artwork.

## Quick Start

### Launch the Gallery

```bash
lumira-web
```

The gallery will start on **<http://localhost:8000>**

### Access Points

- **Gallery Homepage**: <http://localhost:8000>
- **API Documentation**: <http://localhost:8000/docs>
- **Health Check**: <http://localhost:8000/health>

## Features

### 🖼️ Image Gallery

- **Grid View**: Beautiful responsive grid layout
- **Lazy Loading**: Images load as you scroll
- **Modal View**: Click any image for full-screen viewing
- **Metadata Display**: View prompts, dates, and generation details

### 🔍 Search & Filter

- **Text Search**: Search artwork by prompt keywords
- **Featured Filter**: Show only featured/curated artwork
- **Real-time Results**: Search updates as you type

### 📊 Statistics Dashboard

- Total artwork count
- Featured artwork count
- Unique prompts count
- Date range information

### 📱 Responsive Design

- Works on desktop, tablet, and mobile
- Touch-friendly interface
- Adaptive grid layout

## API Endpoints

### List Images

```bash
GET /api/images?limit=50&offset=0&featured=true&search=sunset
```

**Query Parameters**:

- `limit`: Number of images (1-500, default: 50)
- `offset`: Pagination offset (default: 0)
- `featured`: Filter featured only (true/false)
- `search`: Search in prompts

**Response**:

```json
[
  {
    "path": "2026/01/09/archive/20260109_102341_noseed.png",
    "filename": "20260109_102341_noseed.png",
    "prompt": "a serene landscape at sunset...",
    "created_at": "2026-01-09T10:23:41",
    "featured": false,
    "metadata": {...},
    "thumbnail_url": "/api/images/file/...",
    "full_url": "/api/images/file/..."
  }
]
```

### Get Image File

```bash
GET /api/images/file/2026/01/09/archive/20260109_102341_noseed.png
```

Returns the actual PNG image file.

### Gallery Statistics

```bash
GET /api/stats
```

**Response**:

```json
{
  "total_images": 42,
  "featured_images": 8,
  "total_prompts": 35,
  "date_range": {
    "earliest": "2026-01-08T10:00:00",
    "latest": "2026-01-09T15:30:00"
  }
}
```

### Health Check

```bash
GET /health
```

**Response**:

```json
{
  "status": "healthy",
  "timestamp": "2026-01-09T16:00:00",
  "gallery_initialized": true
}
```

## Configuration

### Gallery Path

The gallery reads from the `gallery/` directory by default. This is where `GalleryManager` saves generated images.

### Port Configuration

Default port is **8000**. To change:

```python
# In src/ai_artist/web/cli.py
uvicorn.run(
    "ai_artist.web.app:app",
    host="0.0.0.0",
    port=8080,  # Change this
    ...
)
```

### Production Deployment

For production, use a proper ASGI server setup:

```bash
# With Gunicorn + Uvicorn workers
gunicorn ai_artist.web.app:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

Or with Docker:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 8000
CMD ["lumira-web"]
```

## Architecture

### Backend Stack

- **FastAPI**: Modern Python web framework
- **Uvicorn**: ASGI server
- **Pydantic**: Data validation
- **Jinja2**: Template engine

### Frontend

- **Vanilla JavaScript**: No framework dependencies
- **CSS Grid**: Responsive layout
- **Fetch API**: Async image loading
- **Modal Component**: Full-screen image viewing

### File Structure

```
src/ai_artist/web/
├── __init__.py
├── app.py              # FastAPI application
├── cli.py              # CLI launcher
└── templates/
    └── gallery.html    # Frontend UI
```

## Development

### Running in Debug Mode

```bash
# With auto-reload
uvicorn ai_artist.web.app:app --reload --port 8000
```

### Testing Endpoints

```bash
# Test health check
curl http://localhost:8000/health

# Test stats
curl http://localhost:8000/api/stats

# Test image listing
curl "http://localhost:8000/api/images?limit=5"

# Search for images
curl "http://localhost:8000/api/images?search=sunset"
```

### Adding Custom Endpoints

Edit `src/ai_artist/web/app.py`:

```python
@app.get("/api/custom")
async def custom_endpoint():
    """Your custom endpoint."""
    return {"message": "Hello!"}
```

## Troubleshooting

### Port Already in Use

```
ERROR: [Errno 48] Address already in use
```

**Solution**: Change the port in `cli.py` or kill the process using port 8000:

```bash
lsof -ti:8000 | xargs kill -9
```

### Gallery Not Found

```
Gallery not initialized
```

**Solution**: Ensure the `gallery/` directory exists and contains images with `.json` metadata files.

### Images Not Loading

**Solution**: Check that:

1. PNG files exist in `gallery/`
2. Corresponding `.json` metadata files exist
3. File paths are readable by the server

## Security Notes

### Path Traversal Protection

The API validates that requested image paths are within the gallery directory.

### CORS Configuration

For API access from external domains, add CORS middleware:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
```

### Production Security

- Use HTTPS (TLS certificates)
- Add authentication if needed
- Rate limiting for API endpoints
- Input validation (already included via Pydantic)

## Performance Tips

1. **Image Optimization**: The gallery serves full-resolution PNGs. Consider adding thumbnail generation for faster loading.

2. **Caching**: Add HTTP caching headers for static assets:

   ```python
   @app.get("/api/images/file/{file_path:path}")
   async def get_image_file(file_path: str, response: Response):
       response.headers["Cache-Control"] = "public, max-age=86400"
       # ... rest of code
   ```

3. **Database**: For large galleries (1000+ images), consider adding a database index instead of filesystem scanning.

## Next Steps

- Add user favorites/likes
- Implement tagging system
- Add download functionality
- Create slideshow mode
- Add social sharing
- Integrate with external galleries

---

**Note**: The web gallery is designed to complement the CLI tools, not replace them. Use `lumira-gallery` for terminal-based viewing and `lumira-web` for browser-based exploration.
