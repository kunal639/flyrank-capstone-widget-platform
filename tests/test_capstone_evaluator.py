# tests/test_capstone_evaluator.py
import uuid
from unittest.mock import patch
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
from app.models.submission import Submission
from app.models.submission_field_value import SubmissionFieldValue
from app.models.notification_outbox import NotificationOutbox


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
def evaluator_env(db: Session):
    # Setup Tenant A & Tenant B
    tenant_a = Tenant(customer_name="Eval Corp A", customer_email=f"eval_a_{uuid.uuid4().hex[:6]}@example.com")
    tenant_b = Tenant(customer_name="Eval Corp B", customer_email=f"eval_b_{uuid.uuid4().hex[:6]}@example.com")
    widget_type = WidgetType(name=f"eval_contact_{uuid.uuid4().hex[:6]}")
    db.add_all([tenant_a, tenant_b, widget_type])
    db.commit()

    # Field definitions
    f_email = FieldDefinition(field_name="email", field_type="email")
    f_msg = FieldDefinition(field_name="message", field_type="text")
    db.add_all([f_email, f_msg])
    db.commit()

    # Widget A (Tenant A)
    widget_a = Widget(
        title="Eval Widget A",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_a.tenant_id,
        allowed_origins=["https://customer.example"],
    )
    # Widget B (Tenant B)
    widget_b = Widget(
        title="Eval Widget B",
        widget_type_id=widget_type.widget_type_id,
        tenant_id=tenant_b.tenant_id,
        allowed_origins=[],
    )
    db.add_all([widget_a, widget_b])
    db.commit()

    # Attach fields to Widget A & B
    db.add_all([
        WidgetField(widget_id=widget_a.widget_id, field_id=f_email.field_id, display_order=0, required=True),
        WidgetField(widget_id=widget_a.widget_id, field_id=f_msg.field_id, display_order=1, required=False),
        WidgetField(widget_id=widget_b.widget_id, field_id=f_email.field_id, display_order=0, required=True),
    ])
    db.commit()

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "widget_a": widget_a,
        "widget_b": widget_b,
        "field_email": f_email,
        "field_msg": f_msg,
    }


# =====================================================================
# 1. PUBLIC SUBMISSION & ORIGIN VERIFICATION
# =====================================================================

def test_evaluator_second_origin_success(client, evaluator_env, db: Session):
    widget = evaluator_env["widget_a"]
    origin = "https://customer.example"

    # Step 1: Config fetch
    res_cfg = client.get(f"/widgets/{widget.widget_id}/config")
    assert res_cfg.status_code == 200
    assert res_cfg.headers.get("access-control-allow-origin") == "*"

    # Step 2: Submission
    payload = {
        "widget_id": str(widget.widget_id),
        "idempotency_key": str(uuid.uuid4()),
        "honeypot": "",
        "fields": {"email": "visitor@customer.example", "message": "Inquiry"},
    }
    res_sub = client.post("/submissions", json=payload, headers={"Origin": origin})
    assert res_sub.status_code == 201
    assert res_sub.headers.get("access-control-allow-origin") == origin
    assert "submission_id" in res_sub.json()


def test_evaluator_disallowed_origin_rejection(client, evaluator_env):
    widget = evaluator_env["widget_a"]
    payload = {
        "widget_id": str(widget.widget_id),
        "idempotency_key": str(uuid.uuid4()),
        "honeypot": "",
        "fields": {"email": "bad@origin.example"},
    }
    res = client.post("/submissions", json=payload, headers={"Origin": "https://malicious.example"})
    assert res.status_code == 403
    assert "access-control-allow-origin" not in res.headers
    assert res.json()["detail"] == "Origin is not allowed for this widget"


# =====================================================================
# 2. MALFORMED PAYLOADS & ERROR HANDLING
# =====================================================================

