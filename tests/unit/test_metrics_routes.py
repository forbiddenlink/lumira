"""Tests for Prometheus metrics routes."""

import pytest
from fastapi.testclient import TestClient

from ai_artist.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_metrics_endpoint_returns_text(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


def test_monitoring_page_loads(client):
    response = client.get("/monitoring")
    assert response.status_code == 200
    assert "Lumira Monitoring" in response.text
