"""Integration-test isolation.

Integration tests construct a real :class:`~ai_artist.main.AIArtist`, whose memory /
mood / adaptive-learning / narrative subsystems persist to hardcoded relative paths
(``data/lumira_memory.json``, ``data/lumira_mood_history.json``, ...). Without isolation
those writes land in the repo's real ``data/`` files and pollute local runtime state
(the "test landscape" entries seen previously). Redirect the working directory to a temp
dir for every integration test so all relative ``data/`` / ``logs/`` / ``gallery/`` writes
stay contained.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path, monkeypatch):
    # Only chdir: the app's persisters self-create their parent dirs
    # (mkdir parents=True, exist_ok=True), and some tests create their own
    # gallery/config dirs, so pre-creating here would collide.
    monkeypatch.chdir(tmp_path)
    yield
