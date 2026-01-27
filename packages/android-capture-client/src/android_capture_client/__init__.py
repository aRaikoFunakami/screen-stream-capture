"""
android-capture-client - Client library for Android screen capture

Usage:
    # Async usage
    from android_capture_client import CaptureClient
    
    async with CaptureClient("emulator-5554") as client:
        result = await client.capture()
        with open("screenshot.jpg", "wb") as f:
            f.write(result.jpeg_data)
    
    # Sync usage (with background thread)
    from android_capture_client import CaptureSession
    
    with CaptureSession("emulator-5554") as session:
        result = session.capture()
"""

from .client import CaptureClient
from .session import CaptureSession
from .types import CaptureResult, CaptureError

__version__ = "0.1.0"

__all__ = [
    "CaptureClient",
    "CaptureSession",
    "CaptureResult",
    "CaptureError",
]
