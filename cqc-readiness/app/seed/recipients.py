"""
Seed script: inserts placeholder recipients into the database.

Run with:
    python -m app.seed.recipients
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_engine, get_session_factory
from app.models.recipient import Recipient

logger = logging.getLogger(__name__)

RECIPIENTS_DATA = [
    # ── Home Managers ─────────────────────────────────────────────────────────
    {
        "full_name": "Sarah Mitchell",
        "email": "sarah.mitchell@bristolcarehomes.co.uk",
        "role": "HomeManager",
        "home_name": "Sunrise House",
    },
    {
        "full_name": "David Okafor",
        "email": "david.okafor@bristolcarehomes.co.uk",
        "role": "HomeManager",
        "home_name": "Meadowbrook Lodge",
    },
    # ── Deputy Managers ───────────────────────────────────────────────────────
    {
        "full_name": "Priya Sharma",
        "email": "priya.sharma@bristolcarehomes.co.uk",
        "role": "DeputyManager",
        "home_name": "Sunrise House",
    },
    {
        "full_name": "James Whitfield",
        "email": "james.whitfield@bristolcarehomes.co.uk",
        "role": "DeputyManager",
        "home_name": "Meadowbrook Lodge",
    },
    # ── Operations Manager ────────────────────────────────────────────────────
    {
        "full_name": "Karen Brennan",
        "email": "karen.brennan@bristolcarehomes.co.uk",
        "role": "OperationsManager",
        "home_name": None,
    },
    # ── Care Quality Manager ──────────────────────────────────────────────────
    {
        "full_name": "Claire Ashford",
        "email": "claire.ashford@bristolcarehomes.co.uk",
        "role": "CareQualityManager",
        "home_name": None,
    },
]


async def seed_recipients(session: AsyncSession) -> None:
    """Insert placeholder recipients. Skips any email addresses that already exist."""
    from sqlalchemy import select

    existing_result = await session.execute(select(Recipient.email))
    existing_emails = {row for row in existing_result.scalars().all()}

    inserted = 0
    skipped = 0

    for data in RECIPIENTS_DATA:
        if data["email"] in existing_emails:
            skipped += 1
            continue
        recipient = Recipient(**data)
        session.add(recipient)
        inserted += 1

    await session.commit()
    logger.info("Recipients seeded: %d inserted, %d skipped", inserted, skipped)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = get_engine()
    factory = get_session_factory(engine)

    async with factory() as session:
        await seed_recipients(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
