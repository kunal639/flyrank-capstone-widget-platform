# app/schemas/__init__.py
from app.schemas.widget import (
    WidgetCreate,
    WidgetListResponse,
    WidgetResponse,
    WidgetSummary,
    WidgetUpdate,
)

__all__ = [
    "WidgetCreate",
    "WidgetUpdate",
    "WidgetResponse",
    "WidgetSummary",
    "WidgetListResponse",
]