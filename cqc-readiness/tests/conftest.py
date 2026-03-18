"""
Shared pytest fixtures for cqc-readiness tests.

Uses an in-memory SQLite database (via aiosqlite) so tests run without
a live PostgreSQL server.  UUID columns are stored as strings in SQLite.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.database as db_module
from app.database import Base, get_db
from app.main import create_app
from app.models.assignment import DailyAssignment
from app.models.recipient import Recipient
from app.models.response import Response
from app.models.statement import WeStatement

# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the whole test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create an in-memory async SQLite engine and build all tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def test_session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session that is rolled back after each test."""
    async with test_session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# FastAPI app + HTTP client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def app(test_engine, test_session_factory):
    """Build the FastAPI application wired to the test database."""
    # Patch module-level engine and session factory
    db_module.engine = test_engine
    db_module.SessionFactory = test_session_factory

    application = create_app()

    # Override get_db to use the test session factory
    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Return an async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Sample model fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sample_statement(db_session: AsyncSession) -> WeStatement:
    stmt = WeStatement(
        key_question="Safe",
        role_group="manager",
        statement_text="We manage medicines safely — people receive their medicines as prescribed.",
        evidence_types=["MAR charts", "Medication audits"],
        guidance_notes="Inspectors will scrutinise MAR charts for gaps.",
        inspection_tips="Be ready to walk through a MAR chart.",
        sort_order=1,
        is_active=True,
    )
    db_session.add(stmt)
    await db_session.flush()
    return stmt


@pytest_asyncio.fixture
async def sample_recipient(db_session: AsyncSession) -> Recipient:
    recipient = Recipient(
        full_name="Test Manager",
        email=f"test.manager.{uuid.uuid4().hex[:6]}@example.com",
        role="HomeManager",
        home_name="Sunrise House",
        is_active=True,
    )
    db_session.add(recipient)
    await db_session.flush()
    return recipient


@pytest_asyncio.fixture
async def sample_assignment(
    db_session: AsyncSession,
    sample_recipient: Recipient,
    sample_statement: WeStatement,
) -> DailyAssignment:
    from datetime import datetime
    import pytz
    from app.config import get_settings

    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    today = datetime.now(tz).date()

    assignment = DailyAssignment(
        recipient_id=sample_recipient.id,
        statement_id=sample_statement.id,
        assignment_date=today,
        token=uuid.uuid4(),
    )
    db_session.add(assignment)
    await db_session.flush()
    return assignment


@pytest_asyncio.fixture
async def past_assignment(
    db_session: AsyncSession,
    sample_recipient: Recipient,
    sample_statement: WeStatement,
) -> DailyAssignment:
    """Assignment from yesterday — token should be expired."""
    from datetime import timedelta
    import pytz
    from app.config import get_settings

    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    yesterday = (datetime.now(tz) - timedelta(days=1)).date()

    assignment = DailyAssignment(
        recipient_id=sample_recipient.id,
        statement_id=sample_statement.id,
        assignment_date=yesterday,
        token=uuid.uuid4(),
    )
    db_session.add(assignment)
    await db_session.flush()
    return assignment
