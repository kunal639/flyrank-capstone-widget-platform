# app/repositories/widget.py
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from app.models.widget import Widget

class WidgetRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, widget_id: uuid.UUID) -> Optional[Widget]:
        return self.db.query(Widget).filter(Widget.widget_id == widget_id).first()

    def get_by_id_and_tenant(
        self, widget_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Optional[Widget]:
        return (
            self.db.query(Widget)
            .filter(Widget.widget_id == widget_id, Widget.tenant_id == tenant_id)
            .first()
        )

    def list_for_tenant(self, tenant_id: uuid.UUID) -> list[Widget]:
        return (
            self.db.query(Widget)
            .filter(Widget.tenant_id == tenant_id)
            .all()
        )

    def create(
        self,
        title: str,
        widget_type_id: uuid.UUID,
        tenant_id: Optional[uuid.UUID] = None,
        allowed_origins: Optional[list[str]] = None,
    ) -> Widget:
        widget = Widget(
            title=title,
            widget_type_id=widget_type_id,
            tenant_id=tenant_id,
            allowed_origins=allowed_origins if allowed_origins is not None else [],
        )
        self.db.add(widget)
        self.db.flush()
        return widget

    def update(
        self,
        widget: Widget,
        title: Optional[str] = None,
        allowed_origins: Optional[list[str]] = None,
    ) -> Widget:
        if title is not None:
            widget.title = title
        if allowed_origins is not None:
            widget.allowed_origins = allowed_origins
        self.db.flush()
        return widget

    def delete(self, widget: Widget) -> None:
        self.db.delete(widget)
        self.db.flush()