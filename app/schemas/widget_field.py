# app/schemas/widget_field.py
import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class WidgetFieldConfigItem(BaseModel):
    field_id: uuid.UUID
    display_order: int = Field(default=0, ge=0)
    required: bool = False


class WidgetFieldConfigureRequest(BaseModel):
    fields: list[WidgetFieldConfigItem]


class WidgetFieldItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    widget_field_id: uuid.UUID
    field_id: uuid.UUID
    display_order: int
    required: bool


class WidgetFieldListResponse(BaseModel):
    widget_id: uuid.UUID
    fields: list[WidgetFieldItemResponse]


class WidgetFieldSingleAddRequest(BaseModel):
    field_id: uuid.UUID
    display_order: int = Field(default=0, ge=0)
    required: bool = False


class WidgetFieldUpdateRequest(BaseModel):
    display_order: Optional[int] = Field(None, ge=0)
    required: Optional[bool] = None