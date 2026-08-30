"""HTTP-level tests for the learning web app.

The app module reads its configuration from the environment at import
time, so the fixture sets a temporary database and dummy premium
credentials before importing it, then serves it on an ephemeral port.
"""
import base64
import http.client
import importlib.util
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

APP_FILE = Path(__file__).resolve().parent.parent / "app.py"

TEST_USER = "test-user"
TEST_PASSWORD = "test-password"  # dummy value, only used inside these tests


def load_app(tmp_path, monkeypatch):
    monkeypatch.setenv("LEARNING_DB", str(tmp_path / "learning.sqlite3"))
    monkeypatch.setenv("PREMIUM_USER", TEST_USER)
    monkeypatch.setenv("PREMIUM_PASSWORD", TEST_PASSWORD)
    monkeypatch.setenv("HERMES_API_KEY", "test-api-key")
    monkeypatch.setenv("SYNC_TOKEN", "test-sync-token")
    spec = importlib.util.spec_from_file_location("learning_app", APP_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.init_db()
    return module


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    monkeypatch = pytest.MonkeyPatch()
    module = load_app(tmp_path_factory.mktemp("db"), monkeypatch)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", module
    httpd.shutdown()
    thread.join(timeout=5)
    monkeypatch.undo()


def request(base, method, path, body=None, headers=None):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers or {},
        method=method,
    )
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def basic_auth(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def register(base):
    status, data = request(base, "POST", "/api/learner")
    assert status == 201
    return data["learner"]


def raw_get(base, path):
    host, port = base.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status


def first_gradable_scene(module):
    course = module.load_course()
    for lesson in course["lessons"]:
        for scene in lesson.get("scenes", []):
            if "correct" in scene:
                return scene
    raise AssertionError("course has no gradable scene")


def test_path_traversal_rejected(server):
    base, _ = server
    assert raw_get(base, "/../app.py") == 404
    assert raw_get(base, "/../../etc/passwd") == 404
    assert raw_get(base, "/%2e%2e/app.py") == 404


def test_static_index_served(server):
    base, _ = server
    assert raw_get(base, "/") == 200
    assert raw_get(base, "/index.html") == 200


def test_public_course_hides_scene_answers(server):
    base, _ = server
    status, course = request(base, "GET", "/api/course")
    assert status == 200
    for lesson in course["lessons"]:
        for scene in lesson.get("scenes", []):
            assert "correct" not in scene
            assert "feedback" not in scene
        for exercise in lesson.get("exercises", []):
            assert "answer" not in exercise
            assert "rubric" not in exercise


def test_scene_check_grades_answers(server):
    base, module = server
    scene = first_gradable_scene(module)
    wrong = next(i for i in range(len(scene["options"]) + 1) if i != scene["correct"])

    status, data = request(base, "POST", "/api/scene/check", {"scene_id": scene["id"], "answer": scene["correct"]})
    assert status == 200
    assert data["correct"] is True
    assert data["can_continue"] is True

    status, data = request(base, "POST", "/api/scene/check", {"scene_id": scene["id"], "answer": wrong})
    assert status == 200
    assert data["correct"] is False
    assert data["can_continue"] is False
    assert data["feedback"] == module.RETRY_FEEDBACK

    status, _ = request(base, "POST", "/api/scene/check", {"scene_id": "no-such-scene", "answer": 0})
    assert status == 404


def test_wrong_credentials_not_authenticated(server):
    base, _ = server
    status, data = request(base, "GET", "/api/premium/status", headers={"Authorization": basic_auth(TEST_USER, "wrong")})
    assert status == 200
    assert data["configured"] is True
    assert data["authenticated"] is False

    status, _ = request(base, "GET", "/api/ai/explain", headers={"Authorization": basic_auth(TEST_USER, "wrong")})
    assert status == 401

    status, data = request(base, "GET", "/api/premium/status", headers={"Authorization": basic_auth(TEST_USER, TEST_PASSWORD)})
    assert status == 200
    assert data["authenticated"] is True


def test_progress_identity_isolation(server):
    base, _ = server
    alice, bob = register(base), register(base)
    assert alice != bob

    status, _ = request(base, "GET", "/api/progress")
    assert status == 401
    status, _ = request(base, "GET", "/api/progress", headers={"X-Learner": "self-chosen-name"})
    assert status == 401

    status, _ = request(
        base, "POST", "/api/progress",
        {"lesson_id": "l1", "exercise_id": "ex1", "answer": "alice answer"},
        headers={"X-Learner": alice},
    )
    assert status == 201

    status, data = request(base, "GET", "/api/progress", headers={"X-Learner": alice})
    assert status == 200
    assert [i["answer"] for i in data["items"]] == ["alice answer"]

    status, data = request(base, "GET", "/api/progress", headers={"X-Learner": bob})
    assert status == 200
    assert data["items"] == []


def test_premium_progress_uses_authenticated_identity(server):
    base, _ = server
    headers = {"Authorization": basic_auth(TEST_USER, TEST_PASSWORD)}
    status, _ = request(base, "POST", "/api/progress", {"lesson_id": "l2", "exercise_id": "ex9", "answer": "premium answer"}, headers=headers)
    assert status == 201

    status, data = request(base, "GET", "/api/progress", headers=headers)
    assert status == 200
    assert data["learner"].startswith("premium:")
    assert any(i["answer"] == "premium answer" for i in data["items"])

    # An anonymous learner must not see the premium learner's records.
    status, data = request(base, "GET", "/api/progress", headers={"X-Learner": register(base)})
    assert status == 200
    assert all(i["answer"] != "premium answer" for i in data["items"])


def test_skip_is_recorded_but_not_completed(server):
    base, _ = server
    learner = register(base)
    status, data = request(
        base, "POST", "/api/progress",
        {"lesson_id": "l1", "exercise_id": "l1-predict", "skipped": True},
        headers={"X-Learner": learner},
    )
    assert status == 201
    assert data["skipped"] is True
    assert data["completed"] is False

    status, data = request(base, "GET", "/api/progress", headers={"X-Learner": learner})
    assert data["items"][0]["completed"] == 0
    assert "跳过" in data["items"][0]["feedback"]


def test_sync_requires_token_and_explicit_learner(server):
    base, _ = server
    status, _ = request(base, "GET", "/api/sync/telegram")
    assert status == 401
    status, _ = request(base, "GET", "/api/sync/telegram", headers={"X-Sync-Token": "test-sync-token"})
    assert status == 400
    status, data = request(base, "GET", "/api/sync/telegram?learner=someone", headers={"X-Sync-Token": "test-sync-token"})
    assert status == 200
    assert data["learner"] == "someone"


def test_ai_rate_limit_window(server):
    _, module = server
    old_limit, old_window = module.AI_RATE_LIMIT, module.AI_RATE_WINDOW
    module.AI_RATE_LIMIT, module.AI_RATE_WINDOW = 2, 60
    module._ai_calls.clear()
    try:
        assert module.ai_rate_ok('premium:test', now=100.0)
        assert module.ai_rate_ok('premium:test', now=101.0)
        assert not module.ai_rate_ok('premium:test', now=102.0)
        assert module.ai_rate_ok('premium:test', now=161.0)
    finally:
        module.AI_RATE_LIMIT, module.AI_RATE_WINDOW = old_limit, old_window
        module._ai_calls.clear()
