# tests/test_api_widgets.py
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.widget_type import WidgetType
from app.models.widget import Widget

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
def tenants_and_types(db):
    tenant_a = Tenant(
        customer_name="Alpha Corp",
        customer_email=f"alpha_{uuid.uuid4().hex[:6]}@alpha.com"
    )
    tenant_b = Tenant(
        customer_name="Beta Corp",
        customer_email=f"beta_{uuid.uuid4().hex[:6]}@beta.com"
    )
    wt = WidgetType(name="contact_modal_" + uuid.uuid4().hex[:6])
    db.add_all([tenant_a, tenant_b, wt])
    db.commit()
    return tenant_a, tenant_b, wt

def test_widget_crud_lifecycle(client, tenants_and_types):
    tenant_a, _, wt = tenants_and_types
    headers = {"Authorization": f"Bearer {tenant_a.tenant_id}"}

    # 1. Create Widget (POST /widgets)
    create_payload = {
        "widget_type_id": str(wt.widget_type_id),
        "title": "Contact Us",
        "allowed_origins": ["https://example.com"]
    }
    res_create = client.post("/widgets", json=create_payload, headers=headers)
    assert res_create.status_code == 201
    created_data = res_create.json()
    widget_id = created_data["widget_id"]
    assert created_data["title"] == "Contact Us"
    assert created_data["allowed_origins"] == ["https://example.com"]

    # 2. List Widgets (GET /widgets)
    res_list = client.get("/widgets", headers=headers)
    assert res_list.status_code == 200
    items = res_list.json()["widgets"]
    assert any(w["widget_id"] == widget_id for w in items)

    # 3. Get Specific Widget (GET /widgets/{widget_id})
    res_get = client.get(f"/widgets/{widget_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["widget_id"] == widget_id

    # 4. Update Widget (PATCH /widgets/{widget_id})
    update_payload = {
        "title": "Contact Support",
        "allowed_origins": ["https://example.com", "https://app.example.com"]
    }
    res_update = client.patch(f"/widgets/{widget_id}", json=update_payload, headers=headers)
    assert res_update.status_code == 200
    updated_data = res_update.json()
    assert updated_data["title"] == "Contact Support"
    assert len(updated_data["allowed_origins"]) == 2

    # 5. Delete Widget (DELETE /widgets/{widget_id})
    res_delete = client.delete(f"/widgets/{widget_id}", headers=headers)
    assert res_delete.status_code == 204

    # 6. Verify Deleted
    res_get_after = client.get(f"/widgets/{widget_id}", headers=headers)
    assert res_get_after.status_code == 404

def test_widget_type_validation(client, tenants_and_types):
    tenant_a, _, _ = tenants_and_types
    headers = {"Authorization": f"Bearer {tenant_a.tenant_id}"}

    # Nonexistent widget_type_id
    res = client.post(
        "/widgets",
        json={
            "widget_type_id": str(uuid.uuid4()),
            "title": "Invalid Type Widget",
            "allowed_origins": []
        },
        headers=headers
    )
    assert res.status_code == 400
    assert "does not exist" in res.json()["detail"]

def test_cross_tenant_isolation(client, tenants_and_types, db):
    tenant_a, tenant_b, wt = tenants_and_types
    headers_a = {"Authorization": f"Bearer {tenant_a.tenant_id}"}
    headers_b = {"Authorization": f"Bearer {tenant_b.tenant_id}"}

    # Create widget owned by Tenant A
    res_a = client.post(
        "/widgets",
        json={"widget_type_id": str(wt.widget_type_id), "title": "Widget A", "allowed_origins": []},
        headers=headers_a
    )
    widget_a_id = res_a.json()["widget_id"]

    # Create widget owned by Tenant B
    res_b = client.post(
        "/widgets",
        json={"widget_type_id": str(wt.widget_type_id), "title": "Widget B", "allowed_origins": []},
        headers=headers_b
    )
    widget_b_id = res_b.json()["widget_id"]

    # 1. Tenant A lists widgets -> must contain Widget A, must NOT contain Widget B
    list_a = client.get("/widgets", headers=headers_a).json()["widgets"]
    ids_a = [w["widget_id"] for w in list_a]
    assert widget_a_id in ids_a
    assert widget_b_id not in ids_a

    # 2. Tenant A tries to GET Tenant B's widget -> 404
    assert client.get(f"/widgets/{widget_b_id}", headers=headers_a).status_code == 404

    # 3. Tenant A tries to PATCH Tenant B's widget -> 404
    assert client.patch(
        f"/widgets/{widget_b_id}",
        json={"title": "Hacked Title"},
        headers=headers_a
    ).status_code == 404

    # 4. Tenant A tries to DELETE Tenant B's widget -> 404
    assert client.delete(f"/widgets/{widget_b_id}", headers=headers_a).status_code == 404

    # Verify Tenant B's widget is still intact
    res_b_verify = client.get(f"/widgets/{widget_b_id}", headers=headers_b)
    assert res_b_verify.status_code == 200
    assert res_b_verify.json()["title"] == "Widget B"