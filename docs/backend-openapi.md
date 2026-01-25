# Backend API ドキュメント（FastAPI / OpenAPI）

このプロジェクトの公式バックエンドは FastAPI を利用しており、OpenAPI を自動生成します。
手書きの API 仕様よりも、**実装と同期した OpenAPI** を正とする運用を推奨します。

## 参照先

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## 使い方の例

- デバイス一覧: `GET /api/devices`
- デバイス詳細: `GET /api/devices/{serial}`
- デバイス変更イベント（SSE）: `GET /api/events`
- H.264 ストリーム（WebSocket）: `WS /api/ws/stream/{serial}`

## OpenAPI の保存（任意）

```bash
curl -fsS http://localhost:8000/openapi.json -o openapi.json
```

必要なら、この `openapi.json` を元に API クライアント生成（TypeScript / Python）を行えます。
