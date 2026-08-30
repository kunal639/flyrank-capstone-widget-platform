# app/models/submission.py
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.widget import Widget
    from app.models.submission_field_value import SubmissionFieldValue
    from app.models.notification_outbox import NotificationOutbox

class Submission(Base):
    __tablename__ = "submission"
    __table_args__ = (
        UniqueConstraint("widget_id", "idempotency_key", name="uq_submission_widget_id_idempotency_key"),
        Index("ix_submission_widget_id_created_at", "widget_id", "created_at"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    widget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("widget.widget_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    region: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    latitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    notification_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending"
    )
    notification_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    widget: Mapped["Widget"] = relationship(
        "Widget",
        back_populates="submissions"
    )
    field_values: Mapped[list["SubmissionFieldValue"]] = relationship(
        "SubmissionFieldValue",
        back_populates="submission",
        cascade="all, delete-orphan"
    )
    notification_outbox: Mapped[Optional["NotificationOutbox"]] = relationship(
        "NotificationOutbox",
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan"
    )