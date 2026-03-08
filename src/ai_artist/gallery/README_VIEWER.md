# Gallery Viewer CLI Tool

## Status: Standalone / Not Integrated

⚠️ **This is a standalone CLI tool that is not currently integrated into the main application.**

## What It Does

This tool provides a command-line interface for viewing and browsing the gallery of generated images:

- Lists recent images with timestamps and dimensions
- Displays image metadata
- Can be run independently from the main application

## Usage

The tool is registered as a console script in `pyproject.toml`:

```bash
lumira-gallery --help
lumira-gallery --gallery ./gallery --limit 20
```

## Why It's Not Integrated

The main application uses:

1. **Web Gallery** (`src/ai_artist/web/`) - Full-featured web interface with:
   - Real-time image viewing
   - Filtering and search
   - Responsive grid layout
   - Metadata display

2. **Gallery Management** (`src/ai_artist/gallery/manager.py`) - Programmatic access:
   - Database integration
   - Image tracking
   - Automated cleanup

This CLI tool provides a simple text-based alternative for quick inspection without
starting the web server.

## Decision: Keep or Remove?

**Recommendation**: Keep as optional utility tool.

- Small footprint: 93 lines
- Useful for quick inspection/debugging
- No dependencies on main application
- Can be helpful for CI/CD or scripts
- Already registered as console script in package

## Integration Possibility

Could be enhanced to work with the database:

```python
from ai_artist.db import get_session
from ai_artist.db.models import Artwork

def list_artworks_from_db(limit: int = 10):
    with get_session() as session:
        artworks = session.query(Artwork).order_by(
            Artwork.created_at.desc()
        ).limit(limit).all()
        # Display artwork info...
```

This would make it a useful database inspection tool.
