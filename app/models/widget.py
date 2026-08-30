# app/models/widget.py
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.widget_type import WidgetType

class Widget(Base):
    __tablename__ = "widget"

    widget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.tenant_id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    widget_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("widget_type.widget_type_id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list
    )

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship(
        "Tenant",
        back_populates="widgets"
    )
    widget_type: Mapped["WidgetType"] = relationship(
        "WidgetType",
        back_populates="widgets"
    )