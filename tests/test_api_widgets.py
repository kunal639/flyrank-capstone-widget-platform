# tests/test_api_widgets.py
import uuid
import pytest
from fastapi.testclient import TestClient

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


def test_replace_widget_fields(client, tenants_and_types, db):
    tenant_a, _, widget_type = tenants_and_types
    headers = {"Authorization": f"Bearer {tenant_a.tenant_id}"}
    widget = Widget(
        title="Configured Widget",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_a.tenant_id,
        allowed_origins=[],
    )
    email_field = FieldDefinition(field_name="email", field_type="email")
    message_field = FieldDefinition(field_name="message", field_type="text")
    db.add_all([widget, email_field, message_field])
    db.commit()

    response = client.put(
        f"/widgets/{widget.widget_id}/fields",
        json={
            "fields": [
                {
                    "field_id": str(email_field.field_id),
                    "display_order": 0,
                    "required": True,
                },
                {
                    "field_id": str(message_field.field_id),
                    "display_order": 1,
                    "required": False,
                },
            ]
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["widget_id"] == str(widget.widget_id)
    assert [field["field_id"] for field in response.json()["fields"]] == [
        str(email_field.field_id),
        str(message_field.field_id),
    ]

    replacement = client.put(
        f"/widgets/{widget.widget_id}/fields",
        json={
            "fields": [
                {
                    "field_id": str(message_field.field_id),
                    "display_order": 0,
                    "required": True,
                }
            ]
        },
        headers=headers,
    )

    assert replacement.status_code == 200
    configured_fields = replacement.json()["fields"]
    assert len(configured_fields) == 1
    assert configured_fields[0]["field_id"] == str(message_field.field_id)
    assert configured_fields[0]["display_order"] == 0
    assert configured_fields[0]["required"] is True


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            [
                {"field_id": "{field_id}", "display_order": 0, "required": True},
                {"field_id": "{field_id}", "display_order": 1, "required": False},
            ],
            "Duplicate fields in configuration are not allowed",
        ),
        (
            [
                {"field_id": "{field_id}", "display_order": 0, "required": True},
                {"field_id": "{other_field_id}", "display_order": 0, "required": False},
            ],
            "Duplicate display_order values are not allowed",
        ),
    ],
)

