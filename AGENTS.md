# AGENTS.md

このリポジトリで AI（例: GitHub Copilot）と人間が作業するための **契約**。
迷ったらこのファイルを最優先する。

---

## 0. TL;DR（最重要だけ）

- 変更は **1ステップずつ**。各ステップで必ず検証する（バッチ変更禁止）
- 「カウントされる変更」以外に寄り道しない（ドリフト防止）
- Non-negotiables を破らない
- “直った/改善した”は **証拠（tests/metrics/diff）** が出てから言う
- 実行は必ず **制限付き**（timeout / スコープ / リソース）


## 2. 「カウントされる変更 / されない変更」

### 2.1 カウントされる（進捗）

- 新機能：<定義>（回帰テスト必須）
- バグ修正：<定義>（Fail→Pass テスト必須）
- 安定性：クラッシュ/パニック/例外の排除（回帰テスト必須）
- 終了性：タイムアウト/無限ループの排除（回帰テスト必須）
- 適合性：意味のあるテストカバレッジ追加
- UX：ユーザーに見える品質向上

### 2.2 カウントされない（ドリフト防止）

- ツール/インフラだけ：成果に直結しない変更
- パフォーマンスだけ：終了性や精度に繋がらない最適化
- ドキュメントだけ：混乱を解消しない文書追加

---

## 3. Non-negotiables（絶対禁止）

- 特定ケースだけ通すハック禁止（host名・特定入力・マジック値で帳尻合わせ等）
- 仕様ショートカット禁止（「動くからOK」禁止）
- <panic/例外握りつぶし> 禁止：<プロジェクト標準のエラー方針> を使う
- 無制限実行禁止：必ず timeout / スコープ制限をかける
- 巨大差分禁止：1PRの上限 <files/LOC>、逸脱時は分割

---

## 4. 証拠（Evidence）要件

### 4.1 証拠レベル

- 最良：自動テスト（Fail→Pass） + 回帰
- 次点：メトリクス（Before/After） + 再現手順
- 最低：手動確認ログ（スクショ/動画/チェックリスト）
- 禁止：「改善した」宣言のみ

### 4.2 主張→必要証拠

| 主張 | 必要な証拠 |
| --- | --- |
| バグを修正した | Fail→Pass テスト |
| 性能が改善した | Before/After（数値） + 再現スクリプト |
| 終了性を改善した | timeout/無限ループ再現→解消テスト |

---

## 5. 開発ループ（Single-step）

1) 現状確認（再現 or ベースライン取得）
2) 差異を1つ特定
3) 変更を1つ入れる
4) 直後に検証（tests/metrics）
5) ダメなら 2 に戻る

---

## 6. 実行（許可コマンド）

- ビルド：`timeout -k <k> <t> <build command>`
- テスト：`timeout -k <k> <t> <test command>`
- ベンチ：`timeout -k <k> <t> <bench command>`
- スコープ制限：<workspace/package/target の指定方法>



---

## クイックリファレンス

> **重要**: 作業開始前に必ず [README.md](./README.md) を確認してください。

| 項目 | 内容 |
|------|------|
| **プロジェクト名** | screen-stream-capture |
| **主要言語** | Python, TypeScript |
| **フレームワーク** | FastAPI, React |
| **パッケージマネージャー** | uv (Python), npm (Node.js) |
| **テストフレームワーク** | pytest, Jest |

---

## ⚠️ 作業前の必須確認事項

**作業を始める前に、以下のドキュメントを必ず確認すること：**

| ドキュメント | 確認するタイミング |
|-------------|-------------------|
| **[README.md](./README.md)** | プロジェクト全体の把握、セットアップ方法 |
| **[docs/architecture.md](./docs/architecture.md)** | アーキテクチャ詳細 |
| **[docs/api-reference.md](./docs/api-reference.md)** | API リファレンス |
| **[docs/backend-openapi.md](./docs/backend-openapi.md)** | FastAPI の自動生成 API ドキュメント（/docs）の見方 |

**重要**: 一般的なフレームワークの知識だけで推測して作業しないこと。プロジェクト固有のルールや設定を必ず確認してください。

---

## プロジェクト概要

### 説明

Android デバイスの画面を Web ブラウザにリアルタイムでストリーミングするライブラリ。scrcpy-server を活用し、H.264 ビデオストリームを WebSocket 経由でブラウザに送信、JMuxer でデコードして表示します。

### アーキテクチャ

アーキテクチャ: docs/architecture.md
バックエンドAPI: docs/api-reference.md (削除するか検討)
バックエンドAPI: docs/backend-openapi.md 
raw H.264 配信を途中から受信を実現する方法: docs/latest-join.md

---

## ディレクトリ構造

