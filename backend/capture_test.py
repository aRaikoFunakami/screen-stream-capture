#!/usr/bin/env python3
"""H.264ストリームをキャプチャしてファイルに保存するテストスクリプト"""

import asyncio
from scrcpy_client import ScrcpyRawClient


async def main():
    client = ScrcpyRawClient(device_serial="emulator-5554")
    print("Starting scrcpy client...")
    await client.start()
    print("Connected! Capturing stream...")
    
    total = 0
    with open('/tmp/test_stream.h264', 'wb') as f:
        async for data in client.stream():
            f.write(data)
            total += len(data)
            print(f'Received chunk: {len(data)} bytes, total: {total}')
            if total > 500000:  # 500KB
                break
    
    await client.stop()
    print(f'\n=== Captured {total} bytes to /tmp/test_stream.h264 ===')


if __name__ == "__main__":
    asyncio.run(main())
