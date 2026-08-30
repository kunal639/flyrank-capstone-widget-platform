# app/models/widget_type.py
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.widget import Widget

class WidgetType(Base):
    __tablename__ = "widget_type"

    widget_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True
    )

    # 1:N relationship
    widgets: Mapped[list["Widget"]] = relationship(
        "Widget",
        back_populates="widget_type"
    )