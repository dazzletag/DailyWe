"""
Tests for the assignment scheduling and statement rotation logic.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.assignment import DailyAssignment
from app.models.recipient import Recipient
from app.models.statement import WeStatement
from app.services.assignment import (
    _get_eligible_statements,
    _pick_next_statement,
    create_daily_assignments,
)

pytestmark = pytest.mark.asyncio

settings = get_settings()
TZ = pytz.timezone(settings.SCHEDULER_TIMEZONE)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _make_statement(
    db: AsyncSession,
    key_question: str = "Safe",
    role_group: str = "manager",
    sort_order: int = 1,
    is_active: bool = True,
) -> WeStatement:
    stmt = WeStatement(
        key_question=key_question,
        role_group=role_group,
        statement_text=f"Test statement {uuid.uuid4().hex[:6]}",
        evidence_types=["Doc A"],
        sort_order=sort_order,
        is_active=is_active,
    )
    db.add(stmt)
    await db.flush()
    return stmt


async def _make_recipient(
    db: AsyncSession,
    role: str = "HomeManager",
    home: str = "Test Home",
) -> Recipient:
    r = Recipient(
        full_name=f"Test {role} {uuid.uuid4().hex[:4]}",
        email=f"test.{uuid.uuid4().hex[:6]}@example.com",
        role=role,
        home_name=home,
        is_active=True,
    )
    db.add(r)
    await db.flush()
    return r


async def _make_assignment(
    db: AsyncSession,
    recipient: Recipient,
    statement: WeStatement,
    days_ago: int = 1,
) -> DailyAssignment:
    today = datetime.now(TZ).date()
    assign_date = today - timedelta(days=days_ago)
    a = DailyAssignment(
        recipient_id=recipient.id,
        statement_id=statement.id,
        assignment_date=assign_date,
        token=uuid.uuid4(),
    )
    db.add(a)
    await db.flush()
    return a


# ── Tests: Manager role group ─────────────────────────────────────────────────

class TestManagerStatementRotation:
    async def test_manager_gets_manager_and_all_statements(
        self, db_session: AsyncSession
    ):
        """Manager role should receive 'manager' and 'all' group statements."""
        s_manager = await _make_statement(db_session, role_group="manager")
        s_all = await _make_statement(db_session, role_group="all")
        s_deputy = await _make_statement(db_session, role_group="deputy")

        eligible = await _get_eligible_statements(db_session, ["manager", "all"])
        eligible_ids = {s.id for s in eligible}

        assert s_manager.id in eligible_ids
        assert s_all.id in eligible_ids
        assert s_deputy.id not in eligible_ids

    async def test_inactive_statements_excluded(self, db_session: AsyncSession):
        """Inactive statements should not appear in the eligible list."""
        active = await _make_statement(db_session, role_group="manager", is_active=True)
        inactive = await _make_statement(db_session, role_group="manager", is_active=False)

        eligible = await _get_eligible_statements(db_session, ["manager", "all"])
        eligible_ids = {s.id for s in eligible}

        assert active.id in eligible_ids
        assert inactive.id not in eligible_ids

    async def test_first_assignment_uses_first_statement(self, db_session: AsyncSession):
        """A recipient with no prior assignments should receive the first statement."""
        s1 = await _make_statement(db_session, role_group="manager", sort_order=10)
        s2 = await _make_statement(db_session, role_group="manager", sort_order=20)
        recipient = await _make_recipient(db_session, role="HomeManager")

        eligible = await _get_eligible_statements(db_session, ["manager", "all"])
        # Filter to just s1 and s2 for this test
        test_eligible = [s for s in eligible if s.id in {s1.id, s2.id}]
        test_eligible.sort(key=lambda x: (x.sort_order, x.id))

        picked = await _pick_next_statement(db_session, recipient.id, test_eligible)
        assert picked.id == test_eligible[0].id

    async def test_rotation_advances_after_each_assignment(self, db_session: AsyncSession):
        """
        After using statement A, the next pick should be statement B.
        """
        s1 = await _make_statement(db_session, role_group="manager", sort_order=100)
        s2 = await _make_statement(db_session, role_group="manager", sort_order=200)
        recipient = await _make_recipient(db_session, role="HomeManager")

        test_eligible = [s1, s2]

        # Simulate s1 was used yesterday
        await _make_assignment(db_session, recipient, s1, days_ago=1)

        picked = await _pick_next_statement(db_session, recipient.id, test_eligible)
        assert picked.id == s2.id

    async def test_rotation_cycles_back_after_all_used(self, db_session: AsyncSession):
        """After using the last statement, rotation wraps back to the first."""
        s1 = await _make_statement(db_session, role_group="manager", sort_order=300)
        s2 = await _make_statement(db_session, role_group="manager", sort_order=400)
        recipient = await _make_recipient(db_session, role="HomeManager")

        test_eligible = [s1, s2]

        # Simulate s2 was the most recently used
        await _make_assignment(db_session, recipient, s1, days_ago=2)
        await _make_assignment(db_session, recipient, s2, days_ago=1)

        picked = await _pick_next_statement(db_session, recipient.id, test_eligible)
        assert picked.id == s1.id


# ── Tests: Deputy role group ──────────────────────────────────────────────────

class TestDeputyStatementRotation:
    async def test_deputy_gets_deputy_and_all_statements(self, db_session: AsyncSession):
        """Deputy role should receive 'deputy' and 'all' group statements."""
        s_deputy = await _make_statement(db_session, role_group="deputy")
        s_manager = await _make_statement(db_session, role_group="manager")

        eligible = await _get_eligible_statements(db_session, ["deputy", "all"])
        eligible_ids = {s.id for s in eligible}

        assert s_deputy.id in eligible_ids
        assert s_manager.id not in eligible_ids


# ── Tests: Idempotency ────────────────────────────────────────────────────────

class TestIdempotency:
    async def test_no_duplicate_assignments_same_day(self, db_session: AsyncSession):
        """Running create_daily_assignments twice on the same day should not double-up."""
        # Seed a statement and recipient with unique roles for isolation
        s = await _make_statement(db_session, role_group="manager", sort_order=999)
        r = await _make_recipient(db_session, role="HomeManager", home="Idempotency Home")

        today = datetime.now(TZ).date()

        await create_daily_assignments(db_session, for_date=today)
        await create_daily_assignments(db_session, for_date=today)

        result = await db_session.execute(
            select(DailyAssignment).where(
                DailyAssignment.recipient_id == r.id,
                DailyAssignment.assignment_date == today,
            )
        )
        assignments = result.scalars().all()
        assert len(assignments) == 1

    async def test_skip_if_email_already_sent(self, db_session: AsyncSession):
        """
        The scheduler should only send to assignments where email_sent_at is None.
        This test verifies the query filter behaviour.
        """
        s = await _make_statement(db_session, role_group="manager")
        r = await _make_recipient(db_session)

        today = datetime.now(TZ).date()

        # Create an assignment that's already been emailed
        sent_assignment = DailyAssignment(
            recipient_id=r.id,
            statement_id=s.id,
            assignment_date=today,
            token=uuid.uuid4(),
            email_sent_at=datetime.now(pytz.utc),
        )
        db_session.add(sent_assignment)
        await db_session.flush()

        # Query for pending assignments (email_sent_at is None)
        result = await db_session.execute(
            select(DailyAssignment).where(
                DailyAssignment.recipient_id == r.id,
                DailyAssignment.assignment_date == today,
                DailyAssignment.email_sent_at.is_(None),
            )
        )
        pending = result.scalars().all()
        # The sent assignment should NOT appear
        assert sent_assignment.id not in [a.id for a in pending]
