import base64
import hmac
import json
import os
import secrets
import sqlite3
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
COURSE_FILE = ROOT / "course_public.json"
DB_FILE = Path(os.environ.get("LEARNING_DB", ROOT / "data" / "learning.sqlite3"))
HERMES_API_BASE = os.environ.get("HERMES_API_BASE", "http://127.0.0.1:18644").rstrip("/")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
PREMIUM_USER = os.environ.get("PREMIUM_USER", "")
PREMIUM_PASSWORD = os.environ.get("PREMIUM_PASSWORD", "")
SYNC_TOKEN = os.environ.get("SYNC_TOKEN", "")
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

RETRY_FEEDBACK = "还不能进入下一步。请重新检查题目中的因果条件，再做一次预测。"


def premium_enabled():
    return bool(PREMIUM_USER and PREMIUM_PASSWORD and HERMES_API_KEY)


def authorized(handler):
    if not premium_enabled():
        return False
    raw = handler.headers.get("Authorization", "")
    if not raw.startswith("Basic "):
        return False
    try:
        user, password = base64.b64decode(raw[6:], validate=True).decode().split(":", 1)
    except (ValueError, UnicodeError):
        return False
    return hmac.compare_digest(user, PREMIUM_USER) and hmac.compare_digest(password, PREMIUM_PASSWORD)


def require_premium(handler):
    if authorized(handler):
        return True
    handler.send_json({"error": "premium authentication required"}, HTTPStatus.UNAUTHORIZED, challenge=True)
    return False


def sync_authorized(handler):
    token = handler.headers.get("X-Sync-Token", "")
    return bool(SYNC_TOKEN and hmac.compare_digest(token, SYNC_TOKEN))


