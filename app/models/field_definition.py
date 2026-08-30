# app/models/field_definition.py
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.widget_field import WidgetField

class FieldDefinition(Base):
    __tablename__ = "field_definition"

    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    field_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # Relationships
    widget_fields: Mapped[list["WidgetField"]] = relationship(
        "WidgetField",
        back_populates="field_definition",
        cascade="all, delete-orphan"
    )