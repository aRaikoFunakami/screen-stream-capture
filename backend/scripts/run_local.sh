#!/usr/bin/env bash
# Docker なしでバックエンドをセットアップ & 起動するスクリプト
#
# Usage:
#   ./backend/scripts/run_local.sh [--setup-only] [--host HOST] [--port PORT]
#
# Options:
#   --setup-only  セットアップのみ実行（起動しない）
#   --host HOST   バインドするホスト（デフォルト: 127.0.0.1）
#   --port PORT   バインドするポート（デフォルト: 8000）

set -euo pipefail

# スクリプトのディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$BACKEND_DIR")"

# デフォルト値
HOST="127.0.0.1"
PORT="8000"
SETUP_ONLY=false

# 引数のパース
while [[ $# -gt 0 ]]; do
    case $1 in
        --setup-only)
            SETUP_ONLY=true
            shift
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== Screen Stream Capture Backend - Local Setup ==="
echo ""

# uv がインストールされているか確認
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# adb がインストールされているか確認
if ! command -v adb &> /dev/null; then
    echo "Warning: adb is not installed. Android device connection will not work."
fi

# scrcpy-server をダウンロード
SCRCPY_SERVER_PATH="$PROJECT_ROOT/vendor/scrcpy-server.jar"
if [[ ! -f "$SCRCPY_SERVER_PATH" ]]; then
    echo "=== Downloading scrcpy-server ==="
    cd "$PROJECT_ROOT"
    make download-scrcpy-server
else
    echo "=== scrcpy-server already exists ==="
fi

# バックエンドディレクトリに移動
cd "$BACKEND_DIR"

# android-screen-stream を editable install（まだされていない場合）
ANDROID_STREAM_PKG="$PROJECT_ROOT/packages/android-screen-stream"
echo "=== Installing dependencies ==="

# pyproject.toml に android-screen-stream が含まれているか確認
if ! grep -q "android-screen-stream" "$BACKEND_DIR/pyproject.toml" 2>/dev/null; then
    echo "Adding android-screen-stream as editable dependency..."
    uv add --editable "$ANDROID_STREAM_PKG"
fi

# 依存関係を同期
uv sync

echo ""
echo "=== Setup complete ==="

if [[ "$SETUP_ONLY" == true ]]; then
    echo ""
    echo "To start the backend, run:"
    echo "  cd backend && uv run uvicorn app.main:app --host $HOST --port $PORT --reload"
    exit 0
fi

echo ""
echo "=== Starting backend server ==="
echo "Host: $HOST"
echo "Port: $PORT"
echo ""
echo "Swagger UI: http://$HOST:$PORT/docs"
echo "Health check: http://$HOST:$PORT/api/health"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# バックエンド起動
exec uv run uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
