# app/api/__init__.py
from app.api.widgets import router as widgets_router

__all__ = ["widgets_router"]