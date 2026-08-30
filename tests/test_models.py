# tests/test_models.py
import pytest
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.widget_type import WidgetType

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