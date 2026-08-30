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
from app.models.submission import Submission
from app.models.submission_field_value import SubmissionFieldValue
from app.models.notification_outbox import NotificationOutbox

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

def test_submission_and_field_values_valid(db):
    wt = WidgetType(name="submission_test_wt_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    widget = Widget(title="Contact Form", widget_type_id=wt.widget_type_id, allowed_origins=[])
    db.add(widget)
    db.commit()

    fd_name = FieldDefinition(field_name="name", field_type="text")
    fd_email = FieldDefinition(field_name="email", field_type="email")
    db.add_all([fd_name, fd_email])
    db.commit()

    wf_name = WidgetField(widget_id=widget.widget_id, field_id=fd_name.field_id, display_order=1)
    wf_email = WidgetField(widget_id=widget.widget_id, field_id=fd_email.field_id, display_order=2)
    db.add_all([wf_name, wf_email])
    db.commit()

    # Valid Submission with nullable geo and default notification values
    sub = Submission(
        widget_id=widget.widget_id,
        idempotency_key="idemp-12345",
        country="India",
        city="Patna",
        region="Bihar",
        latitude=25.5941,
        longitude=85.1376,
    )
    db.add(sub)
    db.commit()
    assert sub.submission_id is not None
    assert sub.notification_status == "pending"
    assert sub.notification_attempts == 0
    assert sub.created_at is not None

    # Add multiple field values to the submission
    val_name = SubmissionFieldValue(
        submission_id=sub.submission_id,
        widget_field_id=wf_name.widget_field_id,
        value_text="Alice"
    )
    val_email = SubmissionFieldValue(
        submission_id=sub.submission_id,
        widget_field_id=wf_email.widget_field_id,
        value_text="alice@example.com"
    )
    db.add_all([val_name, val_email])
    db.commit()
    assert val_name.submission_field_value_id is not None
    assert val_email.submission_field_value_id is not None

def test_submission_constraints_and_idempotency(db):
    wt = WidgetType(name="idemp_test_wt_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    widget = Widget(title="Feedback Widget", widget_type_id=wt.widget_type_id, allowed_origins=[])
    db.add(widget)
    db.commit()

    fd = FieldDefinition(field_name="score", field_type="number")
    db.add(fd)
    db.commit()

    wf = WidgetField(widget_id=widget.widget_id, field_id=fd.field_id)
    db.add(wf)
    db.commit()

    # 1. Invalid: Nonexistent widget_id
    invalid_sub = Submission(widget_id=uuid.uuid4(), idempotency_key="key-1")
    db.add(invalid_sub)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # 2. Insert valid submission
    sub1 = Submission(widget_id=widget.widget_id, idempotency_key="idemp-unique-1")
    db.add(sub1)
    db.commit()

    # 3. Invalid: Duplicate (widget_id, idempotency_key)
    sub_dup = Submission(widget_id=widget.widget_id, idempotency_key="idemp-unique-1")
    db.add(sub_dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # 4. Insert valid field value
    fv1 = SubmissionFieldValue(
        submission_id=sub1.submission_id,
        widget_field_id=wf.widget_field_id,
        value_number=9.5
    )
    db.add(fv1)
    db.commit()

    # 5. Invalid: Duplicate (submission_id, widget_field_id)
    fv_dup = SubmissionFieldValue(
        submission_id=sub1.submission_id,
        widget_field_id=wf.widget_field_id,
        value_number=10.0
    )
    db.add(fv_dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # 6. Invalid: Nonexistent widget_field_id
    fv_invalid_wf = SubmissionFieldValue(
        submission_id=sub1.submission_id,
        widget_field_id=uuid.uuid4(),
        value_text="Invalid"
    )
    db.add(fv_invalid_wf)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

def test_notification_outbox_valid_and_defaults(db):
    wt = WidgetType(name="outbox_test_wt_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    widget = Widget(title="Notification Form", widget_type_id=wt.widget_type_id, allowed_origins=[])
    db.add(widget)
    db.commit()

    submission = Submission(widget_id=widget.widget_id, idempotency_key=f"outbox-idemp-{uuid.uuid4().hex[:6]}")
    db.add(submission)
    db.commit()

    # Valid NotificationOutbox record
    outbox = NotificationOutbox(submission_id=submission.submission_id)
    db.add(outbox)
    db.commit()

    assert outbox.outbox_id is not None
    assert outbox.submission_id == submission.submission_id
    assert outbox.status == "pending"
    assert outbox.attempts == 0
    assert outbox.available_at is not None
    assert outbox.created_at is not None
    assert outbox.last_error is None
    assert outbox.processed_at is None

def test_notification_outbox_constraints(db):
    wt = WidgetType(name="outbox_constraint_wt_" + uuid.uuid4().hex[:6])
    db.add(wt)
    db.commit()

    widget = Widget(title="Outbox Constraints", widget_type_id=wt.widget_type_id, allowed_origins=[])
    db.add(widget)
    db.commit()

    submission = Submission(widget_id=widget.widget_id, idempotency_key=f"outbox-idemp-{uuid.uuid4().hex[:6]}")
    db.add(submission)
    db.commit()

    # 1. Invalid: Nonexistent submission_id
    invalid_outbox = NotificationOutbox(submission_id=uuid.uuid4())
    db.add(invalid_outbox)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # 2. First outbox entry for submission succeeds
    outbox1 = NotificationOutbox(submission_id=submission.submission_id, status="pending")
    db.add(outbox1)
    db.commit()

    # 3. Invalid: Duplicate submission_id (1:1 constraint)
    outbox_dup = NotificationOutbox(submission_id=submission.submission_id, status="processing")
    db.add(outbox_dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()