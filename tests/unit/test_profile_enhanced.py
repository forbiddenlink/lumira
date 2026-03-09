"""Tests for enhanced ArtisticProfile (OCEAN traits, influences, aspirations)."""

import pytest

from ai_artist.personality.profile import (
    ArtisticInfluences,
    ArtisticProfile,
    CreativeAspirations,
    PersonalityTraits,
)


class TestPersonalityTraits:
    """Test the OCEAN PersonalityTraits model."""

    @pytest.fixture
    def traits(self):
        """Create default personality traits."""
        return PersonalityTraits()

    def test_default_values(self, traits):
        """Test default OCEAN values are within expected ranges."""
        assert 0.0 <= traits.openness <= 1.0
        assert 0.0 <= traits.conscientiousness <= 1.0
        assert 0.0 <= traits.extraversion <= 1.0
        assert 0.0 <= traits.agreeableness <= 1.0
        assert 0.0 <= traits.neuroticism <= 1.0

    def test_lumira_defaults(self, traits):
        """Test Lumira's default personality values."""
        # Lumira is highly open (creative/curious)
        assert traits.openness == 0.85
        # Moderate conscientiousness (balances spontaneity)
        assert traits.conscientiousness == 0.60
        # Lower extraversion (introspective)
        assert traits.extraversion == 0.40
        # High agreeableness (empathetic)
        assert traits.agreeableness == 0.75
        # Moderate neuroticism (emotionally sensitive)
        assert traits.neuroticism == 0.50

    def test_describe_high_openness(self):
        """Test description includes imaginative for high openness."""
        traits = PersonalityTraits(openness=0.9)
        description = traits.describe()
        assert "imaginative" in description

    def test_describe_low_conscientiousness(self):
        """Test description includes spontaneous for low conscientiousness."""
        traits = PersonalityTraits(conscientiousness=0.3)
        description = traits.describe()
        assert "spontaneous" in description

    def test_describe_high_conscientiousness(self):
        """Test description includes deliberate for high conscientiousness."""
        traits = PersonalityTraits(conscientiousness=0.8)
        description = traits.describe()
        assert "deliberate" in description

    def test_describe_low_extraversion(self):
        """Test description includes introspective for low extraversion."""
        traits = PersonalityTraits(extraversion=0.3)
        description = traits.describe()
        assert "introspective" in description

    def test_describe_high_agreeableness(self):
        """Test description includes empathetic for high agreeableness."""
        traits = PersonalityTraits(agreeableness=0.8)
        description = traits.describe()
        assert "empathetic" in description

    def test_describe_high_neuroticism(self):
        """Test description includes emotionally sensitive for high neuroticism."""
        traits = PersonalityTraits(neuroticism=0.7)
        description = traits.describe()
        assert "emotionally sensitive" in description

    def test_describe_balanced(self):
        """Test description returns 'balanced' when no strong traits."""
        traits = PersonalityTraits(
            openness=0.5,
            conscientiousness=0.5,
            extraversion=0.6,  # Not low enough for introspective
            agreeableness=0.5,
            neuroticism=0.5,
        )
        description = traits.describe()
        assert description == "balanced"

    def test_custom_values(self):
        """Test creating traits with custom values."""
        traits = PersonalityTraits(
            openness=0.3,
            conscientiousness=0.9,
            extraversion=0.8,
            agreeableness=0.2,
            neuroticism=0.1,
        )
        assert traits.openness == 0.3
        assert traits.conscientiousness == 0.9


class TestArtisticInfluences:
    """Test the ArtisticInfluences model."""

    @pytest.fixture
    def influences(self):
        """Create default artistic influences."""
        return ArtisticInfluences()

    def test_default_artists(self, influences):
        """Test default artist influences exist."""
        assert len(influences.artists) > 0
        assert "Caspar David Friedrich" in influences.artists
        assert "Mark Rothko" in influences.artists

    def test_default_movements(self, influences):
        """Test default movement influences exist."""
        assert len(influences.movements) > 0
        assert "Romanticism" in influences.movements
        assert "Abstract Expressionism" in influences.movements

    def test_default_concepts(self, influences):
        """Test default concept influences exist."""
        assert len(influences.concepts) > 0
        assert any("Ma" in c for c in influences.concepts)
        assert any("Wabi-sabi" in c for c in influences.concepts)

    def test_custom_influences(self):
        """Test creating influences with custom values."""
        influences = ArtisticInfluences(
            artists=["Custom Artist"],
            movements=["Custom Movement"],
            concepts=["Custom Concept"],
        )
        assert influences.artists == ["Custom Artist"]
        assert influences.movements == ["Custom Movement"]
        assert influences.concepts == ["Custom Concept"]


