# Database Schema Documentation

Complete database schema for Lumira project using SQLite + SQLAlchemy + Alembic.

---

## Table of Contents

- [Overview](#overview)
- [Schema Design](#schema-design)
- [Tables](#tables)
- [Indexes](#indexes)
- [Migrations](#migrations)
- [Queries](#common-queries)
- [Backup Strategy](#backup-strategy)

---

## Overview

### Technology Stack

- **Database**: SQLite 3.x with WAL mode
- **ORM**: SQLAlchemy 2.0+
- **Migrations**: Alembic 1.13+
- **Connection Pooling**: StaticPool (single process) or QueuePool (multi-process)

### Design Principles

- **Denormalization**: Store JSON metadata for flexibility
- **Indexing**: Index all frequently queried columns
- **WAL Mode**: Enable Write-Ahead Logging for better concurrency
- **Type Safety**: Use Pydantic models for validation before database insertion

---

## Schema Design

### Entity Relationship Diagram

```
┌─────────────────────┐
│  GeneratedImage     │
│  (Artwork Records)  │
└──────────┬──────────┘
           │
           │ N:1
           │
           ▼
┌─────────────────────┐       ┌────────────────────┐
│  TrainingSession    │       │  CreationSession   │
│  (LoRA Training)    │       │  (Batch Jobs)      │
└─────────────────────┘       └────────────────────┘
```

---

## Tables

### `generated_images`

Primary table for storing generated artwork metadata.

**Purpose**: Track every image created, its generation parameters, quality scores, and curation status.

#### Schema

```sql
CREATE TABLE generated_images (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- File Information
    filename TEXT NOT NULL UNIQUE,

    -- Prompts
    prompt TEXT NOT NULL,
    negative_prompt TEXT DEFAULT '',

    -- Source Tracking (for legal compliance)
    source_url TEXT,
    source_query TEXT,

    -- Generation Configuration
    model_id TEXT NOT NULL,
    generation_params JSON DEFAULT '{}',
    seed INTEGER,

    -- Quality Metrics
    aesthetic_score REAL,
    clip_score REAL,
    technical_score REAL,
    final_score REAL,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Curation Status
    status TEXT DEFAULT 'pending',  -- pending, curated, rejected
    is_featured BOOLEAN DEFAULT 0,

    -- Metadata
    tags JSON DEFAULT '[]'
);
```

#### Indexes

```sql
CREATE INDEX idx_filename ON generated_images(filename);
CREATE INDEX idx_model_id ON generated_images(model_id);
CREATE INDEX idx_created_at ON generated_images(created_at DESC);
CREATE INDEX idx_status ON generated_images(status);
CREATE INDEX idx_final_score ON generated_images(final_score DESC);
CREATE INDEX idx_featured ON generated_images(is_featured);
```

#### Column Details

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Auto-increment primary key |
| `filename` | TEXT | No | Unique filename (e.g., "20260108_120000_sunset.png") |
| `prompt` | TEXT | No | Generation prompt |
| `negative_prompt` | TEXT | Yes | Negative prompt (what to avoid) |
| `source_url` | TEXT | Yes | Unsplash/Pexels source image URL |
| `source_query` | TEXT | Yes | Search query that found source |
| `model_id` | TEXT | No | Model identifier (e.g., "sdxl-1.0") |
| `generation_params` | JSON | Yes | Full generation config as JSON |
| `seed` | INTEGER | Yes | Random seed for reproducibility |
| `aesthetic_score` | REAL | Yes | CLIP aesthetic score (0-10) |
| `clip_score` | REAL | Yes | Text-image alignment (0-1) |
| `technical_score` | REAL | Yes | Resolution, sharpness (0-1) |
| `final_score` | REAL | Yes | Weighted overall score (0-10) |
| `created_at` | DATETIME | No | Creation timestamp (UTC) |
| `status` | TEXT | No | Curation status |
| `is_featured` | BOOLEAN | No | Featured in gallery flag |
| `tags` | JSON | Yes | Tag array (e.g., ["landscape", "sunset"]) |

#### Example Row

```json
{
    "id": 1,
    "filename": "20260108_120000_sunset_42.png",
    "prompt": "a beautiful sunset over snow-capped mountains, highly detailed",
    "negative_prompt": "blurry, low quality, distorted",
    "source_url": "https://images.unsplash.com/photo-xyz",
    "source_query": "mountain sunset",
    "model_id": "stabilityai/stable-diffusion-xl-base-1.0",
    "generation_params": {
        "width": 1024,
        "height": 1024,
        "num_inference_steps": 30,
        "guidance_scale": 7.5,
        "lora_scale": 0.8
    },
    "seed": 42,
    "aesthetic_score": 7.8,
    "clip_score": 0.85,
    "technical_score": 0.92,
    "final_score": 8.2,
    "created_at": "2026-01-08T12:00:00Z",
    "status": "curated",
    "is_featured": true,
    "tags": ["landscape", "sunset", "mountains", "winter"]
}
```

---

### `training_sessions`

Track LoRA training runs.

**Purpose**: Record training configuration, duration, and results for reproducibility and comparison.

#### Schema

```sql
CREATE TABLE training_sessions (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Session Info
    name TEXT NOT NULL,
    model_path TEXT NOT NULL,

    -- Training Configuration
    config JSON DEFAULT '{}',
    dataset_size INTEGER,

    -- Training Results
    final_loss REAL,
    training_time_seconds REAL,
    metrics JSON DEFAULT '{}',

    -- Timestamps
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,

    -- Status
    status TEXT DEFAULT 'running'  -- running, completed, failed
);
```

#### Indexes

```sql
CREATE INDEX idx_training_name ON training_sessions(name);
CREATE INDEX idx_training_status ON training_sessions(status);
CREATE INDEX idx_training_started ON training_sessions(started_at DESC);
```

#### Example Row

```json
{
    "id": 1,
    "name": "landscape_style_v1",
    "model_path": "models/lora/landscape_v1.safetensors",
    "config": {
        "network_dim": 64,
        "network_alpha": 32,
        "learning_rate": 1e-4,
        "max_train_steps": 2000,
        "dataset": "datasets/landscapes"
    },
    "dataset_size": 75,
    "final_loss": 0.0234,
    "training_time_seconds": 7200,
    "metrics": {
        "fid_score": 28.5,
        "sample_images": ["sample_1.png", "sample_2.png"]
    },
    "started_at": "2026-01-05T10:00:00Z",
    "completed_at": "2026-01-05T12:00:00Z",
    "status": "completed"
}
```

---

### `creation_sessions`

Track automated creation batches.

**Purpose**: Monitor automated creation jobs, success rates, and quality trends over time.

#### Schema

```sql
CREATE TABLE creation_sessions (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Session Info
    theme TEXT,

    -- Statistics
    images_created INTEGER DEFAULT 0,
    images_kept INTEGER DEFAULT 0,
    avg_score REAL,

    -- Timestamps
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);
```

#### Indexes

```sql
CREATE INDEX idx_session_started ON creation_sessions(started_at DESC);
CREATE INDEX idx_session_theme ON creation_sessions(theme);
```

#### Example Row

```json
{
    "id": 1,
    "theme": "landscapes",
    "images_created": 5,
    "images_kept": 2,
    "avg_score": 6.8,
    "started_at": "2026-01-08T09:00:00Z",
    "completed_at": "2026-01-08T09:15:00Z"
}
```

---

## Indexes

### Index Strategy

**Principle**: Index columns frequently used in WHERE, ORDER BY, and JOIN clauses.

### Index Performance

| Index | Purpose | Query Speed Improvement |
|-------|---------|-------------------------|
| `idx_created_at` | Recent images | ~100x for date range queries |
| `idx_final_score` | Top quality images | ~50x for sorting by score |
| `idx_status` | Filter by curation status | ~75x for status filtering |
| `idx_filename` | Lookup by filename | ~1000x for unique lookups |

### Composite Index Considerations

For multi-column queries, consider composite indexes:

```sql
-- If frequently querying: WHERE status = 'curated' ORDER BY final_score DESC
CREATE INDEX idx_status_score ON generated_images(status, final_score DESC);
```

---

## Migrations

### Alembic Setup

**Initialize Alembic:**

```bash
alembic init alembic
```

**Configure `alembic.ini`:**

```ini
sqlalchemy.url = sqlite:///./data/lumira.db
```

**Configure `alembic/env.py`:**

```python
from src.ai_artist.db.models import Base

target_metadata = Base.metadata

def run_migrations_online():
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # CRITICAL for SQLite
    )
```

### Creating Migrations

**Auto-generate migration:**

```bash
alembic revision --autogenerate -m "Add new column"
```

**Example Migration:**

```python
"""Add diversity_score column

Revision ID: 002
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.add_column(sa.Column('diversity_score', sa.Float(), nullable=True))
        batch_op.create_index('idx_diversity_score', ['diversity_score'])

def downgrade():
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.drop_index('idx_diversity_score')
        batch_op.drop_column('diversity_score')
```

**Apply migrations:**

```bash
alembic upgrade head
```

**Rollback:**

```bash
alembic downgrade -1
```

---

## Common Queries

### Get Recent High-Quality Images

```sql
SELECT * FROM generated_images
WHERE status = 'curated'
  AND final_score >= 7.0
ORDER BY created_at DESC
LIMIT 10;
```

### Get Uncurated Images for Processing

```sql
SELECT id, filename, prompt
FROM generated_images
WHERE status = 'pending'
ORDER BY created_at ASC
LIMIT 100;
```

### Quality Distribution

```sql
SELECT
    CASE
        WHEN final_score >= 8.0 THEN 'Excellent'
        WHEN final_score >= 6.0 THEN 'Good'
        WHEN final_score >= 4.0 THEN 'Fair'
        ELSE 'Poor'
    END as quality_tier,
    COUNT(*) as count,
    AVG(final_score) as avg_score
FROM generated_images
WHERE status = 'curated'
GROUP BY quality_tier;
```

### Training Session Statistics

```sql
SELECT
    name,
    dataset_size,
    final_loss,
    training_time_seconds / 3600.0 as training_hours,
    status
FROM training_sessions
ORDER BY started_at DESC;
```

### Daily Creation Statistics

```sql
SELECT
    DATE(started_at) as date,
    COUNT(*) as sessions,
    SUM(images_created) as total_created,
    SUM(images_kept) as total_kept,
    ROUND(AVG(avg_score), 2) as avg_quality
FROM creation_sessions
GROUP BY DATE(started_at)
ORDER BY date DESC;
```

---

## Backup Strategy

### Automated Backups

**Daily Backup Script:**

```python
from pathlib import Path
import sqlite3
from datetime import datetime

def backup_database(db_path: Path, backup_dir: Path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"backup_{timestamp}.db"

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)

    source.backup(dest)

    source.close()
    dest.close()

    return backup_path
```

**Retention Policy:**

- Keep daily backups for 7 days
- Keep weekly backups for 1 month
- Keep monthly backups for 1 year

**Backup Schedule:**

```bash
# Cron job (daily at 2 AM)
0 2 * * * /path/to/venv/bin/python scripts/backup_db.py
```

---

## Performance Optimization

### WAL Mode Configuration

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-64000;  -- 64MB cache
PRAGMA temp_store=MEMORY;
```

**Benefits:**

- Faster writes (no lock contention)
- Concurrent reads during writes
- Better crash recovery

### Query Optimization

**Use EXPLAIN QUERY PLAN:**

```sql
EXPLAIN QUERY PLAN
SELECT * FROM generated_images
WHERE status = 'curated'
ORDER BY final_score DESC
LIMIT 10;
```

**Optimize with covering indexes:**

```sql
-- If query only needs these columns:
CREATE INDEX idx_covering ON generated_images(status, final_score, filename, created_at);
```

---

## Data Integrity

### Constraints

**Unique Constraints:**

```sql
ALTER TABLE generated_images ADD CONSTRAINT unique_filename UNIQUE (filename);
```

**Check Constraints:**

```sql
ALTER TABLE generated_images ADD CONSTRAINT check_score_range
    CHECK (final_score >= 0 AND final_score <= 10);

ALTER TABLE generated_images ADD CONSTRAINT check_status_valid
    CHECK (status IN ('pending', 'curated', 'rejected'));
```

### Triggers

**Auto-update timestamp:**

```sql
CREATE TRIGGER update_timestamp
AFTER UPDATE ON generated_images
FOR EACH ROW
BEGIN
    UPDATE generated_images
    SET created_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;
```

---

## Monitoring

### Database Size

```sql
SELECT
    page_count * page_size / 1024.0 / 1024.0 as size_mb
FROM pragma_page_count(), pragma_page_size();
```

### Table Statistics

```sql
SELECT
    name,
    (SELECT COUNT(*) FROM generated_images) as row_count
FROM sqlite_master
WHERE type = 'table' AND name = 'generated_images';
```

### Index Usage

```sql
PRAGMA index_list('generated_images');
PRAGMA index_info('idx_final_score');
```

---

## Troubleshooting

### "Database is locked"

**Solution:**

- Enable WAL mode
- Reduce transaction duration
- Use proper connection pooling

### Slow Queries

**Diagnosis:**

```sql
EXPLAIN QUERY PLAN SELECT ...;
```

**Solutions:**

- Add missing indexes
- Use ANALYZE to update statistics
- Consider denormalization for complex joins

### Database Corruption

**Check integrity:**

```sql
PRAGMA integrity_check;
```

**Recovery:**

```bash
# Restore from backup
sqlite3 lumira.db ".backup backup.db"
```

---

**Document Version:** 1.0
**Last Updated:** 2026-01-08
