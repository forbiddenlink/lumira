#!/usr/bin/env python3
"""Remove test/spam artworks that flooded the gallery (phoenix variations + 'test' img2img).

USAGE:
    python scripts/cleanup_spam_artworks.py --dry-run
    python scripts/cleanup_spam_artworks.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, text

TRIVIAL = {"test", "testing", "foo", "bar", "asdf", "hello", "hi"}


def _is_trivial(prompt: str | None) -> bool:
    p = (prompt or "").strip().lower()
    if not p:
        return True
    if p in TRIVIAL:
        return True
    if p.startswith("test,") or p.startswith("test "):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", default="sqlite:///data/ai_artist.db")
    args = parser.parse_args()

    eng = create_engine(args.db)
    to_delete: list[tuple[int, str, str]] = []

    with eng.connect() as c:
        rows = c.execute(
            text(
                "SELECT id, prompt, filename, model_id, generation_params "
                "FROM generated_images"
            )
        ).fetchall()

        for row in rows:
            img_id, prompt, filename, model_id, params = row
            params = params or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}

            reason = None
            if _is_trivial(prompt):
                reason = "trivial_prompt"
            elif model_id == "sdxl-variation" and params.get("variation_of") == 1:
                reason = "spam_variation_of_1"
            elif (
                model_id == "sdxl-img2img"
                and params.get("source_id") == 1
                and _is_trivial(prompt)
            ):
                reason = "spam_img2img_test"

            if reason:
                to_delete.append((img_id, filename or "", reason))

    print(f"Matched {len(to_delete)} spam/test artworks")
    by_reason: dict[str, int] = {}
    for _, _, reason in to_delete:
        by_reason[reason] = by_reason.get(reason, 0) + 1
    for reason, n in sorted(by_reason.items()):
        print(f"  {n:4d}  {reason}")

    if args.dry_run:
        print("\nDRY RUN — no changes made")
        for img_id, filename, reason in to_delete[:15]:
            print(f"  would delete id={img_id} [{reason}] {filename}")
        if len(to_delete) > 15:
            print(f"  ... and {len(to_delete) - 15} more")
        return

    deleted_files = 0
    with eng.begin() as c:
        for img_id, filename, _reason in to_delete:
            c.execute(
                text("DELETE FROM generated_images WHERE id = :id"),
                {"id": img_id},
            )
            if not filename:
                continue
            path = Path(filename)
            if not path.is_absolute():
                # DB sometimes stores gallery/... and sometimes relative under gallery
                candidates = [path, Path("gallery") / path]
            else:
                candidates = [path]
            for candidate in candidates:
                if candidate.exists() and candidate.is_file():
                    candidate.unlink()
                    deleted_files += 1
                    sidecar = candidate.with_suffix(".json")
                    if sidecar.exists():
                        sidecar.unlink()
                    break

    # Scrub desire subject spam
    desires_path = Path("data/lumira_desires.json")
    if desires_path.exists():
        data = json.loads(desires_path.read_text())
        usage = data.get("subject_usage") or {}
        if "test" in usage:
            del usage["test"]
            data["subject_usage"] = usage
            desires_path.write_text(json.dumps(data, indent=2) + "\n")
            print("Cleared subject_usage['test'] from lumira_desires.json")

    remaining = 0
    with eng.connect() as c:
        remaining = c.execute(text("SELECT COUNT(*) FROM generated_images")).scalar() or 0

    print(f"Deleted {len(to_delete)} DB rows, {deleted_files} image files")
    print(f"Remaining generated_images: {remaining}")


if __name__ == "__main__":
    main()
