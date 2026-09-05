import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.field_definition import FieldDefinition
from app.models.submission import Submission
from app.models.submission_field_value import SubmissionFieldValue
from app.models.tenant import Tenant
from app.models.widget import Widget
from app.models.widget_field import WidgetField
from app.models.widget_type import WidgetType


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


def create_submission_for_tenant(db, tenant, widget_type, message):
    widget = Widget(
        title="Dashboard Widget",
        tenant_id=tenant.tenant_id,
        widget_type_id=widget_type.widget_type_id,
        allowed_origins=[],
    )
    field = FieldDefinition(field_name=f"message_{uuid.uuid4().hex[:8]}", field_type="text")
    db.add_all([widget, field])
    db.commit()
    widget_field = WidgetField(widget_id=widget.widget_id, field_id=field.field_id)
    db.add(widget_field)
    db.commit()
    submission = Submission(widget_id=widget.widget_id, idempotency_key=uuid.uuid4().hex)
    db.add(submission)
    db.commit()
    db.add(
        SubmissionFieldValue(
            submission_id=submission.submission_id,
            widget_field_id=widget_field.widget_field_id,
            value_text=message,
        )
    )
    db.commit()
    return submission, field


def test_dashboard_lists_and_reads_only_current_tenant_submissions(client, db):
    tenant_a = Tenant(customer_name="Alpha", customer_email=f"alpha-{uuid.uuid4()}@example.com")
    tenant_b = Tenant(customer_name="Beta", customer_email=f"beta-{uuid.uuid4()}@example.com")
    widget_type = WidgetType(name=f"dashboard-{uuid.uuid4().hex[:8]}")
    db.add_all([tenant_a, tenant_b, widget_type])
    db.commit()
    submission_a, field_a = create_submission_for_tenant(
        db, tenant_a, widget_type, "Alpha message"
    )
    submission_b, _ = create_submission_for_tenant(db, tenant_b, widget_type, "Beta message")
    headers_a = {"Authorization": f"Bearer {tenant_a.tenant_id}"}

    listed = client.get("/submissions", headers=headers_a)
    fetched = client.get(f"/submissions/{submission_a.submission_id}", headers=headers_a)
    cross_tenant = client.get(f"/submissions/{submission_b.submission_id}", headers=headers_a)

    assert listed.status_code == 200
    submissions = listed.json()["submissions"]
    assert [item["submission_id"] for item in submissions] == [str(submission_a.submission_id)]
    assert submissions[0]["fields"] == [
        {
            "field_id": str(field_a.field_id),
            "name": field_a.field_name,
            "type": "text",
            "value": "Alpha message",
        }
    ]
    assert fetched.status_code == 200
    assert fetched.json()["submission_id"] == str(submission_a.submission_id)
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"] == "Submission not found"


def test_dashboard_requires_authentication(client):
    assert client.get("/submissions").status_code == 401
    assert client.get(f"/submissions/{uuid.uuid4()}").status_code == 401
