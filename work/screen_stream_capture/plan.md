# 作業計画: Screen Stream Capture System

## 概要

本計画書は、Android デバイス画面ストリーミングシステムの実装を段階的に進めるための作業計画である。
かならずTODO管理をしながら開発を進めなさい。

**設計書**: [design.md](./design.md)

---

## フェーズ構成

| フェーズ | 内容 | 期間目安 |
|---------|------|----------|
| Phase 1 | プロジェクト基盤構築 | 1日 |
| Phase 2 | デバイス管理基盤 | 1日 |
| Phase 3 | ストリーミング基盤 | 2日 |
| Phase 4 | キャプチャ機能 | 1日 |
| Phase 5 | フロントエンド基盤 | 1日 |
| Phase 6 | MSE 動画再生 | 2日 |
| Phase 7 | 統合・テスト | 1日 |
| Phase 8 | Appium 統合 | 1日 |

---

## Phase 1: プロジェクト基盤構築

### 目標
- Python/Node.js プロジェクト構造の確立
- 開発環境のセットアップ

### TODO

- [ ] **1.1** バックエンドプロジェクト初期化
  - [ ] `backend/` ディレクトリ作成
  - [ ] `pyproject.toml` 作成（uv 管理）
  - [ ] FastAPI, uvicorn 追加
  - [ ] `.python-version` 設定（3.12+）

- [ ] **1.2** フロントエンドプロジェクト初期化
  - [ ] `frontend/` ディレクトリ作成
  - [ ] Vite + React + TypeScript セットアップ
  - [ ] TailwindCSS 設定

- [ ] **1.3** 開発環境設定
  - [ ] `.gitignore` 作成
  - [ ] `README.md` 作成（セットアップ手順）
  - [ ] Makefile 作成（起動コマンド統一）

### 完了条件
- `uv run python -m uvicorn main:app` でサーバー起動
- `npm run dev` でフロントエンド起動
- `/healthz` エンドポイントが応答

---

## Phase 2: デバイス管理基盤

### 目標
- ADB デバイス検知の実装
- デバイス情報の取得・キャッシュ

### TODO

- [ ] **2.1** DeviceMonitor 実装
  - [ ] `backend/device_monitor.py` 作成
  - [ ] `adb track-devices` サブプロセス起動
  - [ ] イベントパース（add/remove/state）
  - [ ] コールバック登録機構

- [ ] **2.2** DeviceRegistry 実装
  - [ ] `backend/device_registry.py` 作成
  - [ ] デバイス情報データクラス定義
  - [ ] 登録/削除/取得メソッド
  - [ ] 状態変更通知

- [ ] **2.3** デバイス情報取得
  - [ ] `adb shell getprop` でモデル・メーカー取得
  - [ ] エミュレータ判定ロジック
  - [ ] 非同期実行（`asyncio.to_thread`）

- [ ] **2.4** REST API 実装
  - [ ] `GET /api/devices` エンドポイント
  - [ ] レスポンススキーマ定義（Pydantic）

- [ ] **2.5** WebSocket 実装
  - [ ] `WS /ws/devices` エンドポイント
  - [ ] 接続管理（ConnectionManager）
  - [ ] デバイス変更ブロードキャスト

### 完了条件
- デバイス接続で WebSocket にイベント配信
- `/api/devices` でデバイス一覧取得
- ポーリングなし（ログで確認）

---

## Phase 3: ストリーミング基盤

### 目標
- scrcpy + ffmpeg によるストリーミングパイプライン構築
- HTTP Streaming 配信

### TODO

- [ ] **3.1** ScrcpyStreamManager 実装
  - [ ] `backend/scrcpy_manager.py` 作成
  - [ ] scrcpy プロセス起動（パラメータ化）
  - [ ] H.264 ストリーム読み取り
  - [ ] プロセス停止・クリーンアップ

- [ ] **3.2** Fmp4Muxer 実装
  - [ ] `backend/fmp4_muxer.py` 作成
  - [ ] ffmpeg サブプロセス起動
  - [ ] stdin/stdout パイプ接続
  - [ ] Init Segment キャッシュ

- [ ] **3.3** StreamSession 実装
  - [ ] `backend/stream_session.py` 作成
  - [ ] asyncio.Queue によるマルチキャスト
  - [ ] 購読/解除管理
  - [ ] 全クライアント切断時のクリーンアップ

- [ ] **3.4** Streaming API 実装
  - [ ] `GET /api/stream/{serial}` エンドポイント
  - [ ] StreamingResponse 設定
  - [ ] Init Segment 先行送信

- [ ] **3.5** リソース管理
  - [ ] デバイス切断時のストリーム停止
  - [ ] プロセス残留防止（lifespan）
  - [ ] メモリリーク対策

### 完了条件
- curl でストリーム取得可能
- ffplay で再生確認
- デバイス切断で自動停止

---

## Phase 4: キャプチャ機能

### 目標
- 最新フレームからの JPEG 生成
- ダウンロード可能なレスポンス

### TODO

- [ ] **4.1** フレームバッファ実装
  - [ ] 最新フレーム保持機構
  - [ ] H.264 → raw frame デコード
  - [ ] スレッドセーフなアクセス

- [ ] **4.2** CaptureService 実装
  - [ ] `backend/capture_service.py` 作成
  - [ ] JPEG エンコード（OpenCV/Pillow）
  - [ ] 品質パラメータ対応

- [ ] **4.3** Capture API 実装
  - [ ] `POST /api/devices/{serial}/capture`
  - [ ] ファイル名生成（規則準拠）
  - [ ] Content-Disposition ヘッダー

