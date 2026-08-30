"""
Prometheus metrics endpoints for monitoring.

Provides /metrics endpoint for Prometheus scraping.
"""

import structlog
from fastapi import APIRouter, Depends, Response

from ai_artist.monitoring.metrics import get_metrics, is_metrics_available

from .dependencies import require_api_key

logger = structlog.get_logger(__name__)

# Metrics expose internal operational state (queue depth, error rates); gate
# behind the same API key as admin. Fail-closed dependency 503s when no keys
# are configured and dev_mode is off, so Prometheus must send X-API-Key.
router = APIRouter(tags=["metrics"], dependencies=[Depends(require_api_key)])


@router.get("/metrics")
async def prometheus_metrics() -> Response:
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
