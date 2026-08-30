# app/repositories/tenant.py
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from app.models.tenant import Tenant

class TenantRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, tenant_id: uuid.UUID) -> Optional[Tenant]:
        return self.db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()

    def get_by_email(self, email: str) -> Optional[Tenant]:
        return self.db.query(Tenant).filter(Tenant.customer_email == email).first()

    def create(self, customer_name: str, customer_email: str) -> Tenant:
        tenant = Tenant(
            customer_name=customer_name,
            customer_email=customer_email
        )
        self.db.add(tenant)
        self.db.flush()
        return tenant