from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Date, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyAssignment(Base):
    """Links a recipient to a We Statement for a given day, with a unique token."""

    __tablename__ = "daily_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    recipient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recipients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("we_statements.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Date of the assignment (one per recipient per day)
    assignment_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, index=True
    )

    # Unique token embedded in email links
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=uuid.uuid4,
        index=True,
    )

    # Timestamp when the daily email was dispatched
    email_sent_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamp when all 3 questions have been answered
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    recipient: Mapped["Recipient"] = relationship("Recipient", back_populates="assignments")
    statement: Mapped["WeStatement"] = relationship("WeStatement", back_populates="assignments")
    responses: Mapped[list["Response"]] = relationship(
        "Response", back_populates="assignment", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["CQMAlert"]] = relationship(
        "CQMAlert", back_populates="assignment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<DailyAssignment id={self.id} recipient_id={self.recipient_id} "
            f"date={self.assignment_date} token={self.token}>"
        )
