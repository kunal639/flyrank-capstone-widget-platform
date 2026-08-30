# app/main.py
from typing import Annotated
from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict
import uuid

from app.auth.dependencies import get_current_tenant
from app.models.tenant import Tenant

app = FastAPI(title="Widget Platform API")

class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    customer_name: str
    customer_email: str

@app.get("/health")
def health_check():
    return {"status" : "ok"}

@app.get("/me", response_model=TenantResponse)
def read_current_tenant(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """
    Returns the authenticated tenant context.
    Identity is extracted solely from the auth credential.
    """
    return current_tenant
