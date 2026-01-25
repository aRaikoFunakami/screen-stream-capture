#!/usr/bin/env python3
"""Test raw H.264 stream from scrcpy-server"""

import subprocess
import socket
import time
import os
import signal

DEVICE = "emulator-5554"
PORT = 27183
SERVER_JAR = "/data/local/tmp/scrcpy-server.jar"
VERSION = "3.3.4"
OUTPUT = "/tmp/test_raw.h264"

def run_cmd(cmd):
    """Run command and return output"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr

def main():
    # Kill existing
    run_cmd("pkill -f scrcpy-server 2>/dev/null")
    time.sleep(1)
    
    # Setup forward
    run_cmd(f"adb -s {DEVICE} forward --remove-all")
    result = run_cmd(f"adb -s {DEVICE} forward tcp:{PORT} localabstract:scrcpy")
    print(f"Forward setup: {result.strip()}")
    
    # Start server
    server_cmd = [
        "adb", "-s", DEVICE, "shell",
        f"CLASSPATH={SERVER_JAR}",
        "app_process", "/", "com.genymobile.scrcpy.Server", VERSION,
        "tunnel_forward=true",
        "audio=false",
        "control=false",
        "cleanup=false",
        "raw_stream=true",
        "max_size=720",
        "max_fps=15",
        "video_bit_rate=2000000",
    ]
    
    print(f"Starting server: {' '.join(server_cmd)}")
    server_proc = subprocess.Popen(
        server_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    
    time.sleep(2)
    
    # Read some server output
    print("Server output (non-blocking):")
    server_proc.stdout.readline()  # Read first line
    
    # Connect and receive
    print(f"Connecting to localhost:{PORT}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(("localhost", PORT))
        print("Connected!")
        
        # Receive data
        data = b""
        start = time.time()
        while time.time() - start < 5:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    print("Connection closed by server")
                    break
                data += chunk
                print(f"Received {len(chunk)} bytes, total: {len(data)}")
            except socket.timeout:
                break
        
        sock.close()
        
        if data:
            # Save to file
            with open(OUTPUT, "wb") as f:
                f.write(data)
            print(f"\nSaved {len(data)} bytes to {OUTPUT}")
            
            # Show first bytes
            print(f"First 32 bytes (hex): {data[:32].hex()}")
            
            # Try ffprobe
            result = run_cmd(f"ffprobe -f h264 {OUTPUT} 2>&1 | head -15")
            print(f"\nffprobe output:\n{result}")
        else:
            print("No data received!")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        server_proc.terminate()
        server_proc.wait()

if __name__ == "__main__":
    main()
