# app/repositories/__init__.py
from app.repositories.tenant import TenantRepository
from app.repositories.widget import WidgetRepository
from app.repositories.submission import SubmissionRepository

__all__ = ["TenantRepository", "WidgetRepository", "SubmissionRepository"]