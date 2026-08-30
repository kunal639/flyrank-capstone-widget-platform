# app/auth/__init__.py
from app.auth.dependencies import get_current_tenant

__all__ = ["get_current_tenant"]