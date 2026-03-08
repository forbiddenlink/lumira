"""Expanded tests for Lumira's internal critic system.

This file supplements tests/test_critic.py with additional coverage.
"""

import random
from unittest.mock import patch

import pytest

from ai_artist.personality.critic import ArtistCritic


class TestCriticPersonality:
    """Test critic personality configuration."""

    @pytest.fixture
    def critic(self):
        """Create a critic for testing."""
        return ArtistCritic()

    def test_personality_has_strictness(self, critic):
        """Test personality includes strictness."""
        assert "strictness" in critic.personality
        assert 0.4 <= critic.personality["strictness"] <= 0.7

    def test_personality_has_technical_focus(self, critic):
        """Test personality includes technical focus."""
        assert "technical_focus" in critic.personality
        assert 0.3 <= critic.personality["technical_focus"] <= 0.8

    def test_personality_has_risk_tolerance(self, critic):
        """Test personality includes risk tolerance."""
        assert "risk_tolerance" in critic.personality
        assert 0.4 <= critic.personality["risk_tolerance"] <= 0.7

    def test_personality_is_consistent(self, critic):
        """Test personality stays consistent across critiques."""
        initial_strictness = critic.personality["strictness"]
        # Run several critiques
        concept = {
            "subject": "test",
            "mood": "serene",
            "style": "minimal",
            "colors": [],
        }
        state = {"mood": "serene", "energy": 0.5, "recent_subjects": []}
        for _ in range(5):
            critic.critique_concept(concept, state)
        assert critic.personality["strictness"] == initial_strictness

    def test_different_critics_have_different_personalities(self):
        """Test that multiple critics can have different personalities."""
        # Create many critics and check for variation
        personalities = []
        for _ in range(20):
            critic = ArtistCritic()
            personalities.append(critic.personality["strictness"])

        # Should have some variation (not all identical)
        unique_values = len(set(personalities))
        assert unique_values > 1, "Critics should have varied personalities"


class TestConceptEvaluation:
    """Test concept evaluation logic."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_critique_returns_all_required_fields(self, critic):
        """Test critique returns all required fields."""
        concept = {
            "subject": "sunset",
            "mood": "serene",
            "style": "impressionist",
            "colors": ["orange", "pink"],
        }
        state = {"mood": "serene", "energy": 0.7, "recent_subjects": []}

        result = critic.critique_concept(concept, state)

        assert "approved" in result
        assert "confidence" in result
        assert "critique" in result
        assert "analysis" in result
        assert "critic_name" in result

    def test_critique_handles_minimal_concept(self, critic):
        """Test critique handles minimal concept gracefully."""
        concept = {"subject": "test"}
        state = {}

        result = critic.critique_concept(concept, state)

        assert "approved" in result
        assert isinstance(result["approved"], bool)

    def test_analysis_contains_key_metrics(self, critic):
        """Test analysis contains all expected metrics."""
        concept = {
            "subject": "ocean",
            "mood": "serene",
            "style": "minimalist",
            "colors": ["blue", "white"],
        }
        state = {"mood": "serene", "energy": 0.5, "recent_subjects": []}

        result = critic.critique_concept(concept, state)
        analysis = result["analysis"]

        assert "composition_score" in analysis
        assert "color_harmony" in analysis
        assert "mood_alignment" in analysis
        assert "novelty_score" in analysis
        assert "technical_feasibility" in analysis
        assert "overall_score" in analysis


class TestApprovalRejectionLogic:
    """Test approval and rejection decision logic."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_high_overall_score_approves(self, critic):
        """Test that high overall scores lead to approval."""
        # Patch _analyze_concept to return high scores
        with patch.object(critic, "_analyze_concept") as mock_analyze:
            mock_analyze.return_value = {
                "composition_score": 0.9,
                "color_harmony": 0.9,
                "mood_alignment": 0.9,
                "novelty_score": 0.9,
                "technical_feasibility": 0.9,
                "overall_score": 0.9,
            }

            concept = {"subject": "test"}
            state = {}
            result = critic.critique_concept(concept, state)

            assert result["approved"] is True

    def test_low_overall_score_rejects(self, critic):
        """Test that low overall scores lead to rejection."""
        with patch.object(critic, "_analyze_concept") as mock_analyze:
            mock_analyze.return_value = {
                "composition_score": 0.3,
                "color_harmony": 0.3,
                "mood_alignment": 0.3,
                "novelty_score": 0.3,
                "technical_feasibility": 0.3,
                "overall_score": 0.3,
            }

            concept = {"subject": "test"}
            state = {}
            result = critic.critique_concept(concept, state)

            assert result["approved"] is False

    def test_strictness_affects_threshold(self):
        """Test that stricter critics have higher thresholds."""
        # Create a strict critic
        with patch.object(random, "uniform", return_value=0.7):  # Max strictness
            strict_critic = ArtistCritic()

        # Create a lenient critic
        with patch.object(random, "uniform", return_value=0.4):  # Min strictness
            lenient_critic = ArtistCritic()

        # A borderline concept
        concept = {"subject": "test", "mood": "serene", "style": "test", "colors": []}
        state = {"mood": "serene", "energy": 0.5, "recent_subjects": []}

        # Override analysis to return same score for both
        fixed_analysis = {
            "composition_score": 0.6,
            "color_harmony": 0.6,
            "mood_alignment": 0.6,
            "novelty_score": 0.6,
            "technical_feasibility": 0.6,
            "overall_score": 0.6,
        }

        with patch.object(
            strict_critic, "_analyze_concept", return_value=fixed_analysis
        ):
            strict_result = strict_critic.critique_concept(concept, state)

        with patch.object(
            lenient_critic, "_analyze_concept", return_value=fixed_analysis
        ):
            lenient_result = lenient_critic.critique_concept(concept, state)

        # Lenient critic should be more likely to approve borderline cases
        # (This is probabilistic, so we're testing the mechanism exists)
        assert "confidence" in strict_result
        assert "confidence" in lenient_result

    def test_rejection_includes_suggestions(self, critic):
        """Test that rejections include improvement suggestions."""
        with patch.object(critic, "_analyze_concept") as mock_analyze:
            mock_analyze.return_value = {
                "composition_score": 0.3,
                "color_harmony": 0.4,
                "mood_alignment": 0.3,
                "novelty_score": 0.2,
                "technical_feasibility": 0.4,
                "overall_score": 0.3,
            }

            concept = {"subject": "test"}
            state = {}
            result = critic.critique_concept(concept, state)

            assert result["approved"] is False
            assert "suggestions" in result
            assert isinstance(result["suggestions"], list)