def hermes_chat(messages):
    request = urllib.request.Request(
        HERMES_API_BASE + "/v1/chat/completions",
        data=json.dumps({"model": "hermes-agent", "messages": messages, "temperature": 0.2}).encode(),
        headers={"Authorization": "Bearer " + HERMES_API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode())
    return data["choices"][0]["message"]["content"]


def load_course():
    return json.loads(COURSE_FILE.read_text(encoding="utf-8"))


def init_db():
    with sqlite3.connect(DB_FILE) as db:
        db.execute("CREATE TABLE IF NOT EXISTS progress (learner TEXT NOT NULL, lesson_id TEXT NOT NULL, exercise_id TEXT, answer TEXT, feedback TEXT, completed INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (learner, lesson_id, exercise_id))")
        db.execute("CREATE TABLE IF NOT EXISTS learners (token TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'anon', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")


def register_learner():
    token = "learner-" + secrets.token_urlsafe(24)
    with sqlite3.connect(DB_FILE) as db:
        db.execute("INSERT INTO learners(token, kind) VALUES(?, 'anon')", (token,))
    return token


def learner_registered(token):
    with sqlite3.connect(DB_FILE) as db:
        return db.execute("SELECT 1 FROM learners WHERE token=?", (token,)).fetchone() is not None


def resolve_learner(handler):
    """Return the trusted learner identity for this request, or None.

    Premium requests use the authenticated account as identity; public
    requests must present a server-issued anonymous learner token. A raw
    self-chosen X-Learner value is never trusted.
    """
    if authorized(handler):
        return "premium:" + PREMIUM_USER
    token = handler.headers.get("X-Learner", "")[:120]
    if token and learner_registered(token):
        return token
    return None


def progress_rows(learner):
    with sqlite3.connect(DB_FILE) as db:
        return db.execute("SELECT lesson_id, exercise_id, answer, feedback, completed, updated_at FROM progress WHERE learner=? ORDER BY updated_at", (learner,)).fetchall()


def progress_payload(learner):
    return {"learner": learner, "items": [dict(zip(("lesson_id", "exercise_id", "answer", "feedback", "completed", "updated_at"), r)) for r in progress_rows(learner)]}


def public_course():
    course = load_course()
    for lesson in course.get("lessons", []):
        for scene in lesson.get("scenes", []):
            scene.pop("correct", None)
            scene.pop("feedback", None)
        for exercise in lesson.get("exercises", []):
            exercise.pop("answer", None)
            exercise.pop("rubric", None)
    return course


def find_scene(course, scene_id):
    for lesson in course.get("lessons", []):
        for scene in lesson.get("scenes", []):
            if scene.get("id") == scene_id:
                return lesson, scene
    return None, None


def find_lesson(course, lesson_id):
    for lesson in course.get("lessons", []):
        if lesson.get("id") == lesson_id:
            return lesson
    return None


def progress_summary(learner):
    rows = progress_rows(learner)[-50:]
    if not rows:
        return "该学习者暂无进度记录。"
    done = sum(1 for r in rows if r[4])
    skipped = len(rows) - done
    recent = "；".join(f"{r[0]}/{r[1]}{'已完成' if r[4] else '暂时跳过'}" for r in rows[-10:])
    return f"共有 {len(rows)} 条进度记录：完成 {done} 项，暂时跳过 {skipped} 项。最近记录：{recent}"


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=HTTPStatus.OK, challenge=False):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if challenge:
            self.send_header("WWW-Authenticate", 'Basic realm="Hermes Premium"')
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_file(self, path, content_type):
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def serve_static(self, url_path):
        static_root = (ROOT / "static").resolve()
        name = "index.html" if url_path in ("/", "") else url_path.lstrip("/")
        try:
            path = (static_root / name).resolve()
            path.relative_to(static_root)
        except (ValueError, OSError):
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        if path.is_file():
            content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "text/plain; charset=utf-8"
            return self.send_file(path, content_type)
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def progress_response(self):
        learner = resolve_learner(self)
        if learner is None:
            return self.send_json({"error": "learner token required; register via POST /api/learner"}, HTTPStatus.UNAUTHORIZED)
        return self.send_json(progress_payload(learner))

    def ai_tutor(self, kind, lesson_id, scene_id):
        course = public_course()
        lessons = course.get("lessons", [])
        lesson = find_lesson(course, lesson_id) or (lessons[0] if lessons else {})
        scene = find_scene(course, scene_id)[1] or (lesson.get("scenes") or [{}])[0]
        context = json.dumps({
            "course_title": course.get("title", ""),
            "course_objectives": course.get("objectives", []),
            "current_lesson": lesson,
            "current_scene": scene,
            "progress_summary": progress_summary("premium:" + PREMIUM_USER),
        }, ensure_ascii=False)
        if kind == "explain":
            prompt = "请用中文为学习者讲解以下DFT课程的当前课与当前场景，先给直观解释，再给一个工程例子，最后列出3个自测问题。\n\n" + context
        else:
            prompt = "请根据以下DFT课程的当前课、当前场景和学习者进度摘要，为学习者制定一个7天、每天30分钟的个性化学习计划。要求包含每天主题、学习目标、练习和复习检查点。用中文输出。\n\n" + context
        try:
            return self.send_json({"ok": True, "content": hermes_chat([{"role": "user", "content": prompt}])})
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
            return self.send_json({"error": "Hermes service unavailable", "detail": str(exc)}, HTTPStatus.BAD_GATEWAY)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            return self.send_json({"ok": True, "service": "hermes-learning-web"})
        if parsed.path == "/api/course":
            return self.send_json(public_course())
        if parsed.path == "/api/progress":
            return self.progress_response()
        if parsed.path == "/api/sync/telegram":
            if not sync_authorized(self):
                return self.send_json({"error": "sync authentication required"}, HTTPStatus.UNAUTHORIZED)
            learner = parse_qs(parsed.query).get("learner", [""])[0][:120]
            if not learner:
                return self.send_json({"error": "learner query parameter required"}, HTTPStatus.BAD_REQUEST)
            return self.send_json(progress_payload(learner))
        if parsed.path == "/api/premium/status":
            return self.send_json({"configured": premium_enabled(), "authenticated": authorized(self)})
        if parsed.path in ("/api/ai/explain", "/api/ai/plan"):
            if not require_premium(self):
                return
            params = parse_qs(parsed.query)
            return self.ai_tutor(parsed.path.rsplit("/", 1)[-1], params.get("lesson_id", [""])[0][:80], params.get("scene_id", [""])[0][:80])
        return self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/learner":
            return self.send_json({"learner": register_learner()}, HTTPStatus.CREATED)
        if parsed.path == "/api/scene/check":
            try:
                body = self.read_json()
            except (ValueError, json.JSONDecodeError) as exc:
                return self.send_json({"error": f"invalid request: {exc}"}, HTTPStatus.BAD_REQUEST)
            scene_id = str(body.get("scene_id", ""))[:80]
            _, scene = find_scene(load_course(), scene_id)
            if not scene or "correct" not in scene:
                return self.send_json({"error": "unknown or non-gradable scene"}, HTTPStatus.NOT_FOUND)
            try:
                answer = int(body.get("answer"))
            except (TypeError, ValueError):
                return self.send_json({"error": "answer must be an option index"}, HTTPStatus.BAD_REQUEST)
            correct = answer == int(scene["correct"])
            feedback = str(scene.get("feedback", "")) if correct else RETRY_FEEDBACK
            return self.send_json({"scene_id": scene_id, "correct": correct, "feedback": feedback, "can_continue": correct})
        if parsed.path in ("/api/ai/explain", "/api/ai/plan"):
            if not require_premium(self):
                return
            try:
                body = self.read_json()
            except (ValueError, json.JSONDecodeError):
                body = {}
            return self.ai_tutor(parsed.path.rsplit("/", 1)[-1], str(body.get("lesson_id", ""))[:80], str(body.get("scene_id", ""))[:80])
        if parsed.path == "/api/ai/grade":
            if not require_premium(self):
                return
            try:
                body = self.read_json()
                prompt = "你是数字芯片 DFT 教师。请用中文批改下面的简答题，输出：得分(0-100)、正确点、遗漏点、改进建议和一个追问。不要编造课程外事实。\n题目：" + str(body.get("question", ""))[:2000] + "\n学习者答案：" + str(body.get("answer", ""))[:10000]
                return self.send_json({"ok": True, "content": hermes_chat([{"role": "user", "content": prompt}])})
            except (ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
                return self.send_json({"error": "Hermes service unavailable", "detail": str(exc)}, HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/sync/telegram":
            if not sync_authorized(self):
                return self.send_json({"error": "sync authentication required"}, HTTPStatus.UNAUTHORIZED)
            try:
                body = self.read_json()
                learner = str(body.get("learner", ""))[:120]
                if not learner:
                    return self.send_json({"error": "learner field required"}, HTTPStatus.BAD_REQUEST)
                items = body.get("items", [])
                with sqlite3.connect(DB_FILE) as db:
                    for item in items[:200]:
                        db.execute("INSERT INTO progress(learner, lesson_id, exercise_id, answer, feedback, completed) VALUES(?,?,?,?,?,?) ON CONFLICT(learner, lesson_id, exercise_id) DO UPDATE SET answer=excluded.answer, feedback=excluded.feedback, completed=excluded.completed, updated_at=CURRENT_TIMESTAMP", (learner, str(item["lesson_id"])[:80], str(item.get("exercise_id", "lesson"))[:80], str(item.get("answer", ""))[:10000], str(item.get("feedback", ""))[:10000], int(bool(item.get("completed", True)))))
                return self.send_json({"ok": True, "learner": learner, "imported": min(len(items), 200)})
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                return self.send_json({"error": f"invalid sync request: {exc}"}, HTTPStatus.BAD_REQUEST)
        if parsed.path != "/api/progress":
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        learner = resolve_learner(self)
        if learner is None:
            return self.send_json({"error": "learner token required; register via POST /api/learner"}, HTTPStatus.UNAUTHORIZED)
        try:
            body = self.read_json()
            lesson_id = str(body["lesson_id"])[:80]
            exercise_id = str(body.get("exercise_id", "lesson"))[:80]
            answer = str(body.get("answer", ""))[:10000]
            skipped = bool(body.get("skipped"))
            feedback = "已明确记录为暂时跳过。" if skipped else "已记录。建议对照本课的可控性、可观察性、故障激活和响应传播概念复盘。"
            with sqlite3.connect(DB_FILE) as db:
                db.execute("INSERT INTO progress(learner, lesson_id, exercise_id, answer, feedback, completed) VALUES(?,?,?,?,?,?) ON CONFLICT(learner, lesson_id, exercise_id) DO UPDATE SET answer=excluded.answer, feedback=excluded.feedback, completed=excluded.completed, updated_at=CURRENT_TIMESTAMP", (learner, lesson_id, exercise_id, answer, feedback, 0 if skipped else 1))
            return self.send_json({"ok": True, "lesson_id": lesson_id, "exercise_id": exercise_id, "feedback": feedback, "completed": not skipped, "skipped": skipped}, HTTPStatus.CREATED)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.send_json({"error": f"invalid request: {exc}"}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "3001"))), Handler)
    print(f"learning web listening on {server.server_address}", flush=True)
    server.serve_forever()
