"""Tests for gallery manager and community gallery features."""

import json

import pytest
from PIL import Image

from ai_artist.db.models import (
    Base,
    GalleryComment,
    GalleryLike,
    GalleryShare,
    GeneratedImage,
)
from ai_artist.db.session import create_db_engine, create_session_factory
from ai_artist.gallery.manager import GalleryManager


@pytest.fixture
def test_gallery(tmp_path):
    """Create test gallery."""
    return GalleryManager(tmp_path / "test_gallery")


def test_save_image(test_gallery):
    """Test saving image with metadata."""
    # Create a test image
    image = Image.new("RGB", (512, 512), color="red")
    prompt = "a test image"
    metadata = {"seed": 42, "model": "test-model"}

    # Save image
    saved_path = test_gallery.save_image(
        image=image, prompt=prompt, metadata=metadata, featured=False
    )

    # Verify file exists
    assert saved_path.exists()
    assert saved_path.suffix == ".png"

    # Verify metadata file exists
    metadata_path = saved_path.with_suffix(".json")
    assert metadata_path.exists()

    # Verify metadata content
    saved_metadata = json.loads(metadata_path.read_text())
    assert saved_metadata["prompt"] == prompt
    assert saved_metadata["generation_params"]["seed"] == 42
    assert saved_metadata["featured"] is False


def test_save_featured_image(test_gallery):
    """Test saving featured image to correct directory."""
    image = Image.new("RGB", (512, 512), color="blue")
    prompt = "featured test"
    metadata = {"seed": 123}

    saved_path = test_gallery.save_image(
        image=image, prompt=prompt, metadata=metadata, featured=True
    )

    # Verify it's in the featured directory
    assert "featured" in str(saved_path)


def test_list_images(test_gallery):
    """Test listing images in gallery."""
    # Create some test images
    for i in range(3):
        image = Image.new("RGB", (512, 512), color="red")
        test_gallery.save_image(
            image=image,
            prompt=f"test {i}",
            metadata={"seed": i},
            featured=(i == 0),
        )

    # List all images
    all_images = test_gallery.list_images(featured_only=False)
    assert len(all_images) >= 3

    # List only featured
    featured_images = test_gallery.list_images(featured_only=True)
    assert len(featured_images) >= 1


# === Community Gallery Model Tests ===


@pytest.fixture
def community_db(tmp_path):
    """Create test database for community gallery."""
    db_path = tmp_path / "test_community.db"
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    return create_session_factory(db_path)


@pytest.fixture
def sample_public_image(community_db):
    """Create a sample public image for testing."""
    session = community_db()
    try:
        image = GeneratedImage(
            filename="test_community.png",
            prompt="a beautiful sunset",
            model_id="test-model",
            is_public=True,
            share_id="abc123xyz",
            like_count=0,
            comment_count=0,
            share_count=0,
            view_count=0,
            tags=["sunset", "nature"],
        )
        session.add(image)
        session.commit()
        session.refresh(image)
        return image.id, image.share_id
    finally:
        session.close()


