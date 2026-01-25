#!/bin/bash
# サーバーが起動していなければ起動する

cd "$(dirname "$0")/.."

# バックエンド確認・起動
if ! lsof -i :8000 2>/dev/null | grep -q LISTEN; then
    echo "Starting backend..."
    cd backend && nohup uv run uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
    cd ..
    sleep 2
fi

# フロントエンド確認・起動
if ! lsof -i :5173 2>/dev/null | grep -q LISTEN; then
    echo "Starting frontend..."
    cd frontend && nohup npm run dev > ../frontend.log 2>&1 &
    cd ..
    sleep 2
fi

# 状態表示
echo "=== Server Status ==="
echo -n "Backend (8000): "
lsof -i :8000 2>/dev/null | grep -q LISTEN && echo "RUNNING" || echo "NOT RUNNING"
echo -n "Frontend (5173): "
lsof -i :5173 2>/dev/null | grep -q LISTEN && echo "RUNNING" || echo "NOT RUNNING"
