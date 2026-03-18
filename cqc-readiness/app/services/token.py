from __future__ import annotations

import uuid
from datetime import datetime

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.assignment import DailyAssignment


async def generate_token() -> uuid.UUID:
    """Generate a new random UUID token."""
    return uuid.uuid4()


async def lookup_assignment(
    token: uuid.UUID, db: AsyncSession
) -> DailyAssignment | None:
    """
    Look up a DailyAssignment by its token UUID.

    Eagerly loads the related Recipient and WeStatement so callers don't need
    additional queries.
    """
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(DailyAssignment)
        .options(
            selectinload(DailyAssignment.recipient),
            selectinload(DailyAssignment.statement),
            selectinload(DailyAssignment.responses),
        )
        .where(DailyAssignment.token == token)
    )
    return result.scalar_one_or_none()


def is_token_valid(assignment: DailyAssignment) -> bool:
    """
    Return True if the assignment belongs to today in the configured UK timezone.

    Tokens are valid only on the calendar day they were issued.
    """
    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    today = datetime.now(tz).date()
    return assignment.assignment_date == today
