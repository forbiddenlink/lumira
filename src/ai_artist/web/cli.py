#!/usr/bin/env python3
"""CLI tool to launch the web gallery."""

import os
import sys

import uvicorn

from ai_artist.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def main() -> None:
    """Launch the web gallery server."""
    # Use PORT environment variable if available (Railway sets this)
    port = int(os.getenv("PORT", "8000"))

    logger.info("starting_web_gallery", host="0.0.0.0", port=port)  # nosec B104

    print("\n🎨 AI Artist Web Gallery")
    print("=" * 50)
    print(f"\n📍 Gallery URL: http://localhost:{port}")
    print(f"📊 API Docs:    http://localhost:{port}/docs")
    print(f"❤️  Health:     http://localhost:{port}/health")
    print("\nPress Ctrl+C to stop the server\n")
    print("=" * 50)

    try:
        uvicorn.run(
            "ai_artist.web.app:app",
            host="0.0.0.0",  # nosec B104
            port=port,
            log_level="info",
            reload=False,
            ws="websockets",  # Explicitly force websockets
        )
    except KeyboardInterrupt:
        logger.info("web_gallery_stopped")
        print("\n\n👋 Gallery server stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
