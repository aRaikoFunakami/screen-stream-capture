// RemoteControlLayer の座標変換(object-fit の余白を除いた映像領域に対する 0..1)のテスト。npm test(build 後)で実行。
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mapToVideo } from '../dist/RemoteControlLayer.js'

const rect = { left: 100, top: 50, width: 800, height: 800 } // 正方形の枠に 16:10 の映像 → 上下に余白

test('contain: 映像の中央は 0.5,0.5', () => {
  assert.deepEqual(mapToVideo(500, 450, rect, 1280, 800), { x: 0.5, y: 0.5 })
})
test('contain: 上下の余白は映像の外(null)', () => {
  assert.equal(mapToVideo(500, 60, rect, 1280, 800), null)
})
test('contain: 映像の左上端は 0,0', () => {
  // 表示高さ 500 → 上余白 150
  assert.deepEqual(mapToVideo(100, 200, rect, 1280, 800), { x: 0, y: 0 })
})
test('映像サイズ未確定なら null', () => {
  assert.equal(mapToVideo(500, 450, rect, 0, 0), null)
})
