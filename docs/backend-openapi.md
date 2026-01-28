# Backend API ドキュメント（FastAPI / OpenAPI）

このプロジェクトの公式バックエンドは FastAPI を利用しており、OpenAPI を自動生成します。
手書きの API 仕様よりも、**実装と同期した OpenAPI** を正とする運用を推奨します。

## 参照先

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: [docs/openapi.json](openapi.json)（サーバー起動不要）

## REST API

- デバイス一覧: `GET /api/devices`
- デバイス詳細: `GET /api/devices/{serial}`
- デバイス変更イベント（SSE）: `GET /api/events`
- セッション一覧: `GET /api/sessions`

詳細は [docs/openapi.json](openapi.json) を参照。

## WebSocket API

OpenAPI は WebSocket を表現できないため、**ソースコードのdocstringが正**です。

### H.264 ストリーム: `WS /api/ws/stream/{serial}`

📄 ソース: [backend/app/api/endpoints/stream.py](../backend/app/api/endpoints/stream.py)

| 方向 | 形式 | 説明 |
|------|------|------|
| server → client | binary | H.264 NAL units（Annex-B形式） |

- 接続するとストリーミング開始、切断で終了
- 画面回転時はSPS/PPSが変更される

### JPEG キャプチャ: `WS /api/ws/capture/{serial}`

📄 ソース: [backend/app/api/endpoints/capture.py](../backend/app/api/endpoints/capture.py)

| 方向 | 形式 | 説明 |
|------|------|------|
| client → server | JSON | キャプチャリクエスト |
| server → client | JSON | 結果メタデータ |
| server → client | binary | JPEG画像 |

⚠️ **重要: 初期化待機時間**

WebSocket 接続後、最初のキャプチャリクエストを送信する前に **約6〜8秒の待機が必要** です。
これはバックエンドがH.264デコーダ（ffmpeg）を起動し、最初のフレームをデコードするのにかかる時間です。

| タイミング | 待機時間 | 説明 |
|-----------|---------|------|
| 接続直後 | 約6〜8秒 | デコーダ起動 + 最初のフレームデコード |
| 2回目以降 | 約60〜120ms | デコード済みフレームのJPEGエンコード |

待機せずにキャプチャリクエストを送信すると、`CAPTURE_TIMEOUT` エラーが返されます。

**リクエスト例**:
```json
{"type": "capture", "format": "jpeg", "quality": 80, "save": false}
```

**レスポンス例**:
```json
{"type": "capture_result", "capture_id": "...", "width": 1080, "height": 1920, ...}
```
（続いてJPEGバイナリが送信される）

## 環境変数

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `CAPTURE_OUTPUT_DIR` | キャプチャ画像の保存先 | `captures/` |
| `CAPTURE_JPEG_QUALITY` | JPEG品質（1〜100） | `80` |
| `STREAM_IDLE_TIMEOUT_SEC` | アイドル時のセッション停止秒数 | `5` |

## OpenAPI の更新

```bash
make openapi
```

`docs/openapi.json` が更新されます。
