"""
android-screen-stream - Android screen streaming library using scrcpy-server

Usage:
    from android_screen_stream import ScrcpyClient, StreamSession, StreamConfig

    # Low-level client
    async with ScrcpyClient("emulator-5554", server_jar="path/to/scrcpy-server.jar") as client:
        async for chunk in client.stream():
            process(chunk)

    # Session with multicast support
    session = StreamSession("emulator-5554", server_jar="path/to/scrcpy-server.jar")
    await session.start()
    async for chunk in session.subscribe():
        await websocket.send_bytes(chunk)
"""

from .config import StreamConfig
from .client import ScrcpyClient
from .session import StreamSession, StreamManager

__version__ = "0.1.0"

__all__ = [
    "StreamConfig",
    "ScrcpyClient",
    "StreamSession",
    "StreamManager",
]
