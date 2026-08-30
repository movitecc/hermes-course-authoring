// Pure frontend logic for the learning web app.
// No DOM, fetch, or storage globals are touched here, so every function can
// be unit-tested under Node (see tests/frontend_logic.test.mjs).

// --- Scan chain simulator --------------------------------------------------
// Shift model: on a shift clock (scan_enable=1) SI enters the lowest bit and
// every flip-flop takes the previous stage's value (state moves up).
// Capture model: a deliberately minimal, explicit combinational model where
// each scan cell's functional input is the inversion of its own current
// output (D_i = ~Q_i), so learners can predict the capture result by hand.

function shiftScanState(state, si) {
  return String(state).slice(1) + (si === '1' ? '1' : '0');
}

function scanCaptureState(state) {
  return String(state).split('').map((b) => (b === '1' ? '0' : '1')).join('');
}

// Explain how the current state produces the capture result under the model.
function explainScanCapture(state) {
  const q = String(state);
  const d = scanCaptureState(q);
  return `Capture 前 Q=${q}。本实验的最小组合逻辑模型为 D_i=¬Q_i（每个触发器的功能输入取自身输出取反），`
    + `因此功能响应 D=${d}；scan_enable=0 的 capture 时钟沿后，新状态锁存为 ${d}。`;
}

// --- Scene position persistence -------------------------------------------
// Only the current lesson/scene id is stored locally. Answers, feedback and
// credentials are never written to storage.
const POSITION_KEY = 'hermes_position';

function savePosition(storage, lessonId, sceneId) {
  if (!lessonId || !sceneId) return;
  storage.setItem(POSITION_KEY, JSON.stringify({ lesson: String(lessonId), scene: String(sceneId) }));
}

// Return {lesson, scene} indexes when the saved position still exists in the
// course; malformed or stale data is ignored and returns null.
function restorePosition(storage, lessons) {
  let saved;
  try {
    saved = JSON.parse(storage.getItem(POSITION_KEY) || 'null');
  } catch (e) {
    return null;
  }
  if (!saved || typeof saved.lesson !== 'string' || typeof saved.scene !== 'string') return null;
  const lesson = (lessons || []).findIndex((l) => l.id === saved.lesson);
  if (lesson < 0) return null;
  const scene = (lessons[lesson].scenes || []).findIndex((s) => s.id === saved.scene);
  if (scene < 0) return null;
  return { lesson, scene };
}

// --- Server progress -> scene completion ----------------------------------
// A scene counts as done when its progress record is completed, or when it
// was explicitly skipped (the server marks skips in the feedback text).
function sceneDoneFromProgress(items, sceneIds) {
  const done = new Set();
  for (const it of items || []) {
    const key = it.lesson_id + ':' + it.exercise_id;
    if (!sceneIds.has(key)) continue;
    if (Number(it.completed) || String(it.feedback || '').includes('跳过')) done.add(key);
  }
  return done;
}

// --- AI error classification ------------------------------------------------
function aiErrorMessage(status) {
  if (status === 401) return '高级模式未登录或登录已过期，请先登录 AI 功能。';
  if (status === 429) return '请求过于频繁，已触发限流，请稍后再试。';
  return 'Hermes 服务暂不可用，请稍后再试。';
}
