"""Type definitions for android-capture-client."""

from __future__ import annotations

from dataclasses import dataclass


class CaptureError(Exception):
    """Capture operation failed."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass
class CaptureResult:
    """Result of a capture operation.
    
    Attributes:
        capture_id: Unique identifier for this capture
        serial: Device serial number
        width: Image width in pixels
        height: Image height in pixels
        jpeg_data: Raw JPEG image bytes
        captured_at: ISO timestamp when captured
        path: Server-side path if save=True, None otherwise
    """

    capture_id: str
    serial: str
    width: int
    height: int
    jpeg_data: bytes
    captured_at: str
    path: str | None = None

    def save(self, filepath: str) -> None:
        """Save the JPEG data to a file.
        
        Args:
            filepath: Path to save the JPEG file
        """
        with open(filepath, "wb") as f:
            f.write(self.jpeg_data)