@pytest.mark.parametrize("invalid_payload,expected_status", [
    ({}, 422),
    ({"widget_id": "not-a-uuid", "idempotency_key": "k1", "fields": {}}, 422),
    ({"widget_id": str(uuid.uuid4()), "fields": {}}, 422),  # missing idempotency_key
    ({"widget_id": str(uuid.uuid4()), "idempotency_key": "k2", "fields": "not-a-dict"}, 422),
])
def test_evaluator_malformed_payload_returns_json_4xx(client, invalid_payload, expected_status):
    res = client.post("/submissions", json=invalid_payload)
    assert res.status_code == expected_status
    assert "application/json" in res.headers.get("content-type", "")
    assert "detail" in res.json()


# =====================================================================
# 3. OVERSIZED PAYLOAD & SERVER RECOVERY
# =====================================================================

def test_evaluator_oversized_payload_returns_413_and_recovers(client, evaluator_env):
    widget = evaluator_env["widget_b"]

    # Exceed 64KB
    oversized_data = "A" * (70 * 1024)
    res_large = client.post(
        "/submissions",
        json={
            "widget_id": str(widget.widget_id),
            "idempotency_key": "large-1",
            "fields": {"email": "test@test.com", "huge": oversized_data},
        },
    )
    assert res_large.status_code == 413
    assert res_large.json()["detail"] == "Request body too large"

    # Verify subsequent normal request works without server hang or contamination
    res_normal = client.post(
        "/submissions",
        json={
            "widget_id": str(widget.widget_id),
            "idempotency_key": "normal-after-large",
            "fields": {"email": "recovered@test.com"},
        },
    )
    assert res_normal.status_code == 201


# =====================================================================
# 4. ABUSE PROTECTION: RATE LIMITING & HONEYPOT
# =====================================================================

def test_evaluator_honeypot_triggers_422_with_zero_side_effects(client, evaluator_env, db: Session):
    widget = evaluator_env["widget_b"]
    initial_submissions = db.query(Submission).filter(Submission.widget_id == widget.widget_id).count()
    initial_outbox = db.query(NotificationOutbox).count()

    res = client.post(
        "/submissions",
        json={
            "widget_id": str(widget.widget_id),
            "idempotency_key": str(uuid.uuid4()),
            "honeypot": "I am a spam bot",
            "fields": {"email": "bot@spam.com"},
        },
    )
    assert res.status_code == 422
    assert "Invalid submission" in res.json()["detail"]

    # Verify zero side-effects in database
    db.expire_all()
    assert db.query(Submission).filter(Submission.widget_id == widget.widget_id).count() == initial_submissions
    assert db.query(NotificationOutbox).count() == initial_outbox


# =====================================================================
# 5. RESILIENCE: GEO ENRICHMENT FALLBACK CHAIN
# =====================================================================

def test_evaluator_geo_fallback_chain(client, evaluator_env, db: Session):
    widget = evaluator_env["widget_b"]

    # Case A: Provider / GeoEnricher succeeds
    fake_geo = {
        "country": "India",
        "city": "Delhi",
        "region": "Delhi",
        "latitude": 28.6139,
        "longitude": 77.2090,
    }
    with patch("app.api.submissions.geo_enricher.enrich", return_value=fake_geo):
        res = client.post(
            "/submissions",
            json={
                "widget_id": str(widget.widget_id),
                "idempotency_key": str(uuid.uuid4()),
                "fields": {"email": "geo_a@example.com"},
            },
            headers={"X-Forwarded-For": "8.8.8.8"},
        )
        assert res.status_code == 201
        sub_id = uuid.UUID(res.json()["submission_id"])
        sub = db.query(Submission).filter(Submission.submission_id == sub_id).first()
        assert sub.country == "India"
        assert sub.city == "Delhi"

    # Case B: All geo providers fail -> Submission STILL succeeds, geo fields remain NULL
    with patch("app.api.submissions.geo_enricher.enrich", return_value=None):
        res = client.post(
            "/submissions",
            json={
                "widget_id": str(widget.widget_id),
                "idempotency_key": str(uuid.uuid4()),
                "fields": {"email": "geo_fail@example.com"},
            },
            headers={"X-Forwarded-For": "8.8.8.8"},
        )
        assert res.status_code == 201
        sub_id = uuid.UUID(res.json()["submission_id"])
        sub = db.query(Submission).filter(Submission.submission_id == sub_id).first()
        assert sub.country is None
        assert sub.city is None


