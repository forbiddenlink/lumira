"""status_holds_pipeline_state_only

Three of the five GeneratedImage write paths in lumira_routes.py set
``status=mood.value``, so the status column ended up carrying two different
vocabularies: pipeline states ("curated") alongside mood names ("melancholic",
"serene", ...). Any status filter silently missed those rows, and the
collection breakdown on the admin console could answer neither question.

The writers are fixed. This moves the existing rows over.

The mood is not lost. Every affected row already carries its mood in ``tags``
(verified across all 393 rows on the development database), so the mood is
copied into ``generation_params.mood`` -- where the correctly-written rows keep
it -- before the status is corrected to "curated". Those rows all have a
final_score, which is what "curated" means here.

Revision ID: d7f2c9a41b83
Revises: c1a2b3d4e5f6
Create Date: 2026-08-30 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7f2c9a41b83"
down_revision: str | None = "c1a2b3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ai_artist.personality.moods.Mood values. Spelled out rather than imported so
# the migration keeps describing the data as it was when written, even if the
# mood set changes later.
MOOD_STATUSES = (
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
)


def upgrade() -> None:
    connection = op.get_bind()
    placeholders = ", ".join(f":m{i}" for i in range(len(MOOD_STATUSES)))
    params = {f"m{i}": mood for i, mood in enumerate(MOOD_STATUSES)}

    rows = connection.execute(
        sa.text(
            "SELECT id, status, generation_params FROM generated_images "
            f"WHERE status IN ({placeholders})"
        ),
        params,
    ).fetchall()

    for row_id, status, generation_params in rows:
        try:
            existing = json.loads(generation_params) if generation_params else {}
        except (TypeError, ValueError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}

        # Only fill it in when it is genuinely missing; never overwrite a mood
        # the generator recorded itself.
        if not existing.get("mood"):
            existing["mood"] = status
            connection.execute(
                sa.text(
                    "UPDATE generated_images SET generation_params = :params "
                    "WHERE id = :id"
                ),
                {"params": json.dumps(existing), "id": row_id},
            )

    connection.execute(
        sa.text(
            "UPDATE generated_images SET status = 'curated' "
            f"WHERE status IN ({placeholders})"
        ),
        params,
    )


def downgrade() -> None:
    # Not reversible: once these rows read "curated" they are indistinguishable
    # from the ones that were always correct, so putting the mood back in the
    # status column would corrupt those too. The mood itself is still in
    # generation_params and tags, so nothing is lost by leaving this be.
    pass