def test_replace_widget_fields_rejects_duplicate_configuration(
    client, tenants_and_types, db, fields, message
):
    tenant_a, _, widget_type = tenants_and_types
    widget = Widget(
        title="Configured Widget",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_a.tenant_id,
        allowed_origins=[],
    )
    field = FieldDefinition(field_name="email", field_type="email")
    other_field = FieldDefinition(field_name="message", field_type="text")
    db.add_all([widget, field, other_field])
    db.commit()

    response = client.put(
        f"/widgets/{widget.widget_id}/fields",
        json={
            "fields": [
                {
                    **item,
                    "field_id": item["field_id"].format(
                        field_id=field.field_id, other_field_id=other_field.field_id
                    ),
                }
                for item in fields
            ]
        },
        headers={"Authorization": f"Bearer {tenant_a.tenant_id}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == message


def test_replace_widget_fields_rejects_missing_or_cross_tenant_widget(
    client, tenants_and_types, db
):
    tenant_a, tenant_b, widget_type = tenants_and_types
    widget_b = Widget(
        title="Tenant B Widget",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_b.tenant_id,
        allowed_origins=[],
    )
    field = FieldDefinition(field_name="message", field_type="text")
    db.add_all([widget_b, field])
    db.commit()

    response = client.put(
        f"/widgets/{widget_b.widget_id}/fields",
        json={"fields": []},
        headers={"Authorization": f"Bearer {tenant_a.tenant_id}"},
    )

    assert response.status_code == 404


def test_replace_widget_fields_rejects_unknown_field(client, tenants_and_types, db):
    tenant_a, _, widget_type = tenants_and_types
    widget = Widget(
        title="Configured Widget",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_a.tenant_id,
        allowed_origins=[],
    )
    db.add(widget)
    db.commit()

    response = client.put(
        f"/widgets/{widget.widget_id}/fields",
        json={
            "fields": [
                {"field_id": str(uuid.uuid4()), "display_order": 0, "required": True}
            ]
        },
        headers={"Authorization": f"Bearer {tenant_a.tenant_id}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "One or more field definitions do not exist"


def test_replace_widget_fields_rejects_invalid_display_order(
    client, tenants_and_types, db
):
    tenant_a, _, widget_type = tenants_and_types
    widget = Widget(
        title="Configured Widget",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_a.tenant_id,
        allowed_origins=[],
    )
    field = FieldDefinition(field_name="message", field_type="text")
    db.add_all([widget, field])
    db.commit()

    response = client.put(
        f"/widgets/{widget.widget_id}/fields",
        json={
            "fields": [
                {"field_id": str(field.field_id), "display_order": -1, "required": True}
            ]
        },
        headers={"Authorization": f"Bearer {tenant_a.tenant_id}"},
    )

    assert response.status_code == 422


def test_get_public_widget_config_exposes_only_rendering_data(
    client, tenants_and_types, db
):
    tenant_a, _, widget_type = tenants_and_types
    widget = Widget(
        title="Contact Us",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_a.tenant_id,
        allowed_origins=["https://example.com"],
    )
    email_field = FieldDefinition(field_name="email", field_type="email")
    message_field = FieldDefinition(field_name="message", field_type="text")
    db.add_all([widget, email_field, message_field])
    db.commit()
    db.add_all(
        [
            WidgetField(
                widget_id=widget.widget_id,
                field_id=message_field.field_id,
                display_order=1,
                required=True,
            ),
            WidgetField(
                widget_id=widget.widget_id,
                field_id=email_field.field_id,
                display_order=0,
                required=False,
            ),
        ]
    )
    db.commit()

    response = client.get(f"/widgets/{widget.widget_id}/config")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=60"
    assert response.json() == {
        "widget_id": str(widget.widget_id),
        "widget_type": widget_type.name,
        "title": "Contact Us",
        "fields": [
            {
                "field_id": str(email_field.field_id),
                "name": "email",
                "type": "email",
                "required": False,
            },
            {
                "field_id": str(message_field.field_id),
                "name": "message",
                "type": "text",
                "required": True,
            },
        ],
    }


def test_get_public_widget_config_returns_404_for_missing_widget(client):
    response = client.get(f"/widgets/{uuid.uuid4()}/config")

    assert response.status_code == 404
    assert response.json()["detail"] == "Widget not found"

def test_public_widget_config_requires_no_auth(client, tenants_and_types, db):
    tenant, _, wt = tenants_and_types
    widget = Widget(
        title="No Auth Widget",
        widget_type_id=wt.widget_type_id,
        tenant_id=tenant.tenant_id,
        allowed_origins=[],
    )
    db.add(widget)
    db.commit()

    # Public caller without Authorization header
    response = client.get(f"/widgets/{widget.widget_id}/config")
    assert response.status_code == 200
    assert response.json()["widget_id"] == str(widget.widget_id)


def test_public_widget_config_empty_fields(client, tenants_and_types, db):
    tenant, _, wt = tenants_and_types
    widget = Widget(
        title="Empty Config Widget",
        widget_type_id=wt.widget_type_id,
        tenant_id=tenant.tenant_id,
        allowed_origins=[],
    )
    db.add(widget)
    db.commit()

    response = client.get(f"/widgets/{widget.widget_id}/config")
    assert response.status_code == 200
    data = response.json()
    assert data["fields"] == []


def test_public_widget_config_returns_fields_in_display_order(
    client, tenants_and_types, db
):
    tenant, _, wt = tenants_and_types
    widget = Widget(
        title="Ordered Widget",
        widget_type_id=wt.widget_type_id,
        tenant_id=tenant.tenant_id,
        allowed_origins=[],
    )
    fd1 = FieldDefinition(field_name="last_field", field_type="text")
    fd2 = FieldDefinition(field_name="first_field", field_type="text")
    fd3 = FieldDefinition(field_name="middle_field", field_type="text")
    db.add_all([widget, fd1, fd2, fd3])
    db.commit()

    # Insert out of order
    db.add_all(
        [
            WidgetField(
                widget_id=widget.widget_id,
                field_id=fd1.field_id,
                display_order=20,
                required=False,
            ),
            WidgetField(
                widget_id=widget.widget_id,
                field_id=fd2.field_id,
                display_order=5,
                required=True,
            ),
            WidgetField(
                widget_id=widget.widget_id,
                field_id=fd3.field_id,
                display_order=10,
                required=False,
            ),
        ]
    )
    db.commit()

    response = client.get(f"/widgets/{widget.widget_id}/config")
    assert response.status_code == 200
    names = [f["name"] for f in response.json()["fields"]]
    assert names == ["first_field", "middle_field", "last_field"]


def test_public_widget_config_does_not_expose_private_tenant_data(
    client, tenants_and_types, db
):
    tenant, _, wt = tenants_and_types
    widget = Widget(
        title="Safe Config Widget",
        widget_type_id=wt.widget_type_id,
        tenant_id=tenant.tenant_id,
        allowed_origins=["https://private-domain.internal"],
    )
    db.add(widget)
    db.commit()

    response = client.get(f"/widgets/{widget.widget_id}/config")
    assert response.status_code == 200
    data = response.json()

    # Ensure no tenant-identifying or internal storage fields are leaked
    assert "tenant_id" not in data
    assert "allowed_origins" not in data
    assert "customer_name" not in data
    assert "customer_email" not in data
    assert "created_at" not in data
    assert "updated_at" not in data
    for field in data["fields"]:
        assert "widget_field_id" not in field