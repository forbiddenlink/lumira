"""SQLAlchemy database models."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class GeneratedImage(Base):  # type: ignore[misc, valid-type]
    """Model for generated artwork."""

    __tablename__ = "generated_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False, unique=True, index=True)
    prompt = Column(String, nullable=False)
    negative_prompt = Column(String, default="")

    # Source information
    source_url = Column(String)
    source_query = Column(String)

    # Generation parameters
    model_id = Column(String, nullable=False, index=True)
    generation_params = Column(JSON, default=dict)
    seed = Column(Integer)

    # Quality metrics
    aesthetic_score = Column(Float)
    clip_score = Column(Float)
    technical_score = Column(Float)
    final_score = Column(Float, index=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), index=True)
    status = Column(String, default="pending", index=True)  # pending, curated, rejected
    is_featured = Column(Boolean, default=False)
    tags = Column(JSON, default=list)

    # Community gallery fields
    is_public = Column(Boolean, default=False, index=True)
    share_id = Column(String(12), unique=True, index=True)  # Unique share ID
    like_count = Column(Integer, default=0, index=True)
    comment_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0, index=True)

    # Relationships
    likes = relationship(
        "GalleryLike", back_populates="image", cascade="all, delete-orphan"
    )
    comments = relationship(
        "GalleryComment", back_populates="image", cascade="all, delete-orphan"
    )
    shares = relationship(
        "GalleryShare", back_populates="image", cascade="all, delete-orphan"
    )


class TrainingSession(Base):  # type: ignore[misc, valid-type]
    """Model for LoRA training sessions."""

    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    model_path = Column(String, nullable=False)

    # Training configuration
    config = Column(JSON, default=dict)
    dataset_size = Column(Integer)

    # Training metrics
    final_loss = Column(Float)
    training_time_seconds = Column(Float)
    metrics = Column(JSON, default=dict)

    # Timestamps
    started_at = Column(DateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime)

    status = Column(String, default="running")  # running, completed, failed


class CreationSession(Base):  # type: ignore[misc, valid-type]
    """Model for automated creation sessions."""

    __tablename__ = "creation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    theme = Column(String)
    images_created = Column(Integer, default=0)
    images_kept = Column(Integer, default=0)
    avg_score = Column(Float)
    started_at = Column(DateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime)


class GalleryLike(Base):  # type: ignore[misc, valid-type]
    """Model for image likes in community gallery."""

    __tablename__ = "gallery_likes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(
        Integer,
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationship
    image = relationship("GeneratedImage", back_populates="likes")

    __table_args__ = ({"sqlite_autoincrement": True},)


class GalleryComment(Base):  # type: ignore[misc, valid-type]
    """Model for image comments in community gallery."""

    __tablename__ = "gallery_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(
        Integer,
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(String(64), nullable=False, index=True)
    display_name = Column(String(50), default="Anonymous")
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), index=True)

    # Relationship
    image = relationship("GeneratedImage", back_populates="comments")


class GalleryShare(Base):  # type: ignore[misc, valid-type]
    """Model for tracking image shares in community gallery."""

    __tablename__ = "gallery_shares"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(
        Integer,
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform = Column(String(20), nullable=False)  # twitter, facebook, etc.
    shared_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationship
    image = relationship("GeneratedImage", back_populates="shares")


class GalleryCollection(Base):  # type: ignore[misc, valid-type]
    """A curated collection of artworks."""

    __tablename__ = "gallery_collections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    theme = Column(String(100), nullable=True)  # e.g., "Abstract Blue Period"
    cover_image_id = Column(Integer, ForeignKey("generated_images.id"), nullable=True)
    is_public = Column(Boolean, default=True)
    created_by_aria = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    cover_image = relationship("GeneratedImage", foreign_keys=[cover_image_id])


@event.listens_for(GalleryCollection, "before_update")
def _update_collection_timestamp(mapper, connection, target):  # type: ignore[misc]
    """Keep updated_at current on every UPDATE — SQLite-safe replacement for onupdate."""
    target.updated_at = datetime.now(UTC)


class CollectionArtwork(Base):  # type: ignore[misc, valid-type]
    """Many-to-many relationship between collections and artworks."""

    __tablename__ = "collection_artworks"

    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(
        Integer,
        ForeignKey("gallery_collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_id = Column(
        Integer,
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        nullable=False,
    )
    position = Column(Integer, default=0)  # For ordering within collection
    added_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    collection = relationship("GalleryCollection", backref="artworks")
    image = relationship("GeneratedImage")

    __table_args__ = (
        UniqueConstraint("collection_id", "image_id", name="unique_collection_artwork"),
    )


class UserFeedback(Base):  # type: ignore[misc, valid-type]
    """Feedback signal recorded by the adaptive learner (RLAIF).

    Replaces flat JSON files so feedback is SQL-queryable for analytics
    and bandit learning.
    """

    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Which artwork this feedback refers to (may be None for session-level signals)
    artwork_id = Column(
        Integer,
        ForeignKey("generated_images.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Filename fallback when artwork is not in DB yet
    artwork_filename = Column(String(512), nullable=True, index=True)

    # Action that triggered this feedback record
    action = Column(
        String(50),
        nullable=False,
        index=True,
    )  # e.g. "like", "share", "download", "critic_eval", "regenerate"

    # Numeric signal (e.g. critic confidence score, 0–1)
    signal_value = Column(Float, nullable=True)

    # Snapshot of generation parameters at feedback time (for bandit learning)
    generation_params = Column(JSON, default=dict)

    # Mood at generation time
    mood = Column(String(50), nullable=True, index=True)

    # Session / source identification
    session_id = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC), index=True)

    # Relationship
    artwork = relationship("GeneratedImage")
