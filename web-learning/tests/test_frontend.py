"""Frontend checks: run the Node unit tests for static/logic.js and assert
key properties of the shipped HTML/JS (capture not hardcoded, AI panel in
place of full-content overwrite).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for frontend logic tests")
def test_frontend_logic_node():
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "frontend_logic.test.mjs")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_index_references_external_scripts_and_ai_panel():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'src="logic.js"' in html
    assert 'src="app.js"' in html
    assert 'id="aiPanel"' in html


def test_scan_capture_not_hardcoded():
    app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "scanState='101'" not in app
    assert "scanCaptureState(scanState)" in app


def test_ai_action_does_not_overwrite_content():
    app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "getElementById('content').innerHTML='<h2>'" not in app
    assert "aiPanel" in app
