"""E2E test fixtures for Playwright testing of Lumira web UI."""

import os
import socket
import time
from collections.abc import Generator
from contextlib import closing
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page


def find_free_port() -> int:
    """Find a free port on localhost."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def test_port() -> int:
    """Get a free port for the test server."""
    return find_free_port()


@pytest.fixture(scope="session")
def server_process(test_port: int) -> Generator[None, None, None]:
    """Start FastAPI server for E2E tests.

    This fixture starts the server in a subprocess and waits for it
    to be ready before yielding. Shuts down the server after tests.
    """
    import subprocess

    import httpx

    # Ensure test gallery directory exists with a sample image for E2E
    gallery_path = Path("gallery")
    gallery_path.mkdir(exist_ok=True)
    sample_dir = gallery_path / "2026" / "06" / "25"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_img = sample_dir / "e2e-sample.png"
    sample_json = sample_dir / "e2e-sample.json"
    if not sample_img.exists():
        try:
            from PIL import Image

            Image.new("RGB", (64, 64), color=(120, 80, 200)).save(sample_img)
            sample_json.write_text(
                '{"prompt": "E2E test artwork", "created_at": "2026-06-25T12:00:00"}',
                encoding="utf-8",
            )
        except Exception:
            pass

    # Set environment variables for test mode
    env = os.environ.copy()
    env["PORT"] = str(test_port)
    env["TESTING"] = "1"

    # Start the server
    proc = subprocess.Popen(
        [
            "python",
            "-m",
            "uvicorn",
            "ai_artist.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(test_port),
            "--no-access-log",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready (with timeout)
    base_url = f"http://127.0.0.1:{test_port}"
    max_wait = 30  # seconds
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            response = httpx.get(f"{base_url}/health/ready", timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(
            f"Server failed to start within {max_wait}s.\n"
            f"stdout: {stdout.decode()}\n"
            f"stderr: {stderr.decode()}"
        )

    yield

    # Shutdown server
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="session")
def base_url(test_port: int, server_process: None) -> str:
    """Get the base URL for the test server."""
    return f"http://127.0.0.1:{test_port}"


@pytest.fixture(scope="function")
def page_with_server(
    browser: Browser,
    base_url: str,
) -> Generator[Page, None, None]:
    """Create a page connected to the running test server.

    This fixture creates a new browser context and page for each test,
    ensuring test isolation.
    """
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        # Disable service worker for test consistency
        service_workers="block",
    )
    page = context.new_page()

    # Set a reasonable timeout for E2E tests
    page.set_default_timeout(10000)  # 10 seconds

    yield page

    context.close()


@pytest.fixture(scope="function")
def lumira_page(page_with_server: Page, base_url: str) -> Page:
    """Navigate to Lumira page and wait for it to be ready."""
    page = page_with_server
    page.set_default_timeout(30000)
    page.goto(f"{base_url}/lumira", wait_until="domcontentloaded", timeout=30000)

    # Wait for the page to be interactive
    page.wait_for_selector("h1:has-text('LUMIRA')", timeout=30000)

    # Wait for initial state fetch to complete
    page.wait_for_selector("#mood-text:not(:has-text('Awakening...'))", timeout=30000)

    return page


@pytest.fixture(scope="function")
def gallery_page(page_with_server: Page, base_url: str) -> Page:
    """Navigate to the modern gallery homepage."""
    page = page_with_server
    page.goto(f"{base_url}/")
    page.wait_for_selector("#gallery", timeout=15000)
    return page


@pytest.fixture(scope="function")
def standalone_page(browser: Browser) -> Generator[Page, None, None]:
    """Create a standalone page for testing without server.

    Useful for testing UI interactions that don't require API calls.
    """
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        offline=True,  # Simulate offline to prevent API calls
    )
    page = context.new_page()
    page.set_default_timeout(5000)

    yield page

    context.close()
