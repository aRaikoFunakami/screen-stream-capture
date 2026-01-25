# Screen Stream Capture

複数の Android デバイスの画面を同時に Web ブラウザへ動画配信し、任意の瞬間にサーバー側で JPEG キャプチャを生成できる Web システム。

## 特徴

- **リアルタイム映像配信**: MSE + fMP4/H264 による低遅延ストリーミング
- **マルチデバイス対応**: 複数デバイスの同時視聴
- **オンデマンドキャプチャ**: 最新フレームから即座に JPEG 生成
- **自動デバイス検知**: adb track-devices によるイベント駆動

## クイックスタート

### 必要条件

- Python 3.12+
- Node.js 20+
- uv (Python パッケージマネージャー)
- adb (Android Debug Bridge)
- scrcpy
- ffmpeg

### セットアップ

```bash
# リポジトリのクローン
git clone <repository-url>
cd screen-stream-capture

# バックエンドのセットアップ
cd backend
uv sync

# フロントエンドのセットアップ
cd ../frontend
npm install
```

### 起動

```bash
# Makefile を使用（推奨）
make dev

# または個別に起動
# ターミナル 1: バックエンド
cd backend && uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# ターミナル 2: フロントエンド
cd frontend && npm run dev
```

### アクセス

- フロントエンド: http://localhost:5173
- バックエンド API: http://localhost:8000
- API ドキュメント: http://localhost:8000/docs

## プロジェクト構成

```
screen-stream-capture/
├── AGENTS.md           # AI エージェント向けガイド
├── README.md           # 本ファイル
├── Makefile            # 開発コマンド
├── backend/            # Python FastAPI バックエンド
│   ├── main.py         # アプリケーションエントリーポイント
│   ├── pyproject.toml  # Python 依存関係
│   └── uv.lock         # 依存関係ロックファイル
├── frontend/           # React + Vite フロントエンド
│   ├── src/
│   │   ├── App.tsx     # メインコンポーネント
│   │   └── main.tsx    # エントリーポイント
│   ├── package.json    # npm 依存関係
│   └── vite.config.ts  # Vite 設定
└── work/               # 設計書・計画書
    └── screen_stream_capture/
        ├── design.md   # 設計書
        ├── plan.md     # 作業計画
        └── notes.md    # 調査メモ
```

## API

### REST API

| エンドポイント | メソッド | 説明 |
|---------------|----------|------|
| `/healthz` | GET | ヘルスチェック |
| `/api/devices` | GET | デバイス一覧 |
| `/api/devices/{serial}/capture` | POST | 画面キャプチャ |
| `/api/stream/{serial}` | GET | 映像ストリーム |

### WebSocket

| エンドポイント | 説明 |
|---------------|------|
| `/ws/devices` | デバイス状態変更通知 |

## 開発

開発の詳細は [AGENTS.md](./AGENTS.md) を参照してください。

## ライセンス

MIT
