"""
Scheduler Module

Sets up APScheduler for automated jobs:
- Weekly discovery scan (Monday 6am by default)
- Hourly validation timeout checker
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import get_settings
from ..db import SessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler: Optional[AsyncIOScheduler] = None


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    global scheduler
    scheduler = AsyncIOScheduler()

    # Parse discovery cron expression
    cron_parts = settings.discovery_cron.split()
    if len(cron_parts) == 5:
        minute, hour, day, month, day_of_week = cron_parts
    else:
        minute, hour, day, month, day_of_week = "0", "6", "*", "*", "1"

    # Weekly discovery scan
    scheduler.add_job(
        _run_discovery_scan,
        CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        ),
        id="weekly_discovery_scan",
        name="Weekly Discovery Scan",
        replace_existing=True,
    )

    # Hourly validation timeout check
    scheduler.add_job(
        _check_validation_timeouts,
        CronTrigger(minute="0"),  # every hour at :00
        id="validation_timeout_check",
        name="Validation Timeout Check",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler configured: discovery={settings.discovery_cron}, "
        f"validation_timeout=hourly"
    )

    return scheduler


async def _run_discovery_scan():
    """Execute the weekly discovery scan."""
    logger.info("Scheduler: Running weekly discovery scan...")
    db = SessionLocal()
    try:
        from .discovery import run_weekly_discovery_scan
        result = run_weekly_discovery_scan(db)
        logger.info(f"Scheduler: Discovery scan complete: {result}")
    except Exception as e:
        logger.error(f"Scheduler: Discovery scan failed: {e}")
    finally:
        db.close()


async def _check_validation_timeouts():
    """Check for timed-out validation requests."""
    db = SessionLocal()
    try:
        from .validation import ValidationOrchestrator
        orchestrator = ValidationOrchestrator(db)
        count = orchestrator.check_timeouts()
        if count > 0:
            logger.info(f"Scheduler: {count} validation requests timed out")
    except Exception as e:
        logger.error(f"Scheduler: Timeout check failed: {e}")
    finally:
        db.close()


def start_scheduler():
    """Start the scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = create_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
