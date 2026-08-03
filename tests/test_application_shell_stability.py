from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "src" / "pallet_optimizer" / "static" / "application_shell.js"
PANEL = ROOT / "src" / "pallet_optimizer" / "application_shell_panel.py"


def test_shell_and_permanent_logout_are_injected_last(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")
    assert response.status_code == 200
    html = response.text

    assert html.count('id="site-logout"') == 1
    assert 'data-shell-control="logout"' in html
    assert html.count('/static/application_shell.css?v=0.19.5') == 1
    assert html.count('/static/application_shell.js?v=0.19.5') == 1
    assert html.index('id="site-logout"') < html.index('/static/application_shell.js?v=0.19.5')
    assert html.rfind('/static/application_shell.js?v=0.19.5') > html.rfind('/static/prompt_center_experience.js')
    assert html.rfind('/static/application_shell.js?v=0.19.5') > html.rfind('/static/admin.js')


def test_shell_javascript_is_syntactically_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")
    completed = subprocess.run(
        [node, "--check", str(SHELL)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_rapid_navigation_keeps_only_the_last_request() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")

    probe = r"""
const scriptPath = process.argv[1];
const frames = [];
global.window = {
  __AXIOLOAD_SHELL_TEST_ONLY__: true,
  requestAnimationFrame(callback) { frames.push(callback); return frames.length; }
};
require(scriptPath);
const applied = [];
const scheduler = window.AxioLoadShellTest.createLastWinsScheduler(
  value => applied.push(value),
  callback => { frames.push(callback); return frames.length; }
);
scheduler.schedule('database');
scheduler.schedule('documents');
scheduler.schedule('optimization');
if (frames.length !== 1) throw new Error(`expected one frame, got ${frames.length}`);
frames.shift()();
const roles = {
  admin: window.AxioLoadShellTest.roleFromContext({mode:'assistance', company:{id:'local'}, actor:'b.olivier@circoe.com'}),
  user: window.AxioLoadShellTest.roleFromContext({mode:'user', company:{id:'local'}, user:{id:'u1'}}),
  assistance: window.AxioLoadShellTest.roleFromContext({mode:'assistance', company:{id:'client'}, actor:'support'}),
  anonymous: window.AxioLoadShellTest.roleFromContext(null)
};
process.stdout.write(JSON.stringify({applied, roles, pending:scheduler.hasPending()}));
"""
    completed = subprocess.run(
        [node, "-e", probe, str(SHELL)],
        capture_output=True,
        text=True,
        check=True,
        timeout=3,
    )
    result = json.loads(completed.stdout)
    assert result == {
        "applied": ["optimization"],
        "roles": {
            "admin": "super_admin",
            "user": "user",
            "assistance": "assistance",
            "anonymous": "anonymous",
        },
        "pending": False,
    }


def test_shell_avoids_global_polling_and_event_blocking() -> None:
    source = SHELL.read_text(encoding="utf-8")
    panel = PANEL.read_text(encoding="utf-8")

    assert "setInterval" not in source
    assert "stopImmediatePropagation" not in source
    assert "stopPropagation" not in source
    assert "observe(document.body" not in source
    assert "MutationObserver(syncPermissions)" in source
    assert "attributeFilter: ['hidden', 'disabled']" in source
    assert "'aria-hidden', 'class'" not in source
    assert "application-shell-legacy" in source
    assert 'data-shell-control="logout"' in panel
