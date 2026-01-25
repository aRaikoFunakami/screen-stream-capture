"""Device discovery endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas.device import Device
from app.services.device_manager import get_device_manager

router = APIRouter()


@router.get("/devices", response_model=list[Device], summary="List connected devices")
async def list_devices() -> list[dict]:
    device_manager = get_device_manager()
    devices = await device_manager.list_devices()
    return [d.to_dict() for d in devices]


@router.get("/devices/{serial}", response_model=Device, summary="Get device info")
async def get_device(serial: str) -> dict:
    device_manager = get_device_manager()
    device = await device_manager.get_device(serial)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {serial} not found")
    return device.to_dict()
