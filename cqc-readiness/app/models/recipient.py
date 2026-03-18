from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Recipient(Base):
    """A person who receives daily CQC readiness check emails."""

    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)

    # Role: HomeManager, DeputyManager, OperationsManager, CareQualityManager
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # The care home this person is associated with (null for ops/cqm roles)
    home_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

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
        "DailyAssignment", back_populates="recipient"
    )

    def __repr__(self) -> str:
        return (
            f"<Recipient id={self.id} email={self.email!r} role={self.role!r} "
            f"home={self.home_name!r}>"
        )
