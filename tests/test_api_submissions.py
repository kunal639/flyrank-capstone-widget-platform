import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.field_definition import FieldDefinition
from app.models.notification_outbox import NotificationOutbox
from app.models.submission import Submission
from app.models.submission_field_value import SubmissionFieldValue
from app.models.widget import Widget
from app.models.widget_field import WidgetField
from app.models.widget_type import WidgetType
from app.rate_limit import SlidingWindowRateLimiter


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def configured_widget(db):
    widget_type = WidgetType(name=f"submission_api_{uuid.uuid4().hex[:8]}")
    widget = Widget(title="Contact Us", widget_type=widget_type, allowed_origins=[])
    email_field = FieldDefinition(field_name="email", field_type="email")
    message_field = FieldDefinition(field_name="message", field_type="text")
    score_field = FieldDefinition(field_name="score", field_type="number")
    subscribed_field = FieldDefinition(field_name="subscribed", field_type="boolean")
    db.add_all(
        [widget, email_field, message_field, score_field, subscribed_field]
    )
    db.commit()
    db.add_all(
        [
            WidgetField(
                widget_id=widget.widget_id,
                field_id=email_field.field_id,
                display_order=0,
                required=True,
            ),
            WidgetField(
                widget_id=widget.widget_id,
                field_id=message_field.field_id,
                display_order=1,
                required=True,
            ),
            WidgetField(
                widget_id=widget.widget_id,
                field_id=score_field.field_id,
                display_order=2,
                required=False,
            ),
            WidgetField(
                widget_id=widget.widget_id,
                field_id=subscribed_field.field_id,
                display_order=3,
                required=False,
            ),
        ]
    )
    db.commit()
    return widget


def test_create_submission_persists_values_and_outbox(client, db, configured_widget):
    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": "submission-1",
            "fields": {
                "email": "visitor@example.com",
                "message": "Hello",
                "score": 8.5,
                "subscribed": True,
            },
        },
    )

    assert response.status_code == 201
    submission_id = response.json()["submission_id"]
    submission = db.get(Submission, uuid.UUID(submission_id))
    assert submission is not None
    assert submission.widget_id == configured_widget.widget_id
    assert submission.notification_status == "pending"
    assert db.query(SubmissionFieldValue).filter_by(submission_id=submission.submission_id).count() == 4
    assert db.query(NotificationOutbox).filter_by(submission_id=submission.submission_id).count() == 1


@pytest.mark.parametrize(
    ("fields", "expected_field"),
    [
        ({"email": "visitor@example.com"}, "message"),
        (
            {"email": "not-an-email", "message": "Hello"},
            "email",
        ),
        (
            {"email": "visitor@example.com", "message": "Hello", "score": "8"},
            "score",
        ),
        (
            {"email": "visitor@example.com", "message": "Hello", "unknown": "x"},
            None,
        ),
    ],
)
def test_create_submission_rejects_invalid_field_data(
    client, db, configured_widget, fields, expected_field
):
    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": f"invalid-{uuid.uuid4()}",
            "fields": fields,
        },
    )

    assert response.status_code == 422
    field_errors = response.json()["detail"]["fields"]
    if expected_field:
        assert expected_field in field_errors
    else:
        assert field_errors == "Contains fields not configured for this widget"
    assert db.query(Submission).filter_by(widget_id=configured_widget.widget_id).count() == 0


def test_create_submission_uses_database_idempotency_constraint(
    client, db, configured_widget
):
    payload = {
        "widget_id": str(configured_widget.widget_id),
        "idempotency_key": "same-key",
        "fields": {"email": "visitor@example.com", "message": "Hello"},
    }

    first = client.post("/submissions", json=payload)
    duplicate = client.post("/submissions", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Duplicate idempotency key for this widget"
    assert db.query(Submission).filter_by(widget_id=configured_widget.widget_id).count() == 1


def test_create_submission_returns_404_for_unknown_widget(client):
    response = client.post(
        "/submissions",
        json={
            "widget_id": str(uuid.uuid4()),
            "idempotency_key": "unknown-widget",
            "fields": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Widget not found"


def test_create_submission_accepts_allowed_origin(client, db, configured_widget):
    configured_widget.allowed_origins = ["https://allowed.example"]
    db.commit()

    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": "allowed-origin",
            "fields": {"email": "visitor@example.com", "message": "Hello"},
        },
        headers={"Origin": "https://allowed.example"},
    )

    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == "https://allowed.example"


def test_create_submission_rejects_disallowed_origin(client, db, configured_widget):
    configured_widget.allowed_origins = ["https://allowed.example"]
    db.commit()

    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": "disallowed-origin",
            "fields": {"email": "visitor@example.com", "message": "Hello"},
        },
        headers={"Origin": "https://blocked.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Origin is not allowed for this widget"
    assert "access-control-allow-origin" not in response.headers
    assert db.query(Submission).filter_by(widget_id=configured_widget.widget_id).count() == 0


@pytest.mark.parametrize("origin", ["https://first.example", "https://second.example"])
def test_create_submission_accepts_each_configured_origin(
    client, db, configured_widget, origin
):
    configured_widget.allowed_origins = [
        "https://first.example",
        "https://second.example",
    ]
    db.commit()

    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": f"multiple-{uuid.uuid4()}",
            "fields": {"email": "visitor@example.com", "message": "Hello"},
        },
        headers={"Origin": origin},
    )

    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == origin


