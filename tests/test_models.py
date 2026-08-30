# tests/test_models.py
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.widget_type import WidgetType
from app.models.widget import Widget
from app.models.field_definition import FieldDefinition
from app.models.widget_field import WidgetField

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_tenant_insertion_and_unique_email(db):
    email = "founder@example.com"
    # Cleanup if leftover
    db.query(Tenant).filter_by(customer_email=email).delete()
    db.commit()

    # Insert 1st tenant
    tenant1 = Tenant(customer_name="Acme Corp", customer_email=email)
    db.add(tenant1)
    db.commit()
    assert tenant1.tenant_id is not None

    # Insert 2nd tenant with duplicate email (should fail)
    tenant2 = Tenant(customer_name="Duplicate Corp", customer_email=email)
    db.add(tenant2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Cleanup
    db.query(Tenant).filter_by(customer_email=email).delete()
    db.commit()


def test_widget_type_insertion_and_unique_name(db):
    name = "feedback_collector"
    # Cleanup if leftover
    db.query(WidgetType).filter_by(name=name).delete()
    db.commit()

    # Insert 1st widget type
    wt1 = WidgetType(name=name)
    db.add(wt1)
    db.commit()
    assert wt1.widget_type_id is not None

    # Insert 2nd widget type with duplicate name (should fail)
    wt2 = WidgetType(name=name)
    db.add(wt2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Cleanup
    db.query(WidgetType).filter_by(name=name).delete()
    db.commit()


def test_widget_creation_with_and_without_tenant(db):
    wt = WidgetType(name="contact_modal_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    # 1. Valid: Widget without tenant (tenant_id = None)
    widget_no_tenant = Widget(
        title="Public Feedback",
        widget_type_id=wt.widget_type_id,
        tenant_id=None,
        allowed_origins=[]
    )
    db.add(widget_no_tenant)
    db.commit()
    assert widget_no_tenant.widget_id is not None
    assert widget_no_tenant.tenant_id is None
    assert widget_no_tenant.allowed_origins == []

    # 2. Valid: Widget with tenant and multiple allowed origins
    tenant = Tenant(
        customer_name="Beta Corp",
        customer_email=f"contact_{uuid.uuid4().hex[:6]}@beta.com"
    )
    db.add(tenant)
    db.commit()

    widget_with_tenant = Widget(
        title="Beta Support Widget",
        widget_type_id=wt.widget_type_id,
        tenant_id=tenant.tenant_id,
        allowed_origins=["https://example.com", "https://app.example.com"]
    )
    db.add(widget_with_tenant)
    db.commit()
    assert widget_with_tenant.widget_id is not None
    assert widget_with_tenant.tenant_id == tenant.tenant_id
    assert len(widget_with_tenant.allowed_origins) == 2


def test_widget_invalid_foreign_keys_and_null_title(db):
    wt = WidgetType(name="survey_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    # Invalid: Nonexistent tenant_id
    fake_tenant_id = uuid.uuid4()
    widget_invalid_tenant = Widget(
        title="Survey",
        widget_type_id=wt.widget_type_id,
        tenant_id=fake_tenant_id
    )
    db.add(widget_invalid_tenant)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Invalid: Nonexistent widget_type_id
    fake_wt_id = uuid.uuid4()
    widget_invalid_wt = Widget(
        title="Survey",
        widget_type_id=fake_wt_id,
        tenant_id=None
    )
    db.add(widget_invalid_wt)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Invalid: Missing / NULL title
    widget_no_title = Widget(
        title=None,
        widget_type_id=wt.widget_type_id,
        tenant_id=None
    )
    db.add(widget_no_title)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

def test_field_definition_and_widget_field_valid(db):
    # Setup widget type & widgets
    wt = WidgetType(name="contact_form_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    w1 = Widget(title="Widget A", widget_type_id=wt.widget_type_id, allowed_origins=[])
    w2 = Widget(title="Widget B", widget_type_id=wt.widget_type_id, allowed_origins=[])
    db.add_all([w1, w2])
    db.commit()

    # Create reusable field definitions
    email_field = FieldDefinition(field_name="email", field_type="email")
    message_field = FieldDefinition(field_name="message", field_type="text")
    db.add_all([email_field, message_field])
    db.commit()

    # Widget A uses email (required) and message (optional)
    wf_a1 = WidgetField(widget_id=w1.widget_id, field_id=email_field.field_id, display_order=1, required=True)
    wf_a2 = WidgetField(widget_id=w1.widget_id, field_id=message_field.field_id, display_order=2, required=False)

    # Widget B reuses email (optional)
    wf_b1 = WidgetField(widget_id=w2.widget_id, field_id=email_field.field_id, display_order=1, required=False)

    db.add_all([wf_a1, wf_a2, wf_b1])
    db.commit()

    assert wf_a1.required is True
    assert wf_b1.required is False
    assert wf_a1.field_id == wf_b1.field_id

def test_widget_field_duplicate_and_invalid_foreign_keys(db):
    wt = WidgetType(name="feedback_form_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    widget = Widget(title="Support Widget", widget_type_id=wt.widget_type_id, allowed_origins=[])
    db.add(widget)
    db.commit()

    field = FieldDefinition(field_name="phone", field_type="tel")
    db.add(field)
    db.commit()

    # 1. Add field to widget
    wf1 = WidgetField(widget_id=widget.widget_id, field_id=field.field_id, display_order=1, required=True)
    db.add(wf1)
    db.commit()

    # 2. Invalid: Add the same field to the same widget again (Duplicate composite key)
    wf_duplicate = WidgetField(widget_id=widget.widget_id, field_id=field.field_id, display_order=2, required=False)
    db.add(wf_duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # 3. Invalid: Nonexistent widget_id
    wf_invalid_w = WidgetField(widget_id=uuid.uuid4(), field_id=field.field_id, display_order=1, required=True)
    db.add(wf_invalid_w)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # 4. Invalid: Nonexistent field_id
    wf_invalid_f = WidgetField(widget_id=widget.widget_id, field_id=uuid.uuid4(), display_order=1, required=True)
    db.add(wf_invalid_f)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()