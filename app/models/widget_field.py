# app/models/widget_field.py
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.widget import Widget
    from app.models.field_definition import FieldDefinition

class WidgetField(Base):
    __tablename__ = "widget_field"
    __table_args__ = (
        UniqueConstraint("widget_id", "field_id", name="uq_widget_field_widget_id_field_id"),
    )

    # Using composite primary key
    widget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("widget.widget_id", ondelete="CASCADE"),
        primary_key=True
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("field_definition.field_id", ondelete="CASCADE"),
        primary_key=True
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    # Relationships
    widget: Mapped["Widget"] = relationship(
        "Widget",
        back_populates="widget_fields"
    )
    field_definition: Mapped["FieldDefinition"] = relationship(
        "FieldDefinition",
        back_populates="widget_fields"
    )