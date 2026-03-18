from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Valid answer values
VALID_ANSWERS = ("confident", "partly", "not_confident")
# Valid question numbers
VALID_QUESTION_NUMS = (1, 2, 3)

# Human-readable question text keyed by question number
QUESTION_TEXT = {
    1: "I understand what this statement means and what evidence is needed",
    2: "I feel confident that our current practice meets this standard",
    3: "I can confidently evidence this to a CQC inspector today",
}


class Response(Base):
    """Stores a single answer (one of 3 questions) for a daily assignment."""

    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("daily_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 1, 2, or 3
    question_num: Mapped[int] = mapped_column(Integer, nullable=False)

    # 'confident', 'partly', or 'not_confident'
    answer: Mapped[str] = mapped_column(String(20), nullable=False)

    # IP address of the respondent (optional, for audit trail)
    respondent_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    answered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    assignment: Mapped["DailyAssignment"] = relationship(
        "DailyAssignment", back_populates="responses"
    )

    def __repr__(self) -> str:
        return (
            f"<Response id={self.id} assignment_id={self.assignment_id} "
            f"q={self.question_num} answer={self.answer!r}>"
        )
