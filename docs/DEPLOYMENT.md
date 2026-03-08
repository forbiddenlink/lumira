# Deployment Guide

Comprehensive guide for deploying Lumira in production environments.

## Table of Contents

- [Quick Deploy: Vercel (Gallery Only)](#quick-deploy-vercel-gallery-only)
- [Quick Deploy: Railway](#quick-deploy-railway)
- [Deployment Options](#deployment-options)
- [Containerization](#containerization)
- [Cloud Deployment](#cloud-deployment)
- [Cost Management](#cost-management)
- [Database Migrations](#database-migrations)
- [Monitoring & Alerting](#monitoring--alerting)
- [Disaster Recovery](#disaster-recovery)

---

## Quick Deploy: Vercel (Gallery Only)

Deploy your gallery to Vercel in minutes. Note: Image generation requires GPU support, which Vercel doesn't provide. Use this for showcasing your artwork online.

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy (from project root)
vercel

# Set environment variables (optional)
vercel env add GALLERY_ONLY_MODE true
```

**What works on Vercel:**

- Viewing gallery images
- API endpoints for listing/filtering images
- Health checks

**What doesn't work on Vercel:**

- Image generation (no GPU)
- Long-running processes
- Large model files

For full functionality, use Railway, Render, or Docker deployment.

---

## Quick Deploy: Railway

Railway supports full web applications with persistent storage.

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and deploy
railway login
railway init
railway up

# Add environment variables in Railway dashboard:
# - UNSPLASH_ACCESS_KEY
# - UNSPLASH_SECRET_KEY
```

**For GPU support:** Use Railway's GPU compute add-on or deploy to a GPU-enabled cloud provider.

---

## Deployment Options

### Local Development

- **Best for**: Initial development, testing, personal use
- **Requirements**: GPU-enabled machine (NVIDIA RTX 3060+ recommended)
- **Pros**: Full control, no ongoing costs, data privacy
- **Cons**: Limited scalability, requires local GPU

### Docker Deployment

- **Best for**: Consistent deployment across environments
- **Requirements**: Docker, Docker Compose, NVIDIA Container Toolkit
- **Pros**: Portable, reproducible, easy rollback
- **Cons**: Additional complexity, resource overhead

### Kubernetes Deployment

- **Best for**: Production, high availability, auto-scaling
- **Requirements**: K8s cluster, GPU node pools
- **Pros**: Auto-scaling, load balancing, high availability
- **Cons**: Complex setup, higher operational overhead

### Cloud Platform Deployment

- **Best for**: Managed infrastructure, elastic scaling
- **Options**: AWS SageMaker, Azure ML, Google Cloud Vertex AI
- **Pros**: Managed infrastructure, auto-scaling, built-in monitoring
- **Cons**: Higher costs, vendor lock-in

---

## Containerization

### Dockerfile Structure

```dockerfile
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Install Python 3.11
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create necessary directories
RUN mkdir -p models gallery logs data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MODEL_CACHE=/app/models

# Run the application
CMD ["python", "src/main.py"]
```

### Docker Compose Setup

```yaml
version: '3.8'

services:
  lumira:
    build: .
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - UNSPLASH_ACCESS_KEY=${UNSPLASH_ACCESS_KEY}
      - PEXELS_API_KEY=${PEXELS_API_KEY}
    volumes:
      - ./gallery:/app/gallery
      - ./models:/app/models
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config/config.yaml:/app/config/config.yaml:ro
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### Multi-Stage Build (Optimized)

```dockerfile
# Builder stage
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y python3.11 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
COPY src/ /app/src/
COPY config/ /app/config/

ENV PATH=/root/.local/bin:$PATH
WORKDIR /app
CMD ["python3.11", "src/main.py"]
```

---

## Cloud Deployment

### AWS Deployment

#### Using EC2 with GPU

```bash
# Launch g4dn.xlarge instance (T4 GPU)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type g4dn.xlarge \
  --key-name your-key \
  --security-groups lumira-sg \
  --user-data file://user-data.sh

# user-data.sh
#!/bin/bash
apt-get update
apt-get install -y docker.io nvidia-docker2
systemctl restart docker
docker run -d --gpus all your-registry/lumira:latest
```

#### Using SageMaker

```python
from sagemaker.estimator import Estimator

estimator = Estimator(
    image_uri="your-registry/lumira:latest",
    role="arn:aws:iam::account:role/SageMakerRole",
    instance_count=1,
    instance_type="ml.g4dn.xlarge",
    volume_size=100,
    max_run=86400,  # 24 hours
    environment={
        'UNSPLASH_ACCESS_KEY': 'your-key',
        'PEXELS_API_KEY': 'your-key'
    }
)

estimator.fit(wait=False)
```

### GCP Deployment

#### Using GKE (Google Kubernetes Engine)

```bash
# Create GKE cluster with GPU nodes
gcloud container clusters create lumira-cluster \
  --zone us-central1-a \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 1 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 3

# Install NVIDIA device plugin
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml

# Deploy application
kubectl apply -f k8s/deployment.yaml
```

#### Kubernetes Deployment Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lumira
spec:
  replicas: 1
  selector:
    matchLabels:
      app: lumira
  template:
    metadata:
      labels:
        app: lumira
    spec:
      containers:
      - name: lumira
        image: gcr.io/your-project/lumira:latest
        resources:
          limits:
            nvidia.com/gpu: 1
        env:
        - name: UNSPLASH_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: api-secrets
              key: unsplash-key
        - name: PEXELS_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-secrets
              key: pexels-key
        volumeMounts:
        - name: gallery
          mountPath: /app/gallery
        - name: models
          mountPath: /app/models
      volumes:
      - name: gallery
        persistentVolumeClaim:
          claimName: gallery-pvc
      - name: models
        persistentVolumeClaim:
          claimName: models-pvc
      nodeSelector:
        cloud.google.com/gke-accelerator: nvidia-tesla-t4
```

### Azure Deployment

#### Using Azure ML

```python
from azureml.core import Workspace, Experiment, Environment, ScriptRunConfig
from azureml.core.compute import AmlCompute

ws = Workspace.from_config()

# Create GPU compute target
compute_target = AmlCompute(ws, "gpu-cluster")

# Create environment
env = Environment.from_dockerfile("lumira-env", "Dockerfile")

# Configure run
config = ScriptRunConfig(
    source_directory="src",
    script="main.py",
    compute_target=compute_target,
    environment=env
)

# Submit experiment
experiment = Experiment(ws, "lumira")
run = experiment.submit(config)
```

---

## Cost Management

### GPU Cost Analysis (2026)

#### Cloud Provider Comparison

| Provider | Instance Type | GPU | Cost/Hour | Monthly (24/7) |
|----------|--------------|-----|-----------|----------------|
| AWS | g4dn.xlarge | T4 | $0.526 | ~$380 |
| AWS | g5.xlarge | A10G | $1.006 | ~$726 |
| GCP | n1-standard-4 + T4 | T4 | $0.45 | ~$325 |
| Azure | NC4as_T4_v3 | T4 | $0.526 | ~$380 |
| Lambda Labs | GPU Cloud | A100 | $1.10 | ~$792 |
| Vast.ai | Market | A100 | $0.80-$1.20 | ~$576-$864 |

#### Cost-Effective Strategies

**1. Scheduled Generation (Recommended for this project)**

```python
# Generate daily at 2 AM when costs are lowest
schedule.every().day.at("02:00").do(generate_artwork)

# Estimated monthly cost: 1 hour/day × 30 days × $0.80 = $24/month
```

**2. Spot Instances (70% cost reduction)**

```bash
# AWS Spot request
aws ec2 request-spot-instances \
  --instance-count 1 \
  --type "one-time" \
  --launch-specification file://specification.json

# Typical cost: $0.15-$0.20/hour (vs $0.526 on-demand)
```

**3. Preemptible/Spot Instances on GCP**

```yaml
# Add to deployment
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-preemptible: "true"

# Cost: ~30% of regular price
```

**4. Auto-Scaling with Scale-to-Zero**

```yaml
# KEDA ScaledObject for Kubernetes
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: lumira-scaler
spec:
  scaleTargetRef:
    name: lumira
  minReplicaCount: 0
  maxReplicaCount: 3
  triggers:
  - type: cron
    metadata:
      timezone: America/New_York
      start: 0 2 * * *  # 2 AM daily
      end: 0 3 * * *    # 3 AM daily
      desiredReplicas: "1"
```

### Cost Optimization Recommendations

1. **Use Local GPU for Development**
   - RTX 4060: $300 one-time
   - Breakeven: ~12 months of cloud usage
   - Best for: Continuous development

2. **Cloud for Production**
   - Spot instances for scheduled generation
   - Reserved instances for 24/7 operation (40% discount)
   - Multi-region for better spot availability

3. **Hybrid Approach**
   - Train LoRA weights locally
   - Deploy inference to cloud
   - Use cloud storage for gallery

4. **Model Optimization**
   - Use SDXL Turbo for faster inference (2s vs 48s)
   - Enable attention slicing to reduce VRAM
   - Quantize models to FP16 (50% memory reduction)

### Budget Scenarios

**Minimal Budget ($10-20/month)**

- Local generation on personal GPU
- Free tier API usage (Unsplash: 50 req/hr)
- Local storage

**Small Budget ($50-100/month)**

- Scheduled cloud generation (1-2 hours/day)
- Spot/preemptible instances
- Cloud storage for gallery

**Medium Budget ($200-500/month)**

- Reserved instance for consistent availability
- Higher API limits
- Managed MLOps platform (MLflow, W&B)

---

## Database Migrations

### Using Alembic

#### Setup

```bash
# Install Alembic
pip install alembic

# Initialize Alembic
alembic init alembic

# Edit alembic.ini
sqlalchemy.url = sqlite:///data/lumira.db
```

#### Configuration (alembic/env.py)

```python
from src.database import Base
from src.models import Artwork, InspirationImage, TrainingSession

target_metadata = Base.metadata

# For SQLite batch operations
def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True  # Important for SQLite
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True  # Important for SQLite
        )

        with context.begin_transaction():
            context.run_migrations()
```

#### Create Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add performance_metrics column"

# Manual migration
alembic revision -m "Add indexes for performance"
```

#### Example Migration (alembic/versions/001_initial.py)

```python
"""Initial schema

Revision ID: 001
Create Date: 2026-01-15 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Artworks table
    op.create_table(
        'artworks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=True),
        sa.Column('aesthetic_score', sa.Float(), nullable=True),
        sa.Column('technical_score', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_artworks_created_at', 'artworks', ['created_at'])
    op.create_index('ix_artworks_aesthetic_score', 'artworks', ['aesthetic_score'])

def downgrade():
    op.drop_index('ix_artworks_aesthetic_score')
    op.drop_index('ix_artworks_created_at')
    op.drop_table('artworks')
```

#### Example Migration with SQLite Batch Operations

```python
def upgrade():
    # SQLite doesn't support ALTER COLUMN directly
    with op.batch_alter_table('artworks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('embedding', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('metadata', sa.JSON(), nullable=True))
        batch_op.create_index('ix_artworks_metadata', ['metadata'])

def downgrade():
    with op.batch_alter_table('artworks', schema=None) as batch_op:
        batch_op.drop_index('ix_artworks_metadata')
        batch_op.drop_column('metadata')
        batch_op.drop_column('embedding')
```

#### Run Migrations

```bash
# Check current version
alembic current

# View migration history
alembic history

# Upgrade to latest
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Upgrade to specific version
alembic upgrade 003
```

#### CI/CD Integration

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Check for pending migrations
        run: |
          alembic check || {
            echo "⚠️ Database schema changes detected!"
            echo "Please generate migrations with:"
            echo "  alembic revision --autogenerate -m 'description'"
            exit 1
          }
```

### Migration Best Practices

1. **Always use batch operations for SQLite**

   ```python
   with op.batch_alter_table('table_name') as batch_op:
       batch_op.add_column(...)
   ```

2. **Test migrations both ways**

   ```bash
   alembic upgrade head
   alembic downgrade base
   alembic upgrade head
   ```

3. **Backup before production migrations**

   ```bash
   cp data/lumira.db data/lumira.db.backup.$(date +%Y%m%d_%H%M%S)
   alembic upgrade head
   ```

4. **Version control all migrations**
   - Commit `alembic/versions/*.py` files
   - Never modify existing migration files
   - Create new migrations for changes

---

## Monitoring & Alerting

### Metrics to Track

#### Application Metrics

- Generation success/failure rate
- Average generation time
- API request latency
- Queue depth
- Model inference time
- VRAM usage
- Aesthetic score distribution

#### Infrastructure Metrics

- GPU utilization
- GPU memory usage
- CPU usage
- Disk I/O
- Network bandwidth
- Container restarts

### Prometheus Integration

#### Expose Metrics

```python
from prometheus_client import start_http_server, Counter, Histogram, Gauge
import time

# Define metrics
GENERATION_REQUESTS = Counter('ai_artist_generation_requests_total', 'Total generation requests')
GENERATION_DURATION = Histogram('ai_artist_generation_duration_seconds', 'Time spent generating')
GENERATION_ERRORS = Counter('ai_artist_generation_errors_total', 'Total generation errors', ['error_type'])
GPU_MEMORY = Gauge('ai_artist_gpu_memory_bytes', 'GPU memory usage')
AESTHETIC_SCORE = Histogram('ai_artist_aesthetic_score', 'Aesthetic scores of generated images')

# Start metrics server
start_http_server(8000)

# Instrument code
@GENERATION_DURATION.time()
def generate_artwork():
    GENERATION_REQUESTS.inc()
    try:
        # Generation logic
        result = model.generate()
        AESTHETIC_SCORE.observe(result.aesthetic_score)
        return result
    except Exception as e:
        GENERATION_ERRORS.labels(error_type=type(e).__name__).inc()
        raise
```

#### Prometheus Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'lumira'
    static_configs:
      - targets: ['localhost:8000']
    scrape_interval: 15s
```

### Grafana Dashboards

#### Sample Dashboard JSON

```json
{
  "dashboard": {
    "title": "Lumira Performance",
    "panels": [
      {
        "title": "Generation Rate",
        "targets": [
          {
            "expr": "rate(ai_artist_generation_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(ai_artist_generation_errors_total[5m])"
          }
        ]
      },
      {
        "title": "GPU Memory Usage",
        "targets": [
          {
            "expr": "ai_artist_gpu_memory_bytes"
          }
        ]
      }
    ]
  }
}
```

### Alerting Rules

#### Prometheus Alerts

```yaml
# alerts.yml
groups:
  - name: lumira
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(ai_artist_generation_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec"

      - alert: GenerationStalled
        expr: rate(ai_artist_generation_requests_total[10m]) == 0
        for: 30m
        labels:
          severity: critical
        annotations:
          summary: "No generations in 30 minutes"

      - alert: HighGPUMemory
        expr: ai_artist_gpu_memory_bytes > 15e9  # 15 GB
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU memory usage high"
```

### Logging Best Practices

#### Structured Logging with Structlog

```python
import structlog
from structlog.processors import JSONRenderer

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger()

# Usage
log.info("generation_started",
         prompt="sunset landscape",
         model="sdxl",
         seed=42)

log.error("generation_failed",
          error=str(e),
          prompt=prompt,
          retries=3)
```

#### Log Aggregation

**Using ELK Stack:**

```yaml
# docker-compose.yml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
    ports:
      - "9200:9200"

  logstash:
    image: docker.elastic.co/logstash/logstash:8.11.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    depends_on:
      - elasticsearch

  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    ports:
      - "5601:5601"
    depends_on:
      - elasticsearch
```

---

## Disaster Recovery

### Backup Strategy

#### What to Backup

1. **Critical Data (Daily)**
   - SQLite database (`data/lumira.db`)
   - Generated gallery images
   - Configuration files

2. **Model Artifacts (Weekly)**
   - Trained LoRA weights (`models/`)
   - Fine-tuned checkpoints

3. **Logs (Monthly Archive)**
   - Application logs
   - Training logs

#### Automated Backup Script

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/lumira"
SOURCE_DIR="/app"

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup database
echo "Backing up database..."
sqlite3 "$SOURCE_DIR/data/lumira.db" ".backup '$BACKUP_DIR/$DATE/lumira.db'"

# Backup gallery (incremental)
echo "Backing up gallery..."
rsync -av --link-dest="$BACKUP_DIR/latest" \
  "$SOURCE_DIR/gallery/" \
  "$BACKUP_DIR/$DATE/gallery/"

# Backup models
echo "Backing up models..."
tar -czf "$BACKUP_DIR/$DATE/models.tar.gz" \
  -C "$SOURCE_DIR" models/

# Backup config
echo "Backing up config..."
cp "$SOURCE_DIR/config/config.yaml" "$BACKUP_DIR/$DATE/"

# Update latest symlink
ln -sfn "$BACKUP_DIR/$DATE" "$BACKUP_DIR/latest"

# Cleanup old backups (keep last 30 days)
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;

echo "Backup completed: $BACKUP_DIR/$DATE"
```

#### Cloud Backup Integration

```python
# backup.py
import boto3
from datetime import datetime

def backup_to_s3():
    s3 = boto3.client('s3')
    bucket = 'lumira-backups'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Upload database
    s3.upload_file(
        'data/lumira.db',
        bucket,
        f'backups/{timestamp}/lumira.db'
    )

    # Upload models
    s3.upload_file(
        'models/lora_weights.safetensors',
        bucket,
        f'backups/{timestamp}/lora_weights.safetensors'
    )

    print(f"Backup completed to s3://{bucket}/backups/{timestamp}/")
```

### Recovery Procedures

#### Database Recovery

```bash
# Restore from backup
cp /backups/lumira/20260115_120000/lumira.db data/lumira.db

# Verify integrity
sqlite3 data/lumira.db "PRAGMA integrity_check;"

# Restart application
docker-compose restart lumira
```

#### Model Recovery

```bash
# Restore models
tar -xzf /backups/lumira/20260115_120000/models.tar.gz -C /app/

# Verify model files
python -c "from safetensors import safe_open;
           safe_open('models/lora_weights.safetensors', framework='pt')"
```

#### Complete System Recovery

```bash
#!/bin/bash
# restore.sh

BACKUP_DATE=$1  # e.g., 20260115_120000
BACKUP_DIR="/backups/lumira/$BACKUP_DATE"

if [ ! -d "$BACKUP_DIR" ]; then
    echo "Backup not found: $BACKUP_DIR"
    exit 1
fi

echo "Restoring from backup: $BACKUP_DATE"

# Stop application
docker-compose down

# Restore database
cp "$BACKUP_DIR/lumira.db" data/lumira.db

# Restore gallery
rsync -av "$BACKUP_DIR/gallery/" gallery/

# Restore models
tar -xzf "$BACKUP_DIR/models.tar.gz" -C .

# Restore config
cp "$BACKUP_DIR/config.yaml" config/config.yaml

# Restart application
docker-compose up -d

echo "Recovery completed. Application restarted."
```

### RPO/RTO Targets

- **Recovery Point Objective (RPO)**: 24 hours
  - Daily backups ensure max 1 day of data loss

- **Recovery Time Objective (RTO)**: 1 hour
  - Automated recovery scripts enable quick restoration

### High Availability Setup (Optional)

#### Multi-Region Deployment

```yaml
# For critical production environments
regions:
  primary: us-east-1
  secondary: us-west-2

# Replication strategy
replication:
  database: Continuous (every 5 min)
  models: Daily
  gallery: Hourly
```

#### Health Checks

```python
from fastapi import FastAPI
import torch

app = FastAPI()

@app.get("/health")
def health_check():
    try:
        # Check GPU availability
        if not torch.cuda.is_available():
            return {"status": "unhealthy", "reason": "GPU not available"}

        # Check database
        db.execute("SELECT 1")

        # Check model loaded
        if model is None:
            return {"status": "unhealthy", "reason": "Model not loaded"}

        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "reason": str(e)}

@app.get("/ready")
def readiness_check():
    # Check if system is ready to accept requests
    return {
        "ready": model is not None and torch.cuda.is_available(),
        "gpu_memory_used": torch.cuda.memory_allocated() / 1e9,
        "queue_size": scheduler.queue_size()
    }
```

---

## Additional Resources

- [SECURITY.md](SECURITY.md) - Security best practices
- [TESTING.md](TESTING.md) - Testing strategies
- [LEGAL.md](LEGAL.md) - Copyright and compliance
- [MLOps Best Practices (2026)](https://www.moontechnolabs.com/blog/mlops-best-practices/)
- [Kubernetes GPU Deployment Guide](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Prometheus Monitoring](https://prometheus.io/docs/introduction/overview/)
