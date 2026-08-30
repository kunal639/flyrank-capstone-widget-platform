# app/models/submission_field_value.py
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.submission import Submission
    from app.models.widget_field import WidgetField

class SubmissionFieldValue(Base):
    __tablename__ = "submission_field_value"
    __table_args__ = (
        UniqueConstraint("submission_id", "widget_field_id", name="uq_submission_field_value_sub_wf"),
    )

    submission_field_value_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submission.submission_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    widget_field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("widget_field.widget_field_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    value_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    value_number: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    value_boolean: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )

    # Relationships
    submission: Mapped["Submission"] = relationship(
        "Submission",
        back_populates="field_values"
    )
    widget_field: Mapped["WidgetField"] = relationship(
        "WidgetField",
        back_populates="submission_values"
    )