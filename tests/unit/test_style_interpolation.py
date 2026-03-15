"""Tests for Style Interpolation system."""

import pytest

from ai_artist.core.mood_blender import (
    DEFAULT_MOOD_PROFILES,
    BlendedMood,
    MoodBlender,
    MoodProfile,
)
from ai_artist.core.style_interpolator import (
    RECOMMENDED_BLENDS,
    LatentExplorer,
    StyleBlend,
    StyleInterpolator,
)


class TestMoodProfile:
    """Tests for MoodProfile dataclass."""

    def test_mood_profile_defaults(self):
        """Test creating a mood profile."""
        profile = MoodProfile(
            name="test",
            energy_min=0.3,
            energy_max=0.7,
            colors=["blue", "green"],
            styles=["minimal"],
            atmosphere="calm",
        )
        assert profile.name == "test"
        assert profile.avg_energy == 0.5

    def test_all_default_moods_defined(self):
        """Test all 10 Lumira moods have profiles."""
        expected = {
            "contemplative",
            "playful",
            "melancholic",
            "euphoric",
            "serene",
            "anxious",
            "nostalgic",
            "curious",
            "rebellious",
            "transcendent",
        }
        assert set(DEFAULT_MOOD_PROFILES.keys()) == expected

    def test_mood_profiles_have_colors_and_styles(self):
        """Test all profiles have colors and styles."""
        for name, profile in DEFAULT_MOOD_PROFILES.items():
            assert len(profile.colors) >= 2, f"{name} needs more colors"
            assert len(profile.styles) >= 2, f"{name} needs more styles"
            assert profile.atmosphere != "", f"{name} needs atmosphere"


class TestBlendedMood:
    """Tests for BlendedMood dataclass."""

    def test_blended_mood_creation(self):
        """Test creating a blended mood."""
        blend = BlendedMood(
            components={"serene": 0.7, "playful": 0.3},
            energy=0.5,
            colors=["blue", "yellow"],
            styles=["zen", "whimsical"],
            atmosphere="peaceful joy",
            name="serene+playful",
        )
        assert blend.components["serene"] == 0.7
        assert "blue" in blend.colors

    def test_blended_mood_to_dict(self):
        """Test serialization."""
        blend = BlendedMood(
            components={"calm": 1.0},
            energy=0.4,
            colors=["grey"],
            styles=["minimal"],
            atmosphere="quiet",
            name="calm",
        )
        d = blend.to_dict()
        assert d["name"] == "calm"
        assert d["energy"] == 0.4


class TestMoodBlender:
    """Tests for MoodBlender."""

    @pytest.fixture
    def blender(self):
        """Create a MoodBlender instance."""
        return MoodBlender()

    def test_blend_single_mood(self, blender):
        """Test blending with a single mood."""
        blend = blender.blend({"contemplative": 1.0})

        assert blend.name == "contemplative"
        assert "contemplative" in blend.components
        assert blend.components["contemplative"] == 1.0
        assert len(blend.colors) > 0
        assert len(blend.styles) > 0

    def test_blend_two_moods(self, blender):
        """Test blending two moods."""
        blend = blender.blend({"melancholic": 0.7, "serene": 0.3})

        assert "melancholic" in blend.components
        assert "serene" in blend.components
        # Name should reflect both
        assert "melancholic" in blend.name
        # Energy should be weighted average
        melancholic_energy = DEFAULT_MOOD_PROFILES["melancholic"].avg_energy
        serene_energy = DEFAULT_MOOD_PROFILES["serene"].avg_energy
        expected_energy = 0.7 * melancholic_energy + 0.3 * serene_energy
        assert abs(blend.energy - expected_energy) < 0.01

    def test_blend_normalizes_weights(self, blender):
        """Test that weights are normalized."""
        blend = blender.blend({"playful": 2.0, "curious": 2.0})

        # Should be normalized to 0.5 each
        assert abs(blend.components["playful"] - 0.5) < 0.01
        assert abs(blend.components["curious"] - 0.5) < 0.01

    def test_blend_empty_defaults_to_contemplative(self, blender):
        """Test empty weights default to contemplative."""
        blend = blender.blend({})
        assert "contemplative" in blend.components

    def test_blend_colors_combined(self, blender):
        """Test that colors from both moods appear."""
        blend = blender.blend({"euphoric": 0.5, "melancholic": 0.5})

        # Should have colors from both moods
        assert len(blend.colors) >= 3

    def test_get_mood_contrast(self, blender):
        """Test mood contrast suggestions."""
        assert blender.get_mood_contrast("contemplative") == "playful"
        assert blender.get_mood_contrast("playful") == "melancholic"
        assert blender.get_mood_contrast("unknown") == "contemplative"

    def test_suggest_blend(self, blender):
        """Test blend suggestions."""
        suggestion = blender.suggest_blend("serene", tension=0.3)

        assert suggestion["serene"] == 0.7
        contrast = blender.get_mood_contrast("serene")
        assert suggestion[contrast] == 0.3

    def test_interpolate(self, blender):
        """Test smooth interpolation between moods."""
        # At t=0, should be pure mood_a
        blend_0 = blender.interpolate("playful", "melancholic", t=0.0)
        assert blend_0.components["playful"] == 1.0

        # At t=1, should be pure mood_b
        blend_1 = blender.interpolate("playful", "melancholic", t=1.0)
        assert blend_1.components["melancholic"] == 1.0

        # At t=0.5, should be even mix
        blend_mid = blender.interpolate("playful", "melancholic", t=0.5)
        assert abs(blend_mid.components["playful"] - 0.5) < 0.01
        assert abs(blend_mid.components["melancholic"] - 0.5) < 0.01

    def test_get_profile(self, blender):
        """Test getting a mood profile."""
        profile = blender.get_profile("anxious")
        assert profile is not None
        assert profile.name == "anxious"

        assert blender.get_profile("nonexistent") is None


