import base64
import hmac
import json
import os
import sqlite3
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
COURSE_FILE = ROOT / "course_public.json"
DB_FILE = Path(os.environ.get("LEARNING_DB", ROOT / "data" / "learning.sqlite3"))
HERMES_API_BASE = os.environ.get("HERMES_API_BASE", "http://127.0.0.1:18644").rstrip("/")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
PREMIUM_USER = os.environ.get("PREMIUM_USER", "")
PREMIUM_PASSWORD = os.environ.get("PREMIUM_PASSWORD", "")
DB_FILE.parent.mkdir(parents=True, exist_ok=True)


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


def public_course():
    course = load_course()
    for lesson in course.get("lessons", []):
        for exercise in lesson.get("exercises", []):
            exercise.pop("answer", None)
            exercise.pop("rubric", None)
    return course


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

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            return self.send_json({"ok": True, "service": "hermes-learning-web"})
        if parsed.path == "/api/course":
            return self.send_json(public_course())
        if parsed.path == "/api/progress":
            learner = self.headers.get("X-Learner", "default")[:120]
            with sqlite3.connect(DB_FILE) as db:
                rows = db.execute("SELECT lesson_id, exercise_id, answer, feedback, completed, updated_at FROM progress WHERE learner=? ORDER BY updated_at", (learner,)).fetchall()
            return self.send_json({"learner": learner, "items": [dict(zip(("lesson_id", "exercise_id", "answer", "feedback", "completed", "updated_at"), r)) for r in rows]})
        if parsed.path == "/api/premium/status":
            return self.send_json({"configured": premium_enabled(), "authenticated": authorized(self)})
        if parsed.path in ("/api/ai/explain", "/api/ai/plan"):
            if not require_premium(self):
                return
            course = public_course()
            if parsed.path.endswith("/explain"):
                prompt = "请用中文为学习者讲解以下DFT课程内容，先给直观解释，再给一个工程例子，最后列出3个自测问题。\n\n" + json.dumps(course, ensure_ascii=False)[:18000]
            else:
                prompt = "请根据以下DFT课程，为学习者制定一个7天、每天30分钟的个性化学习计划。要求包含每天主题、学习目标、练习和复习检查点。用中文输出。\n\n" + json.dumps(course, ensure_ascii=False)[:18000]
            try:
                return self.send_json({"ok": True, "content": hermes_chat([{"role": "user", "content": prompt}])})
            except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
                return self.send_json({"error": "Hermes service unavailable", "detail": str(exc)}, HTTPStatus.BAD_GATEWAY)
            learner = self.headers.get("X-Learner", "default")[:120]
            with sqlite3.connect(DB_FILE) as db:
                rows = db.execute("SELECT lesson_id, exercise_id, answer, feedback, completed, updated_at FROM progress WHERE learner=? ORDER BY updated_at", (learner,)).fetchall()
            return self.send_json({"learner": learner, "items": [dict(zip(("lesson_id", "exercise_id", "answer", "feedback", "completed", "updated_at"), r)) for r in rows]})
        path = ROOT / "static" / ("index.html" if parsed.path in ("/", "") else parsed.path.lstrip("/"))
        if path.is_file() and ROOT / "static" in path.parents:
            content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "text/plain; charset=utf-8"
            return self.send_file(path, content_type)
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/ai/grade":
            if not require_premium(self):
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                prompt = "你是数字芯片 DFT 教师。请用中文批改下面的简答题，输出：得分(0-100)、正确点、遗漏点、改进建议和一个追问。不要编造课程外事实。\n题目：" + str(body.get("question", ""))[:2000] + "\n学习者答案：" + str(body.get("answer", ""))[:10000]
                return self.send_json({"ok": True, "content": hermes_chat([{"role": "user", "content": prompt}])})
            except (ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
                return self.send_json({"error": "Hermes service unavailable", "detail": str(exc)}, HTTPStatus.BAD_GATEWAY)
        if parsed.path != "/api/progress":
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            learner = self.headers.get("X-Learner", "default")[:120]
            lesson_id = str(body["lesson_id"])[:80]
            exercise_id = str(body.get("exercise_id", "lesson"))[:80]
            answer = str(body.get("answer", ""))[:10000]
            feedback = "已记录。建议对照本课的可控性、可观察性、故障激活和响应传播概念复盘。"
            with sqlite3.connect(DB_FILE) as db:
                db.execute("INSERT INTO progress(learner, lesson_id, exercise_id, answer, feedback, completed) VALUES(?,?,?,?,?,1) ON CONFLICT(learner, lesson_id, exercise_id) DO UPDATE SET answer=excluded.answer, feedback=excluded.feedback, completed=1, updated_at=CURRENT_TIMESTAMP", (learner, lesson_id, exercise_id, answer, feedback))
            return self.send_json({"ok": True, "lesson_id": lesson_id, "exercise_id": exercise_id, "feedback": feedback, "completed": True}, HTTPStatus.CREATED)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.send_json({"error": f"invalid request: {exc}"}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "3001"))), Handler)
    print(f"learning web listening on {server.server_address}", flush=True)
    server.serve_forever()
