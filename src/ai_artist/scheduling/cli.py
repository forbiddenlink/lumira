#!/usr/bin/env python
"""CLI tool for managing scheduled artwork creation."""

import argparse
import asyncio
import sys
from pathlib import Path

from ai_artist.main import AIArtist
from ai_artist.scheduling.scheduler import ScheduledArtist
from ai_artist.utils.config import load_config
from ai_artist.utils.logging import get_logger, set_request_id

logger = get_logger(__name__)


async def start_scheduler(args: argparse.Namespace) -> None:
    """Start the scheduler with configured jobs."""
    set_request_id()  # Set request ID for scheduler session

    config = load_config(Path("config/config.yaml"))
    artist = AIArtist(config)
    scheduled_artist = ScheduledArtist(artist)

    # Set up schedules based on args
    if args.daily:
        hour, minute = map(int, args.daily.split(":"))
        scheduled_artist.schedule_daily(hour=hour, minute=minute)
        logger.info(
            "scheduled_daily",
            hour=hour,
            minute=minute,
        )

    if args.interval:
        scheduled_artist.schedule_interval(hours=args.interval)
        logger.info("scheduled_interval", hours=args.interval)

    if args.batch:
        count, time_str = args.batch.split("@")
        count = int(count)
        hour, minute = map(int, time_str.split(":"))
        scheduled_artist.schedule_batch_daily(count=count, hour=hour, minute=minute)
        logger.info(
            "scheduled_batch_daily",
            count=count,
            hour=hour,
            minute=minute,
        )

    # Start the scheduler
    scheduled_artist.start()
    logger.info("scheduler_started")

    # List scheduled jobs
    jobs = scheduled_artist.list_jobs()
    if jobs:
        logger.info("scheduled_jobs", count=len(jobs), jobs=[j["name"] for j in jobs])

    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("scheduler_interrupted")
        scheduled_artist.shutdown()
        logger.info("scheduler_stopped")


async def run_now(args: argparse.Namespace) -> None:
    """Run artwork creation immediately."""
    set_request_id()  # Set request ID for this run

    config = load_config(Path("config/config.yaml"))
    artist = AIArtist(config)

    if args.batch_size:
        scheduled_artist = ScheduledArtist(artist)
        logger.info("batch_creation_started", batch_size=args.batch_size)
        await scheduled_artist.create_batch(count=args.batch_size)
        logger.info("batch_creation_completed", batch_size=args.batch_size)
    else:
        await artist.create_artwork(theme=args.theme)


async def list_jobs(args: argparse.Namespace) -> None:
    """List all scheduled jobs."""
    config = load_config(Path("config/config.yaml"))
    artist = AIArtist(config)
    scheduled_artist = ScheduledArtist(artist)

    jobs = scheduled_artist.list_jobs()
    if not jobs:
        logger.info("no_scheduled_jobs")
        return

    logger.info("listing_jobs", count=len(jobs))
    for job in jobs:
        logger.info(
            "job_details",
            id=job["id"],
            name=job["name"],
            next_run=str(job["next_run"]),
            trigger=str(job["trigger"]),
        )


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI Artist Scheduler - Automated artwork creation"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start scheduler
    start_parser = subparsers.add_parser("start", help="Start the scheduler")
    start_parser.add_argument(
        "--daily",
        type=str,
        metavar="HH:MM",
        help="Schedule daily creation at specified time (e.g., 09:00)",
    )
    start_parser.add_argument(
        "--interval",
        type=int,
        metavar="HOURS",
        help="Schedule creation every N hours",
    )
    start_parser.add_argument(
        "--batch",
        type=str,
        metavar="COUNT@HH:MM",
        help="Schedule daily batch (e.g., 3@09:00 for 3 artworks at 9am)",
    )

    # Run now
    run_parser = subparsers.add_parser("run", help="Create artwork now")
    run_parser.add_argument(
        "--theme",
        type=str,
        default=None,
        help="Theme for artwork",
    )
    run_parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Create multiple artworks",
    )

    # List jobs
    subparsers.add_parser("list", help="List scheduled jobs")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "start":
            asyncio.run(start_scheduler(args))
        elif args.command == "run":
            asyncio.run(run_now(args))
        elif args.command == "list":
            asyncio.run(list_jobs(args))
    except Exception as e:
        logger.error("command_failed", command=args.command, error=str(e))
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
