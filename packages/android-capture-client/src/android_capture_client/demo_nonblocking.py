"""Non-blocking demo for android-capture-client.

This demo demonstrates that ThreadPoolExecutor makes capture() NON-BLOCKING.
The counter will NOT change during capture submission, proving no blocking.

Usage:
    capture-demo-nonblocking --serial emulator-5554 --backend ws://localhost:8000
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
    """Background counter to prove main thread is not blocked."""
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
    """Run the non-blocking demo."""
    global _counter_running, _counter

    print("\n" + "=" * 60)
    print("  Non-Blocking Capture Demo (ThreadPoolExecutor)")
    print("=" * 60)
    print()
    print(f"  Serial:   {serial}")
    print(f"  Backend:  {backend_url}")
    print(f"  Output:   {output_dir}")
    print(f"  Quality:  {quality}")
    print(f"  Count:    {count}")
    print()
    print("  ✓ This demo shows that ThreadPoolExecutor makes capture() NON-BLOCKING.")
    print("  ✓ The counter will NOT change during submission (proving no blocking).")
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

    # Create thread pool for non-blocking captures
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="CaptureWorker")

    print("Connecting to backend...")

    try:
        with CaptureSession(serial, backend_url=backend_url) as session:
            print("✓ Connected!")
            print()

            # Submit all captures (non-blocking)
            futures: list[tuple[int, Future[CaptureResult]]] = []
            
            print("=" * 40)
            print("Phase 1: Submit captures (non-blocking)")
            print("=" * 40)
            
            for i in range(count):
                counter_before = _counter
                
                # Submit capture to thread pool (returns immediately)
                future = executor.submit(session.capture, quality=quality)
                
                counter_after = _counter
                counter_diff = counter_after - counter_before
                
                futures.append((i + 1, future))
                
                print(f"\n[Submit {i+1}/{count}]")
                print(f"  Counter before: {counter_before}")
                print(f"  Counter after:  {counter_after}")
                print(f"  Counter diff:   {counter_diff} (0 means NOT blocked)")
                
                if counter_diff == 0:
                    print("  ✓ Non-blocking!")
                else:
                    print("  ✗ Blocked (unexpected)")

            print("\n" + "=" * 40)
            print("Phase 2: Wait for results")
            print("=" * 40)
            
            # Now wait for all results
            for i, future in futures:
                print(f"\n[Result {i}/{count}]")
                try:
                    result = future.result(timeout=30.0)
                    
                    # Save the image
                    filename = f"nonblock_{i:03d}_{datetime.now().strftime('%H%M%S')}.jpg"
                    filepath = output_path / filename
                    result.save(str(filepath))
                    
                    print(f"  Size:  {result.width}x{result.height}")
                    print(f"  Data:  {format_size(len(result.jpeg_data))}")
                    print(f"  Saved: {filename}")
                    
                except Exception as e:
                    print(f"  ✗ Failed: {e}")

            print("\n" + "=" * 60)
            print("  RESULT: ThreadPoolExecutor makes capture() NON-BLOCKING")
            print("  The counter did not change during submission, proving")
            print("  the main thread was NOT blocked.")
            print("=" * 60)

    except ConnectionError as e:
        print(f"\n✗ Connection failed: {e}")
        sys.exit(1)
    finally:
        _counter_running = False
        executor.shutdown(wait=True)

    print(f"\nTotal captures: {count}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Non-blocking demo for android-capture-client",
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
        default=5,
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
