"""Synchronous wrapper for CaptureClient with background thread."""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
import weakref
from concurrent.futures import Future
from types import TracebackType
from typing import Self

from .client import CaptureClient
from .types import CaptureResult

logger = logging.getLogger(__name__)

# Track all active sessions for cleanup at exit
_active_sessions: weakref.WeakSet[CaptureSession] = weakref.WeakSet()


def _cleanup_all_sessions() -> None:
    """Cleanup all active sessions on interpreter exit."""
    for session in list(_active_sessions):
        try:
            session.stop()
        except Exception as e:
            logger.warning(f"Error stopping session on exit: {e}")


atexit.register(_cleanup_all_sessions)


class CaptureSession:
    """Synchronous wrapper for CaptureClient that runs in a background thread.
    
    This class provides a blocking API for capturing screenshots while
    maintaining a persistent WebSocket connection in a background thread.
    The main application thread is never blocked by WebSocket operations.
    
    Usage with context manager (recommended):
        with CaptureSession("emulator-5554") as session:
            result = session.capture()
            result.save("screenshot.jpg")
    
    Manual usage:
        session = CaptureSession("emulator-5554")
        session.start()
        try:
            result = session.capture()
        finally:
            session.stop()
    """

    def __init__(
        self,
        serial: str,
        backend_url: str = "ws://localhost:8000",
        connect_timeout: float = 10.0,
        capture_timeout: float = 30.0,
    ):
        """Initialize the capture session.
        
        Args:
            serial: Android device serial number (e.g., "emulator-5554")
            backend_url: WebSocket URL of the backend server
            connect_timeout: Timeout for WebSocket connection
            capture_timeout: Timeout for capture operation
        """
        self.serial = serial
        self.backend_url = backend_url
        self.connect_timeout = connect_timeout
        self.capture_timeout = capture_timeout
        
        self._client: CaptureClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._stopping = False
        self._ready_event = threading.Event()
        self._error: Exception | None = None

    @property
    def is_running(self) -> bool:
        """Check if the session is running."""
        return self._started and not self._stopping

    def start(self) -> None:
        """Start the background thread and connect to the backend.
        
        This method blocks until the connection is established.
        
        Raises:
            RuntimeError: If already started
            ConnectionError: If connection fails
        """
        if self._started:
            raise RuntimeError("Session already started")

        self._error = None
        self._ready_event.clear()
        self._stopping = False

        # Start background thread
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name=f"CaptureSession-{self.serial}",
            daemon=True,  # Don't prevent program exit
        )
        self._thread.start()
        logger.info(f"Started background thread for {self.serial}")

        # Wait for connection
        if not self._ready_event.wait(timeout=self.connect_timeout + 5):
            self.stop()
            raise ConnectionError("Timeout waiting for connection")

        if self._error is not None:
            self.stop()
            raise self._error

        # Register for cleanup
        _active_sessions.add(self)
        self._started = True
        logger.info(f"CaptureSession ready for {self.serial}")

    def stop(self) -> None:
        """Stop the background thread and disconnect from the backend.
        
        This method is safe to call multiple times.
        """
        if self._stopping:
            return

        self._stopping = True
        logger.info(f"Stopping CaptureSession for {self.serial}")

        # Stop the event loop
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        # Wait for thread to finish
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning(f"Background thread did not stop cleanly for {self.serial}")

        self._loop = None
        self._thread = None
        self._client = None
        self._started = False
        logger.info(f"CaptureSession stopped for {self.serial}")

    def capture(
        self,
        quality: int = 80,
        save: bool = False,
        timeout: float | None = None,
    ) -> CaptureResult:
        """Capture a screenshot from the device.
        
        This method blocks until the capture is complete, but the actual
        WebSocket communication happens in the background thread.
        
        Args:
            quality: JPEG quality (1-100)
            save: Whether to save the capture on the server
            timeout: Timeout for the operation (default: capture_timeout)
            
        Returns:
            CaptureResult with the captured image data
            
        Raises:
            RuntimeError: If session not started
            CaptureError: If capture fails
            TimeoutError: If operation times out
        """
        if not self.is_running:
            raise RuntimeError("Session not started. Call start() first.")

        if timeout is None:
            timeout = self.capture_timeout

        # Create a future to get the result
        future: Future[CaptureResult] = Future()

        async def do_capture() -> None:
            try:
                assert self._client is not None
                result = await self._client.capture(quality=quality, save=save)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

        # Schedule on the event loop
        assert self._loop is not None
        asyncio.run_coroutine_threadsafe(do_capture(), self._loop)

        # Wait for result
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f"Capture timed out after {timeout}s")

    def _run_event_loop(self) -> None:
        """Run the event loop in the background thread."""
        try:
            # Create new event loop for this thread
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Run connection and wait
            self._loop.run_until_complete(self._connect_and_wait())

        except Exception as e:
            self._error = e
            logger.error(f"Event loop error: {e}")
        finally:
            # Cleanup
            if self._loop is not None:
                try:
                    self._loop.run_until_complete(self._disconnect())
                except Exception as e:
                    logger.warning(f"Error during disconnect: {e}")
                finally:
                    self._loop.close()
            self._ready_event.set()

    async def _connect_and_wait(self) -> None:
        """Connect to the backend and wait until stopped."""
        self._client = CaptureClient(
            serial=self.serial,
            backend_url=self.backend_url,
            connect_timeout=self.connect_timeout,
            capture_timeout=self.capture_timeout,
        )

        try:
            await self._client.connect()
            self._ready_event.set()

            # Keep running until stopped
            while not self._stopping:
                await asyncio.sleep(0.1)

        except Exception as e:
            self._error = e
            self._ready_event.set()
            raise

    async def _disconnect(self) -> None:
        """Disconnect from the backend."""
        if self._client is not None:
            await self._client.disconnect()

    def __enter__(self) -> Self:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.stop()
