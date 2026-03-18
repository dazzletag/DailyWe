from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CQMAlert(Base):
    """An alert raised when a recipient responds with low confidence."""

    __tablename__ = "cqm_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("daily_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Denormalised fields for quick querying without joins
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    home_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_question: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Summarise which answers triggered the alert, e.g. "q2:partly, q3:not_confident"
    trigger_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    assignment: Mapped["DailyAssignment"] = relationship(
        "DailyAssignment", back_populates="alerts"
    )

    def __repr__(self) -> str:
        return (
            f"<CQMAlert id={self.id} home={self.home_name!r} "
            f"resolved={self.is_resolved}>"
        )
