# app/main.py
import os
import uuid
from typing import Annotated
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.api.widgets import router as widgets_router
from app.api.submissions import router as submissions_router
from app.auth.dependencies import get_current_tenant
from app.models.tenant import Tenant
from app.api.widget_fields import router as widget_fields_router

app = FastAPI(title="Widget Platform API")

MAX_PUBLIC_SUBMISSION_BYTES = int(
    os.getenv("MAX_PUBLIC_SUBMISSION_BYTES", str(64 * 1024))
)


@app.middleware("http")
async def limit_public_submission_size(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/submissions":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )
            if declared_size < 0:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )
            if declared_size > MAX_PUBLIC_SUBMISSION_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )

        body = await request.body()
        if len(body) > MAX_PUBLIC_SUBMISSION_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive

    return await call_next(request)

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
    return current_tenant

app.include_router(widgets_router)
app.include_router(submissions_router)
app.include_router(widget_fields_router)