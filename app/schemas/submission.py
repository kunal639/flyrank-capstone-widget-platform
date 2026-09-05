import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SubmissionCreate(BaseModel):
    widget_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=255)
    fields: dict[str, Any] = Field(default_factory=dict)
    honeypot: str | None = Field(default=None, max_length=255)


class SubmissionResponse(BaseModel):
    submission_id: uuid.UUID


class SubmissionFieldValueResponse(BaseModel):
    field_id: uuid.UUID
    name: str
    type: str
    value: str | float | bool | None


class DashboardSubmissionResponse(BaseModel):
    submission_id: uuid.UUID
    widget_id: uuid.UUID
    created_at: datetime
    country: str | None
    city: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    notification_status: str
    notification_attempts: int
    fields: list[SubmissionFieldValueResponse]


class SubmissionListResponse(BaseModel):
    submissions: list[DashboardSubmissionResponse]