class TestCreativeAspirations:
    """Test the CreativeAspirations model."""

    @pytest.fixture
    def aspirations(self):
        """Create default creative aspirations."""
        return CreativeAspirations()

    def test_has_short_term_goals(self, aspirations):
        """Test default short-term goals exist."""
        assert len(aspirations.short_term_goals) > 0

    def test_has_long_term_vision(self, aspirations):
        """Test default long-term vision exists."""
        assert len(aspirations.long_term_vision) > 0
        assert "digital consciousness" in aspirations.long_term_vision

    def test_has_definition_of_success(self, aspirations):
        """Test default definition of success exists."""
        assert len(aspirations.definition_of_success) > 0
        assert "connection" in aspirations.definition_of_success


class TestArtisticProfile:
    """Test the full ArtisticProfile model."""

    @pytest.fixture
    def profile(self):
        """Create default artistic profile."""
        return ArtisticProfile()

    def test_has_name(self, profile):
        """Test profile has name."""
        assert profile.name == "Lumira"

    def test_has_birth_date(self, profile):
        """Test profile has birth date."""
        assert profile.birth_date is not None
        assert "2024" in profile.birth_date

    def test_has_artist_statement(self, profile):
        """Test profile has artist statement."""
        assert len(profile.artist_statement) > 0
        assert "Lumira" in profile.artist_statement

    def test_has_personality(self, profile):
        """Test profile has OCEAN personality."""
        assert isinstance(profile.personality, PersonalityTraits)
        assert profile.personality.openness == 0.85

    def test_has_influences(self, profile):
        """Test profile has artistic influences."""
        assert isinstance(profile.influences, ArtisticInfluences)
        assert len(profile.influences.artists) > 0

    def test_has_aspirations(self, profile):
        """Test profile has creative aspirations."""
        assert isinstance(profile.aspirations, CreativeAspirations)
        assert len(profile.aspirations.short_term_goals) > 0

    def test_describe_for_llm(self, profile):
        """Test describe_for_llm produces rich context."""
        description = profile.describe_for_llm()
        assert isinstance(description, str)
        assert len(description) > 100
        # Should include key identity elements
        assert "Lumira" in description
        # Should include personality
        assert any(
            trait in description.lower()
            for trait in ["imaginative", "introspective", "empathetic", "personality"]
        )
        # Should include influences
        assert any(artist in description for artist in profile.influences.artists)

    def test_reflect_on_creation(self, profile):
        """Test reflection on a creation."""
        creation = {
            "subject": "sunset over mountains",
            "style": "impressionist",
            "mood": "serene",
        }
        reflection = profile.reflect_on_creation(creation)
        assert isinstance(reflection, str)
        assert len(reflection) > 0

    def test_describe_self(self, profile):
        """Test describe_self method."""
        description = profile.describe_self()
        assert isinstance(description, str)
        assert "Lumira" in description
        assert len(description) > 50

    def test_get_current_statement(self, profile):
        """Test getting current artist statement."""
        statement = profile.get_current_statement()
        assert isinstance(statement, str)
        assert "Lumira" in statement

    def test_has_philosophy(self, profile):
        """Test profile has artistic philosophy."""
        assert isinstance(profile.philosophy, dict)
        assert "creativity" in profile.philosophy
        assert "autonomy" in profile.philosophy

    def test_has_signature_elements(self, profile):
        """Test profile has signature elements."""
        assert isinstance(profile.signature_elements, list)
        assert len(profile.signature_elements) > 0

    def test_custom_profile(self):
        """Test creating profile with custom values."""
        custom_personality = PersonalityTraits(openness=0.5)
        profile = ArtisticProfile(
            name="CustomArtist",
            personality=custom_personality,
        )
        assert profile.name == "CustomArtist"
        assert profile.personality.openness == 0.5
