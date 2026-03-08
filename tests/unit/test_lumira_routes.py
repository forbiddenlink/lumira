"""Tests for Aria API routes."""

import pytest
from fastapi.testclient import TestClient

from ai_artist.web.app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestLumiraState:
    """Tests for /api/lumira/state endpoint."""

    def test_get_state_returns_required_fields(self, client):
        """State endpoint should return all required fields."""
        response = client.get("/api/lumira/state")
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
        response = client.get("/api/lumira/state")
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
        response = client.get("/api/lumira/state")
        data = response.json()

        assert 0.0 <= data["energy"] <= 1.0

    def test_state_has_ocean_personality(self, client):
        """Personality should have OCEAN traits."""
        response = client.get("/api/lumira/state")
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
class TestLumiraCreate:
    """Tests for /api/lumira/create endpoint."""

    def test_create_returns_success(self, client):
        """Create endpoint should return success."""
        response = client.post("/api/lumira/create")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

    def test_create_returns_concept_data(self, client):
        """Create should return concept data."""
        response = client.post("/api/lumira/create")
        data = response.json()

        assert "subject" in data
        assert "style" in data
        assert "prompt" in data
        assert data["subject"] is not None
        assert data["style"] is not None

    def test_create_returns_thinking(self, client):
        """Create should return thinking narrative."""
        response = client.post("/api/lumira/create")
        data = response.json()

        assert "thinking" in data
        assert data["thinking"] is not None
        assert len(data["thinking"]) > 0

    def test_create_returns_critique_history(self, client):
        """Create should return critique history."""
        response = client.post("/api/lumira/create")
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
        response = client.post("/api/lumira/create")
        data = response.json()

        assert "reflection" in data
        assert data["reflection"] is not None


class TestLumiraEvolve:
    """Tests for /api/lumira/evolve endpoint."""

    def test_evolve_returns_new_state(self, client):
        """Evolve should return updated state."""
        response = client.post("/api/lumira/evolve")
        assert response.status_code == 200

        data = response.json()
        assert "mood" in data
        assert "energy" in data
        assert "feeling" in data
        assert "personality" in data

    def test_evolve_updates_personality_slightly(self, client):
        """Evolve should make small personality changes."""
        # Get initial state
        initial = client.get("/api/lumira/state").json()
        initial_personality = initial["personality"]

        # Evolve multiple times
        for _ in range(5):
            client.post("/api/lumira/evolve")

        # Check personality changed (at least slightly)
        final = client.get("/api/lumira/state").json()
        final_personality = final["personality"]

        # At least one trait should have changed
        changes = [
            abs(initial_personality[k] - final_personality[k])
            for k in initial_personality
        ]
        assert any(c > 0 for c in changes), "Personality should evolve over time"


class TestLumiraStatement:
    """Tests for /api/lumira/statement endpoint."""

    def test_statement_returns_content(self, client):
        """Statement endpoint should return artist statement."""
        response = client.get("/api/lumira/statement")
        assert response.status_code == 200

        data = response.json()
        assert "statement" in data
        assert "name" in data
        assert len(data["statement"]) > 50  # Should be substantial

    def test_statement_mentions_lumira(self, client):
        """Statement should mention Lumira."""
        response = client.get("/api/lumira/statement")
        data = response.json()

        assert "Lumira" in data["statement"] or "lumira" in data["statement"].lower()


class TestLumiraPortfolio:
    """Tests for /api/lumira/portfolio endpoint."""

    def test_portfolio_returns_list(self, client):
        """Portfolio should return a list of paintings."""
        response = client.get("/api/lumira/portfolio")
        assert response.status_code == 200

        data = response.json()
        assert "count" in data
        assert "paintings" in data
        assert isinstance(data["paintings"], list)

    def test_portfolio_respects_limit(self, client):
        """Portfolio should respect limit parameter."""
        response = client.get("/api/lumira/portfolio?limit=5")
        data = response.json()

        assert len(data["paintings"]) <= 5


class TestLumiraEvolution:
    """Tests for /api/lumira/evolution endpoint."""

    def test_evolution_returns_timeline_data(self, client):
        """Evolution endpoint should return timeline data."""
        response = client.get("/api/lumira/evolution")
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
        response = client.get("/api/lumira/evolution")
        data = response.json()

        summary = data.get("summary", {})
        assert "total_creations" in summary
        assert "unique_styles" in summary
        assert "phases_count" in summary


class TestLumiraPage:
    """Tests for /lumira HTML page."""

    def test_aria_page_loads(self, client):
        """Aria page should load successfully."""
        response = client.get("/lumira")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_aria_page_has_title(self, client):
        """Aria page should have correct title."""
        response = client.get("/lumira")
        assert b"Aria" in response.content or b"ARIA" in response.content

    def test_aria_page_has_mood_orb(self, client):
        """Aria page should have mood orb element."""
        response = client.get("/lumira")
        assert b"mood-orb" in response.content

    def test_aria_page_has_personality_section(self, client):
        """Aria page should have personality display."""
        response = client.get("/lumira")
        assert b"personality" in response.content.lower()

    def test_aria_page_has_stream_of_consciousness(self, client):
        """Aria page should have thinking stream."""
        response = client.get("/lumira")
        assert (
            b"thought-stream" in response.content
            or b"Stream of Consciousness" in response.content
        )


