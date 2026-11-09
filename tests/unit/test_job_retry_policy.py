"""Paid cloud jobs must not auto-retry: a retry after a billed failure pays twice."""

import pytest

from ai_artist.queue.job_queue import _max_retries_for


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("LUMIRA_JOB_MAX_RETRIES", raising=False)
    monkeypatch.delenv("LUMIRA_JOB_RETRY_PAID", raising=False)
    # No config/config.yaml in cwd, so the backend falls back to "local".
    monkeypatch.chdir(tmp_path)


def test_local_backend_keeps_default_retries():
    assert _max_retries_for({}) == 3
    assert _max_retries_for({"backend": "local"}) == 3


@pytest.mark.parametrize("backend", ["replicate", "magica", "Magica", "something-new"])
def test_paid_or_unknown_backend_gets_no_retries(backend):
    assert _max_retries_for({"backend": backend}) == 0


def test_paid_backend_from_config_yaml_gets_no_retries(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text("model:\n  backend: replicate\n")
    assert _max_retries_for({}) == 0


def test_opt_in_restores_retries_for_paid(monkeypatch):
    monkeypatch.setenv("LUMIRA_JOB_RETRY_PAID", "1")
    monkeypatch.setenv("LUMIRA_JOB_MAX_RETRIES", "2")
    assert _max_retries_for({"backend": "magica"}) == 2


def test_global_zero_still_disables_local(monkeypatch):
    monkeypatch.setenv("LUMIRA_JOB_MAX_RETRIES", "0")
    assert _max_retries_for({"backend": "local"}) == 0
