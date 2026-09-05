# tests/test_api_widget_fields.py
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.widget_type import WidgetType
from app.models.widget import Widget
from app.models.field_definition import FieldDefinition


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
def setup_data(db):
    tenant_a = Tenant(customer_name="Tenant A", customer_email=f"ta_{uuid.uuid4().hex[:6]}@t.com")
    tenant_b = Tenant(customer_name="Tenant B", customer_email=f"tb_{uuid.uuid4().hex[:6]}@t.com")
    wt = WidgetType(name=f"wt_{uuid.uuid4().hex[:6]}")
    db.add_all([tenant_a, tenant_b, wt])
    db.commit()

    widget_a = Widget(title="Widget A", widget_type_id=wt.widget_type_id, tenant_id=tenant_a.tenant_id)
    widget_b = Widget(title="Widget B", widget_type_id=wt.widget_type_id, tenant_id=tenant_b.tenant_id)

    fd_email = FieldDefinition(field_name="email", field_type="email")
    fd_message = FieldDefinition(field_name="message", field_type="text")
    fd_phone = FieldDefinition(field_name="phone", field_type="text")

    db.add_all([widget_a, widget_b, fd_email, fd_message, fd_phone])
    db.commit()

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "widget_a": widget_a,
        "widget_b": widget_b,
        "email_field": fd_email,
        "message_field": fd_message,
        "phone_field": fd_phone,
    }


def test_configure_widget_fields_success(client, setup_data):
    data = setup_data
    headers = {"Authorization": f"Bearer {data['tenant_a'].tenant_id}"}
    w_id = data["widget_a"].widget_id

    payload = {
        "fields": [
            {"field_id": str(data["email_field"].field_id), "display_order": 1, "required": True},
            {"field_id": str(data["message_field"].field_id), "display_order": 2, "required": False},
        ]
    }

    # PUT /widgets/:id/fields
    res = client.put(f"/widgets/{w_id}/fields", json=payload, headers=headers)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["widget_id"] == str(w_id)
    assert len(res_data["fields"]) == 2

    first = res_data["fields"][0]
    assert first["field_id"] == str(data["email_field"].field_id)
    assert first["display_order"] == 1
    assert first["required"] is True
    assert "widget_field_id" in first

    second = res_data["fields"][1]
    assert second["field_id"] == str(data["message_field"].field_id)
    assert second["display_order"] == 2
    assert second["required"] is False
    assert "widget_field_id" in second

    # GET /widgets/:id/fields
    res_get = client.get(f"/widgets/{w_id}/fields", headers=headers)
    assert res_get.status_code == 200
    assert len(res_get.json()["fields"]) == 2


def test_configure_widget_fields_validations(client, setup_data):
    data = setup_data
    headers = {"Authorization": f"Bearer {data['tenant_a'].tenant_id}"}
    w_id = data["widget_a"].widget_id

    # 1. Nonexistent field_id -> 400
    fake_id = str(uuid.uuid4())
    res = client.put(
        f"/widgets/{w_id}/fields",
        json={"fields": [{"field_id": fake_id, "display_order": 1, "required": True}]},
        headers=headers,
    )
    assert res.status_code == 400
    assert "do not exist" in res.json()["detail"]

    # 2. Duplicate field_id in request -> 400
    email_id = str(data["email_field"].field_id)
    res_dup = client.put(
        f"/widgets/{w_id}/fields",
        json={
            "fields": [
                {"field_id": email_id, "display_order": 1, "required": True},
                {"field_id": email_id, "display_order": 2, "required": False},
            ]
        },
        headers=headers,
    )
    email_id = str(data["email_field"].field_id)
    res_dup = client.put(
        f"/widgets/{w_id}/fields",
        json={
            "fields": [
                {"field_id": email_id, "display_order": 1, "required": True},
                {"field_id": email_id, "display_order": 2, "required": False},
            ]
        },
        headers=headers,
    )
    print("\nSTATUS:", res_dup.status_code)
    print("BODY:", res_dup.json())
    assert res_dup.status_code == 400
    
    assert "Duplicate fields" in res_dup.json()["detail"]

    # 3. Duplicate display_order -> 400
    msg_id = str(data["message_field"].field_id)
    res_order = client.put(
        f"/widgets/{w_id}/fields",
        json={
            "fields": [
                {"field_id": email_id, "display_order": 1, "required": True},
                {"field_id": msg_id, "display_order": 1, "required": False},
            ]
        },
        headers=headers,
    )
    assert res_order.status_code == 400
    assert "Duplicate display_order" in res_order.json()["detail"]


def test_single_field_crud_endpoints(client, setup_data):
    data = setup_data
    headers = {"Authorization": f"Bearer {data['tenant_a'].tenant_id}"}
    w_id = data["widget_a"].widget_id
    email_id = str(data["email_field"].field_id)

    # POST add field
    res_add = client.post(
        f"/widgets/{w_id}/fields",
        json={"field_id": email_id, "display_order": 1, "required": True},
        headers=headers,
    )
    assert res_add.status_code == 201
    assert res_add.json()["required"] is True

    # Duplicate POST -> 409
    res_add_dup = client.post(
        f"/widgets/{w_id}/fields",
        json={"field_id": email_id, "display_order": 2, "required": False},
        headers=headers,
    )

    assert res_add_dup.status_code == 409

    # PATCH update field
    res_patch = client.patch(
        f"/widgets/{w_id}/fields/{email_id}",
        json={"required": False, "display_order": 5},
        headers=headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["required"] is False
    assert res_patch.json()["display_order"] == 5

    # DELETE remove field
    res_del = client.delete(f"/widgets/{w_id}/fields/{email_id}", headers=headers)
    assert res_del.status_code == 204

    # Verify gone
    res_list = client.get(f"/widgets/{w_id}/fields", headers=headers)
    assert len(res_list.json()["fields"]) == 0


def test_tenant_isolation_on_widget_fields(client, setup_data):
    data = setup_data
    headers_a = {"Authorization": f"Bearer {data['tenant_a'].tenant_id}"}
    widget_b_id = data["widget_b"].widget_id
    email_id = str(data["email_field"].field_id)

    # Tenant A tries to configure Tenant B's widget -> 404
    res_put = client.put(
        f"/widgets/{widget_b_id}/fields",
        json={"fields": [{"field_id": email_id, "display_order": 1, "required": True}]},
        headers=headers_a,
    )
    assert res_put.status_code == 404

    # Tenant A tries to list Tenant B's widget fields -> 404
    assert client.get(f"/widgets/{widget_b_id}/fields", headers=headers_a).status_code == 404

    # Tenant A tries to delete Tenant B's widget field -> 404
    assert client.delete(f"/widgets/{widget_b_id}/fields/{email_id}", headers=headers_a).status_code == 404