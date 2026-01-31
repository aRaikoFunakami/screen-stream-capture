# ストリーミング遅延計測結果

作成日: 2026-01-31

---

## 計測方針

ログ形式で測れる遅延に集中し、E2E（端末画面→ブラウザ表示）は人力で別途計測する。

### 計測対象

| # | 対象 | 目的 | 方法 |
|---|------|------|------|
| A | WebSocket RTT | 純粋なネットワーク遅延 | Echo WS で往復時間を計測 |
| B | Backend 処理遅延 | サーバ内部の生成→送信遅延 | 疑似NALを固定FPSで生成し、受信ジッタを計測 |
| C | scrcpy ストリーム | 実際のH.264配信頻度 | TCP chunk/NAL 到着間隔を計測 |

---

## A. WebSocket Echo RTT

**計測条件:**
- payload: 1024 bytes
- 回数: 100
- 間隔: 33ms

**結果:**

| 指標 | 値 |
|------|-----|
| avg | 3.15 ms |
| min | 0.99 ms |
| max | 20.85 ms |
| p50 | 3.07 ms |
| p95 | 3.95 ms |
| p99 | 20.85 ms |

**評価:** ✅ 問題なし。WebSocket 自体の遅延は 3ms 程度で十分低い。

---

## B. Synthetic Stream（疑似NAL配信）

**計測条件:**
- fps: 30
- payload: 4096 bytes
- duration: 10秒

**結果（受信ジッタ）:**

| 指標 | 値 |
|------|-----|
| avg | 3.55 ms |
| min | 0.01 ms |
| max | 14.41 ms |
| p50 | 2.65 ms |
| p95 | 9.68 ms |
| p99 | 11.22 ms |

**サーバ側ログ（send_ms）:**
- 0.06 ~ 1.5 ms

**評価:** ✅ 問題なし。Backend の処理遅延は 1ms 未満で、ジッタも 10ms 以下。

---

## C. scrcpy ストリーム

### クライアント側計測（受信間隔）

**計測条件:**
- 対象: emulator-5554
- duration: 10秒
- 画面状態: 静止（ほぼ変化なし）

**結果:**

| 指標 | 値 |
|------|-----|
| avg | 65.94 ms |
| min | 0.01 ms |
| max | 128.30 ms |
| p50 | 99.05 ms |
| p95 | 114.76 ms |
| p99 | 122.48 ms |

**評価:** ⚠️ **問題あり。30fps 設定なのに約 10fps しか来ていない。**

### サーバ側ログ（SCRCPY_CHUNK / NAL_BROADCAST）

**静止時:**
```
[SCRCPY_CHUNK] count=60 interval_ms=70.23  (~14fps)
[SCRCPY_CHUNK] count=90 interval_ms=101.58 (~10fps)
[SCRCPY_CHUNK] count=120 interval_ms=104.82 (~10fps)
```

**スワイプ中（画面更新あり）:**
```
[SCRCPY_CHUNK] count=330 interval_ms=15.95 (~62fps)
[SCRCPY_CHUNK] count=360 interval_ms=39.26 (~25fps)
[SCRCPY_CHUNK] count=390 interval_ms=26.84 (~37fps)
```

**評価:** scrcpy は画面更新がある時だけフレームを送る（デルタエンコード）。静止画面では FPS が大幅に低下する。

---

## 遅延源の分解

| 区間 | 遅延 | 問題レベル |
|------|------|-----------|
| WebSocket RTT | 3 ms | ✅ 問題なし |
| Backend 処理 | < 1 ms | ✅ 問題なし |
| Backend → Client 配信 | < 3 ms | ✅ 問題なし |
| **scrcpy フレーム生成** | **66-100 ms** | ⚠️ **ボトルネック** |

---

## 結論

### 主要なボトルネック

**scrcpy からのフレーム到着頻度が低い（静止時 10-15fps）。**

これは以下の要因による：
1. **scrcpy のデルタエンコード**: 画面変化がないとフレームを生成しない
2. **エミュレータの画面更新頻度**: 実機より低い可能性
3. **MediaCodec のバッファリング**: ハードウェアエンコーダの内部遅延

### WebSocket / Backend は問題なし

- WebSocket RTT: 3ms
- Backend 処理: < 1ms
- 配信ジッタ: < 10ms

これらはストリーミング遅延の原因ではない。

---

## 推奨アクション

### 短期（効果小）
1. ~~JMuxer flushingTime 調整~~ → 効果なし（既に問題なし）
2. ~~Backend ロック最適化~~ → 効果なし（既に問題なし）

### 中期（要検証）
1. **実機でのテスト**: エミュレータ特有の問題かを確認
2. **scrcpy の repeat-previous-frame-after オプション**: 静止時もフレームを送らせる（ただしエミュレータでは動作しない可能性）

### 長期（アーキテクチャ変更）
1. **WebCodecs API への移行**: MSE より低レイテンシ
2. **scrcpy 代替の検討**: ADB screenrecord 直接利用など

---

## 生データ

計測結果の JSON: [measurement-results.json](./measurement-results.json)

```json
{
  "echo_rtt": {
    "count": 100,
    "avg_ms": 3.148,
    "min_ms": 0.995,
    "max_ms": 20.849,
    "p50_ms": 3.07,
    "p95_ms": 3.951,
    "p99_ms": 20.849
  },
  "synthetic_jitter": {
    "count": 272,
    "avg_ms": 3.547,
    "min_ms": 0.011,
    "max_ms": 14.413,
    "p50_ms": 2.65,
    "p95_ms": 9.677,
    "p99_ms": 11.221
  },
  "scrcpy_interval": {
    "count": 152,
    "avg_ms": 65.937,
    "min_ms": 0.006,
    "max_ms": 128.296,
    "p50_ms": 99.05,
    "p95_ms": 114.758,
    "p99_ms": 122.48
  },
  "scrcpy_size": {
    "count": 153,
    "avg_ms": 2740.954,
    "min_ms": 10,
    "max_ms": 79894,
    "p50_ms": 1207,
    "p95_ms": 1384,
    "p99_ms": 79666
  }
}
```
