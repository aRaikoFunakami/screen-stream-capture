.PHONY: setup up down rebuild logs shell-backend download-scrcpy-server clean help openapi

# scrcpy-server のバージョンとURL
SCRCPY_VERSION := 3.3.4
SCRCPY_SERVER_URL := https://github.com/Genymobile/scrcpy/releases/download/v$(SCRCPY_VERSION)/scrcpy-server-v$(SCRCPY_VERSION)
SCRCPY_SERVER_PATH := vendor/scrcpy-server.jar

# OS 検出: Linux なら linux, それ以外（macOS）なら mac
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
    PROFILE := linux
else
    PROFILE := mac
endif

# デフォルトターゲット
.DEFAULT_GOAL := help

# ヘルプ
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Detected OS: $(UNAME_S) -> profile: $(PROFILE)"
	@echo ""
	@echo "Targets:"
	@echo "  setup           初期セットアップ（依存インストール + Docker ビルド + 起動）"
	@echo "  up              Docker コンテナ起動"
	@echo "  down            Docker コンテナ終了"
	@echo "  rebuild         完全再構築（イメージ削除 + 再ビルド + 起動）"
	@echo "  logs            ログ表示"
	@echo "  shell-backend   バックエンドコンテナにシェル接続"
	@echo "  openapi         OpenAPI スキーマを docs/openapi.json に出力"
	@echo "  clean           生成物を削除"
	@echo ""

# scrcpy-server ダウンロード
download-scrcpy-server:
	@mkdir -p vendor
	@if [ ! -f $(SCRCPY_SERVER_PATH) ]; then \
		echo "=== Downloading scrcpy-server v$(SCRCPY_VERSION) ==="; \
		curl -L -o $(SCRCPY_SERVER_PATH) $(SCRCPY_SERVER_URL); \
		echo "Downloaded to $(SCRCPY_SERVER_PATH)"; \
	else \
		echo "=== scrcpy-server already exists at $(SCRCPY_SERVER_PATH) ==="; \
	fi

# 初期セットアップ
setup: download-scrcpy-server
	@echo "=== Installing Python dependencies ==="
	cd packages/android-screen-stream && uv sync
	@echo "=== Installing NPM dependencies ==="
	cd packages/react-android-screen && npm install && npm run build
	cd examples/simple-viewer/frontend && npm install
	cd examples/comparison-viewer/frontend && npm install
	@echo "=== Building Docker images (profile: $(PROFILE)) ==="
	docker compose --profile $(PROFILE) build
	@echo "=== Starting containers ==="
	docker compose --profile $(PROFILE) up -d
	@echo ""
	@echo "=== Setup complete ==="
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend (simple-viewer):     http://localhost:5173"
	@echo "Frontend (comparison-viewer): http://localhost:5174"
	@echo ""
	@echo "View logs: make logs"

# Docker 起動
up:
	docker compose --profile $(PROFILE) up -d
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend (simple-viewer):     http://localhost:5173"
	@echo "Frontend (comparison-viewer): http://localhost:5174"

# Docker 終了
down:
	docker compose --profile $(PROFILE) down

# 完全再構築
rebuild: download-scrcpy-server
	@echo "=== Stopping and removing containers ==="
	docker compose --profile $(PROFILE) down --rmi all --volumes --remove-orphans
	@echo "=== Building local react-android-screen dist ==="
	cd packages/react-android-screen && npm install && npm run build
	@echo "=== Installing frontend dependencies ==="
	cd examples/simple-viewer/frontend && npm install
	cd examples/comparison-viewer/frontend && npm install
	@echo "=== Rebuilding images (profile: $(PROFILE)) ==="
	docker compose --profile $(PROFILE) build --no-cache
	@echo "=== Starting containers ==="
	docker compose --profile $(PROFILE) up -d
	@echo ""
	@echo "=== Rebuild complete ==="
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend (simple-viewer):     http://localhost:5173"
	@echo "Frontend (comparison-viewer): http://localhost:5174"

# ログ表示
logs:
	docker compose --profile $(PROFILE) logs -f

# バックエンドシェル
shell-backend:
	docker compose --profile $(PROFILE) exec backend-$(PROFILE) /bin/bash

# OpenAPI スキーマ出力
openapi:
	@echo "=== Exporting OpenAPI schema ==="
	cd backend && uv run python scripts/export_openapi.py
	@echo ""

# クリーンアップ
clean:
	rm -rf vendor/scrcpy-server.jar
	rm -rf packages/android-screen-stream/.venv
	rm -rf packages/react-android-screen/node_modules
	rm -rf packages/react-android-screen/dist
	rm -rf examples/simple-viewer/frontend/node_modules
	rm -rf examples/comparison-viewer/frontend/node_modules
	rm -rf examples/simple-viewer/frontend/dist
	docker compose --profile $(PROFILE) down --rmi all --volumes --remove-orphans 2>/dev/null || true
