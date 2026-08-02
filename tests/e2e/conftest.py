"""E2E test fixtures for Playwright testing of Lumira web UI."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import closing, suppress
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page


def find_free_port() -> int:
    """Find a free port on localhost."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _seed_e2e_runtime(root: Path) -> None:
    """Create a lightweight runtime tree so E2E does not load dev memory blobs."""
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    gallery_dir = root / "gallery" / "2026" / "06" / "25"
    gallery_dir.mkdir(parents=True, exist_ok=True)

    minimal_memory = {
        "episodic": {"episodes": []},
        "semantic": {
            "knowledge": {
                "style_effectiveness": {},
                "subject_preferences": {},
                "color_associations": {},
                "mood_patterns": {},
            }
        },
        "created_at": "2026-06-25T12:00:00",
        "experience": {"level": 1, "xp": 0, "total_xp": 0, "milestones": []},
        "reflection": {"reflection_count": 0, "insights": [], "last_reflection": None},
    }
    (data_dir / "lumira_enhanced_memory.json").write_text(
        json.dumps(minimal_memory), encoding="utf-8"
    )
    (data_dir / "lumira_memory.json").write_text(
        json.dumps(
            {
                "name": "Lumira",
                "created_at": "2026-06-25T12:00:00",
                "paintings": [],
                "reflections": [],
                "preferences": {
                    "favorite_subjects": {},
                    "favorite_styles": {},
                    "favorite_colors": {},
                },
                "stats": {
                    "total_created": 0,
                    "best_score": 0.0,
                    "favorite_mood": None,
                },
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "lumira_personality.json").write_text(
        json.dumps(
            {
                "traits": {
                    "openness": 0.8,
                    "conscientiousness": 0.5,
                    "extraversion": 0.5,
                    "agreeableness": 0.5,
                    "neuroticism": 0.5,
                },
                "saved_at": "2026-06-25T12:00:00",
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "lumira_mood_history.json").write_text("[]", encoding="utf-8")

    for index, color in enumerate(((120, 80, 200), (80, 150, 120)), start=1):
        sample_img = gallery_dir / f"e2e-sample-{index}.png"
        sample_json = gallery_dir / f"e2e-sample-{index}.json"
        try:
            from PIL import Image

            Image.new("RGB", (64, 64), color=color).save(sample_img)
        except Exception:
            sample_img.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00@\x00\x00\x00@\x08\x02"
                b"\x00\x00\x00%\x0b\xe6\x89\x00\x00\x00\nIDATx\x9cc``\x00\x00\x00\x02"
                b"\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        sample_json.write_text(
            json.dumps(
                {
                    "prompt": f"E2E test artwork {index}",
                    "created_at": f"2026-06-25T12:0{index}:00",
                }
            ),
            encoding="utf-8",
        )


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
    import httpx

    e2e_root = Path(tempfile.mkdtemp(prefix="lumira-e2e-"))
    _seed_e2e_runtime(e2e_root)

    project_root = Path(__file__).resolve().parents[2]
    # Share real config so Magica/local factory resolves like production studio
    config_link = e2e_root / "config"
    if not config_link.exists():
        try:
            config_link.symlink_to(project_root / "config", target_is_directory=True)
        except OSError:
            shutil.copytree(project_root / "config", config_link)

    # Set environment variables for test mode
    env = os.environ.copy()
    env["PORT"] = str(test_port)
    env["TESTING"] = "1"
    env["LUMIRA_DEV_MODE"] = "1"
    env["WS_MAX_CONNECTIONS"] = "20"
    env["PYTHONPATH"] = str(project_root / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    # Capture server output so failures (e.g. a 500 behind an E2E assertion) are
    # diagnosable instead of silently discarded to /dev/null.
    server_log_path = e2e_root / "server.log"
    server_log = open(server_log_path, "w")

    # Start the server in an isolated cwd with minimal data files
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "ai_artist.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(test_port),
            "--no-access-log",
        ],
        cwd=e2e_root,
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )

    def _dump_server_log(reason: str) -> None:
        server_log.flush()
        try:
            tail = server_log_path.read_text(errors="replace").splitlines()[-60:]
        except OSError:
            tail = []
        print(f"\n----- e2e server log ({reason}) -----")
        print("\n".join(tail))
        print("----- end e2e server log -----\n")

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
        proc.wait(timeout=5)
        _dump_server_log("startup timeout")
        server_log.close()
        raise RuntimeError(
            f"Server failed to start within {max_wait}s.\n" f"isolated cwd: {e2e_root}"
        )

    try:
        yield
    finally:
        # Shutdown server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        # Surface any server-side errors (5xx tracebacks) recorded during the run.
        if os.getenv("E2E_DUMP_SERVER_LOG", "1") != "0":
            _dump_server_log("session teardown")
        server_log.close()
        shutil.rmtree(e2e_root, ignore_errors=True)


@pytest.fixture(scope="session")
def base_url(test_port: int, server_process: None) -> str:
    """Get the base URL for the test server."""
    return f"http://127.0.0.1:{test_port}"


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Stabilize headless Chromium for long E2E runs."""
    return {
        "headless": True,
        "args": ["--disable-dev-shm-usage", "--disable-gpu"],
    }


@pytest.fixture(scope="function")
def page_with_server(
    browser: Browser,
    base_url: str,
) -> Generator[Page, None, None]:
    """Create an isolated page connected to the running test server."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        service_workers="block",
    )
    for pattern in (
        r"https?://fonts\.(googleapis|gstatic)\.com/.*",
        r"https?://unpkg\.com/.*",
    ):
        context.route(re.compile(pattern), lambda route: route.abort())
    page = context.new_page()
    page.set_default_timeout(10000)
    try:
        yield page
    finally:
        page.close()
        context.close()


def _wait_for_page_loader(page: Page, timeout: int = 5000) -> None:
    """Wait until the full-screen loader no longer intercepts clicks."""
    try:
        page.wait_for_function(
            "() => { const el = document.getElementById('page-loader');"
            " return !el || el.classList.contains('loaded'); }",
            timeout=timeout,
        )
    except Exception:
        page.evaluate(
            "() => { const el = document.getElementById('page-loader');"
            " if (el) el.classList.add('loaded'); }"
        )


@pytest.fixture(scope="function")
def lumira_page(page_with_server: Page, base_url: str) -> Page:
    """Navigate to Lumira page and wait for it to be ready."""
    page = page_with_server
    page.set_default_timeout(30000)
    page.goto(f"{base_url}/lumira", wait_until="domcontentloaded", timeout=45000)

    # Wait for the page to be interactive
    page.wait_for_selector("h1:has-text('LUMIRA')", timeout=30000)
    _wait_for_page_loader(page)

    # Mood may stay on Awakening if API is slow; don't block the full suite
    with suppress(Exception):
        page.wait_for_selector(
            "#mood-text:not(:has-text('Awakening...'))", timeout=5000
        )

    return page


@pytest.fixture(scope="function")
def gallery_page(page_with_server: Page, base_url: str) -> Page:
    """Navigate to the modern gallery homepage."""
    page = page_with_server
    page.goto(f"{base_url}/")
    page.wait_for_selector("#gallery", timeout=15000)
    _wait_for_page_loader(page)
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
