"""Interactive CUI demo for android-capture-client.

This demo demonstrates that:
1. The main thread is never blocked by WebSocket operations
2. Screenshots can be captured on demand
3. The connection is properly cleaned up on exit

Usage:
    capture-demo --serial emulator-5554 --backend ws://localhost:8000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from . import CaptureSession, CaptureError

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
    print("  Android Screen Capture Demo")
    print("=" * 60)
    print()


def print_help() -> None:
    """Print help message."""
    print("\nCommands:")
    print("  c, capture    - Capture screenshot")
    print("  s, status     - Show connection status")
    print("  q, quit       - Quit the demo")
    print("  h, help       - Show this help")
    print()


def format_size(size: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def run_demo(
    serial: str,
    backend_url: str,
    output_dir: str,
    quality: int,
) -> None:
    """Run the interactive demo."""
    print_banner()
    print(f"  Serial:   {serial}")
    print(f"  Backend:  {backend_url}")
    print(f"  Output:   {output_dir}")
    print(f"  Quality:  {quality}")
    print()

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    capture_count = 0

    print("Connecting to backend...")
    logger.info("Main thread: Starting CaptureSession")

    try:
        with CaptureSession(serial, backend_url=backend_url) as session:
            print("✓ Connected!")
            print()
            print_help()

            # Demonstrate that main thread is not blocked
            logger.info("Main thread: CaptureSession is running in background")
            logger.info("Main thread: Entering interactive loop (not blocked)")

            while True:
                try:
                    # Non-blocking input prompt
                    print("\n> ", end="", flush=True)
                    
                    # Log to show main thread is responsive
                    logger.debug("Main thread: Waiting for user input (not blocked)")
                    
                    cmd = input().strip().lower()

                    if cmd in ("q", "quit", "exit"):
                        print("\nGoodbye!")
                        logger.info("Main thread: User requested quit")
                        break

                    elif cmd in ("h", "help", "?"):
                        print_help()

                    elif cmd in ("s", "status"):
                        print(f"\nStatus: {'Connected' if session.is_running else 'Disconnected'}")
                        print(f"Captures: {capture_count}")
                        print(f"Device: {serial}")

                    elif cmd in ("c", "capture", ""):
                        if cmd == "":
                            print("(capturing...)")
                        
                        logger.info("Main thread: Requesting capture")
                        start_time = time.perf_counter()

                        try:
                            result = session.capture(quality=quality)
                            elapsed = (time.perf_counter() - start_time) * 1000

                            capture_count += 1
                            filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                            filepath = output_path / filename
                            result.save(str(filepath))

                            print(f"\n✓ Captured: {result.width}x{result.height}")
                            print(f"  Size:     {format_size(len(result.jpeg_data))}")
                            print(f"  Time:     {elapsed:.0f}ms")
                            print(f"  Saved:    {filepath}")
                            
                            logger.info(f"Main thread: Capture completed in {elapsed:.0f}ms")

                        except CaptureError as e:
                            print(f"\n✗ Capture failed: {e.code} - {e.message}")
                            logger.error(f"Main thread: Capture error: {e}")
                        except TimeoutError as e:
                            print(f"\n✗ Capture timed out: {e}")
                            logger.error(f"Main thread: Capture timeout: {e}")

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

    logger.info("Main thread: Session ended cleanly")
    print(f"\nTotal captures: {capture_count}")


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