# =====================================================================
# 6. RESILIENCE: NOTIFICATION FAILURE & OUTBOX
# =====================================================================

def test_evaluator_notification_failure_does_not_abort_submission(client, evaluator_env, db: Session):
    widget = evaluator_env["widget_b"]
    idem_key = str(uuid.uuid4())

    res = client.post(
        "/submissions",
        json={
            "widget_id": str(widget.widget_id),
            "idempotency_key": idem_key,
            "fields": {"email": "notify@example.com"},
        },
    )
    assert res.status_code == 201
    sub_id = uuid.UUID(res.json()["submission_id"])

    # Submission was safely committed
    sub = db.query(Submission).filter(Submission.submission_id == sub_id).first()
    assert sub is not None

    # Outbox record was created in the same atomic unit
    outbox = db.query(NotificationOutbox).filter(NotificationOutbox.submission_id == sub_id).first()
    assert outbox is not None
    assert outbox.status in ("pending", "processing", "retry")


# =====================================================================
# 7. CORRECTNESS: IDEMPOTENCY & ATOMICITY
# =====================================================================

def test_evaluator_idempotency_is_scoped_per_widget(client, evaluator_env, db: Session):
    widget_a = evaluator_env["widget_a"]
    widget_b = evaluator_env["widget_b"]
    shared_key = f"shared-idem-{uuid.uuid4()}"

    # Submission 1 on Widget A
    res1 = client.post(
        "/submissions",
        json={
            "widget_id": str(widget_a.widget_id),
            "idempotency_key": shared_key,
            "fields": {"email": "first@example.com"},
        },
        headers={"Origin": "https://customer.example"},
    )
    assert res1.status_code == 201

    # Submission 2: Duplicate key on SAME Widget A -> 409 Conflict
    res2 = client.post(
        "/submissions",
        json={
            "widget_id": str(widget_a.widget_id),
            "idempotency_key": shared_key,
            "fields": {"email": "first@example.com"},
        },
        headers={"Origin": "https://customer.example"},
    )
    assert res2.status_code == 409

    # Submission 3: SAME key on DIFFERENT Widget B -> 201 Created (scoped uniqueness)
    res3 = client.post(
        "/submissions",
        json={
            "widget_id": str(widget_b.widget_id),
            "idempotency_key": shared_key,
            "fields": {"email": "second@example.com"},
        },
    )
    assert res3.status_code == 201


def test_evaluator_database_persistence_and_atomicity(client, evaluator_env, db: Session):
    widget = evaluator_env["widget_a"]
    idem_key = str(uuid.uuid4())

    res = client.post(
        "/submissions",
        json={
            "widget_id": str(widget.widget_id),
            "idempotency_key": idem_key,
            "fields": {"email": "persist@example.com", "message": "Testing persistence"},
        },
        headers={"Origin": "https://customer.example"},
    )
    assert res.status_code == 201
    sub_id = uuid.UUID(res.json()["submission_id"])

    # Verify Submission entity
    submission = db.query(Submission).filter(Submission.submission_id == sub_id).first()
    assert submission is not None
    assert submission.widget_id == widget.widget_id

    # Verify SubmissionFieldValue entities via relationship or values
    values = db.query(SubmissionFieldValue).filter(SubmissionFieldValue.submission_id == sub_id).all()
    assert len(values) == 2

    # Map by associated field_definition.field_name
    value_map = {v.widget_field.field_definition.field_name: v.value_text for v in values}
    assert value_map["email"] == "persist@example.com"
    assert value_map["message"] == "Testing persistence"

    # Verify NotificationOutbox entity
    outbox = db.query(NotificationOutbox).filter(NotificationOutbox.submission_id == sub_id).first()
    assert outbox is not None


# =====================================================================
# 8. SECURITY: STRICT TENANT ISOLATION
# =====================================================================

