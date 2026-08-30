// Unit tests for web-learning/static/logic.js, run under plain Node.
// Invoked from tests/test_frontend.py (and can be run directly:
// `node tests/frontend_logic.test.mjs`).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = path.dirname(fileURLToPath(import.meta.url));
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(readFileSync(path.join(here, '..', 'static', 'logic.js'), 'utf8'), sandbox, { filename: 'logic.js' });
const {
  shiftScanState, scanCaptureState, explainScanCapture,
  savePosition, restorePosition, sceneDoneFromProgress, aiErrorMessage,
} = sandbox;

function fakeStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), _map: m };
}

// --- scan capture is computed, not a fixed constant -----------------------
assert.equal(scanCaptureState('000'), '111');
assert.equal(scanCaptureState('101'), '010');
assert.equal(scanCaptureState('010'), '101');
const results = new Set(['000', '001', '101', '111'].map(scanCaptureState));
assert.ok(results.size > 1, 'capture result must depend on current state');

// --- shift model matches the course quiz (SI=1,0,1 from 000 -> 101) -------
let s = '000';
for (const si of ['1', '0', '1']) s = shiftScanState(s, si);
assert.equal(s, '101');

// --- capture explanation references the current state and the model -------
const ex = explainScanCapture('010');
assert.ok(ex.includes('Q=010') && ex.includes('101'));
assert.ok(ex.includes('D_i=¬Q_i'));

// --- scene completion restored from server progress -----------------------
const sceneIds = new Set(['l1:s1', 'l1:s2', 'l1:s3']);
const done = sceneDoneFromProgress([
  { lesson_id: 'l1', exercise_id: 's1', completed: 1, feedback: '已记录。' },
  { lesson_id: 'l1', exercise_id: 's2', completed: 0, feedback: '已明确记录为暂时跳过。' },
  { lesson_id: 'l1', exercise_id: 's3', completed: 0, feedback: '' },
  { lesson_id: 'lX', exercise_id: 's9', completed: 1, feedback: '' },
], sceneIds);
assert.deepEqual([...done].sort(), ['l1:s1', 'l1:s2']);

// --- position persistence stores ids only and validates on restore --------
const lessons = [
  { id: 'l1', scenes: [{ id: 'a' }, { id: 'b' }] },
  { id: 'l2', scenes: [{ id: 'c' }] },
];
const storage = fakeStorage();
savePosition(storage, 'l2', 'c');
const restored = restorePosition(storage, lessons);
assert.equal(restored?.lesson, 1);
assert.equal(restored?.scene, 0);
const saved = JSON.parse(storage.getItem('hermes_position'));
assert.deepEqual(Object.keys(saved).sort(), ['lesson', 'scene'], 'only ids may be persisted');

savePosition(storage, 'l9', 'zzz');
assert.equal(restorePosition(storage, lessons), null, 'stale ids must be ignored');
savePosition(storage, '', 'c');
assert.equal(storage.getItem('hermes_position'), JSON.stringify({ lesson: 'l9', scene: 'zzz' }), 'empty ids not saved');
storage.setItem('hermes_position', '{not json');
assert.equal(restorePosition(storage, lessons), null, 'malformed data must be ignored');

// --- AI error messages distinguish auth / rate limit / outage -------------
assert.ok(aiErrorMessage(401).includes('登录'));
assert.ok(aiErrorMessage(429).includes('限流'));
assert.ok(aiErrorMessage(502).includes('不可用'));
assert.notEqual(aiErrorMessage(401), aiErrorMessage(429));
assert.notEqual(aiErrorMessage(429), aiErrorMessage(502));

console.log('frontend_logic.test.mjs: all assertions passed');