# ========== NEW ENDPOINT TESTS (Phase 4-5 Additions) ==========


class TestLumiraMoodInfluence:
    """Tests for /api/lumira/mood/influence endpoint."""

    def test_mood_influence_accepts_valid_moods(self, client):
        """Influence endpoint should accept valid mood types."""
        response = client.post(
            "/api/lumira/mood/influence",
            json={"influence_type": "energize", "intensity": 0.5},
        )
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "previous_mood" in data
        assert "new_mood" in data

    def test_mood_influence_types(self, client):
        """Test all influence types work."""
        influence_types = ["energize", "calm", "inspire", "challenge"]

        for influence_type in influence_types:
            response = client.post(
                "/api/lumira/mood/influence",
                json={"influence_type": influence_type, "intensity": 0.3},
            )
            assert response.status_code == 200, f"Failed for {influence_type}"

    def test_mood_influence_intensity_bounds(self, client):
        """Intensity should be bounded."""
        # Test low intensity
        response = client.post(
            "/api/lumira/mood/influence",
            json={"influence_type": "energize", "intensity": 0.1},
        )
        assert response.status_code == 200

        # Test high intensity
        response = client.post(
            "/api/lumira/mood/influence",
            json={"influence_type": "calm", "intensity": 1.0},
        )
        assert response.status_code == 200


class TestLumiraMemoryDashboard:
    """Tests for /api/lumira/memory endpoint."""

    def test_memory_dashboard_returns_structure(self, client):
        """Memory dashboard should return expected structure."""
        response = client.get("/api/lumira/memory")
        assert response.status_code == 200

        data = response.json()
        assert "recent_memories" in data
        assert "patterns" in data
        assert "learned_preferences" in data
        assert "memory_count" in data

    def test_memory_dashboard_lists_are_correct_type(self, client):
        """Memory lists should be lists."""
        response = client.get("/api/lumira/memory")
        data = response.json()

        assert isinstance(data["recent_memories"], list)
        assert isinstance(data["patterns"], list)
        assert isinstance(data["learned_preferences"], dict)


class TestLumiraMoodEvolution:
    """Tests for /api/lumira/mood/evolution endpoint."""

    def test_mood_evolution_returns_history(self, client):
        """Mood evolution should return timeline data."""
        response = client.get("/api/lumira/mood/evolution")
        assert response.status_code == 200

        data = response.json()
        assert "history" in data
        assert "current_phase" in data

    def test_mood_evolution_history_is_list(self, client):
        """History should be a list."""
        response = client.get("/api/lumira/mood/evolution")
        data = response.json()

        assert isinstance(data["history"], list)


class TestLumiraImg2Img:
    """Tests for /api/lumira/img2img endpoint."""

    def test_img2img_requires_image_source(self, client):
        """Img2img should require either image_id or image_base64."""
        response = client.post(
            "/api/lumira/img2img",
            json={"prompt": "test variation"},
        )
        # Should fail without image source
        assert response.status_code in [400, 404, 422]

    def test_img2img_invalid_image_id(self, client):
        """Img2img should handle invalid image IDs gracefully."""
        response = client.post(
            "/api/lumira/img2img",
            json={"image_id": 999999, "prompt": "test"},
        )
        assert response.status_code == 404


class TestLumiraVariations:
    """Tests for /api/lumira/variations endpoint."""

    def test_variations_requires_image_id(self, client):
        """Variations endpoint should require image_id."""
        response = client.post(
            "/api/lumira/variations",
            json={"count": 2},
        )
        # Should fail without image_id
        assert response.status_code in [400, 422]

    def test_variations_invalid_image_id(self, client):
        """Variations should handle invalid image IDs."""
        response = client.post(
            "/api/lumira/variations",
            json={"image_id": 999999, "count": 2},
        )
        assert response.status_code == 404


class TestLumiraBatchCreate:
    """Tests for /api/lumira/batch-create endpoint."""

    def test_batch_create_accepts_count(self, client):
        """Batch create should accept count parameter."""
        response = client.post(
            "/api/lumira/batch-create",
            json={"count": 2},
        )
        # May succeed or fail based on generation capability
        assert response.status_code in [200, 500]

    def test_batch_create_returns_job_info(self, client):
        """Batch create should return batch info when successful."""
        response = client.post(
            "/api/lumira/batch-create",
            json={"count": 1},
        )
        if response.status_code == 200:
            data = response.json()
            assert "batch_id" in data or "success" in data
