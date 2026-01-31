# ストリーミング遅延調査計画

作成日: 2026-01-31  
ブランチ: `investigate/streaming-latency`

---

## 目的

scrcpy 単体で実機画面を見た場合、遅延は肉眼でほぼ分からない。  
しかし本プロジェクト（Backend WS → JMuxer/MSE）経由では**明確に遅延が見える**。

この差を埋めるため、**どこで・どの程度の遅延が発生しているか**を計測し、ボトルネックを特定する。

---

## 調査対象（H.264 の流れに沿って）

今回の調査では、以下の各区間にタイムスタンプを仕込み、遅延を計測する。

| # | 区間 | 起点→終点 | 計測方法（案） |
|---|------|-----------|----------------|
| 1 | **scrcpy → TCP read** | scrcpy-server が encode → ScrcpyClient.stream() が chunk を受信 | chunk 受信時刻を記録 |
| 2 | **TCP read → NAL 抽出** | chunk 受信 → `_H264UnitExtractor.push()` 完了 | 処理前後の時刻差 |
| 3 | **NAL 抽出 → 購読者キュー** | NAL 生成 → `queue.put_nowait()` | NAL に生成時刻を付与し、キュー投入時に記録 |
| 4 | **キュー → WS send_bytes** | `queue.get()` → `websocket.send_bytes()` | get/send 時刻差 |
| 5 | **WS 送信 → ブラウザ受信** | Backend send → `ws.onmessage` 受信 | サーバ側に送信時刻を埋め込み、ブラウザで比較（時刻同期問題あり→差分で見る） |
| 6 | **ブラウザ受信 → JMuxer feed** | `onmessage` → `jmuxer.feed()` | feed 前後の時刻差 |
| 7 | **JMuxer → video 再生** | feed → `<video>` の実際表示 | video.currentTime / buffered.end の差、または timeupdate イベント遅延 |

---

## 仮説（優先順位順）

1. **JMuxer/MSE のバッファリング**（区間7）  
   - MSE は「再生開始までに一定バッファを溜める」設計のため、ここが支配的な可能性が高い
   - scrcpy 本体は MSE を使わず、直接 MediaCodec で描画しているので差が出やすい

2. **キュー待ち / ブロードキャスト処理**（区間3〜4）  
   - 購読者が多い or キューが詰まっている場合に遅延が積み上がる

3. **NAL 抽出処理**（区間2）  
   - 通常は軽量だが、バッファが大きい場合や再アライン処理で遅延する可能性

4. **ネットワーク（WS）**（区間5）  
   - localhost なら無視できるはず

---

## 計測方法（実装案）

### Backend 側（Python）

1. **chunk 受信時刻**  
   `ScrcpyClient.stream()` の `yield chunk` 直前に `time.perf_counter_ns()` を記録

2. **NAL 単位の生成時刻**  
   `_run_broadcast()` で NAL を生成した時刻をログ or NAL に付与  
   （バイナリに埋め込むのは難しいので、ログベースが現実的）

3. **WS 送信時刻**  
   `websocket.send_bytes()` 直前に時刻をログ

4. **ログフォーマット**  
   ```
   [LATENCY] chunk_recv=1706700000000000 nal_gen=1706700000100000 ws_send=1706700000200000 nal_type=5 size=12345
   ```

### Frontend 側（TypeScript）

1. **WS 受信時刻**  
   `ws.onmessage` で `performance.now()` を記録

2. **JMuxer feed 時刻**  
   `jmuxer.feed()` 直前に記録

3. **video 再生遅延**  
   定期的に `video.buffered.end(0) - video.currentTime` を計測（バッファ深さ＝遅延）

4. **ログ出力**  
   開発時のみ `console.log` or DevTools Performance タブ用マーカー

---

## 調査手順

### Phase 1: ログ仕込み（このブランチで実施）

1. [ ] Backend: `ScrcpyClient.stream()` に chunk 受信時刻ログ追加
2. [ ] Backend: `StreamSession._run_broadcast()` に NAL 生成/送信時刻ログ追加
3. [ ] Backend: `stream.py` の WS send に送信時刻ログ追加
4. [ ] Frontend: `useAndroidStream.ts` に受信/feed 時刻ログ追加
5. [ ] Frontend: video バッファ深さを定期計測してログ追加

### Phase 2: 計測実行（自動収集）

DevTools MCP を活用し、ログ収集から集計までを自動化する。

#### 2.1 Backend ログ収集

```bash
# バックエンドをフォアグラウンドで起動し、stdout を tee でファイルに保存
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 | tee ../work/latency-investigation/backend.log
```

または Docker の場合:
```bash
docker compose logs -f backend | tee work/latency-investigation/backend.log
```

#### 2.2 Frontend ログ収集（DevTools MCP 自動）

1. **ブラウザでストリーミング開始**
   - `activate_browser_navigation_tools` → ページを開く
   - または手動で http://localhost:5173 を開く

2. **一定時間待機**（10〜30秒）
   - 画面を動かしてストリーミングを発生させる

3. **コンソールログを自動取得**
   ```
   mcp_playwright_browser_console_messages(level="info")
   ```
   または
   ```
   activate_console_logging_tools → list_console_messages
   ```

4. **ログをファイルに保存**
   ```
   mcp_playwright_browser_console_messages(level="info", filename="work/latency-investigation/frontend.log")
   ```

#### 2.3 自動解析スクリプト

ログ収集後、以下のパターンで解析:

**Backend ログ解析（grep + awk）**
```bash
grep '\[LATENCY\]' work/latency-investigation/backend.log | \
  awk -F'[ =]' '{
    # chunk_recv, nal_gen, ws_send の差分を計算
    print $3, $5, $7, ($5-$3)/1000000 "ms", ($7-$5)/1000000 "ms"
  }'
```

**Frontend ログ解析**
```bash
grep '\[LATENCY\]' work/latency-investigation/frontend.log | \
  awk -F'[ =]' '{
    # ws_recv, feed, buffer_depth を抽出
    print $3, $5, $7
  }'
```

#### 2.4 集計（統計値）

Python スクリプトまたは手動で以下を算出:
- 各区間の平均 / p50 / p95 / max
- 区間別の寄与度（%）

---

### Phase 3: 分析・改善案

- ボトルネック区間を特定
- 改善策を検討（例: MSE バッファ設定、JMuxer flushingTime 調整、キュー戦略変更など）
- 改善後に再計測して効果を確認

---

## 成果物

- 計測結果の集計表（区間別遅延）
- ボトルネック特定レポート
- 改善案のリスト

---

## 次のアクション

1. この計画をレビューして問題なければ、Phase 1 のログ仕込みを開始

---

## 事前修正（調査開始前に実施済み）

### capture_manager.py の高頻度ログ削減

**問題**: `capture_manager.py` で 100 回ごとに INFO ログを出力しており、1秒間に約100回の read が走るため**毎秒1回**程度のログが出続けていた。

```
2026-01-31 14:26:08,087 - app.services.capture_manager - INFO - Capture rawvideo emulator-5554: read #31700, chunk=8192, total=259473152, buf=376832, w=1080, h=672
```

**影響**:
- ログ出力の I/O がブロッキングになり遅延の原因になる可能性
- 遅延調査時に本来見たいログがノイズで埋もれる

**修正内容**:
- 最初の 3 回は INFO のまま（初期動作確認用）
- 4 回目以降は **1000 回ごと** に **DEBUG** レベルに変更

該当箇所:
- `_read_rawvideo_loop()` 内の read ログ（596行目付近）
- `_feed_loop()` 内の chunk ログ（509行目付近）
