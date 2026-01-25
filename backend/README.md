# screen-stream-capture backend

本リポジトリが提供する公式バックエンド（FastAPI）。

## API ドキュメント（FastAPI）

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## 提供API

- `GET /api/devices` デバイス一覧
- `GET /api/events` デバイス変更SSE
- `WS /api/ws/stream/{serial}` raw H.264 ストリーム

## 開発起動（Docker推奨）

プロジェクトルートで:

- `make setup`
- `make up`

フロントエンドのサンプルは [examples/simple-viewer/frontend](../examples/simple-viewer/frontend) を利用。
