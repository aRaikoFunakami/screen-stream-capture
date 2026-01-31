import test from 'node:test'
import assert from 'node:assert/strict'

import {
  computeLiveSyncSeekTime,
  computeLiveSyncSeekTimeInBufferedRange,
  isPlaybackStalled,
} from '../dist/useAndroidStream.js'

test('computeLiveSyncSeekTime: no seek when within max latency', () => {
  const seekTo = computeLiveSyncSeekTime(9.0, 10.0, { maxLatencyMs: 1500, targetLatencyMs: 300 })
  assert.equal(seekTo, null)
})

test('computeLiveSyncSeekTime: seeks near buffered end when latency too high', () => {
  const seekTo = computeLiveSyncSeekTime(0.0, 10.0, { maxLatencyMs: 1500, targetLatencyMs: 300 })
  assert.ok(seekTo !== null)
  assert.ok(seekTo > 9.0)
  assert.ok(seekTo < 10.0)
})

test('computeLiveSyncSeekTime: clamps to >= 0', () => {
  const seekTo = computeLiveSyncSeekTime(0.0, 0.1, { maxLatencyMs: 1, targetLatencyMs: 1000 })
  assert.equal(seekTo, 0)

  const seekTo2 = computeLiveSyncSeekTime(-5.0, 10.0, { maxLatencyMs: 0, targetLatencyMs: 300 })
  assert.equal(seekTo2, null)
})

test('computeLiveSyncSeekTimeInBufferedRange: keeps seek within last range', () => {
  const seekTo = computeLiveSyncSeekTimeInBufferedRange(
    0.0,
    { start: 5.0, end: 10.0 },
    { maxLatencyMs: 1500, targetLatencyMs: 300 },
    0.1,
  )
  assert.ok(seekTo !== null)
  assert.ok(seekTo >= 5.0)
  assert.ok(seekTo <= 9.9)
})

test('computeLiveSyncSeekTimeInBufferedRange: no seek when latency within threshold', () => {
  const seekTo = computeLiveSyncSeekTimeInBufferedRange(
    9.0,
    { start: 0.0, end: 10.0 },
    { maxLatencyMs: 1500, targetLatencyMs: 300 },
    0.1,
  )
  assert.equal(seekTo, null)
})

test('isPlaybackStalled: true when progress timeout exceeded', () => {
  assert.equal(isPlaybackStalled(3000, 0, 2000), true)
  assert.equal(isPlaybackStalled(1999, 0, 2000), false)
  assert.equal(isPlaybackStalled(2001, 0, 2000), true)
})

test('isPlaybackStalled: false for invalid inputs', () => {
  assert.equal(isPlaybackStalled(Number.NaN, 0, 2000), false)
  assert.equal(isPlaybackStalled(1000, 0, 0), false)
  assert.equal(isPlaybackStalled(1000, 0, -1), false)
})
