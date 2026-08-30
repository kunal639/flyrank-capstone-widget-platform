# app/models/tenant.py
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.widget import Widget

class Tenant(Base):
    __tablename__ = "tenant"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    customer_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    customer_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )

    # 1:N relationship
    widgets: Mapped[list["Widget"]] = relationship(
        "Widget",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )