# tests/test_auth.py
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.tenant import Tenant

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

def test_auth_missing_credentials(client):
    response = client.get("/me")
    assert response.status_code == 401
    assert "Missing authentication credentials" in response.json()["detail"]

def test_auth_invalid_token(client):
    response = client.get(
        "/me",
        headers={"Authorization": "Bearer non-existent-tenant-key"}
    )
    assert response.status_code == 401
    assert "Invalid tenant authentication credentials" in response.json()["detail"]

def test_tenant_resolution_and_isolation(client, db):
    # Create Tenant A
    tenant_a = Tenant(
        customer_name="Company Alpha",
        customer_email=f"alpha_{uuid.uuid4().hex[:6]}@alpha.com"
    )
    # Create Tenant B
    tenant_b = Tenant(
        customer_name="Company Beta",
        customer_email=f"beta_{uuid.uuid4().hex[:6]}@beta.com"
    )
    db.add_all([tenant_a, tenant_b])
    db.commit()

    # 1. Authenticate as Tenant A using tenant_id
    res_a = client.get(
        "/me",
        headers={"Authorization": f"Bearer {tenant_a.tenant_id}"}
    )
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["tenant_id"] == str(tenant_a.tenant_id)
    assert data_a["customer_name"] == "Company Alpha"
    assert data_a["customer_email"] == tenant_a.customer_email

    # 2. Authenticate as Tenant B using tenant_id
    res_b = client.get(
        "/me",
        headers={"Authorization": f"Bearer {tenant_b.tenant_id}"}
    )
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["tenant_id"] == str(tenant_b.tenant_id)
    assert data_b["customer_name"] == "Company Beta"
    assert data_b["customer_email"] == tenant_b.customer_email

    # 3. Isolation check: Output of A is strictly distinct from B
    assert data_a["tenant_id"] != data_b["tenant_id"]
    assert data_a["customer_email"] != data_b["customer_email"]