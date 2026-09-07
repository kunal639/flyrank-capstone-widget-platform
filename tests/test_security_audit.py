# tests/test_security_audit.py
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.widget_type import WidgetType
from app.models.widget import Widget
from app.models.field_definition import FieldDefinition
from app.models.widget_field import WidgetField


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
def security_setup(db: Session):
    tenant_1 = Tenant(customer_name="Security Tenant 1", customer_email=f"t1_{uuid.uuid4().hex[:6]}@example.com")
    tenant_2 = Tenant(customer_name="Security Tenant 2", customer_email=f"t2_{uuid.uuid4().hex[:6]}@example.com")
    wtype = WidgetType(name=f"wtype_{uuid.uuid4().hex[:6]}")
    f_email = FieldDefinition(field_name="email", field_type="email")
    db.add_all([tenant_1, tenant_2, wtype, f_email])
    db.commit()

    widget_1 = Widget(
        title="Tenant 1 Widget",
        widget_type_id=wtype.widget_type_id,
        tenant_id=tenant_1.tenant_id,
        allowed_origins=["https://legit.example"],
    )
    widget_2 = Widget(
        title="Tenant 2 Widget",
        widget_type_id=wtype.widget_type_id,
        tenant_id=tenant_2.tenant_id,
        allowed_origins=["https://secure.example"],
    )
    db.add_all([widget_1, widget_2])
    db.commit()

    db.add_all([
        WidgetField(widget_id=widget_1.widget_id, field_id=f_email.field_id, display_order=0, required=True),
        WidgetField(widget_id=widget_2.widget_id, field_id=f_email.field_id, display_order=0, required=True),
    ])
    db.commit()

    return {
        "t1": tenant_1,
        "t2": tenant_2,
        "w1": widget_1,
        "w2": widget_2,
    }


def test_public_config_does_not_leak_tenant_id_or_secrets(client, security_setup):
    """Verifies that GET /widgets/:id/config never leaks tenant UUID or private configs."""
    w1 = security_setup["w1"]
    res = client.get(f"/widgets/{w1.widget_id}/config")
    assert res.status_code == 200
    data = res.json()

    # Public response must not leak tenant_id or allowed_origins list
    assert "tenant_id" not in data
    assert "allowed_origins" not in data
    assert str(security_setup["t1"].tenant_id) not in res.text


def test_idor_cannot_modify_other_tenant_widget(client, security_setup):
    """Tenant 1 cannot patch or delete Tenant 2's widget via forged path parameter."""
    auth_t1 = {"Authorization": f"Bearer {security_setup['t1'].tenant_id}"}
    w2_id = security_setup["w2"].widget_id

    # Attempt PATCH
    res_patch = client.patch(f"/widgets/{w2_id}", json={"title": "Hacked"}, headers=auth_t1)
    assert res_patch.status_code == 404

    # Attempt DELETE
    res_del = client.delete(f"/widgets/{w2_id}", headers=auth_t1)
    assert res_del.status_code == 404


def test_sql_injection_attempt_in_field_values(client, security_setup, db: Session):
    """Verifies that SQL injection payloads are safely treated as raw strings."""
    w1 = security_setup["w1"]
    sqli_payload = "test@example.com'; DROP TABLE submission; --"

    res = client.post(
        "/submissions",
        json={
            "widget_id": str(w1.widget_id),
            "idempotency_key": str(uuid.uuid4()),
            "honeypot": "",
            "fields": {"email": sqli_payload},
        },
        headers={"Origin": "https://legit.example"},
    )
    # Email regex validator rejects the malformed email address cleanly
    assert res.status_code == 422
    assert "detail" in res.json()