```
screen-stream-capture/
├── AGENTS.md                      # 本ファイル（AI向けガイド）
├── README.md                      # プロジェクト概要
├── Makefile                       # ビルド・起動コマンド
├── docker-compose.yml             # Docker Compose 設定
├── backend/                        # 公式 Backend (FastAPI)
├── packages/
│   ├── android-screen-stream/     # Python ライブラリ
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── src/android_screen_stream/
│   │       ├── __init__.py
│   │       ├── config.py          # StreamConfig
│   │       ├── client.py          # ScrcpyClient
│   │       └── session.py         # StreamSession, StreamManager
│   └── react-android-screen/      # React コンポーネント
│       ├── package.json
│       ├── README.md
│       └── src/
│           ├── index.ts
│           ├── H264Player.tsx
│           ├── useAndroidStream.ts
│           └── types.ts
├── examples/
│   └── simple-viewer/             # 使用例
│       └── frontend/
├── vendor/                        # scrcpy-server.jar（make setup でダウンロード）
├── docs/                          # ドキュメント
│   ├── architecture.md
│   └── api-reference.md
└── work/                          # 一時的な設計書・計画書
```

---

## 開発ガイド

### セットアップ

```bash
# 初期セットアップ（scrcpy-server ダウンロード + Docker ビルド + 起動）
make setup

# Docker 起動
make up

# Docker 終了
make down

# 完全再構築
make rebuild
```

### API ドキュメント（FastAPI / OpenAPI）

公式 backend（FastAPI）は OpenAPI を自動生成します。手書き仕様ではなく、
**実装から生成される OpenAPI を正**としてドキュメント運用します。

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

#### API 変更時のルール（重要）

API を追加/変更する場合は、FastAPI の仕組みを最大限活かして以下を必ず行うこと:

- ルータには `summary` / `description` を付ける
- `response_model` を付けてレスポンススキーマを固定する
- `tags` で分類し、`/docs` の見通しを良くする

#### 「自動生成されるもの」をどこに書くか

OpenAPI 自動生成は「生成物（openapi.json）をリポジトリに置く」のではなく、
**ソースコード側にドキュメント情報を埋め込む**運用にする。

- ルータ実装: `backend/app/api/endpoints/` に `summary` / `description` / `response_model` を書く
- スキーマ定義: `backend/app/api/schemas/` の Pydantic `BaseModel` + `Field(...)` で説明・例を付ける
   - 例: `Field(description=..., examples=[...])`

※ `openapi.json` は **実行時にオンデマンド生成**されるため、原則として Git 管理しない。
（例外: クライアント自動生成や契約テストでスキーマを成果物扱いする場合）

確認:

```bash
curl -fsS http://localhost:8000/openapi.json | head -c 200
```

### 依存関係管理

```bash
# Python パッケージの追加（android-screen-stream）
cd packages/android-screen-stream
uv add <package-name>

# NPM パッケージの追加（react-android-screen）
cd packages/react-android-screen
npm install <package-name>
```

### Python 依存関係管理（uv 必須）

Python の依存関係管理には **必ず uv を使用すること**。

```bash
# ライブラリの追加
uv add <package-name>

# 開発用ライブラリの追加
uv add --dev <package-name>

# 依存関係の同期
uv sync

# Python スクリプトの実行
uv run python script.py

# pytest の実行
uv run pytest tests/ -v
```

#### ⚠️ 禁止事項

- `pip install` を直接使用しない
- `requirements.txt` を手動で編集しない
- `pyproject.toml` の dependencies を手動で編集しない（uv add が自動管理）

---

## コーディング規約

### 全般

- **型安全性**: 可能な限り型を明示的に定義する
- **ドキュメント**: 公開 API には必ず docstring/JSDoc を記述する
- **テスト**: 新機能や修正には必ずテストを追加する
- **コミット**: 1 つの論理的な変更につき 1 コミット
- **非同期処理**: async/await を活用し、ブロッキング処理を避ける
- **図表の記述**: アーキテクチャ図やフロー図は Mermaid 形式で記述する（ASCII アートは使用しない）

### 命名規則

| 種類 | 規則 | 例 |
|------|------|-----|
| 変数・関数 | snake_case (Python) / camelCase (TS) | `get_user_data`, `getUserData` |
| クラス | PascalCase | `StreamSession` |
| 定数 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| ファイル | snake_case (Python) / kebab-case (TS) | `stream_session.py`, `H264Player.tsx` |

### Python コードスタイル

```python
from android_screen_stream import StreamSession, StreamConfig

# 型ヒントを使用
async def start_stream(serial: str, config: StreamConfig | None = None) -> StreamSession:
    """ストリーミングセッションを開始する

    Args:
        serial: Android デバイスのシリアル番号
        config: ストリーミング設定（省略時はデフォルト）

    Returns:
        開始されたストリーミングセッション
    """
    session = StreamSession(serial, server_jar="vendor/scrcpy-server.jar", config=config)
    await session.start()
    return session
```

