.PHONY: setup up down rebuild logs shell-backend download-scrcpy-server clean help

# scrcpy-server のバージョンとURL
SCRCPY_VERSION := 3.3.4
SCRCPY_SERVER_URL := https://github.com/Genymobile/scrcpy/releases/download/v$(SCRCPY_VERSION)/scrcpy-server-v$(SCRCPY_VERSION)
SCRCPY_SERVER_PATH := vendor/scrcpy-server.jar

# デフォルトターゲット
.DEFAULT_GOAL := help

# ヘルプ
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  setup           初期セットアップ（依存インストール + Docker ビルド + 起動）"
	@echo "  up              Docker コンテナ起動"
	@echo "  down            Docker コンテナ終了"
	@echo "  rebuild         完全再構築（イメージ削除 + 再ビルド + 起動）"
	@echo "  logs            ログ表示"
	@echo "  shell-backend   バックエンドコンテナにシェル接続"
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
	cd packages/react-android-screen && npm install
	cd examples/simple-viewer/frontend && npm install
	@echo "=== Building Docker images ==="
	docker compose build
	@echo "=== Starting containers ==="
	docker compose up -d
	@echo ""
	@echo "=== Setup complete ==="
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend: http://localhost:5173"
	@echo ""
	@echo "View logs: make logs"

# Docker 起動
up:
	docker compose up -d
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend: http://localhost:5173"

# Docker 終了
down:
	docker compose down

# 完全再構築
rebuild:
	@echo "=== Stopping and removing containers ==="
	docker compose down --rmi all --volumes --remove-orphans
	@echo "=== Rebuilding images ==="
	docker compose build --no-cache
	@echo "=== Starting containers ==="
	docker compose up -d
	@echo ""
	@echo "=== Rebuild complete ==="
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend: http://localhost:5173"

# ログ表示
logs:
	docker compose logs -f

# バックエンドシェル
shell-backend:
	docker compose exec backend /bin/bash

# クリーンアップ
clean:
	rm -rf vendor/scrcpy-server.jar
	rm -rf packages/android-screen-stream/.venv
	rm -rf packages/react-android-screen/node_modules
	rm -rf packages/react-android-screen/dist
	rm -rf examples/simple-viewer/frontend/node_modules
	rm -rf examples/simple-viewer/frontend/dist
	docker compose down --rmi all --volumes --remove-orphans 2>/dev/null || true
