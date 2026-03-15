"""E2E tests for Lumira web UI using Playwright.

Run tests with:
    # Install dependencies
    pip install -e ".[e2e]"
    playwright install chromium

    # Run E2E tests only
    pytest tests/e2e/ -m e2e -v

    # Run with headed browser (visible)
    pytest tests/e2e/ -m e2e --headed

    # Run in debug mode (slower, with DevTools)
    pytest tests/e2e/ -m e2e --headed --slowmo 500
"""