### TypeScript コードスタイル

```tsx
import { H264Player } from 'react-android-screen'

interface StreamViewerProps {
  serial: string
  className?: string
}

const StreamViewer: React.FC<StreamViewerProps> = ({ serial, className }) => {
  return (
    <H264Player
      wsUrl={`/api/ws/stream/${serial}`}
      className={className}
      onConnected={() => console.log('connected')}
    />
  )
}
```

---

## 禁止事項

以下の行為は **禁止** です：

1. **テストなしでコードを変更しない**
2. **ドキュメントを更新せずに API を変更しない**
3. **ハードコードされた値を使用しない**（環境変数または設定ファイルを使用）
4. **計画せずに大規模な変更を始めない**（`work/` に計画書を作成してから実行）

---

## ⚠️ Docker 環境での注意事項

### adb サーバーへのアクセス

Docker コンテナから adb サーバーにアクセスするには、ホストの adb サーバーを使用します：

```yaml
# docker-compose.yml
environment:
  - ADB_SERVER_SOCKET=tcp:host.docker.internal:5037
extra_hosts:
  - "host.docker.internal:host-gateway"
```

**前提条件**: ホストで `adb start-server` が実行されていること。

### ボリュームマウント

editable install のため、ソースコードをマウントしています：

```yaml
volumes:
  - ./packages/android-screen-stream:/app/packages/android-screen-stream:ro
  - ./vendor:/app/vendor:ro
```

---

## 開発ワークフロー

### 基本サイクル

```
1. 課題/タスクを確認
   └─ 何を実装するか明確にする

2. 関連コードを調査
   └─ packages/ 内のライブラリ構造を理解

3. 実装
   └─ 既存のコードスタイルに従う

4. テストを追加・実行
   └─ 全テストがパスすることを確認

5. コミット
   └─ 意味のあるコミットメッセージ
```

### 大規模な変更のワークフロー

1. **計画書を作成**
   - `work/<feature_name>/plan.md` に計画を記述
   - 目的、変更範囲、リスクを明記

2. **ユーザーの承認を得る**
   - 計画の確認前に実装を開始しない

3. **段階的に実装**
   - 1 ステップごとに動作確認
   - 小さなコミットを積み重ねる

4. **ドキュメントを更新**
   - 完了後、`docs/` に成果物の説明を追加

---

## テスト

### テストの実行

```bash
# Python テスト
cd packages/android-screen-stream
uv run pytest tests/ -v

# TypeScript テスト
cd packages/react-android-screen
npm test
```

---

## トラブルシューティング

### よくある問題

| 症状 | 原因 | 対処 |
|------|------|------|
| adb が接続できない | adb サーバー未起動 | `adb start-server` を実行 |
| Docker ビルドエラー | キャッシュの問題 | `make rebuild` |
| ストリームが表示されない | デバイス未接続 | `adb devices` で確認 |
| scrcpy-server.jar がない | ダウンロード未実行 | `make setup` |

### デバッグ手順

1. **ログを確認**: `make logs`
2. **adb 接続確認**: `adb devices`
3. **ポート確認**: `lsof -i :8000` / `lsof -i :5173`

---

## 環境変数

| 変数名 | 説明 | デフォルト値 |
|--------|------|-------------|
| `SCRCPY_SERVER_JAR` | scrcpy-server.jar のパス | `vendor/scrcpy-server.jar` |
| `ADB_SERVER_SOCKET` | adb サーバーのソケット | - |

---

## 参考リンク

### プロジェクト内ドキュメント

- [README.md](./README.md) - プロジェクト概要
- [docs/architecture.md](./docs/architecture.md) - アーキテクチャ詳細
- [docs/api-reference.md](./docs/api-reference.md) - API リファレンス
- [packages/android-screen-stream/README.md](./packages/android-screen-stream/README.md) - Python ライブラリ
- [packages/react-android-screen/README.md](./packages/react-android-screen/README.md) - React コンポーネント

### 外部ドキュメント

- [scrcpy](https://github.com/Genymobile/scrcpy) - Android 画面ミラーリング
- [JMuxer](https://github.com/nicwaller/jmuxer) - H.264 → MSE 変換
- [FastAPI](https://fastapi.tiangolo.com/) - Python Web フレームワーク
- [uv](https://docs.astral.sh/uv/) - Python パッケージマネージャー

---

## 更新履歴

| 日付 | 変更内容 |
|------|----------|
| 2026-01-25 | ライブラリ化に伴い全面改訂 |
