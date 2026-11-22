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
test('contain: 左右の余白(縦長の映像)は映像の外、右下端は 1,1', () => {
  // 800x800 の枠に 400x800 の映像 → 左右に 200 ずつ余白
  assert.equal(mapToVideo(250, 450, rect, 400, 800), null)
  assert.deepEqual(mapToVideo(700, 850, rect, 400, 800), { x: 1, y: 1 })
  assert.deepEqual(mapToVideo(300, 50, rect, 400, 800), { x: 0, y: 0 })
})
test('cover: はみ出した分を除いて枠の中央・端を写す', () => {
  // 1280x800 を 800x800 に cover → 表示 1280x800、左右 240 ずつ枠外
  assert.deepEqual(mapToVideo(500, 450, rect, 1280, 800, 'cover'), { x: 0.5, y: 0.5 })
  assert.deepEqual(mapToVideo(100, 50, rect, 1280, 800, 'cover'), { x: 240 / 1280, y: 0 })
  assert.deepEqual(mapToVideo(900, 850, rect, 1280, 800, 'cover'), { x: 1040 / 1280, y: 1 })
})
test('枠の大きさ未確定なら null', () => {
  assert.equal(mapToVideo(500, 450, { ...rect, width: 0 }, 1280, 800), null)
})
test('chunkText: 256 文字ごとに分け、サロゲートペアを割らない', async () => {
  const { chunkText } = await import('../dist/RemoteControlLayer.js')
  assert.deepEqual(chunkText('abc', 2), ['ab', 'c'])
  assert.deepEqual(chunkText('😀😀😀', 2), ['😀😀', '😀'])
  assert.equal(chunkText('あ'.repeat(600)).length, 3)
  assert.deepEqual(chunkText(''), [])
})
