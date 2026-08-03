#!/usr/bin/env python3
"""Backup Lumira's durable state: SQLite DBs, the gallery, and the vector store.

Nothing here was backed up before — a disk failure meant total loss of the
database, every generated image, and Lumira's ChromaDB memory. This script
produces a consistent, timestamped snapshot.

Usage:
    python scripts/backup.py                     # -> backups/<UTC-timestamp>/
    python scripts/backup.py --dest /mnt/b2      # custom destination root
    python scripts/backup.py --keep 14           # prune snapshots older than N

Databases are copied via SQLite's online ``.backup`` API (consistent even
while the app is running and in WAL mode); a raw ``cp`` of a live WAL DB can
capture a torn state.

Schedule it (launchd/cron/GH Action) and, crucially, test a RESTORE at least
once — an untested backup is not a backup. Restore = stop the app, copy the
snapshot's files back to their original paths, restart.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (source path, label) — sources that don't exist are skipped with a note.
SQLITE_DBS = [
    (REPO_ROOT / "data" / "ai_artist.db", "ai_artist.db"),
    (REPO_ROOT / "data" / "scheduler.db", "scheduler.db"),
]
TREES = [
    (REPO_ROOT / "gallery", "gallery"),
    (REPO_ROOT / "data" / "vector_memory", "vector_memory"),
]


def _backup_sqlite(src: Path, dest: Path) -> None:
    """Consistent online backup of a SQLite DB via the backup API."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)


def run_backup(dest_root: Path, keep: int | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snapshot = dest_root / stamp
    snapshot.mkdir(parents=True, exist_ok=True)

    for src, label in SQLITE_DBS:
        if src.exists():
            _backup_sqlite(src, snapshot / label)
            print(f"  db   {label}")
        else:
            print(f"  db   {label} (skipped — not found)")

    for src, label in TREES:
        if src.exists():
            shutil.copytree(src, snapshot / label, dirs_exist_ok=True)
            print(f"  tree {label}/")
        else:
            print(f"  tree {label}/ (skipped — not found)")

    if keep is not None and keep > 0:
        _prune(dest_root, keep)

    print(f"Snapshot written: {snapshot}")
    return snapshot


def _prune(dest_root: Path, keep: int) -> None:
    snapshots = sorted(
        (p for p in dest_root.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for stale in snapshots[keep:]:
        shutil.rmtree(stale, ignore_errors=True)
        print(f"  pruned {stale.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up Lumira's durable state.")
    parser.add_argument(
        "--dest",
        default=str(REPO_ROOT / "backups"),
        help="Destination root for snapshots (default: ./backups). "
        "Point at off-box storage (mounted S3/R2/B2) for real durability.",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=None,
        help="Keep only the N most recent snapshots (prune older).",
    )
    args = parser.parse_args()

    print("Backing up Lumira state...")
    run_backup(Path(args.dest).expanduser(), args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
