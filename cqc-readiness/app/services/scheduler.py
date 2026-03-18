from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import get_settings

logger = logging.getLogger(__name__)


async def _run_daily_job() -> None:
    """
    Core daily job:
    1. Create assignments for all eligible recipients (idempotent)
    2. Send daily check emails for each assignment that hasn't been emailed yet
    """
    from app.database import SessionFactory
    from app.models.assignment import DailyAssignment
    from app.models.recipient import Recipient
    from app.models.statement import WeStatement
    from app.services.assignment import create_daily_assignments
    from app.services.email import send_daily_check

    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    today = datetime.now(tz).date()

    logger.info("Daily job starting for %s", today)

    async with SessionFactory() as db:
        try:
            # Step 1: Create assignments (idempotent)
            new_assignments = await create_daily_assignments(db, for_date=today)
            await db.commit()
            logger.info("Created %d new assignments", len(new_assignments))

            # Step 2: Fetch all assignments for today where email hasn't been sent
            result = await db.execute(
                select(DailyAssignment)
                .where(
                    DailyAssignment.assignment_date == today,
                    DailyAssignment.email_sent_at.is_(None),
                )
            )
            pending: list[DailyAssignment] = list(result.scalars().all())
            logger.info("Sending emails for %d pending assignments", len(pending))

            sent_count = 0
            error_count = 0

            for assignment in pending:
                # Reload with relationships for email rendering
                result2 = await db.execute(
                    select(DailyAssignment)
                    .where(DailyAssignment.id == assignment.id)
                )
                # Load recipient and statement
                from sqlalchemy.orm import selectinload

                full_result = await db.execute(
                    select(DailyAssignment)
                    .options(
                        selectinload(DailyAssignment.recipient),
                        selectinload(DailyAssignment.statement),
                    )
                    .where(DailyAssignment.id == assignment.id)
                )
                full_assignment = full_result.scalar_one()

                recipient = full_assignment.recipient
                statement = full_assignment.statement

                try:
                    await send_daily_check(full_assignment, recipient, statement)
                    full_assignment.email_sent_at = datetime.now(timezone.utc)
                    await db.commit()
                    sent_count += 1
                    logger.info("Email sent to %s", recipient.email)
                except Exception as exc:
                    error_count += 1
                    logger.error(
                        "Failed to send email to %s (assignment %s): %s",
                        recipient.email,
                        assignment.id,
                        exc,
                        exc_info=True,
                    )

            logger.info(
                "Daily job complete: %d sent, %d errors", sent_count, error_count
            )

        except Exception as exc:
            await db.rollback()
            logger.error("Daily job failed: %s", exc, exc_info=True)
            raise


def create_scheduler() -> AsyncIOScheduler:
    """
    Build and return a configured AsyncIOScheduler.

    The daily job runs Mon–Fri at SCHEDULER_SEND_HOUR in SCHEDULER_TIMEZONE.
    """
    settings = get_settings()

    scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)

    trigger = CronTrigger(
        hour=settings.SCHEDULER_SEND_HOUR,
        minute=0,
        day_of_week="mon-fri",
        timezone=settings.SCHEDULER_TIMEZONE,
    )

    scheduler.add_job(
        _run_daily_job,
        trigger=trigger,
        id="daily_cqc_check",
        name="Daily CQC Readiness Check",
        misfire_grace_time=3600,  # Allow up to 1 hour late if server was down
        coalesce=True,  # Only run once even if multiple misfires
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured: daily job at %02d:00 %s (Mon-Fri)",
        settings.SCHEDULER_SEND_HOUR,
        settings.SCHEDULER_TIMEZONE,
    )

    return scheduler
