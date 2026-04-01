"""Tests for shared exception handler rendering."""

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from ai_artist.web.exception_handlers import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


class Payload(BaseModel):
    """Test request body model."""

    prompt: str = Field(min_length=3)


class TestExceptionHandlers:
    """Tests for browser and API exception handler responses."""

    def _build_app(self) -> FastAPI:
        app = FastAPI()
        app.add_exception_handler(HTTPException, http_exception_handler)
        app.add_exception_handler(RequestValidationError, validation_exception_handler)
        app.add_exception_handler(Exception, general_exception_handler)
        return app

    def test_http_exception_returns_html_error_template_for_browser(self):
        app = self._build_app()

        @app.get("/missing")
        def missing():
            raise HTTPException(status_code=404, detail="gone")

        client = TestClient(app)
        response = client.get("/missing", headers={"accept": "text/html"})

        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert "Lumira" in response.text
        assert "Page Not Found" in response.text
        assert "error-glyph" in response.text

    def test_http_exception_returns_json_for_api_requests(self):
        app = self._build_app()

        @app.get("/api/missing")
        def missing():
            raise HTTPException(status_code=404, detail="gone")

        client = TestClient(app)
        response = client.get("/api/missing", headers={"accept": "text/html"})

        assert response.status_code == 404
        assert response.json()["error"] == "gone"

    def test_general_exception_returns_html_error_template_for_browser(self):
        app = self._build_app()

        @app.get("/boom")
        def boom():
            raise RuntimeError("unexpected")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/boom", headers={"accept": "text/html"})

        assert response.status_code == 500
        assert "Something Went Wrong" in response.text
        assert "Creative Studio" in response.text

    def test_validation_exception_remains_json(self):
        app = self._build_app()

        @app.post("/api/payload")
        def payload(body: Payload):
            return body.model_dump()

        client = TestClient(app)
        response = client.post("/api/payload", json={"prompt": "x"})

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Validation error"
        assert data["path"] == "/api/payload"
