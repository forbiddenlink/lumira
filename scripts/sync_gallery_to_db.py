#!/usr/bin/env python3
"""Backfill orphan gallery PNGs into the DB, then optionally publish/feature them.

USAGE:
    python scripts/sync_gallery_to_db.py --dry-run
    python scripts/sync_gallery_to_db.py
    python scripts/sync_gallery_to_db.py --publish --feature
    python scripts/sync_gallery_to_db.py --publish --min-score 0.7 --feature-top 24
"""

from __future__ import annotations

import argparse
import json
import secrets
import string
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_artist.db.models import GeneratedImage
from ai_artist.utils.prompt_quality import is_trivial_prompt


def _share_id(n: int = 12) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _parse_created_at(raw: object) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _existing_basenames(session: Session) -> set[str]:
    rows = session.execute(select(GeneratedImage.filename)).scalars().all()
    return {Path(str(name)).name for name in rows if name}


def _load_sidecar(png: Path) -> dict:
    meta_path = png.with_suffix(".json")
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text())
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _row_from_png(png: Path, meta: dict) -> GeneratedImage | None:
    prompt = str(meta.get("prompt") or "").strip()
    if is_trivial_prompt(prompt):
        return None

    inner = meta.get("metadata", meta)
    if not isinstance(inner, dict):
        inner = meta if isinstance(meta, dict) else {}

    model_id = inner.get("model") or meta.get("model") or "unknown"
    score = inner.get("final_score")
    if score is None:
        score = meta.get("final_score")
    try:
        final_score = float(score) if score is not None else None
    except (TypeError, ValueError):
        final_score = None

    created = _parse_created_at(meta.get("created_at") or inner.get("created_at"))
    featured_flag = bool(
        meta.get("featured")
        or inner.get("featured")
        or "featured" in str(png).replace("\\", "/")
    )

    tags: list[str] = []
    for key in ("mood", "style", "subject"):
        val = inner.get(key)
        if val:
            tags.append(str(val))

    return GeneratedImage(
        filename=str(png.resolve()),
        prompt=prompt,
        negative_prompt=str(meta.get("negative_prompt") or ""),
        model_id=str(model_id),
        generation_params=inner,
        seed=inner.get("seed") if isinstance(inner.get("seed"), int) else None,
        final_score=final_score,
        aesthetic_score=(
            float(inner["aesthetic_score"])
            if inner.get("aesthetic_score") is not None
            else None
        ),
        clip_score=(
            float(inner["clip_score"]) if inner.get("clip_score") is not None else None
        ),
        technical_score=(
            float(inner["technical_score"])
            if inner.get("technical_score") is not None
            else None
        ),
        created_at=created or datetime.now(UTC),
        status="curated",
        is_featured=featured_flag,
        tags=tags,
        is_public=False,
    )


def backfill(
    session: Session,
    gallery: Path,
    *,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Insert orphan PNGs. Returns (scanned, inserted, skipped_trivial)."""
    known = _existing_basenames(session)
    scanned = 0
    inserted = 0
    skipped = 0

    for png in sorted(gallery.rglob("*.png")):
        if "thumb" in png.name.lower():
            continue
        scanned += 1
        if png.name in known:
            continue

        meta = _load_sidecar(png)
        row = _row_from_png(png, meta)
        if row is None:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        session.add(row)
        known.add(png.name)
        inserted += 1

    if not dry_run and inserted:
        session.commit()
    return scanned, inserted, skipped


def publish_quality(
    session: Session,
    *,
    min_score: float,
    dry_run: bool,
) -> int:
    """Mark non-trivial works public when score meets threshold (or score missing)."""
    rows = session.execute(select(GeneratedImage)).scalars().all()
    count = 0
    for row in rows:
        if is_trivial_prompt(row.prompt):
            continue
        score = row.final_score
        if score is not None and float(score) < min_score:
            continue
        if row.is_public and row.share_id:
            continue
        count += 1
        if dry_run:
            continue
        if not row.share_id:
            row.share_id = _share_id()
        row.is_public = True
    if not dry_run and count:
        session.commit()
    return count


def feature_top(
    session: Session,
    *,
    top_n: int,
    dry_run: bool,
) -> int:
    """Feature the top-N scored non-trivial artworks."""
    rows = (
        session.execute(
            select(GeneratedImage).order_by(
                GeneratedImage.final_score.desc().nulls_last(),
                GeneratedImage.created_at.desc(),
            )
        )
        .scalars()
        .all()
    )
    selected: list[GeneratedImage] = []
    for row in rows:
        if is_trivial_prompt(row.prompt):
            continue
        selected.append(row)
        if len(selected) >= top_n:
            break

    if dry_run:
        return len(selected)

    # Clear previous features then set top-N
    for row in rows:
        if row.is_featured:
            row.is_featured = False
    for row in selected:
        row.is_featured = True
    session.commit()
    return len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", default="sqlite:///data/ai_artist.db")
    parser.add_argument("--gallery", default="gallery")
    parser.add_argument("--publish", action="store_true", help="Make quality works public")
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument(
        "--feature",
        action="store_true",
        help="Mark top-scoring works as featured",
    )
    parser.add_argument("--feature-top", type=int, default=24)
    args = parser.parse_args()

    gallery = Path(args.gallery)
    if not gallery.is_dir():
        raise SystemExit(f"Gallery not found: {gallery}")

    engine = create_engine(args.db)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        scanned, inserted, skipped = backfill(
            session, gallery, dry_run=args.dry_run
        )
        print(
            f"Backfill: scanned={scanned} inserted={inserted} "
            f"skipped_trivial={skipped} dry_run={args.dry_run}"
        )

        published = 0
        if args.publish:
            published = publish_quality(
                session, min_score=args.min_score, dry_run=args.dry_run
            )
            print(
                f"Publish: newly_public={published} min_score={args.min_score} "
                f"dry_run={args.dry_run}"
            )

        featured = 0
        if args.feature:
            featured = feature_top(
                session, top_n=args.feature_top, dry_run=args.dry_run
            )
            print(
                f"Feature: marked={featured} top={args.feature_top} "
                f"dry_run={args.dry_run}"
            )

        total = session.execute(
            select(GeneratedImage.id)
        ).scalars().all()
        public = session.execute(
            select(GeneratedImage).where(GeneratedImage.is_public.is_(True))
        ).scalars().all()
        feat = session.execute(
            select(GeneratedImage).where(GeneratedImage.is_featured.is_(True))
        ).scalars().all()
        print(
            f"DB now: total={len(total)} public={len(public)} featured={len(feat)}"
        )


if __name__ == "__main__":
    main()
