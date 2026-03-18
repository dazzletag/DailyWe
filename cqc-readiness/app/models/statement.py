from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WeStatement(Base):
    """A 'We Statement' from the CQC key question framework."""

    __tablename__ = "we_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # CQC key question: Safe, Effective, Caring, Responsive, Well-led
    key_question: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Role group this statement targets: 'manager', 'deputy', or 'all'
    role_group: Mapped[str] = mapped_column(
        String(20), nullable=False, default="all", index=True
    )

    # The statement text itself
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)

    # JSON array of evidence type strings, e.g. ["MAR charts", "Medication audits"]
    evidence_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Narrative guidance for staff
    guidance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Practical inspection tips
    inspection_tips: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sort order within the key question group
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    assignments: Mapped[list["DailyAssignment"]] = relationship(
        "DailyAssignment", back_populates="statement"
    )

    def __repr__(self) -> str:
        return (
            f"<WeStatement id={self.id} key_question={self.key_question!r} "
            f"role_group={self.role_group!r}>"
        )
