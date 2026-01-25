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
