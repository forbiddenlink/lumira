"""Tests for Aria API routes."""

import pytest
from fastapi.testclient import TestClient

from ai_artist.web.app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestAriaState:
    """Tests for /api/aria/state endpoint."""

    def test_get_state_returns_required_fields(self, client):
        """State endpoint should return all required fields."""
        response = client.get("/api/aria/state")
        assert response.status_code == 200

        data = response.json()
        assert "name" in data
        assert "mood" in data
        assert "energy" in data
        assert "feeling" in data
        assert "paintings_created" in data
        assert "personality" in data

    def test_state_has_valid_mood(self, client):
        """Mood should be a valid mood string."""
        response = client.get("/api/aria/state")
        data = response.json()

        valid_moods = [
            "contemplative",
            "chaotic",
            "melancholic",
            "energized",
            "rebellious",
            "serene",
            "restless",
            "playful",
            "introspective",
            "bold",
        ]
        assert data["mood"] in valid_moods

    def test_state_has_valid_energy(self, client):
        """Energy should be between 0 and 1."""
        response = client.get("/api/aria/state")
        data = response.json()

        assert 0.0 <= data["energy"] <= 1.0

    def test_state_has_ocean_personality(self, client):
        """Personality should have OCEAN traits."""
        response = client.get("/api/aria/state")
        data = response.json()

        personality = data["personality"]
        assert "openness" in personality
        assert "conscientiousness" in personality
        assert "extraversion" in personality
        assert "agreeableness" in personality
        assert "neuroticism" in personality

        # All traits should be between 0 and 1
        for trait, value in personality.items():
            assert 0.0 <= value <= 1.0, f"{trait} should be between 0 and 1"


@pytest.mark.slow
class TestAriaCreate:
    """Tests for /api/aria/create endpoint."""

    def test_create_returns_success(self, client):
        """Create endpoint should return success."""
        response = client.post("/api/aria/create")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

    def test_create_returns_concept_data(self, client):
        """Create should return concept data."""
        response = client.post("/api/aria/create")
        data = response.json()

        assert "subject" in data
        assert "style" in data
        assert "prompt" in data
        assert data["subject"] is not None
        assert data["style"] is not None

    def test_create_returns_thinking(self, client):
        """Create should return thinking narrative."""
        response = client.post("/api/aria/create")
        data = response.json()

        assert "thinking" in data
        assert data["thinking"] is not None
        assert len(data["thinking"]) > 0

    def test_create_returns_critique_history(self, client):
        """Create should return critique history."""
        response = client.post("/api/aria/create")
        data = response.json()

        assert "critique_history" in data
        assert isinstance(data["critique_history"], list)
        assert len(data["critique_history"]) > 0

        critique = data["critique_history"][0]
        assert "critic_name" in critique
        assert "critique" in critique
        assert "approved" in critique

    def test_create_returns_reflection(self, client):
        """Create should return artistic reflection."""
        response = client.post("/api/aria/create")
        data = response.json()

        assert "reflection" in data
        assert data["reflection"] is not None


class TestAriaEvolve:
    """Tests for /api/aria/evolve endpoint."""

    def test_evolve_returns_new_state(self, client):
        """Evolve should return updated state."""
        response = client.post("/api/aria/evolve")
        assert response.status_code == 200

        data = response.json()
        assert "mood" in data
        assert "energy" in data
        assert "feeling" in data
        assert "personality" in data

    def test_evolve_updates_personality_slightly(self, client):
        """Evolve should make small personality changes."""
        # Get initial state
        initial = client.get("/api/aria/state").json()
        initial_personality = initial["personality"]

        # Evolve multiple times
        for _ in range(5):
            client.post("/api/aria/evolve")

        # Check personality changed (at least slightly)
        final = client.get("/api/aria/state").json()
        final_personality = final["personality"]

        # At least one trait should have changed
        changes = [
            abs(initial_personality[k] - final_personality[k])
            for k in initial_personality
        ]
        assert any(c > 0 for c in changes), "Personality should evolve over time"


class TestAriaStatement:
    """Tests for /api/aria/statement endpoint."""

    def test_statement_returns_content(self, client):
        """Statement endpoint should return artist statement."""
        response = client.get("/api/aria/statement")
        assert response.status_code == 200

        data = response.json()
        assert "statement" in data
        assert "name" in data
        assert len(data["statement"]) > 50  # Should be substantial

    def test_statement_mentions_aria(self, client):
        """Statement should mention Aria."""
        response = client.get("/api/aria/statement")
        data = response.json()

        assert "Aria" in data["statement"] or "aria" in data["statement"].lower()


class TestAriaPortfolio:
    """Tests for /api/aria/portfolio endpoint."""

    def test_portfolio_returns_list(self, client):
        """Portfolio should return a list of paintings."""
        response = client.get("/api/aria/portfolio")
        assert response.status_code == 200

        data = response.json()
        assert "count" in data
        assert "paintings" in data
        assert isinstance(data["paintings"], list)

    def test_portfolio_respects_limit(self, client):
        """Portfolio should respect limit parameter."""
        response = client.get("/api/aria/portfolio?limit=5")
        data = response.json()

        assert len(data["paintings"]) <= 5


class TestAriaEvolution:
    """Tests for /api/aria/evolution endpoint."""

    def test_evolution_returns_timeline_data(self, client):
        """Evolution endpoint should return timeline data."""
        response = client.get("/api/aria/evolution")
        assert response.status_code == 200

        data = response.json()
        assert "phases" in data
        assert "milestones" in data
        assert "style_evolution" in data
        assert "mood_distribution" in data
        assert "score_trend" in data
        assert "summary" in data

    def test_evolution_summary_has_stats(self, client):
        """Evolution summary should have statistics."""
        response = client.get("/api/aria/evolution")
        data = response.json()

        summary = data.get("summary", {})
        assert "total_creations" in summary
        assert "unique_styles" in summary
        assert "phases_count" in summary


class TestAriaPage:
    """Tests for /aria HTML page."""

    def test_aria_page_loads(self, client):
        """Aria page should load successfully."""
        response = client.get("/aria")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_aria_page_has_title(self, client):
        """Aria page should have correct title."""
        response = client.get("/aria")
        assert b"Aria" in response.content or b"ARIA" in response.content

    def test_aria_page_has_mood_orb(self, client):
        """Aria page should have mood orb element."""
        response = client.get("/aria")
        assert b"mood-orb" in response.content

    def test_aria_page_has_personality_section(self, client):
        """Aria page should have personality display."""
        response = client.get("/aria")
        assert b"personality" in response.content.lower()

    def test_aria_page_has_stream_of_consciousness(self, client):
        """Aria page should have thinking stream."""
        response = client.get("/aria")
        assert (
            b"thought-stream" in response.content
            or b"Stream of Consciousness" in response.content
        )
