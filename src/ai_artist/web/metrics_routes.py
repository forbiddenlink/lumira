"""
Prometheus metrics endpoints for monitoring.

Provides /metrics endpoint for Prometheus scraping.
"""

import structlog
from fastapi import APIRouter, Response

from ai_artist.monitoring.metrics import get_metrics, is_metrics_available

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format for scraping.
    Configure Prometheus to scrape this endpoint for monitoring.

    Example prometheus.yml:
    ```yaml
    scrape_configs:
      - job_name: 'lumira'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/metrics'
    ```
    """
    if not is_metrics_available():
        logger.warning("metrics_requested_but_unavailable")
        return Response(
            content="# Prometheus client not installed. Install with: pip install prometheus-client\n",
            media_type="text/plain",
        )

    metrics_data, content_type = get_metrics()

    logger.debug("metrics_scraped", size_bytes=len(metrics_data))

    return Response(content=metrics_data, media_type=content_type)
