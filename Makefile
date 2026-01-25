.PHONY: dev dev-backend dev-frontend build clean

# 開発サーバー起動（バックエンド + フロントエンド）
dev:
	@echo "Starting development servers..."
	@make -j2 dev-backend dev-frontend

# バックエンド開発サーバー
dev-backend:
	cd backend && uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# フロントエンド開発サーバー
dev-frontend:
	cd frontend && npm run dev

# 依存関係インストール
install:
	cd backend && uv sync
	cd frontend && npm install

# ビルド
build:
	cd frontend && npm run build

# クリーンアップ
clean:
	rm -rf backend/.venv
	rm -rf backend/__pycache__
	rm -rf frontend/node_modules
	rm -rf frontend/dist

# バックエンドのみ起動
backend:
	cd backend && uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# フロントエンドのみ起動
frontend:
	cd frontend && npm run dev

# ヘルスチェック
health:
	curl -s http://localhost:8000/healthz | python -m json.tool

# バックグラウンドで開発サーバー起動
dev-bg:
	@echo "Starting servers in background..."
	@lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	@lsof -ti :5173 | xargs kill -9 2>/dev/null || true
	@sleep 1
	@cd backend && nohup uv run uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
	@cd frontend && nohup npm run dev > ../frontend.log 2>&1 &
	@sleep 3
	@$(MAKE) status

# サーバー停止
stop:
	@echo "Stopping servers..."
	@lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	@lsof -ti :5173 | xargs kill -9 2>/dev/null || true
	@echo "Servers stopped"

# サーバー状態確認
status:
	@echo "=== Server Status ==="
	@echo "Backend (8000):"
	@lsof -i :8000 2>/dev/null | grep LISTEN || echo "  NOT RUNNING"
	@echo "Frontend (5173):"
	@lsof -i :5173 2>/dev/null | grep LISTEN || echo "  NOT RUNNING"

# ログ確認
logs:
	@echo "=== Backend Log (last 20 lines) ==="
	@tail -20 backend/server.log 2>/dev/null || echo "No log file"
	@echo ""
	@echo "=== Frontend Log (last 20 lines) ==="
	@tail -20 frontend.log 2>/dev/null || echo "No log file"