def test_create_submission_allows_any_origin_when_origins_are_empty(
    client, configured_widget
):
    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": "unrestricted-origin",
            "fields": {"email": "visitor@example.com", "message": "Hello"},
        },
        headers={"Origin": "https://anywhere.example"},
    )

    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == "https://anywhere.example"


def test_submission_preflight_does_not_require_widget_id(client):
    response = client.options(
        "/submissions",
        headers={
            "Origin": "https://embed.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "https://embed.example"
    assert response.headers["access-control-allow-methods"] == "POST, OPTIONS"
    assert response.headers["access-control-allow-headers"] == "Content-Type"


def test_submission_contract_uses_widget_id_only_in_the_request_body(client):
    openapi = client.get("/openapi.json").json()
    post_operation = openapi["paths"]["/submissions"]["post"]
    schema_reference = post_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema_name = schema_reference.rsplit("/", maxsplit=1)[-1]
    request_schema = openapi["components"]["schemas"][schema_name]

    assert "parameters" not in post_operation
    assert "widget_id" in request_schema["properties"]


def test_create_submission_rate_limits_widget_and_client(
    client, configured_widget, monkeypatch
):
    from app.api import submissions

    current_time = [100.0]
    monkeypatch.setattr(
        submissions,
        "submission_rate_limiter",
        SlidingWindowRateLimiter(
            max_requests=2,
            window_seconds=60,
            clock=lambda: current_time[0],
        ),
    )
    payload = {
        "widget_id": str(configured_widget.widget_id),
        "fields": {"email": "visitor@example.com", "message": "Hello"},
    }

    assert client.post(
        "/submissions", json={**payload, "idempotency_key": "rate-1"}
    ).status_code == 201
    assert client.post(
        "/submissions", json={**payload, "idempotency_key": "rate-2"}
    ).status_code == 201
    limited = client.post(
        "/submissions", json={**payload, "idempotency_key": "rate-3"}
    )

    assert limited.status_code == 429
    assert limited.json() == {
        "error": {"code": "RATE_LIMITED", "message": "Too many requests"}
    }

    current_time[0] += 60
    assert client.post(
        "/submissions", json={**payload, "idempotency_key": "rate-4"}
    ).status_code == 201


def test_create_submission_rejects_oversized_request(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "MAX_PUBLIC_SUBMISSION_BYTES", 100)

    response = client.post(
        "/submissions",
        content="x" * 101,
        headers={"Content-Type": "application/json", "Content-Length": "0"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


def test_create_submission_rejects_non_empty_honeypot(client, db, configured_widget):
    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": "honeypot-submission",
            "honeypot": "https://spam.example",
            "fields": {"email": "visitor@example.com", "message": "Hello"},
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid submission"}
    assert db.query(Submission).filter_by(widget_id=configured_widget.widget_id).count() == 0


def test_create_submission_persists_best_effort_geo_data(
    client, db, configured_widget, monkeypatch
):
    from app.api import submissions

    class StaticEnricher:
        def enrich(self, ip_address):
            return {
                "country": "India",
                "city": "Patna",
                "region": "Bihar",
                "latitude": 25.5941,
                "longitude": 85.1376,
            }

    monkeypatch.setattr(submissions, "geo_enricher", StaticEnricher())
    response = client.post(
        "/submissions",
        json={
            "widget_id": str(configured_widget.widget_id),
            "idempotency_key": "geo-submission",
            "fields": {"email": "visitor@example.com", "message": "Hello"},
        },
    )

    assert response.status_code == 201
    submission = db.get(Submission, uuid.UUID(response.json()["submission_id"]))
    assert (submission.country, submission.city, submission.region) == (
        "India",
        "Patna",
        "Bihar",
    )
    assert (submission.latitude, submission.longitude) == (25.5941, 85.1376)
