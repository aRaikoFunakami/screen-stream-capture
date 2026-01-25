"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.device import HealthzResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthzResponse, summary="Health check")
@router.get("/api/healthz", include_in_schema=False)
async def healthz() -> HealthzResponse:
    return HealthzResponse(status="ok", version="0.1.0")
