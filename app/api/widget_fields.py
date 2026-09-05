# app/api/widget_fields.py
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_tenant
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.field_definition import FieldDefinition
from app.repositories.widget import WidgetRepository
from app.repositories.widget_field import WidgetFieldRepository
from app.schemas.widget_field import (
    WidgetFieldConfigureRequest,
    WidgetFieldItemResponse,
    WidgetFieldListResponse,
    WidgetFieldSingleAddRequest,
    WidgetFieldUpdateRequest,
)

router = APIRouter(prefix="/widgets/{widget_id}/fields", tags=["Widget Fields"])


def _get_tenant_widget(
    widget_id: uuid.UUID,
    current_tenant: Tenant,
    db: Session,
):
    widget_repo = WidgetRepository(db)
    widget = widget_repo.get_by_id_and_tenant(widget_id, current_tenant.tenant_id)
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )
    return widget


def _to_response_item(wf) -> WidgetFieldItemResponse:
    return WidgetFieldItemResponse(
        widget_field_id=wf.widget_field_id,
        field_id=wf.field_id,
        field_name=wf.field_definition.field_name if wf.field_definition else "",
        field_type=wf.field_definition.field_type if wf.field_definition else "",
        display_order=wf.display_order,
        required=wf.required,
    )


@router.get("", response_model=WidgetFieldListResponse, status_code=status.HTTP_200_OK)
def list_widget_fields(
    widget_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_tenant_widget(widget_id, current_tenant, db)
    wf_repo = WidgetFieldRepository(db)
    fields = wf_repo.list_for_widget(widget_id)
    return {
        "widget_id": widget_id,
        "fields": [_to_response_item(wf) for wf in fields],
    }


@router.put("", response_model=WidgetFieldListResponse, status_code=status.HTTP_200_OK)
def configure_widget_fields(
    widget_id: uuid.UUID,
    payload: WidgetFieldConfigureRequest,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_tenant_widget(widget_id, current_tenant, db)

    # 1. Reject duplicate field_id in request with 400
    field_ids = [item.field_id for item in payload.fields]
    if len(field_ids) != len(set(field_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate fields in configuration are not allowed",
        )

    # 2. Reject duplicate display_order in request with 400
    orders = [item.display_order for item in payload.fields]
    if len(orders) != len(set(orders)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate display_order values are not allowed",
        )

    # 3. Reject nonexistent field_ids with 400
    if field_ids:
        existing_fields = (
            db.query(FieldDefinition.field_id)
            .filter(FieldDefinition.field_id.in_(field_ids))
            .all()
        )
        existing_set = {f[0] for f in existing_fields}
        missing = set(field_ids) - existing_set
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more field definitions do not exist",
            )

    wf_repo = WidgetFieldRepository(db)
    configs = [item.model_dump() for item in payload.fields]
    updated_fields = wf_repo.set_fields_for_widget(widget_id, configs)
    db.commit()

    return {
        "widget_id": widget_id,
        "fields": [
            {
                "widget_field_id": wf.widget_field_id,
                "field_id": wf.field_id,
                "display_order": wf.display_order,
                "required": wf.required,
            }
            for wf in updated_fields
        ],
    }


@router.post("", response_model=WidgetFieldItemResponse, status_code=status.HTTP_201_CREATED)
def add_widget_field(
    widget_id: uuid.UUID,
    payload: WidgetFieldSingleAddRequest,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_tenant_widget(widget_id, current_tenant, db)

    # Verify field exists
    fd = db.query(FieldDefinition).filter(FieldDefinition.field_id == payload.field_id).first()
    if not fd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"FieldDefinition with ID '{payload.field_id}' does not exist",
        )

    wf_repo = WidgetFieldRepository(db)
    existing = wf_repo.get_by_widget_and_field(widget_id, payload.field_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This field is already attached to this widget",
        )

    wf = wf_repo.add_field(
        widget_id=widget_id,
        field_id=payload.field_id,
        display_order=payload.display_order,
        required=payload.required,
    )
    db.commit()
    db.refresh(wf)
    return _to_response_item(wf)


@router.patch("/{field_id}", response_model=WidgetFieldItemResponse, status_code=status.HTTP_200_OK)
def update_widget_field(
    widget_id: uuid.UUID,
    field_id: uuid.UUID,
    payload: WidgetFieldUpdateRequest,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_tenant_widget(widget_id, current_tenant, db)

    wf_repo = WidgetFieldRepository(db)
    wf = wf_repo.get_by_widget_and_field(widget_id, field_id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget field not found",
        )

    updated_wf = wf_repo.update_field(
        widget_field=wf,
        display_order=payload.display_order,
        required=payload.required,
    )
    db.commit()
    db.refresh(updated_wf)
    return _to_response_item(updated_wf)


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_widget_field(
    widget_id: uuid.UUID,
    field_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_tenant_widget(widget_id, current_tenant, db)

    wf_repo = WidgetFieldRepository(db)
    wf = wf_repo.get_by_widget_and_field(widget_id, field_id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget field not found",
        )

    wf_repo.delete(wf)
    db.commit()
    return None