class TestStyleBlend:
    """Tests for StyleBlend dataclass."""

    def test_style_blend_auto_name(self):
        """Test auto-generated name."""
        blend = StyleBlend(styles={"impressionist": 0.6, "cyberpunk": 0.4})
        assert "impressionist" in blend.name
        assert "cyberpunk" in blend.name

    def test_style_blend_custom_name(self):
        """Test custom name."""
        blend = StyleBlend(
            styles={"zen": 1.0},
            name="my_custom_style",
            description="A peaceful approach",
        )
        assert blend.name == "my_custom_style"

    def test_style_blend_to_dict(self):
        """Test serialization."""
        blend = StyleBlend(
            styles={"minimal": 0.5, "bold": 0.5},
            description="Contrast of approaches",
        )
        d = blend.to_dict()
        assert d["styles"]["minimal"] == 0.5
        assert "description" in d


class TestRecommendedBlends:
    """Tests for recommended blend presets."""

    def test_recommended_blends_exist(self):
        """Test that recommended blends are defined."""
        assert len(RECOMMENDED_BLENDS) >= 4

    def test_recommended_blends_have_descriptions(self):
        """Test that blends have descriptions."""
        for blend in RECOMMENDED_BLENDS:
            assert blend.description != "", f"{blend.name} needs description"

    def test_recommended_blends_have_valid_weights(self):
        """Test that blend weights are valid."""
        for blend in RECOMMENDED_BLENDS:
            total = sum(blend.styles.values())
            assert 0.9 <= total <= 1.1, f"{blend.name} weights should sum to ~1"


class TestStyleInterpolator:
    """Tests for StyleInterpolator."""

    @pytest.fixture
    def interpolator(self):
        """Create a StyleInterpolator with no pipeline."""
        return StyleInterpolator(
            lora_registry={
                "impressionist": "/fake/path/impressionist.safetensors",
                "zen": "/fake/path/zen.safetensors",
            }
        )

    def test_init_with_registry(self, interpolator):
        """Test initialization with LoRA registry."""
        assert "impressionist" in interpolator.registry
        assert "zen" in interpolator.registry

    def test_register_style_nonexistent_path(self, interpolator):
        """Test registering style with invalid path fails."""
        result = interpolator.register_style("bad", "/nonexistent/path.safetensors")
        assert result is False

    @pytest.mark.asyncio
    async def test_load_styles_no_pipeline(self, interpolator):
        """Test loading styles without pipeline returns empty."""
        loaded = await interpolator.load_styles(["impressionist"])
        assert loaded == []

    @pytest.mark.asyncio
    async def test_set_blend_no_pipeline(self, interpolator):
        """Test setting blend without pipeline fails gracefully."""
        result = await interpolator.set_blend({"impressionist": 1.0})
        assert result is False

    def test_get_recommended_blends_filters_by_registry(self):
        """Test that recommendations filter by available styles."""
        # Empty registry should return empty recommendations
        interpolator = StyleInterpolator(lora_registry={})
        blends = interpolator.get_recommended_blends()
        assert len(blends) == 0

    def test_suggest_blend_for_mood(self, interpolator):
        """Test mood-based style suggestions."""
        blend = interpolator.suggest_blend_for_mood("contemplative")
        assert "impressionist" in blend.styles or "minimalist" in blend.styles

        blend = interpolator.suggest_blend_for_mood("rebellious")
        assert "punk" in blend.styles or "street-art" in blend.styles

    def test_suggest_blend_for_unknown_mood(self, interpolator):
        """Test fallback for unknown mood."""
        blend = interpolator.suggest_blend_for_mood("unknown_mood")
        assert "atmospheric" in blend.styles


