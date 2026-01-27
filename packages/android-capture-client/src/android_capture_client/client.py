"""WebSocket-based capture client for async usage."""

from __future__ import annotations

import asyncio
import json
import logging
from types import TracebackType
from typing import Self

import websockets
from websockets.asyncio.client import ClientConnection

from .types import CaptureError, CaptureResult

logger = logging.getLogger(__name__)


class CaptureClient:
    """Async WebSocket client for capturing Android screen.
    
    This client maintains a persistent WebSocket connection to the backend
    and allows capturing screenshots on demand.
    
    Usage:
        async with CaptureClient("emulator-5554") as client:
            result = await client.capture()
            result.save("screenshot.jpg")
    
    Or manually:
        client = CaptureClient("emulator-5554")
        await client.connect()
        try:
            result = await client.capture()
        finally:
            await client.disconnect()
    """

    def __init__(
        self,
        serial: str,
        backend_url: str = "ws://localhost:8000",
        connect_timeout: float = 10.0,
        capture_timeout: float = 30.0,
    ):
        """Initialize the capture client.
        
        Args:
            serial: Android device serial number (e.g., "emulator-5554")
            backend_url: WebSocket URL of the backend server
            connect_timeout: Timeout for WebSocket connection
            capture_timeout: Timeout for capture operation
        """
        self.serial = serial
        self.backend_url = backend_url.rstrip("/")
        self.connect_timeout = connect_timeout
        self.capture_timeout = capture_timeout
        
        self._ws: ClientConnection | None = None
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._connected and self._ws is not None

    async def connect(self) -> None:
        """Establish WebSocket connection to the backend.
        
        Raises:
            ConnectionError: If connection fails
        """
        if self._connected:
            return

        ws_url = f"{self.backend_url}/api/ws/capture/{self.serial}"
        logger.info(f"Connecting to {ws_url}")

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(ws_url),
                timeout=self.connect_timeout,
            )
            self._connected = True
            logger.info(f"Connected to capture WebSocket for {self.serial}")
        except asyncio.TimeoutError:
            raise ConnectionError(f"Connection timeout to {ws_url}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {ws_url}: {e}")

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._ws is not None:
            try:
                await self._ws.close()
                logger.info(f"Disconnected from capture WebSocket for {self.serial}")
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            finally:
                self._ws = None
                self._connected = False

    async def capture(
        self,
        quality: int = 80,
        save: bool = False,
    ) -> CaptureResult:
        """Capture a screenshot from the device.
        
        Args:
            quality: JPEG quality (1-100)
            save: Whether to save the capture on the server
            
        Returns:
            CaptureResult with the captured image data
            
        Raises:
            CaptureError: If capture fails
            ConnectionError: If not connected
        """
        if not self.is_connected or self._ws is None:
            raise ConnectionError("Not connected. Call connect() first.")

        async with self._lock:
            return await self._do_capture(quality, save)

    async def _do_capture(self, quality: int, save: bool) -> CaptureResult:
        """Internal capture implementation."""
        assert self._ws is not None

        # Send capture request
        request = {
            "type": "capture",
            "format": "jpeg",
            "quality": quality,
            "save": save,
        }
        await self._ws.send(json.dumps(request))
        logger.debug(f"Sent capture request: quality={quality}, save={save}")

        try:
            # Receive JSON metadata
            raw_meta = await asyncio.wait_for(
                self._ws.recv(),
                timeout=self.capture_timeout,
            )
            
            if isinstance(raw_meta, bytes):
                raise CaptureError("PROTOCOL_ERROR", "Expected JSON metadata, got binary")
            
            metadata = json.loads(raw_meta)
            
            # Check for error response
            if metadata.get("type") == "error":
                raise CaptureError(
                    metadata.get("code", "UNKNOWN"),
                    metadata.get("message", "Unknown error"),
                )
            
            if metadata.get("type") != "capture_result":
                raise CaptureError("PROTOCOL_ERROR", f"Unexpected message type: {metadata.get('type')}")

            # Receive JPEG binary
            jpeg_data = await asyncio.wait_for(
                self._ws.recv(),
                timeout=self.capture_timeout,
            )
            
            if not isinstance(jpeg_data, bytes):
                raise CaptureError("PROTOCOL_ERROR", "Expected binary JPEG data")

            logger.debug(f"Received capture: {metadata.get('width')}x{metadata.get('height')}, {len(jpeg_data)} bytes")

            return CaptureResult(
                capture_id=metadata.get("capture_id", ""),
                serial=metadata.get("serial", self.serial),
                width=metadata.get("width", 0),
                height=metadata.get("height", 0),
                jpeg_data=jpeg_data,
                captured_at=metadata.get("captured_at", ""),
                path=metadata.get("path"),
            )

        except asyncio.TimeoutError:
            raise CaptureError("TIMEOUT", "Capture operation timed out")
        except json.JSONDecodeError as e:
            raise CaptureError("PROTOCOL_ERROR", f"Invalid JSON: {e}")

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.disconnect()