### 完了条件
- キャプチャで JPEG 取得
- ファイル名形式が正しい
- 品質パラメータが機能

---

## Phase 5: フロントエンド基盤

### 目標
- 基本 UI レイアウト構築
- デバイス一覧表示

### TODO

- [ ] **5.1** レイアウト構築
  - [ ] Header コンポーネント
  - [ ] PanelGrid コンポーネント
  - [ ] Footer コンポーネント

- [ ] **5.2** デバイス管理 UI
  - [ ] useDevices フック（WebSocket）
  - [ ] DeviceSelector コンポーネント
  - [ ] リアルタイム更新確認

- [ ] **5.3** Panel 管理
  - [ ] Panel コンポーネント
  - [ ] 追加/削除ボタン
  - [ ] 状態管理（useState）

- [ ] **5.4** スタイリング
  - [ ] TailwindCSS 適用
  - [ ] レスポンシブ対応
  - [ ] ダークモード（任意）

### 完了条件
- デバイス選択 UI 動作
- Panel 追加/削除動作
- WebSocket でリアルタイム更新

---

## Phase 6: MSE 動画再生

### 目標
- ブラウザでの動画再生
- 複数ストリーム同時再生

### TODO

- [ ] **6.1** MSE ラッパー実装
  - [ ] useMSE フック作成
  - [ ] MediaSource 初期化
  - [ ] SourceBuffer 管理

- [ ] **6.2** VideoPlayer 実装
  - [ ] VideoPlayer コンポーネント
  - [ ] fetch + ReadableStream
  - [ ] appendBuffer 処理

- [ ] **6.3** エラーハンドリング
  - [ ] 接続切断検知
  - [ ] 自動再接続
  - [ ] エラー表示

- [ ] **6.4** 複数ストリーム対応
  - [ ] 同時再生テスト
  - [ ] パフォーマンス確認
  - [ ] メモリ使用量確認

### 完了条件
- 動画がスムーズに再生
- 複数デバイス同時再生
- 途中参加で正常再生

---

## Phase 7: 統合・テスト

### 目標
- エンドツーエンド動作確認
- バグ修正・最適化

### TODO

- [ ] **7.1** キャプチャ UI 実装
  - [ ] CaptureButton コンポーネント
  - [ ] ダウンロード処理
  - [ ] 成功/失敗フィードバック

- [ ] **7.2** 統合テスト
  - [ ] 全機能の動作確認
  - [ ] エッジケーステスト
  - [ ] 負荷テスト（複数デバイス）

- [ ] **7.3** バグ修正
  - [ ] 発見された問題の修正
  - [ ] パフォーマンス最適化
  - [ ] メモリリーク確認

- [ ] **7.4** ドキュメント整備
  - [ ] README 更新
  - [ ] API ドキュメント
  - [ ] トラブルシューティング

### 完了条件
- 全受け入れ条件クリア
- ドキュメント完備

---

## Phase 8: Appium 統合

### 目標
- Appium サーバーの自動管理
- アプリケーション終了時の確実な停止

### TODO

- [ ] **8.1** AppiumManager 実装
  - [ ] `backend/appium_manager.py` 作成
  - [ ] 空きポート確保
  - [ ] プロセス起動/停止
  - [ ] readiness チェック

- [ ] **8.2** lifespan 統合
  - [ ] FastAPI lifespan 設定
  - [ ] 起動時に Appium 起動
  - [ ] 終了時に確実停止

- [ ] **8.3** シグナルハンドリング
  - [ ] SIGINT/SIGTERM 対応
  - [ ] 例外時のクリーンアップ
  - [ ] プロセス残留テスト

- [ ] **8.4** ヘルスチェック拡張
  - [ ] `/healthz` に Appium 状態追加
  - [ ] 異常時の自動再起動（任意）

### 完了条件
- サーバー起動で Appium 自動起動
- サーバー終了で Appium 確実停止
- プロセス残留なし

---

## 進捗トラッキング

### 全体進捗

| フェーズ | 状態 | 完了日 |
|---------|------|--------|
| Phase 1 | ⬜ 未着手 | - |
| Phase 2 | ⬜ 未着手 | - |
| Phase 3 | ⬜ 未着手 | - |
| Phase 4 | ⬜ 未着手 | - |
| Phase 5 | ⬜ 未着手 | - |
| Phase 6 | ⬜ 未着手 | - |
| Phase 7 | ⬜ 未着手 | - |
| Phase 8 | ⬜ 未着手 | - |

### 記号凡例

- ⬜ 未着手
- 🔄 進行中
- ✅ 完了
- ⏸️ 保留

---

## 注意事項

### 作業の進め方

1. **1 フェーズずつ完了させる**
   - 次のフェーズに進む前に完了条件を確認
   - 途中で他フェーズに手を出さない

2. **動作確認を頻繁に行う**
   - 各 TODO 完了時に動作確認
   - 問題発見は早期に対処

3. **コミット粒度**
   - 1 TODO = 1 コミット目安
   - 意味のあるコミットメッセージ

### 技術的な注意

1. **非同期処理**
   - すべての I/O は async/await
   - ブロッキング処理は `asyncio.to_thread`

2. **リソース管理**
   - プロセス起動したら必ず停止処理
   - メモリリークに注意

3. **エラーハンドリング**
   - 例外は適切にキャッチ
   - クリーンアップは finally で

---

## 参考資料

- [order.md](../../order.md) - 元の要件定義
- [investigations.md](../../investigations.md) - 事前調査結果
- [design.md](./design.md) - 設計書