class TestLatentExplorer:
    """Tests for LatentExplorer."""

    @pytest.fixture
    def explorer(self):
        """Create a LatentExplorer with no pipeline."""
        return LatentExplorer()

    @pytest.mark.asyncio
    async def test_encode_prompt_no_pipeline(self, explorer):
        """Test encoding without pipeline returns None."""
        result = await explorer.encode_prompt("test prompt")
        assert result is None

    @pytest.mark.asyncio
    async def test_explore_between_no_pipeline(self, explorer):
        """Test exploration without pipeline returns empty result."""
        result = await explorer.explore_between("concept a", "concept b", steps=3)
        assert result.images == []
        assert result.prompts == []

    def test_spherical_lerp(self, explorer):
        """Test spherical interpolation math."""
        import torch

        # Create simple test embeddings
        embed_a = torch.tensor([1.0, 0.0, 0.0])
        embed_b = torch.tensor([0.0, 1.0, 0.0])

        # t=0 should give embed_a
        result_0 = explorer.spherical_lerp(embed_a, embed_b, 0.0)
        assert torch.allclose(result_0, embed_a, atol=1e-5)

        # t=1 should give embed_b
        result_1 = explorer.spherical_lerp(embed_a, embed_b, 1.0)
        assert torch.allclose(result_1, embed_b, atol=1e-5)

        # t=0.5 should be normalized midpoint
        result_mid = explorer.spherical_lerp(embed_a, embed_b, 0.5)
        # Should be roughly [0.707, 0.707, 0] (normalized)
        assert result_mid[0] > 0.5
        assert result_mid[1] > 0.5

    def test_linear_lerp(self, explorer):
        """Test linear interpolation."""
        import torch

        embed_a = torch.tensor([1.0, 0.0])
        embed_b = torch.tensor([0.0, 1.0])

        result_mid = explorer.linear_lerp(embed_a, embed_b, 0.5)
        expected = torch.tensor([0.5, 0.5])
        assert torch.allclose(result_mid, expected)

    @pytest.mark.asyncio
    async def test_explore_variations_no_pipeline(self, explorer):
        """Test variations without pipeline returns empty."""
        result = await explorer.explore_variations("test concept", count=3)
        assert len(result.images) == 0

    @pytest.mark.asyncio
    async def test_find_midpoint_no_pipeline(self, explorer):
        """Test midpoint finding without pipeline."""
        image, desc = await explorer.find_midpoint("a", "b")
        assert image is None
        assert "Failed" in desc


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for style interpolation with mood blending."""

    async def test_mood_to_style_flow(self):
        """Test the flow from mood blend to style suggestion."""
        blender = MoodBlender()
        interpolator = StyleInterpolator()

        # Blend moods
        mood_blend = blender.blend({"contemplative": 0.6, "curious": 0.4})

        # Get style suggestion for dominant mood
        dominant_mood = max(mood_blend.components.items(), key=lambda x: x[1])[0]
        style_blend = interpolator.suggest_blend_for_mood(dominant_mood)

        assert mood_blend.energy > 0
        assert len(style_blend.styles) > 0

    async def test_interpolation_sequence(self):
        """Test creating an interpolation sequence."""
        blender = MoodBlender()

        # Create 5-step interpolation from playful to melancholic
        sequence = []
        for i in range(5):
            t = i / 4.0
            blend = blender.interpolate("playful", "melancholic", t)
            sequence.append(blend)

        # First should be pure playful
        assert sequence[0].components.get("playful", 0) > 0.9

        # Last should be pure melancholic
        assert sequence[-1].components.get("melancholic", 0) > 0.9

        # Middle should be mixed
        assert sequence[2].components.get("playful", 0) > 0.3
        assert sequence[2].components.get("melancholic", 0) > 0.3
