# app/auth/dependencies.py
import uuid
from typing import Annotated
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tenant import Tenant
from app.repositories.tenant import TenantRepository

security = HTTPBearer(auto_error=False)

def get_current_tenant(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security)],
    db: Annotated[Session, Depends(get_db)],
) -> Tenant:
    """
    Resolves the authenticated tenant from the Authorization header.
    Supports passing tenant UUID or customer_email as token for local dev/testing.
    Raises 401 Unauthorized if missing or invalid.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    tenant_repo = TenantRepository(db)
    tenant = None

    # Try resolving by UUID
    try:
        tenant_uuid = uuid.UUID(token)
        tenant = tenant_repo.get_by_id(tenant_uuid)
    except ValueError:
        # Fallback: resolve by email identifier
        tenant = tenant_repo.get_by_email(token)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tenant