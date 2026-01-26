# 画面回転（縦/横）に Web 表示を追従させるノウハウ

対象: screen-stream-capture の backend と `packages/react-android-screen` を利用する人向け。

## 背景（何が起きるか）

Android 端末で縦/横（orientation）が切り替わると、scrcpy の raw H.264 ストリームは多くの場合「解像度が変わった別ストリーム」になります。

その結果、以下のような症状が出ます。

- Web 側（JMuxer）が古い SPS のままデコードして **真っ黒になる / 再生が止まる**
- 画面は再生できているが、CSS レイアウトが追従せず **縦横比が崩れる / 余白が変**
- backend 側のキャプチャ（ffmpeg decode → JPEG）が古い解像度のまま扱って **歪んだ画像**になる

このリポジトリでは、

- **SPS（Sequence Parameter Set）変化を検出して「デコーダ/プレイヤーをリセット」する**
- **video の intrinsic size 変化（`videoWidth`/`videoHeight`）に合わせてレイアウトを更新する**

という方針で対処しています。

## フロントエンド（react-android-screen）側の対処

### 結論: `H264Player` を貼るだけで OK

利用者側が回転を意識しなくてよいように、`H264Player` は以下を内部で行います。

- H.264 の SPS 変化を検出 → **JMuxer を作り直す**（`useAndroidStream`）
- JMuxer リセット完了後に `onResolutionChange` が呼ばれる → **aspect-ratio を更新**（`H264Player`）
- `loadedmetadata` / `resize` イベントでも **aspect-ratio を更新**（`H264Player`）

### 現在の仕様（期待動作）

`H264Player` をそのまま使った場合、画面回転（= 解像度変更）に対して次を保証する設計です。

- 回転直後にストリームが真っ黒にならず、再生が継続する（JMuxer をリセットして追従）
- 回転後の `videoWidth` / `videoHeight` に合わせて、表示の縦横比が崩れない（`aspect-ratio` を更新）
- リセット中に到着した H.264 データは破棄せず、一時バッファしてリセット完了後に投入する（黒画面の継続を避ける）

注意（設計通りの見え方）:

- 回転して「片方だけ縦長」になると、グリッド/カードレイアウトの都合で他カード側に余白が増えることがあります。
  これは `H264Player` の不具合ではなく、表示側のレイアウト（列の揃え方、固定高さ、`align-items` など）の問題です。
  余白を抑えたい場合は、アプリ側でレイアウト調整してください。

サンプル:

```tsx
import { H264Player } from 'react-android-screen'

export function Viewer() {
  return (
    <H264Player
      wsUrl="/api/ws/stream/<serial>"
      className="w-full"
    />
  )
}
```

#### 追加で CSS を書くなら

- `<video>` は `objectFit: 'contain'` なので、基本はコンテナ幅に合わせて収まります。
- 高さを固定したい場合は、親側で `max-height` / `height` を指定してください。

### `useAndroidStream` を直接使う場合

より自由に UI を組みたい場合は、`useAndroidStream` の `onResolutionChange` を使ってレイアウト更新を入れられます。

```tsx
import { useAndroidStream } from 'react-android-screen'

export function CustomViewer() {
  const { videoRef } = useAndroidStream({
    wsUrl: '/api/ws/stream/<serial>',
    autoConnect: true,
    onResolutionChange: () => {
      const video = videoRef.current
      if (video?.videoWidth && video?.videoHeight) {
        video.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`
      }
    },
  })

  return <video ref={videoRef} autoPlay muted playsInline />
}
```

## backend（capture）側の対処

backend のキャプチャ機能は、H.264 → ffmpeg デコード（rawvideo）→ JPEG エンコードという経路です。

画面回転で解像度が変わると、ffmpeg デコーダは古い解像度前提のままになり得るため、
SPS 変化を検出したら **ffmpeg デコーダプロセスを再起動**して追従させます。

関連実装:

- [backend/app/services/capture_manager.py](backend/app/services/capture_manager.py#L38)（SPS 検出）
- [capture の feed ループ](backend/app/services/capture_manager.py#L443)（SPS 変化で再起動）
- [デコーダ再起動](backend/app/services/capture_manager.py#L366)（ffmpeg 再起動 + 先頭チャンク再投入）

## もし追従しない場合のチェックリスト

- ブラウザ DevTools Console に `SPS changed (resolution change detected)` が出ているか
- WS が reconnect していないか（ネットワーク切断/プロキシ等）
- 親コンテナの CSS が `height: 100%` 固定で、`aspect-ratio` が効かない構造になっていないか

