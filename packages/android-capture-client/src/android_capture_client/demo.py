"""Interactive CUI demo for android-capture-client.

This demo demonstrates that:
1. The main thread is never blocked by WebSocket operations
2. Screenshots can be captured on demand (non-blocking)
3. The connection is properly cleaned up on exit
4. A background counter proves the main thread stays responsive

Usage:
    capture-demo --serial emulator-5554 --backend ws://localhost:8000
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import CaptureSession, CaptureError, CaptureResult

# Configure logging to show that background thread is working
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)-20s] %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_banner() -> None:
    """Print welcome banner."""
    print("\n" + "=" * 60)
    print("  Android Screen Capture Demo (Non-Blocking)")
    print("=" * 60)
    print()


def print_help() -> None:
    """Print help message."""
    print("\nCommands:")
    print("  c, capture    - Capture screenshot (non-blocking)")
    print("  b, burst      - Burst capture 5 shots (non-blocking)")
    print("  s, status     - Show connection status")
    print("  q, quit       - Quit the demo")
    print("  h, help       - Show this help")
    print()
    print("Note: A counter runs continuously to prove the main thread is not blocked.")
    print()


def format_size(size: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# Global state for non-blocking demo
_counter = 0
_counter_running = False
_pending_captures = 0
_capture_count = 0
_executor: ThreadPoolExecutor | None = None
_output_path: Path | None = None
_quality = 80


def _counter_loop() -> None:
    """Background counter to prove main thread responsiveness."""
    global _counter
    while _counter_running:
        _counter += 1
        time.sleep(0.1)


def _do_capture(capture_id: int, session: CaptureSession) -> tuple[int, CaptureResult | None, Exception | None]:
    """Execute capture in background thread."""
    try:
        start = time.perf_counter()
        result = session.capture(quality=_quality)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(f"CaptureWorker: Capture #{capture_id} took {elapsed_ms:.0f}ms")
        return (capture_id, result, None)
    except Exception as e:
        return (capture_id, None, e)


def _handle_capture_result(future: Future[tuple[int, CaptureResult | None, Exception | None]]) -> None:
    """Handle capture result (called from background thread)."""
    global _pending_captures, _capture_count
    _pending_captures -= 1
    
    try:
        capture_id, result, error = future.result()
    except Exception as e:
        print(f"\n[Capture] ✗ Failed: {e}")
        print(f"\n[counter={_counter}] > ", end="", flush=True)
        return
    
    if error:
        print(f"\n[Capture #{capture_id}] ✗ Failed: {error}")
    elif result and _output_path:
        _capture_count += 1
        filename = f"capture_{capture_id:03d}_{datetime.now().strftime('%H%M%S')}.jpg"
        filepath = _output_path / filename
        result.save(str(filepath))
        
        print(f"\n[Capture #{capture_id}] ✓ {result.width}x{result.height}, "
              f"{format_size(len(result.jpeg_data))}, saved: {filename}")
    
    print(f"\n[counter={_counter}] > ", end="", flush=True)


def capture_async(session: CaptureSession) -> int:
    """Start a non-blocking capture. Returns immediately."""
    global _pending_captures, _capture_count
    _pending_captures += 1
    capture_id = _capture_count + _pending_captures
    
    assert _executor is not None
    future = _executor.submit(_do_capture, capture_id, session)
    future.add_done_callback(_handle_capture_result)
    
    return capture_id


def run_demo(
    serial: str,
    backend_url: str,
    output_dir: str,
    quality: int,
) -> None:
    """Run the interactive demo."""
    global _counter_running, _executor, _output_path, _quality, _counter, _capture_count, _pending_captures
    
    print_banner()
    print(f"  Serial:   {serial}")
    print(f"  Backend:  {backend_url}")
    print(f"  Output:   {output_dir}")
    print(f"  Quality:  {quality}")
    print()

    # Create output directory
    _output_path = Path(output_dir)
    _output_path.mkdir(parents=True, exist_ok=True)
    _quality = quality
    _capture_count = 0
    _pending_captures = 0
    _counter = 0

    # Thread pool for non-blocking captures
    _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="CaptureWorker")

    print("Connecting to backend...")
    logger.info("Main thread: Starting CaptureSession")

    try:
        with CaptureSession(serial, backend_url=backend_url) as session:
            print("✓ Connected!")
            print()
            
            # Start background counter to prove main thread is responsive
            _counter_running = True
            counter_thread = threading.Thread(target=_counter_loop, name="Counter", daemon=True)
            counter_thread.start()
            logger.info("Main thread: Background counter started (proves responsiveness)")
            
            print_help()
            logger.info("Main thread: Entering interactive loop (never blocked)")

            while True:
                try:
                    print(f"\n[counter={_counter}] > ", end="", flush=True)
                    cmd = input().strip().lower()

                    if cmd in ("q", "quit", "exit"):
                        print("\nGoodbye!")
                        logger.info("Main thread: User requested quit")
                        break

                    elif cmd in ("h", "help", "?"):
                        print_help()

                    elif cmd in ("s", "status"):
                        print(f"\nStatus: {'Connected' if session.is_running else 'Disconnected'}")
                        print(f"Completed captures: {_capture_count}")
                        print(f"Pending captures: {_pending_captures}")
                        print(f"Counter (proof of responsiveness): {_counter}")
                        print(f"Device: {serial}")

                    elif cmd in ("c", "capture", ""):
                        counter_before = _counter
                        capture_id = capture_async(session)
                        counter_after = _counter
                        print(f"[Capture #{capture_id}] Started (non-blocking)")
                        print(f"  → Counter before: {counter_before}, after: {counter_after} (same = not blocked)")
                        logger.info(f"Main thread: Initiated capture #{capture_id}, returned immediately")

                    elif cmd in ("b", "burst"):
                        counter_before = _counter
                        print("Starting burst capture (5 shots)...")
                        for i in range(5):
                            cid = capture_async(session)
                            print(f"  [Capture #{cid}] Started")
                        counter_after = _counter
                        print(f"  → All 5 initiated, counter ticks: {counter_after - counter_before}")
                        logger.info("Main thread: Initiated 5 burst captures, returned immediately")

                    else:
                        print(f"Unknown command: {cmd}")
                        print_help()

                except KeyboardInterrupt:
                    print("\n\nInterrupted!")
                    logger.info("Main thread: Keyboard interrupt received")
                    break

    except ConnectionError as e:
        print(f"\n✗ Connection failed: {e}")
        logger.error(f"Main thread: Connection error: {e}")
        sys.exit(1)
    finally:
        _counter_running = False
        if _executor:
            _executor.shutdown(wait=False)

    logger.info("Main thread: Session ended cleanly")
    print(f"\nTotal captures: {_capture_count}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive demo for android-capture-client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-s", "--serial",
        default="emulator-5554",
        help="Android device serial number",
    )
    parser.add_argument(
        "-b", "--backend",
        default="ws://localhost:8000",
        help="Backend WebSocket URL",
    )
    parser.add_argument(
        "-o", "--output",
        default="./captures",
        help="Output directory for screenshots",
    )
    parser.add_argument(
        "-q", "--quality",
        type=int,
        default=80,
        help="JPEG quality (1-100)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_demo(
        serial=args.serial,
        backend_url=args.backend,
        output_dir=args.output,
        quality=args.quality,
    )


if __name__ == "__main__":
    main()
