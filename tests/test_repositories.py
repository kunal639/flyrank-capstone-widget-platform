# tests/test_repositories.py
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models.widget_type import WidgetType
from app.models.field_definition import FieldDefinition
from app.models.widget_field import WidgetField
from app.models.submission import Submission
from app.repositories.tenant import TenantRepository
from app.repositories.widget import WidgetRepository
from app.repositories.submission import SubmissionRepository

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

def test_tenant_and_widget_repositories(db):
    tenant_repo = TenantRepository(db)
    widget_repo = WidgetRepository(db)

    # 1. Create tenant
    tenant = tenant_repo.create(
        customer_name="Test Enterprise",
        customer_email=f"repo_test_{uuid.uuid4().hex[:6]}@example.com"
    )
    db.commit()

    fetched_tenant = tenant_repo.get_by_id(tenant.tenant_id)
    assert fetched_tenant is not None
    assert fetched_tenant.customer_name == "Test Enterprise"

    # 2. Setup WidgetType
    wt = WidgetType(name="repo_wt_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    # 3. Create widget for tenant
    widget = widget_repo.create(
        title="Tenant Widget",
        widget_type_id=wt.widget_type_id,
        tenant_id=tenant.tenant_id,
        allowed_origins=["https://test.com"]
    )
    db.commit()

    tenant_widgets = widget_repo.list_for_tenant(tenant.tenant_id)
    assert len(tenant_widgets) >= 1
    assert tenant_widgets[0].widget_id == widget.widget_id

def test_atomic_submission_transaction_success(db):
    wt = WidgetType(name="atom_success_wt_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    widget_repo = WidgetRepository(db)
    widget = widget_repo.create(title="Form Widget", widget_type_id=wt.widget_type_id)
    db.commit()

    fd = FieldDefinition(field_name="message", field_type="text")
    db.add(fd)
    db.commit()

    wf = WidgetField(widget_id=widget.widget_id, field_id=fd.field_id)
    db.add(wf)
    db.commit()

    sub_repo = SubmissionRepository(db)
    idemp_key = f"idemp-atom-{uuid.uuid4().hex[:6]}"

    sub = sub_repo.create_submission_with_values(
        widget_id=widget.widget_id,
        idempotency_key=idemp_key,
        field_values=[{"widget_field_id": wf.widget_field_id, "value_text": "Hello world"}],
        geo_data={"city": "Patna", "country": "India"}
    )
    db.commit()

    # Verify all 3 pieces are persisted
    persisted_sub = sub_repo.get_by_id(sub.submission_id)
    assert persisted_sub is not None
    assert len(persisted_sub.field_values) == 1
    assert persisted_sub.notification_outbox is not None
    assert persisted_sub.notification_outbox.status == "pending"

def test_atomic_submission_transaction_rollback(db):
    wt = WidgetType(name="atom_rollback_wt_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    widget_repo = WidgetRepository(db)
    widget = widget_repo.create(title="Rollback Form", widget_type_id=wt.widget_type_id)
    db.commit()

    sub_repo = SubmissionRepository(db)
    idemp_key = f"idemp-fail-{uuid.uuid4().hex[:6]}"
    fake_widget_field_id = uuid.uuid4()

    # Execute transaction that fails on invalid widget_field_id
    with pytest.raises(IntegrityError):
        sub_repo.create_submission_with_values(
            widget_id=widget.widget_id,
            idempotency_key=idemp_key,
            field_values=[{"widget_field_id": fake_widget_field_id, "value_text": "Will fail"}],
        )
        db.commit()

    db.rollback()

    # Prove submission does NOT exist (clean rollback)
    sub_in_db = sub_repo.get_by_idempotency_key(widget.widget_id, idemp_key)
    assert sub_in_db is None