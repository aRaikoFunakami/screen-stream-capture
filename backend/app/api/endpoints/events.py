"""SSE event endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.device_manager import get_device_manager
from app.services.sse_manager import get_sse_manager

router = APIRouter()


@router.get(
    "/events",
    summary="Device change events (SSE)",
    description=(
        "Server-Sent Events endpoint.\n\n"
        "- `event: devices` でデバイス一覧を配信\n"
        "- 接続直後に現在の一覧を1回送信し、その後は変更時に通知"
    ),
)
async def events() -> StreamingResponse:
    sse_manager = get_sse_manager()

    async def event_generator():
        device_manager = get_device_manager()
        devices = await device_manager.list_devices()
        data = json.dumps([d.to_dict() for d in devices])
        yield f"event: devices\ndata: {data}\n\n"

        async for message in sse_manager.subscribe():
            yield message

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