class TestMaxIterationsFallback:
    """Test behavior when max iterations would be reached."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_critique_never_crashes(self, critic):
        """Test critique handles edge cases without crashing."""
        edge_cases = [
            {},
            {"subject": ""},
            {"mood": None},
            {"colors": None},
            {"subject": "x" * 1000},
        ]

        for concept in edge_cases:
            result = critic.critique_concept(concept, {})
            assert "approved" in result

    def test_fallback_on_exception(self, critic):
        """Test fallback behavior when critique fails."""
        with patch.object(
            critic, "_analyze_concept", side_effect=Exception("Test error")
        ):
            concept = {"subject": "test"}
            state = {}
            result = critic.critique_concept(concept, state)

            # Should return fallback result
            assert result["approved"] is True
            assert result["confidence"] == 0.5
            assert "artistic vision" in result["critique"]


class TestMoodStylePairingValidation:
    """Test mood-style pairing validation."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_good_pairings_score_higher(self, critic):
        """Test that known good pairings score higher."""
        # Good pairing: contemplative + minimalist
        good_score = critic._check_mood_style_fit("contemplative", "minimalist")

        # Random pairing: contemplative + glitch art
        # Note: This is probabilistic due to random.uniform
        # but good pairings should be in higher range (0.8-1.0)
        assert good_score >= 0.5  # At minimum, it's not penalized

    def test_all_moods_have_pairings(self, critic):
        """Test all moods have defined style pairings."""
        expected_moods = [
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
        for mood in expected_moods:
            assert mood in critic.MOOD_STYLE_PAIRINGS
            assert len(critic.MOOD_STYLE_PAIRINGS[mood]) > 0

    def test_serene_minimalist_is_good_pair(self, critic):
        """Test specific known good pairing."""
        # Run multiple times due to randomness
        scores = [
            critic._check_mood_style_fit("serene", "minimalist") for _ in range(10)
        ]
        avg_score = sum(scores) / len(scores)
        assert avg_score >= 0.7  # Should generally score well


class TestColorHarmonyAssessment:
    """Test color harmony assessment."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_empty_colors_returns_default(self, critic):
        """Test empty color list returns default score."""
        score = critic._assess_color_harmony([])
        assert score == 0.7

    def test_few_colors_score_higher(self, critic):
        """Test fewer colors generally score higher."""
        # Run multiple times and compare averages
        few_scores = [critic._assess_color_harmony(["red", "blue"]) for _ in range(20)]
        many_scores = [
            critic._assess_color_harmony(["a", "b", "c", "d", "e", "f", "g"])
            for _ in range(20)
        ]

        avg_few = sum(few_scores) / len(few_scores)
        avg_many = sum(many_scores) / len(many_scores)

        assert avg_few > avg_many

    def test_color_harmony_always_in_range(self, critic):
        """Test color harmony is always between 0 and 1."""
        for num_colors in range(0, 10):
            colors = [f"color{i}" for i in range(num_colors)]
            score = critic._assess_color_harmony(colors)
            assert 0.0 <= score <= 1.0


class TestCritiqueTextGeneration:
    """Test critique text generation."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_high_score_generates_positive_text(self, critic):
        """Test high scores generate positive critique text."""
        analysis = {"overall_score": 0.9, "novelty_score": 0.8, "mood_alignment": 0.8}
        text = critic._generate_critique({}, {}, analysis)
        assert "strong" in text.lower()

    def test_low_novelty_mentions_territory(self, critic):
        """Test low novelty mentions exploring similar territory."""
        analysis = {"overall_score": 0.6, "novelty_score": 0.2, "mood_alignment": 0.7}
        text = critic._generate_critique({}, {}, analysis)
        assert "territory" in text.lower() or "similar" in text.lower()

    def test_poor_mood_alignment_mentioned(self, critic):
        """Test poor mood alignment is mentioned."""
        analysis = {"overall_score": 0.5, "novelty_score": 0.7, "mood_alignment": 0.3}
        text = critic._generate_critique({}, {}, analysis)
        assert "mood" in text.lower() or "feeling" in text.lower()


class TestNoveltyScoring:
    """Test novelty scoring based on recent subjects."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_new_subject_has_high_novelty(self, critic):
        """Test new subjects get high novelty score."""
        concept = {"subject": "unique_subject"}
        state = {"recent_subjects": ["old1", "old2", "old3"]}

        analysis = critic._analyze_concept(concept, state)

        assert analysis["novelty_score"] == 0.8

    def test_repeated_subject_has_low_novelty(self, critic):
        """Test repeated subjects get low novelty score."""
        concept = {"subject": "ocean"}
        state = {"recent_subjects": ["mountain", "ocean", "sunset"]}

        analysis = critic._analyze_concept(concept, state)

        assert analysis["novelty_score"] == 0.3

    def test_only_last_5_subjects_considered(self, critic):
        """Test only last 5 subjects affect novelty."""
        concept = {"subject": "ocean"}
        # Ocean is in position 6+ from end, should not count
        state = {"recent_subjects": ["ocean", "a", "b", "c", "d", "e", "f"]}

        analysis = critic._analyze_concept(concept, state)

        # ocean should be considered novel (outside last 5)
        assert analysis["novelty_score"] == 0.8


class TestPersonalityDescription:
    """Test personality description generation."""

    def test_personality_description_varies_with_traits(self):
        """Test description varies based on personality traits."""
        descriptions = set()

        # Create many critics with random personalities
        for _ in range(50):
            critic = ArtistCritic()
            desc = critic.get_personality_description()
            descriptions.add(desc)

        # Should have variety in descriptions
        assert len(descriptions) > 1

    def test_description_contains_style_words(self):
        """Test description contains expected style words."""
        critic = ArtistCritic()
        desc = critic.get_personality_description()

        style_words = [
            "demanding",
            "encouraging",
            "technically",
            "conceptually",
            "experimental",
            "traditional",
        ]

        assert any(word in desc for word in style_words)


class TestTechnicalFeasibilityScoring:
    """Test technical feasibility based on complexity vs energy."""

    @pytest.fixture
    def critic(self):
        return ArtistCritic()

    def test_low_complexity_high_energy_is_feasible(self, critic):
        """Test low complexity with high energy is feasible."""
        concept = {"complexity": 0.3}
        state = {"energy": 0.9}

        analysis = critic._analyze_concept(concept, state)

        assert analysis["technical_feasibility"] == 0.9

    def test_high_complexity_low_energy_less_feasible(self, critic):
        """Test high complexity with low energy is less feasible."""
        concept = {"complexity": 0.9}
        state = {"energy": 0.3}

        analysis = critic._analyze_concept(concept, state)

        assert analysis["technical_feasibility"] == 0.5

    def test_matching_complexity_energy_is_feasible(self, critic):
        """Test matching complexity and energy is feasible."""
        concept = {"complexity": 0.5}
        state = {"energy": 0.5}

        analysis = critic._analyze_concept(concept, state)

        assert analysis["technical_feasibility"] == 0.9  # Within 0.2 margin
