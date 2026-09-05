# app/api/widgets.py
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_tenant
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.field_definition import FieldDefinition
from app.models.widget import Widget
from app.models.widget_field import WidgetField
from app.models.widget_type import WidgetType
from app.repositories.widget import WidgetRepository
from app.schemas.widget import (
    WidgetCreate,
    WidgetListResponse,
    PublicWidgetConfigResponse,
    WidgetResponse,
    WidgetUpdate,
)

router = APIRouter(prefix="/widgets", tags=["Widgets"])

@router.post("", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
def create_widget(
    payload: WidgetCreate,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    # Validate widget_type exists
    wt = db.query(WidgetType).filter(WidgetType.widget_type_id == payload.widget_type_id).first()
    if not wt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"WidgetType with ID '{payload.widget_type_id}' does not exist",
        )

    repo = WidgetRepository(db)
    widget = repo.create(
        title=payload.title,
        widget_type_id=payload.widget_type_id,
        tenant_id=current_tenant.tenant_id,
        allowed_origins=payload.allowed_origins,
    )
    db.commit()
    db.refresh(widget)
    return widget

@router.get("", response_model=WidgetListResponse, status_code=status.HTTP_200_OK)
def list_widgets(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    repo = WidgetRepository(db)
    widgets = repo.list_for_tenant(current_tenant.tenant_id)
    return {"widgets": widgets}

@router.get("/{widget_id}", response_model=WidgetResponse, status_code=status.HTTP_200_OK)
def get_widget(
    widget_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    repo = WidgetRepository(db)
    widget = repo.get_by_id_and_tenant(widget_id, current_tenant.tenant_id)
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )
    return widget

@router.patch("/{widget_id}", response_model=WidgetResponse, status_code=status.HTTP_200_OK)
def update_widget(
    widget_id: uuid.UUID,
    payload: WidgetUpdate,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    repo = WidgetRepository(db)
    widget = repo.get_by_id_and_tenant(widget_id, current_tenant.tenant_id)
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )

    widget = repo.update(
        widget=widget,
        title=payload.title,
        allowed_origins=payload.allowed_origins,
    )
    db.commit()
    db.refresh(widget)
    return widget

@router.delete("/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_widget(
    widget_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    repo = WidgetRepository(db)
    widget = repo.get_by_id_and_tenant(widget_id, current_tenant.tenant_id)
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )

    repo.delete(widget)
    db.commit()
    return None


@router.get("/{widget_id}/config", response_model=PublicWidgetConfigResponse)
def get_public_widget_config(
    widget_id: uuid.UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    widget = (
        db.query(Widget)
        .options(joinedload(Widget.widget_type))
        .filter(Widget.widget_id == widget_id)
        .first()
    )
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )

    configured_fields = (
        db.query(WidgetField, FieldDefinition)
        .join(
            FieldDefinition,
            WidgetField.field_id == FieldDefinition.field_id,
        )
        .filter(WidgetField.widget_id == widget.widget_id)
        .order_by(WidgetField.display_order)
        .all()
    )
    response.headers["Cache-Control"] = "public, max-age=60"
    return {
        "widget_id": widget.widget_id,
        "widget_type": widget.widget_type.name,
        "title": widget.title,
        "fields": [
            {
                "field_id": widget_field.field_id,
                "name": field_definition.field_name,
                "type": field_definition.field_type,
                "required": widget_field.required,
            }
            for widget_field, field_definition in configured_fields
        ],
    }
