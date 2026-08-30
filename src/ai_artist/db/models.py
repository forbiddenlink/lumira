"""SQLAlchemy database models.

Written in SQLAlchemy 2.0 declarative style: ``Mapped[...]`` annotations with
``mapped_column``. The legacy ``Column(...)`` form typed every attribute read
as ``Column[T]`` rather than ``T``, so ``image.prompt`` looked like a Column to
the type checker and every consumer had to wrap it in ``str(...)`` or a cast to
get past mypy -- noise that hid the one assignment that was genuinely wrong.

Nullability is carried by the annotation: ``Mapped[str]`` is NOT NULL,
``Mapped[str | None]`` is nullable. The DDL this produces is byte-identical to
what the previous definitions produced; the columns that look surprisingly
nullable below (negative_prompt, status, the counters) were already nullable
and are left that way so the mapping keeps matching the migrated database.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Declarative base for every model in this module."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GeneratedImage(Base):
    """Model for generated artwork."""

    __tablename__ = "generated_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String, unique=True, index=True)
    prompt: Mapped[str] = mapped_column(String)
    negative_prompt: Mapped[str | None] = mapped_column(String, default="")

    # Source information
    source_url: Mapped[str | None] = mapped_column(String)
    source_query: Mapped[str | None] = mapped_column(String)

    # Generation parameters
    model_id: Mapped[str] = mapped_column(String, index=True)
    generation_params: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    seed: Mapped[int | None] = mapped_column()

    # Quality metrics
    aesthetic_score: Mapped[float | None] = mapped_column()
    clip_score: Mapped[float | None] = mapped_column()
    technical_score: Mapped[float | None] = mapped_column()
    final_score: Mapped[float | None] = mapped_column(index=True)

    # Metadata
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=_utcnow, index=True
    )
    # Pipeline state only -- pending, curated, rejected. Not the mood; that
    # lives in generation_params and tags (see migration d7f2c9a41b83).
    status: Mapped[str | None] = mapped_column(String, default="pending", index=True)
    is_featured: Mapped[bool | None] = mapped_column(default=False)
    tags: Mapped[list[str] | None] = mapped_column(JSON, default=list)

    # Community gallery fields
    is_public: Mapped[bool | None] = mapped_column(default=False, index=True)
    share_id: Mapped[str | None] = mapped_column(String(12), unique=True, index=True)
    like_count: Mapped[int | None] = mapped_column(default=0, index=True)
    comment_count: Mapped[int | None] = mapped_column(default=0)
    share_count: Mapped[int | None] = mapped_column(default=0)
    view_count: Mapped[int | None] = mapped_column(default=0, index=True)

    # Relationships
    likes: Mapped[list["GalleryLike"]] = relationship(
        "GalleryLike", back_populates="image", cascade="all, delete-orphan"
    )
    comments: Mapped[list["GalleryComment"]] = relationship(
        "GalleryComment", back_populates="image", cascade="all, delete-orphan"
    )
    shares: Mapped[list["GalleryShare"]] = relationship(
        "GalleryShare", back_populates="image", cascade="all, delete-orphan"
    )


class TrainingSession(Base):
    """Model for LoRA training sessions."""

    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    model_path: Mapped[str] = mapped_column(String)

    # Training configuration
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    dataset_size: Mapped[int | None] = mapped_column()

    # Training metrics
    final_loss: Mapped[float | None] = mapped_column()
    training_time_seconds: Mapped[float | None] = mapped_column()
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    status: Mapped[str | None] = mapped_column(String, default="running")


class CreationSession(Base):
    """Model for automated creation sessions."""

    __tablename__ = "creation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    theme: Mapped[str | None] = mapped_column(String)
    images_created: Mapped[int | None] = mapped_column(default=0)
    images_kept: Mapped[int | None] = mapped_column(default=0)
    avg_score: Mapped[float | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class GalleryLike(Base):
    """Model for image likes in community gallery."""

    __tablename__ = "gallery_likes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)

    # Relationship
    image: Mapped["GeneratedImage"] = relationship(
        "GeneratedImage", back_populates="likes"
    )

    __table_args__ = (
        UniqueConstraint(
            "image_id", "session_id", name="uq_gallery_likes_image_session"
        ),
        {"sqlite_autoincrement": True},
    )


class GalleryComment(Base):
    """Model for image comments in community gallery."""

    __tablename__ = "gallery_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str | None] = mapped_column(String(50), default="Anonymous")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=_utcnow, index=True
    )

    # Relationship
    image: Mapped["GeneratedImage"] = relationship(
        "GeneratedImage", back_populates="comments"
    )


class GalleryShare(Base):
    """Model for tracking image shares in community gallery."""

    __tablename__ = "gallery_shares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(20))  # twitter, facebook, etc.
    shared_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)

    # Relationship
    image: Mapped["GeneratedImage"] = relationship(
        "GeneratedImage", back_populates="shares"
    )


class GalleryCollection(Base):
    """A curated collection of artworks."""

    __tablename__ = "gallery_collections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    theme: Mapped[str | None] = mapped_column(String(100))
    cover_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_images.id")
    )
    is_public: Mapped[bool | None] = mapped_column(default=True)
    created_by_aria: Mapped[bool | None] = mapped_column(default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)

    # Relationships
    cover_image: Mapped["GeneratedImage | None"] = relationship(
        "GeneratedImage", foreign_keys=[cover_image_id]
    )


@event.listens_for(GalleryCollection, "before_update")
def _update_collection_timestamp(mapper: Any, connection: Any, target: Any) -> None:
    """Keep updated_at current on every UPDATE — SQLite-safe replacement for onupdate."""
    target.updated_at = datetime.now(UTC)


class CollectionArtwork(Base):
    """Many-to-many relationship between collections and artworks."""

    __tablename__ = "collection_artworks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("gallery_collections.id", ondelete="CASCADE"),
    )
    image_id: Mapped[int] = mapped_column(
        ForeignKey("generated_images.id", ondelete="CASCADE"),
    )
    position: Mapped[int | None] = mapped_column(default=0)
    added_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)

    # Relationships
    collection: Mapped["GalleryCollection"] = relationship(
        "GalleryCollection", backref="artworks"
    )
    image: Mapped["GeneratedImage"] = relationship("GeneratedImage")

    __table_args__ = (
        UniqueConstraint("collection_id", "image_id", name="unique_collection_artwork"),
    )


class UserFeedback(Base):
    """Feedback signal recorded by the adaptive learner (RLAIF).

    Replaces flat JSON files so feedback is SQL-queryable for analytics
    and bandit learning.
    """

    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Which artwork this feedback refers to (may be None for session-level signals)
    artwork_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_images.id", ondelete="SET NULL"),
        index=True,
    )
    # Filename fallback when artwork is not in DB yet
    artwork_filename: Mapped[str | None] = mapped_column(String(512), index=True)

    # Action that triggered this feedback record, e.g. "like", "share",
    # "download", "critic_eval", "regenerate"
    action: Mapped[str] = mapped_column(String(50), index=True)

    # Numeric signal (e.g. critic confidence score, 0–1)
    signal_value: Mapped[float | None] = mapped_column()

    # Snapshot of generation parameters at feedback time (for bandit learning)
    generation_params: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    # Mood at generation time
    mood: Mapped[str | None] = mapped_column(String(50), index=True)

    # Session / source identification
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=_utcnow, index=True
    )

    # Relationship
    artwork: Mapped["GeneratedImage | None"] = relationship("GeneratedImage")
