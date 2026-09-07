import math
import os
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.geo import GeoEnricher, IpApiProvider, IpApiCoProvider
from app.models.field_definition import FieldDefinition
from app.models.submission import Submission
from app.models.submission_field_value import SubmissionFieldValue
from app.models.tenant import Tenant
from app.models.widget import Widget
from app.models.widget_field import WidgetField
from app.auth.dependencies import get_current_tenant
from app.repositories.submission import SubmissionRepository
from app.rate_limit import SlidingWindowRateLimiter
from app.schemas.submission import (
    DashboardSubmissionResponse,
    SubmissionCreate,
    SubmissionListResponse,
    SubmissionResponse,
)


router = APIRouter(prefix="/submissions", tags=["Submissions"])

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TEXT_FIELD_TYPES = {"text", "email", "tel"}
submission_rate_limiter = SlidingWindowRateLimiter(
    max_requests=int(os.getenv("PUBLIC_SUBMISSION_RATE_LIMIT", "10")),
    window_seconds=int(os.getenv("PUBLIC_SUBMISSION_RATE_WINDOW_SECONDS", "60")),
)
geo_enricher = GeoEnricher((IpApiProvider(), IpApiCoProvider()))


def _is_missing_required_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _validated_storage_value(field_type: str, value: Any) -> dict[str, Any]:
    if field_type in TEXT_FIELD_TYPES:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        if field_type == "email" and not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("must be a valid email address")
        return {"value_text": value}

    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number")
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return {"value_number": float(value)}

    if field_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("must be a boolean")
        return {"value_boolean": value}

    raise ValueError(f"uses unsupported field type '{field_type}'")


def _add_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Vary"] = "Origin"


def _dashboard_submission_response(submission: Submission) -> dict[str, Any]:
    fields = []
    for field_value in submission.field_values:
        field_definition = field_value.widget_field.field_definition
        value = next(
            (
                item
                for item in (
                    field_value.value_text,
                    field_value.value_number,
                    field_value.value_boolean,
                )
                if item is not None
            ),
            None,
        )
        fields.append(
            {
                "field_id": field_definition.field_id,
                "name": field_definition.field_name,
                "type": field_definition.field_type,
                "value": value,
            }
        )
    return {
        "submission_id": submission.submission_id,
        "widget_id": submission.widget_id,
        "created_at": submission.created_at,
        "country": submission.country,
        "city": submission.city,
        "region": submission.region,
        "latitude": submission.latitude,
        "longitude": submission.longitude,
        "notification_status": submission.notification_status,
        "notification_attempts": submission.notification_attempts,
        "fields": fields,
    }


@router.options("", status_code=status.HTTP_204_NO_CONTENT)
def submission_preflight(request: Request, response: Response):
    """Respond to browser preflight; authorization happens on POST."""
    response.status_code = status.HTTP_204_NO_CONTENT
    origin = request.headers.get("Origin")
    if origin:
        _add_cors_headers(response, origin)
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@router.post("", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
def create_submission(
    payload: SubmissionCreate,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    widget = db.query(Widget).filter(Widget.widget_id == payload.widget_id).first()
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )

    origin = request.headers.get("Origin")
    if widget.allowed_origins:
        if not origin or origin not in widget.allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origin is not allowed for this widget",
            )
    if origin:
        _add_cors_headers(response, origin)

    client_ip = request.client.host if request.client else "unknown"
    if not submission_rate_limiter.allow((str(widget.widget_id), client_ip)):
        limited_response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests"}},
        )
        if origin:
            _add_cors_headers(limited_response, origin)
        return limited_response

    if payload.honeypot:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid submission",
        )

    geo_data = geo_enricher.enrich(client_ip)

    configured_fields = (
        db.query(WidgetField, FieldDefinition)
        .join(
            FieldDefinition,
            WidgetField.field_id == FieldDefinition.field_id,
        )
        .filter(WidgetField.widget_id == widget.widget_id)
        .all()
    )
    fields_by_name = {
        field_definition.field_name: (widget_field, field_definition)
        for widget_field, field_definition in configured_fields
    }

    unexpected_fields = set(payload.fields) - set(fields_by_name)
    if unexpected_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"fields": "Contains fields not configured for this widget"},
        )

    missing_required_fields = [
        field_definition.field_name
        for widget_field, field_definition in configured_fields
        if widget_field.required
        and (
            field_definition.field_name not in payload.fields
            or _is_missing_required_value(payload.fields[field_definition.field_name])
        )
    ]
    if missing_required_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"fields": {name: "Field is required" for name in missing_required_fields}},
        )

    field_values = []
    validation_errors = {}
    for field_name, value in payload.fields.items():
        widget_field, field_definition = fields_by_name[field_name]
        try:
            stored_value = _validated_storage_value(field_definition.field_type, value)
        except ValueError as error:
            validation_errors[field_name] = str(error)
            continue
        field_values.append(
            {"widget_field_id": widget_field.widget_field_id, **stored_value}
        )

    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"fields": validation_errors},
        )

    repository = SubmissionRepository(db)
    try:
        submission = repository.create_submission_with_values(
            widget_id=widget.widget_id,
            idempotency_key=payload.idempotency_key,
            field_values=field_values,
            geo_data=geo_data,
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "uq_submission_widget_id_idempotency_key" in str(error.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate idempotency key for this widget",
            ) from error
    except IntegrityError as error:
        db.rollback()
        if "uq_submission_widget_id_idempotency_key" in str(error.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate idempotency key for this widget",
            ) from error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while saving the submission",
        ) from None

    return {"submission_id": submission.submission_id}


def _tenant_submission_query(db: Session, tenant_id):
    return (
        db.query(Submission)
        .join(Widget, Submission.widget_id == Widget.widget_id)
        .options(
            joinedload(Submission.field_values)
            .joinedload(SubmissionFieldValue.widget_field)
            .joinedload(WidgetField.field_definition)
        )
        .filter(Widget.tenant_id == tenant_id)
    )


@router.get("", response_model=SubmissionListResponse)
def list_submissions(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    submissions = (
        _tenant_submission_query(db, current_tenant.tenant_id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    return {"submissions": [_dashboard_submission_response(item) for item in submissions]}


@router.get("/{submission_id}", response_model=DashboardSubmissionResponse)
def get_submission(
    submission_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
):
    submission = (
        _tenant_submission_query(db, current_tenant.tenant_id)
        .filter(Submission.submission_id == submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    return _dashboard_submission_response(submission)
