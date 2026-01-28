"""Simple demo for android-capture-client.

This demo demonstrates that CaptureSession.capture() is a BLOCKING call.
The counter will change during capture, proving the main thread is blocked.

Usage:
    capture-demo-simple --serial emulator-5554 --backend ws://localhost:8000
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import CaptureSession, CaptureError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)-20s] %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def format_size(size: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# Global counter for demonstration
_counter = 0
_counter_running = False


def _counter_loop() -> None:
    """Background counter to prove main thread blocking."""
    global _counter
    while _counter_running:
        _counter += 1
        time.sleep(0.1)


def run_demo(
    serial: str,
    backend_url: str,
    output_dir: str,
    quality: int,
    count: int,
) -> None:
    """Run the simple blocking demo."""
    global _counter_running, _counter

    print("\n" + "=" * 60)
    print("  Simple Capture Demo (BLOCKING)")
    print("=" * 60)
    print()
    print(f"  Serial:   {serial}")
    print(f"  Backend:  {backend_url}")
    print(f"  Output:   {output_dir}")
    print(f"  Quality:  {quality}")
    print(f"  Count:    {count}")
    print()
    print("  ⚠️  This demo shows that capture() BLOCKS the main thread.")
    print("  ⚠️  The counter will change during capture (proving blocking).")
    print()

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Start background counter
    _counter = 0
    _counter_running = True
    counter_thread = threading.Thread(target=_counter_loop, name="Counter", daemon=True)
    counter_thread.start()
    logger.info("Background counter started")

    print("Connecting to backend...")

    try:
        with CaptureSession(serial, backend_url=backend_url) as session:
            print("✓ Connected!")
            print()

            for i in range(count):
                print(f"\n[Capture {i+1}/{count}]")
                
                counter_before = _counter
                print(f"  Counter before: {counter_before}")
                
                start_time = time.perf_counter()
                
                # This is a BLOCKING call
                logger.info(f"Calling capture() - this will BLOCK...")
                result = session.capture(quality=quality)
                
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                counter_after = _counter
                
                print(f"  Counter after:  {counter_after}")
                print(f"  Counter diff:   {counter_after - counter_before} (>0 means BLOCKED)")
                print(f"  Elapsed:        {elapsed_ms:.0f}ms")
                print(f"  Size:           {result.width}x{result.height}")
                print(f"  Data:           {format_size(len(result.jpeg_data))}")
                
                # Save the image
                filename = f"simple_{i+1:03d}_{datetime.now().strftime('%H%M%S')}.jpg"
                filepath = output_path / filename
                result.save(str(filepath))
                print(f"  Saved:          {filename}")

            print("\n" + "=" * 60)
            print("  RESULT: capture() is a BLOCKING call")
            print("  The counter changed during capture, proving the main")
            print("  thread was blocked waiting for the result.")
            print("=" * 60)

    except ConnectionError as e:
        print(f"\n✗ Connection failed: {e}")
        sys.exit(1)
    except CaptureError as e:
        print(f"\n✗ Capture failed: {e}")
        sys.exit(1)
    finally:
        _counter_running = False

    print(f"\nTotal captures: {count}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Simple blocking demo for android-capture-client",
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
        "-n", "--count",
        type=int,
        default=3,
        help="Number of captures",
    )

    args = parser.parse_args()

    run_demo(
        serial=args.serial,
        backend_url=args.backend,
        output_dir=args.output,
        quality=args.quality,
        count=args.count,
    )


if __name__ == "__main__":
    main()
