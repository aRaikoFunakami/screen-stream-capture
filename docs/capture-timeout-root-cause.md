# CAPTURE_TIMEOUT の根本原因と対応（2026-01）

## TL;DR

- **主因**: `capture` の JPEG 生成パイプラインで使っている **ffmpeg が 1フレームもデコードできず（rawvideo 0 frames）**、待機側がタイムアウトしていた。
- **トリガー**: ffmpeg 起動オプションの `-fflags ...+nobuffer...` が、pipe 経由で流入する H.264 ストリーム条件と相性が悪く、フレーム確定に必要なバッファリングを阻害していた。
- **副因（不安定化要因）**: H.264 NAL の入力形式が **Annex-B 前提**になっており、環境によって **AVCC（length-prefixed）** で来るケースで境界抽出が崩れてデコード失敗に寄与していた。

本ドキュメントは、上記の現象が再発した際に「どこを見るべきか」「なぜ起きたか」「どう直したか」を短時間で再現・切り分けできるようにまとめたものです。

---

## 事象（Symptoms）

- `capture` WebSocket（JPEG の取得）が **`CAPTURE_TIMEOUT`** で失敗する。
- 一方で `stream` WebSocket（H.264 のストリーム）は接続でき、SPS/PPS/IDR 相当のデータが届いているように見える。
- ログ上は「映像が届いているのに、JPEG が一枚も生成されない」状態。

---

## アーキテクチャ（Relevant Path）

典型的な流れ:

1. Android から scrcpy 経由で H.264 を受信
2. `android-screen-stream` が H.264 を NAL 単位に抽出して WebSocket で配信
3. backend 側が受信した H.264 を ffmpeg に pipe で投入
4. ffmpeg が rawvideo にデコード → JPEG に変換
5. 生成された JPEG が `capture` WS クライアントへ返される

`CAPTURE_TIMEOUT` は、手順 3〜5 が「最初の1枚」を返す前にタイムアウトしたことを意味します。

---

## 根本原因（Root Cause）

### 1) ffmpeg が rawvideo を 0 frames のまま出力しなかった

`backend/app/services/capture_manager.py` の ffmpeg 起動オプションに以下が含まれていました:

- `-fflags +genpts+nobuffer+discardcorrupt`

このうち **`+nobuffer`** は低遅延志向のフラグですが、pipe 経由の H.264 入力（タイムスタンプ情報が乏しい／分割が不規則になりやすい）では、
デコーダがフレーム確定に必要な内部バッファを持てず、結果として **フレームが出ない（0 frames）** 状態を誘発しました。

このため、上流で H.264 が届いていても JPEG が一枚も生成されず、待機ロジックが `CAPTURE_TIMEOUT` になっていました。

#### 対応

- `backend/app/services/capture_manager.py` で **`+nobuffer` を削除**。
- 低遅延を維持したい場合でも「0 frames」の方が致命的なので、まずは確実にフレームが出る構成を優先する。

---

## 不安定化要因（Contributing Factors）

### 2) H.264 NAL 形式（Annex-B / AVCC）の揺れ

従来の NAL 抽出が Annex-B（`00 00 00 01` スタートコード）前提だったため、
入力が AVCC（4バイトの length prefix）で来ると NAL 境界が崩れ、ffmpeg への入力が壊れてデコード不能になり得ました。

#### 対応

- `packages/android-screen-stream/src/android_screen_stream/session.py` の抽出処理を、
  - Annex-B / AVCC の両方から NAL を抽出
  - 配信は **Annex-B に正規化**
 する実装へ更新。
- 先頭ゴミ（scrcpy のヘッダ等）が混入しても、SPS/PPS/IDR を見つけて整列できるようにする。

#### 再発防止（テスト）

- `backend/tests/test_h264_unit_extractor.py` を追加し、以下を検証:
  - Annex-B 抽出
  - AVCC → Annex-B 正規化
  - 先頭ゴミ混入時の整列

---

## 付随対応（Local / CI 安定化）

### 3) scrcpy-server.jar の探索パス

ローカル実行や pytest 実行で `SCRCPY_SERVER_JAR` が未指定の場合、Docker 想定のパス固定だと jar を見失うことがありました。

#### 対応

- `backend/app/core/config.py` で、`SCRCPY_SERVER_JAR` 未指定時に
  - Docker 想定の `/app/vendor/scrcpy-server.jar`
  - リポジトリ内 `vendor/scrcpy-server.jar`
  などの探索を行い、ローカルでも自動解決できるようにしました。

---

## 何を見れば切り分けが速いか（Debug Checklist）

1. `stream` 側で SPS/PPS/IDR 相当が届いているか
   - 届いているなら上流（scrcpy〜WS）は概ね生きている。
2. ffmpeg の stderr に「0 frames」「入力破損」「デコードできない」兆候がないか
   - **H.264 は届くが decode できない** が今回のパターン。
3. NAL 形式が Annex-B 前提で壊れていないか
   - AVCC 由来の length prefix をスタートコードと誤認していないか。

---

## 実行した検証（Evidence）

- 単体テスト:
  - `uv run --extra dev pytest backend/tests/test_h264_unit_extractor.py -v`
- E2E（capture WS）:
  - `uv run --extra dev pytest backend/tests/test_e2e_capture.py::test_capture_jpeg_via_websocket -v`

※ smartestiroid 側の pytest は別リポジトリで実行対象が異なるため、このドキュメントでは本リポジトリ側のみ記載します。
