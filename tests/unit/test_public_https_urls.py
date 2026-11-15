"""Public URLs (canonical, og:*, sitemap, robots) must be https on real hosts."""

import re
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from ai_artist.web.app import app


@pytest.fixture
def prod_client():
    return TestClient(app, base_url="http://gallery.example.com")


@pytest.fixture
def local_client():
    return TestClient(app, base_url="http://localhost:8000")


def test_sitemap_uses_https_on_public_host(prod_client):
    body = prod_client.get("/sitemap.xml").text
    assert "<loc>https://gallery.example.com/</loc>" in body
    assert "<loc>http://" not in body


def test_robots_sitemap_line_uses_https_on_public_host(prod_client):
    body = prod_client.get("/robots.txt").text
    assert "Sitemap: https://gallery.example.com/sitemap.xml" in body


def test_home_canonical_and_og_use_https_on_public_host(prod_client):
    html = prod_client.get("/").text
    urls = re.findall(r'(?:href|content)="(https?://[^"]+)"', html)
    public = [u for u in urls if urlparse(u).hostname == "gallery.example.com"]
    assert public, "expected canonical/og URLs on the public host"
    assert all(urlparse(u).scheme == "https" for u in public)


def test_localhost_stays_http(local_client):
    body = local_client.get("/sitemap.xml").text
    assert "<loc>http://localhost:8000/</loc>" in body
