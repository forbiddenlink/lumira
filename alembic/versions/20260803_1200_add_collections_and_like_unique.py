"""add_collections_and_like_unique

Adds the gallery_collections and collection_artworks tables (previously only
created via Base.metadata.create_all, with no migration) and a unique
constraint on gallery_likes(image_id, session_id) so a session cannot like the
same image twice.

Revision ID: c1a2b3d4e5f6
Revises: 3b4e3ea9e107
Create Date: 2026-08-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f6"
down_revision: str | None = "3b4e3ea9e107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gallery_collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("theme", sa.String(length=100), nullable=True),
        sa.Column("cover_image_id", sa.Integer(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=True),
        sa.Column("created_by_aria", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["cover_image_id"], ["generated_images.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("gallery_collections", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_gallery_collections_id"), ["id"], unique=False
        )

    op.create_table(
        "collection_artworks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["gallery_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["image_id"], ["generated_images.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id", "image_id", name="unique_collection_artwork"
        ),
    )
    with op.batch_alter_table("collection_artworks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_collection_artworks_id"), ["id"], unique=False
        )

    # De-duplicate any existing (image_id, session_id) pairs before adding the
    # unique constraint, otherwise the batch table rebuild would fail.
    op.execute(
        """
        DELETE FROM gallery_likes
        WHERE id NOT IN (
            SELECT MIN(id) FROM gallery_likes GROUP BY image_id, session_id
        )
        """
    )
    with op.batch_alter_table("gallery_likes", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_gallery_likes_image_session", ["image_id", "session_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("gallery_likes", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_gallery_likes_image_session", type_="unique"
        )

    with op.batch_alter_table("collection_artworks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_collection_artworks_id"))
    op.drop_table("collection_artworks")

    with op.batch_alter_table("gallery_collections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_gallery_collections_id"))
    op.drop_table("gallery_collections")
