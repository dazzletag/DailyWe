from __future__ import annotations

import logging
import uuid
from datetime import datetime, date

import pytz
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.assignment import DailyAssignment
from app.models.recipient import Recipient
from app.models.statement import WeStatement

logger = logging.getLogger(__name__)

# Roles that receive 'manager' or 'all' statements
MANAGER_ROLES = {"HomeManager", "OperationsManager"}
# Roles that receive 'deputy' or 'all' statements
DEPUTY_ROLES = {"DeputyManager"}
# CQM role receives no daily check emails
EXCLUDED_ROLES = {"CareQualityManager"}


def _role_group_filter(role: str) -> list[str]:
    """Return the list of role_group values a recipient is eligible for."""
    if role in MANAGER_ROLES:
        return ["manager", "all"]
    if role in DEPUTY_ROLES:
        return ["deputy", "all"]
    return []


async def _get_eligible_statements(
    db: AsyncSession, role_groups: list[str]
) -> list[WeStatement]:
    """Fetch active statements matching the given role groups, ordered by sort_order."""
    if not role_groups:
        return []
    result = await db.execute(
        select(WeStatement)
        .where(
            WeStatement.is_active.is_(True),
            WeStatement.role_group.in_(role_groups),
        )
        .order_by(WeStatement.sort_order, WeStatement.id)
    )
    return list(result.scalars().all())


async def _get_last_statement_id(
    db: AsyncSession, recipient_id: int
) -> int | None:
    """Return the statement_id used in the most recent assignment for this recipient."""
    result = await db.execute(
        select(DailyAssignment.statement_id)
        .where(DailyAssignment.recipient_id == recipient_id)
        .order_by(DailyAssignment.assignment_date.desc(), DailyAssignment.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def _pick_next_statement(
    db: AsyncSession,
    recipient_id: int,
    eligible_statements: list[WeStatement],
) -> WeStatement:
    """
    Pick the next statement in rotation for this recipient.

    Cycles through all eligible statements before repeating.  If the recipient
    has no prior assignments the first statement in the list is used.
    """
    if not eligible_statements:
        raise ValueError(f"No eligible statements found for recipient {recipient_id}")

    last_id = await _get_last_statement_id(db, recipient_id)

    if last_id is None:
        return eligible_statements[0]

    # Find position of the last used statement in the eligible list
    ids = [s.id for s in eligible_statements]
    try:
        last_idx = ids.index(last_id)
    except ValueError:
        # The previous statement was retired or moved out of role group
        return eligible_statements[0]

    next_idx = (last_idx + 1) % len(eligible_statements)
    return eligible_statements[next_idx]


async def create_daily_assignments(
    db: AsyncSession,
    for_date: date | None = None,
) -> list[DailyAssignment]:
    """
    Create DailyAssignment records for all active recipients for a given date.

    If for_date is None, today in the configured timezone is used.

    Recipients that already have an assignment for the date are skipped
    (idempotent).
    """
    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    if for_date is None:
        for_date = datetime.now(tz).date()

    # Load all active recipients
    result = await db.execute(
        select(Recipient).where(Recipient.is_active.is_(True))
    )
    recipients: list[Recipient] = list(result.scalars().all())

    # Load existing assignments for this date to support idempotency
    existing_result = await db.execute(
        select(DailyAssignment.recipient_id).where(
            DailyAssignment.assignment_date == for_date
        )
    )
    already_assigned: set[int] = {row for row in existing_result.scalars().all()}

    new_assignments: list[DailyAssignment] = []

    for recipient in recipients:
        if recipient.role in EXCLUDED_ROLES:
            logger.debug("Skipping recipient %s (role %s)", recipient.email, recipient.role)
            continue

        if recipient.id in already_assigned:
            logger.debug(
                "Recipient %s already has assignment for %s, skipping",
                recipient.email,
                for_date,
            )
            continue

        role_groups = _role_group_filter(recipient.role)
        if not role_groups:
            logger.warning(
                "Recipient %s has unknown role %s, skipping",
                recipient.email,
                recipient.role,
            )
            continue

        eligible = await _get_eligible_statements(db, role_groups)
        if not eligible:
            logger.warning(
                "No eligible statements for recipient %s (role_groups=%s)",
                recipient.email,
                role_groups,
            )
            continue

        statement = await _pick_next_statement(db, recipient.id, eligible)

        assignment = DailyAssignment(
            recipient_id=recipient.id,
            statement_id=statement.id,
            assignment_date=for_date,
            token=uuid.uuid4(),
        )
        db.add(assignment)
        new_assignments.append(assignment)
        logger.info(
            "Created assignment for %s: statement %s (%s)",
            recipient.email,
            statement.id,
            for_date,
        )

    await db.flush()
    return new_assignments
