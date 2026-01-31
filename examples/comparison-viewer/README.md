# Comparison Viewer

MSE/JMuxer と WebCodecs の 2 つのプレイヤーを横に並べて比較するサンプルアプリケーションです。

## 機能

- **デバイス選択**: `adb track-devices` ベースの SSE でリアルタイムにデバイス一覧を取得
- **並列表示**: 選択したデバイスの画面を MSE 版と WebCodecs 版で同時に表示
- **レイテンシ比較**: 画面操作時の反映速度を視覚的に比較可能

## 起動方法

### 開発モード

```bash
cd examples/comparison-viewer/frontend
npm install
npm run dev
```

ブラウザで http://localhost:5174 を開く。

### バックエンドとの接続

バックエンド（FastAPI）が `http://localhost:8000` で起動している必要があります。

```bash
# バックエンド起動（Docker）
make up

# または直接起動
cd backend
uv run uvicorn app.main:app --reload
```

## 構成

```
frontend/
├── src/
│   ├── App.tsx                 # メインアプリケーション
│   ├── components/
│   │   ├── DeviceSelector.tsx  # デバイス選択 UI
│   │   └── ComparisonView.tsx  # MSE/WebCodecs 並列表示
│   └── main.tsx
├── vite.config.ts              # Vite 設定 (ポート 5174)
└── package.json
```

## プレイヤーの違い

| 項目 | MSE / JMuxer | WebCodecs |
|------|--------------|-----------|
| レイテンシ | 25-100ms | <10ms |
| ブラウザ互換性 | 高（Safari 対応） | Chrome/Edge のみ |
| デコード | JMuxer + MSE | VideoDecoder + Canvas |

## 注意事項

- WebCodecs は Chrome / Edge のみ対応
- Safari / Firefox では WebCodecs 側は非対応メッセージを表示
- 両方のプレイヤーが同じストリームを受信するため、帯域幅は 2 倍消費
