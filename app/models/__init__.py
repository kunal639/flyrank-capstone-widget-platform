# app/models/__init__.py
from app.models.tenant import Tenant
from app.models.widget_type import WidgetType

__all__ = ["Tenant", "WidgetType"]