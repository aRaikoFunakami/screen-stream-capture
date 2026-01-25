#!/bin/bash
# Test script for raw H.264 stream from scrcpy-server

set -e

DEVICE="emulator-5554"
PORT=27183
OUTPUT="/tmp/raw_stream.h264"

echo "=== Setting up adb forward ==="
adb -s $DEVICE forward --remove-all 2>/dev/null || true
adb -s $DEVICE forward tcp:$PORT localabstract:scrcpy
echo "Forward set up on port $PORT"

echo ""
echo "=== Starting scrcpy-server ==="
adb -s $DEVICE shell CLASSPATH=/data/local/tmp/scrcpy-server.jar \
    app_process / com.genymobile.scrcpy.Server 3.3.4 \
    tunnel_forward=true \
    audio=false \
    control=false \
    cleanup=false \
    raw_stream=true \
    max_size=720 \
    max_fps=15 \
    video_bit_rate=2000000 &
SERVER_PID=$!

echo "Server PID: $SERVER_PID"
echo "Waiting for server to start..."
sleep 2

echo ""
echo "=== Connecting to stream ==="
rm -f $OUTPUT
timeout 5 nc localhost $PORT > $OUTPUT &
NC_PID=$!

echo "Receiving data for 5 seconds..."
sleep 6

echo ""
echo "=== Results ==="
if [ -f $OUTPUT ]; then
    SIZE=$(stat -f%z $OUTPUT 2>/dev/null || stat -c%s $OUTPUT 2>/dev/null)
    echo "File size: $SIZE bytes"
    
    if [ "$SIZE" -gt 0 ]; then
        echo "First 64 bytes (hex):"
        xxd -l 64 $OUTPUT
        
        echo ""
        echo "Testing with ffprobe:"
        ffprobe -f h264 $OUTPUT 2>&1 | head -10
    else
        echo "WARNING: File is empty!"
    fi
else
    echo "ERROR: Output file not created"
fi

# Cleanup
kill $SERVER_PID 2>/dev/null || true
echo ""
echo "=== Done ==="