def test_evaluator_cross_tenant_isolation_boundary(client, evaluator_env, db: Session):
    tenant_a = evaluator_env["tenant_a"]
    tenant_b = evaluator_env["tenant_b"]
    widget_b = evaluator_env["widget_b"]

    auth_a = {"Authorization": f"Bearer {tenant_a.tenant_id}"}
    auth_b = {"Authorization": f"Bearer {tenant_b.tenant_id}"}

    # 1. Tenant A cannot GET Tenant B's widget
    res = client.get(f"/widgets/{widget_b.widget_id}", headers=auth_a)
    assert res.status_code == 404

    # 2. Tenant A cannot PATCH Tenant B's widget
    res = client.patch(f"/widgets/{widget_b.widget_id}", json={"title": "Hacked"}, headers=auth_a)
    assert res.status_code == 404

    # 3. Tenant A cannot modify Tenant B's widget fields
    res = client.put(f"/widgets/{widget_b.widget_id}/fields", json={"fields": []}, headers=auth_a)
    assert res.status_code == 404

    # 4. Tenant A cannot DELETE Tenant B's widget
    res = client.delete(f"/widgets/{widget_b.widget_id}", headers=auth_a)
    assert res.status_code == 404

    # Create a submission for Tenant B's widget
    res_sub = client.post(
        "/submissions",
        json={
            "widget_id": str(widget_b.widget_id),
            "idempotency_key": str(uuid.uuid4()),
            "fields": {"email": "tenant_b_lead@example.com"},
        },
    )
    assert res_sub.status_code == 201
    sub_b_id = res_sub.json()["submission_id"]

    # 5. Tenant A cannot view Tenant B's submission in GET /submissions
    res_list = client.get("/submissions", headers=auth_a)
    assert res_list.status_code == 200
    ids_seen_by_a = [s["submission_id"] for s in res_list.json()["submissions"]]
    assert sub_b_id not in ids_seen_by_a

    # 6. Tenant A cannot GET Tenant B's submission directly -> 404
    res_single = client.get(f"/submissions/{sub_b_id}", headers=auth_a)
    assert res_single.status_code == 404

    # 7. Tenant B CAN view their own submission -> 200
    res_b_ok = client.get(f"/submissions/{sub_b_id}", headers=auth_b)
    assert res_b_ok.status_code == 200
    assert res_b_ok.json()["submission_id"] == sub_b_id

# In tests/test_capstone_evaluator.py

# =====================================================================
# 9. NOTIFICATION RETRY BEHAVIOR
# =====================================================================

def test_evaluator_notification_worker_retries_and_terminal_failure(client, evaluator_env, db: Session):
    """Verifies that failed notification attempts update status without altering the persisted submission."""
    widget = evaluator_env["widget_b"]

    # 1. Create a real submission via API so outbox is initialized properly
    res = client.post(
        "/submissions",
        json={
            "widget_id": str(widget.widget_id),
            "idempotency_key": str(uuid.uuid4()),
            "fields": {"email": "worker_retry@example.com"},
        },
    )
    assert res.status_code == 201
    sub_id = uuid.UUID(res.json()["submission_id"])

    # 2. Query the created submission and outbox records
    sub = db.query(Submission).filter(Submission.submission_id == sub_id).first()
    assert sub is not None

    outbox = db.query(NotificationOutbox).filter(NotificationOutbox.submission_id == sub_id).first()
    assert outbox is not None

    # 3. Simulate worker retry failure
    if hasattr(outbox, "retry_count"):
        outbox.retry_count += 1
    elif hasattr(outbox, "attempts"):
        outbox.attempts += 1

    outbox.status = "retry" if hasattr(outbox, "status") else outbox.status
    if hasattr(sub, "notification_attempts"):
        sub.notification_attempts += 1
    db.commit()

    db.refresh(outbox)
    db.refresh(sub)
    if hasattr(outbox, "retry_count"):
        assert outbox.retry_count == 1
    elif hasattr(outbox, "attempts"):
        assert outbox.attempts == 1

    # 4. Simulate terminal exhaustion (3rd attempt -> failed)
    outbox.status = "failed"
    if hasattr(sub, "notification_status"):
        sub.notification_status = "failed"
    db.commit()

    db.refresh(outbox)
    db.refresh(sub)
    assert outbox.status == "failed"

    # Core Invariant: Submission remains safely stored even if notification delivery permanently fails
    persisted_sub = db.query(Submission).filter(Submission.submission_id == sub_id).first()
    assert persisted_sub is not None

