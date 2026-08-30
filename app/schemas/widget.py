# app/schemas/widget.py
import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class WidgetCreate(BaseModel):
    widget_type_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    allowed_origins: list[str] = Field(default_factory=list)

class WidgetUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    allowed_origins: Optional[list[str]] = None

class WidgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    widget_id: uuid.UUID
    widget_type_id: uuid.UUID
    title: str
    allowed_origins: list[str]

class WidgetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    widget_id: uuid.UUID
    widget_type_id: uuid.UUID
    title: str

class WidgetListResponse(BaseModel):
    widgets: list[WidgetSummary]