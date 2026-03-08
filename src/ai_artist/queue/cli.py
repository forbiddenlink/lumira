#!/usr/bin/env python3
"""CLI tool to launch RQ workers for image generation.

Usage:
    lumira-worker              # Start worker for all queues
    lumira-worker --high       # Start worker for high priority only
    lumira-worker --burst      # Process jobs and exit
    lumira-worker --verbose    # Enable verbose logging
"""

import argparse
import os
import sys

from ai_artist.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def main():
    """Launch an RQ worker for image generation jobs."""
    parser = argparse.ArgumentParser(
        description="Run an AI Artist image generation worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    lumira-worker                    # Start worker for all queues
    lumira-worker --high             # High priority queue only
    lumira-worker --normal           # Normal priority queue only
    lumira-worker --burst            # Process available jobs and exit
    lumira-worker --with-scheduler   # Start with job scheduler

Environment Variables:
    REDIS_URL                           # Redis connection URL
                                        # Default: redis://localhost:6379
        """,
    )

    parser.add_argument(
        "--high",
        action="store_true",
        help="Only process high priority queue",
    )
    parser.add_argument(
        "--normal",
        action="store_true",
        help="Only process normal priority queue",
    )
    parser.add_argument(
        "--low",
        action="store_true",
        help="Only process low priority queue",
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Run in burst mode (process jobs and exit)",
    )
    parser.add_argument(
        "--with-scheduler",
        action="store_true",
        help="Start with job scheduler for periodic tasks",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--redis-url",
        type=str,
        default=os.getenv("REDIS_URL", "redis://localhost:6379"),
        help="Redis connection URL",
    )

    args = parser.parse_args()

    # Try to import RQ
    try:
        from redis import Redis  # type: ignore[import-untyped]
        from rq import Queue, Worker
    except ImportError:
        print("\nError: RQ is not installed.")
        print("Install it with: pip install lumira[queue]")
        print("Or: pip install rq")
        sys.exit(1)

    # Determine which queues to listen to
    queue_names = []

    if args.high:
        queue_names.append("generation-high")
    if args.normal:
        queue_names.append("generation")
    if args.low:
        queue_names.append("generation-low")

    # If no specific queue selected, listen to all (high priority first)
    if not queue_names:
        queue_names = ["generation-high", "generation", "generation-low"]

    # Connect to Redis
    try:
        redis_conn = Redis.from_url(args.redis_url)
        redis_conn.ping()  # Test connection
    except Exception as e:
        print(f"\nError: Could not connect to Redis at {args.redis_url}")
        print(f"Details: {e}")
        print("\nMake sure Redis is running:")
        print("  docker run -d -p 6379:6379 redis:7-alpine")
        sys.exit(1)

    # Create queues
    queues = [Queue(name, connection=redis_conn) for name in queue_names]

    logger.info(
        "starting_worker",
        queues=queue_names,
        burst=args.burst,
        redis_url=args.redis_url.split("@")[-1],  # Hide credentials
    )

    print("\n=================================================")
    print("          AI Artist Worker")
    print("=================================================")
    print(f"\n  Queues: {', '.join(queue_names)}")
    print(f"  Redis:  {args.redis_url.split('@')[-1]}")
    print(f"  Mode:   {'Burst' if args.burst else 'Continuous'}")
    print("\n  Press Ctrl+C to stop the worker")
    print("=================================================\n")

    try:
        # Create and start worker
        worker = Worker(
            queues,
            connection=redis_conn,
            name=f"lumira-worker-{os.getpid()}",
        )

        worker.work(
            burst=args.burst,
            logging_level="DEBUG" if args.verbose else "INFO",
            with_scheduler=args.with_scheduler,
        )

    except KeyboardInterrupt:
        logger.info("worker_stopped_by_user")
        print("\n\n  Worker stopped")
        sys.exit(0)
    except Exception as e:
        logger.error("worker_failed", error=str(e))
        print(f"\nWorker error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