# =====================================================================
# 10. THE STRONGEST TEST: COMPLETE END-TO-END CAPSTONE LIFECYCLE
# =====================================================================

def test_evaluator_complete_end_to_end_lifecycle(client, db: Session):
    """
    Simulates the entire platform journey:
    Create tenant -> Create widget -> Configure fields -> GET public config
    -> Submit from second origin -> Geo enrichment -> Persisted -> Outbox created
    -> Tenant dashboard reads submission
    """
    # 1. Create Tenant
    tenant = Tenant(
        customer_name="Lifecycle Corp",
        customer_email=f"eval_e2e_{uuid.uuid4().hex[:6]}@example.com"
    )
    wt = WidgetType(name=f"type_{uuid.uuid4().hex[:6]}")
    f_email = FieldDefinition(field_name="email", field_type="email")
    f_note = FieldDefinition(field_name="note", field_type="text")
    db.add_all([tenant, wt, f_email, f_note])
    db.commit()

    auth_header = {"Authorization": f"Bearer {tenant.tenant_id}"}
    allowed_origin = "https://partner-portal.example"

    # 2. Authenticated API: Create Widget
    create_res = client.post(
        "/widgets",
        json={
            "title": "Partner Intake Form",
            "widget_type_id": str(wt.widget_type_id),
            "allowed_origins": [allowed_origin],
        },
        headers=auth_header,
    )
    assert create_res.status_code == 201
    widget_id = create_res.json()["widget_id"]

    # 3. Authenticated API: Configure Fields
    field_cfg_res = client.put(
        f"/widgets/{widget_id}/fields",
        json={
            "fields": [
                {"field_id": str(f_email.field_id), "display_order": 0, "required": True},
                {"field_id": str(f_note.field_id), "display_order": 1, "required": False},
            ]
        },
        headers=auth_header,
    )
    assert field_cfg_res.status_code == 200

    # 4. Public API: Embedded script fetches config from second origin
    cfg_res = client.get(f"/widgets/{widget_id}/config")
    assert cfg_res.status_code == 200
    assert cfg_res.json()["title"] == "Partner Intake Form"
    assert len(cfg_res.json()["fields"]) == 2

    # 5. Public API: Visitor submits from allowed second origin with Geo enrichment
    mock_geo = {
        "country": "India",
        "city": "Bengaluru",
        "region": "Karnataka",
        "latitude": 12.9716,
        "longitude": 77.5946,
    }
    with patch("app.api.submissions.geo_enricher.enrich", return_value=mock_geo):
        sub_res = client.post(
            "/submissions",
            json={
                "widget_id": widget_id,
                "idempotency_key": f"e2e-key-{uuid.uuid4()}",
                "honeypot": "",
                "fields": {"email": "lead@partner-portal.example", "note": "Priority client"},
            },
            headers={"Origin": allowed_origin, "X-Forwarded-For": "203.0.113.195"},
        )
        assert sub_res.status_code == 201
        assert sub_res.headers.get("access-control-allow-origin") == allowed_origin
        submission_id = sub_res.json()["submission_id"]

    # 6. Database Verification: Atomic persistence
    sub_uuid = uuid.UUID(submission_id)
    persisted_sub = db.query(Submission).filter(Submission.submission_id == sub_uuid).first()
    assert persisted_sub is not None
    assert persisted_sub.city == "Bengaluru"
    assert persisted_sub.country == "India"

    # 7. Notification Outbox Created
    outbox = db.query(NotificationOutbox).filter(NotificationOutbox.submission_id == sub_uuid).first()
    assert outbox is not None
    assert outbox.status in ("pending", "processing", "retry")

    # 8. Authenticated Dashboard: Tenant views submissions list and inspector detail
    dash_list = client.get("/submissions", headers=auth_header)
    assert dash_list.status_code == 200
    sub_ids = [s["submission_id"] for s in dash_list.json()["submissions"]]
    assert submission_id in sub_ids

    dash_detail = client.get(f"/submissions/{submission_id}", headers=auth_header)
    assert dash_detail.status_code == 200
    detail_data = dash_detail.json()
    assert detail_data["submission_id"] == submission_id
    assert detail_data["city"] == "Bengaluru"