class TestCommunityGalleryModels:
    """Test community gallery database models."""

    def test_create_image_with_gallery_fields(self, community_db):
        """Test creating an image with community gallery fields."""
        session = community_db()
        try:
            image = GeneratedImage(
                filename="community_test.png",
                prompt="test image",
                model_id="test-model",
                is_public=True,
                share_id="test123abc",
                like_count=5,
                comment_count=2,
                share_count=1,
                view_count=100,
            )
            session.add(image)
            session.commit()

            result = (
                session.query(GeneratedImage)
                .filter_by(filename="community_test.png")
                .first()
            )

            assert result is not None
            assert result.is_public is True
            assert result.share_id == "test123abc"
            assert result.like_count == 5
            assert result.comment_count == 2
            assert result.share_count == 1
            assert result.view_count == 100
        finally:
            session.close()

    def test_gallery_defaults(self, community_db):
        """Test default values for gallery fields."""
        session = community_db()
        try:
            image = GeneratedImage(
                filename="defaults_test.png",
                prompt="test",
                model_id="test-model",
            )
            session.add(image)
            session.commit()

            result = (
                session.query(GeneratedImage)
                .filter_by(filename="defaults_test.png")
                .first()
            )

            assert result.is_public is False
            assert result.share_id is None
            assert result.like_count == 0
            assert result.comment_count == 0
        finally:
            session.close()

    def test_create_gallery_like(self, community_db, sample_public_image):
        """Test creating a like record."""
        image_id, _ = sample_public_image
        session = community_db()
        try:
            like = GalleryLike(
                image_id=image_id,
                session_id="user_session_123",
            )
            session.add(like)
            session.commit()

            result = session.query(GalleryLike).filter_by(image_id=image_id).first()

            assert result is not None
            assert result.session_id == "user_session_123"
            assert result.created_at is not None
        finally:
            session.close()

    def test_create_gallery_comment(self, community_db, sample_public_image):
        """Test creating a comment record."""
        image_id, _ = sample_public_image
        session = community_db()
        try:
            comment = GalleryComment(
                image_id=image_id,
                session_id="user_session_456",
                display_name="ArtLover",
                text="Beautiful artwork!",
            )
            session.add(comment)
            session.commit()

            result = session.query(GalleryComment).filter_by(image_id=image_id).first()

            assert result is not None
            assert result.display_name == "ArtLover"
            assert result.text == "Beautiful artwork!"
            assert result.created_at is not None
        finally:
            session.close()

    def test_create_gallery_share(self, community_db, sample_public_image):
        """Test creating a share tracking record."""
        image_id, _ = sample_public_image
        session = community_db()
        try:
            share = GalleryShare(
                image_id=image_id,
                platform="twitter",
            )
            session.add(share)
            session.commit()

            result = session.query(GalleryShare).filter_by(image_id=image_id).first()

            assert result is not None
            assert result.platform == "twitter"
            assert result.shared_at is not None
        finally:
            session.close()

    def test_cascade_delete_likes(self, community_db, sample_public_image):
        """Test that likes are deleted when image is deleted."""
        image_id, _ = sample_public_image
        session = community_db()
        try:
            # Add a like
            like = GalleryLike(image_id=image_id, session_id="test_session")
            session.add(like)
            session.commit()

            # Verify like exists
            assert session.query(GalleryLike).filter_by(image_id=image_id).count() == 1

            # Delete image
            image = session.query(GeneratedImage).filter_by(id=image_id).first()
            session.delete(image)
            session.commit()

            # Verify likes are deleted
            assert session.query(GalleryLike).filter_by(image_id=image_id).count() == 0
        finally:
            session.close()


class TestCommunityGalleryQueries:
    """Test community gallery query patterns."""

    def test_query_public_images(self, community_db):
        """Test querying only public images."""
        session = community_db()
        try:
            # Create mix of public and private images
            public_image = GeneratedImage(
                filename="public.png",
                prompt="public art",
                model_id="test",
                is_public=True,
                share_id="pub123",
            )
            private_image = GeneratedImage(
                filename="private.png",
                prompt="private art",
                model_id="test",
                is_public=False,
            )
            session.add_all([public_image, private_image])
            session.commit()

            # Query public only
            public_count = (
                session.query(GeneratedImage)
                .filter(GeneratedImage.is_public == True)  # noqa: E712
                .count()
            )

            assert public_count == 1
        finally:
            session.close()

    def test_sort_by_likes(self, community_db):
        """Test sorting images by like count."""
        session = community_db()
        try:
            # Create images with different like counts
            for i, likes in enumerate([10, 5, 20, 1]):
                image = GeneratedImage(
                    filename=f"likes_{i}.png",
                    prompt="test",
                    model_id="test",
                    is_public=True,
                    share_id=f"likes{i}xx",
                    like_count=likes,
                )
                session.add(image)
            session.commit()

            # Query sorted by likes
            results = (
                session.query(GeneratedImage)
                .filter(GeneratedImage.is_public == True)  # noqa: E712
                .order_by(GeneratedImage.like_count.desc())
                .all()
            )

            assert results[0].like_count == 20
            assert results[1].like_count == 10
            assert results[2].like_count == 5
            assert results[3].like_count == 1
        finally:
            session.close()

    def test_lookup_by_share_id(self, community_db, sample_public_image):
        """Test finding image by share_id."""
        _, share_id = sample_public_image
        session = community_db()
        try:
            result = session.query(GeneratedImage).filter_by(share_id=share_id).first()

            assert result is not None
            assert result.filename == "test_community.png"
        finally:
            session.close()
