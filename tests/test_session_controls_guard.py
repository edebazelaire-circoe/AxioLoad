from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def test_application_page_loads_the_session_guard(tmp_path) -> None:
    page = TestClient(create_app(tmp_path)).get("/")

    assert page.status_code == 200
    assert f"/static/session_controls_guard.js?v={APP_VERSION}" in page.text


def test_session_guard_installs_logout_without_settings_button() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")

    probe = r"""
const scriptPath = process.argv[1];
const nodes = new Map();
const topbar = {
  append(node){ nodes.set('#' + node.id, node); }
};
nodes.set('.topbar', topbar);
const makeNode = () => ({
  id: '', type: '', className: '', disabled: false, innerHTML: '',
  setAttribute(){}, addEventListener(){},
});
global.document = {
  readyState: 'complete',
  querySelector(selector){ return nodes.get(selector) || null; },
  createElement(){ return makeNode(); },
  addEventListener(){},
};
global.window = {
  setTimeout(callback){ callback(); return 1; },
};
global.localStorage = {removeItem(){}};
global.location = {href: ''};
let contextCalls = 0;
global.fetch = async url => {
  if (url === '/api/company/context') {
    contextCalls += 1;
    return {
      ok: true,
      json: async () => ({
        mode: 'user',
        company: {id: 'local'},
        user: {id: 'test-user'},
        actor: 'Utilisateur test'
      })
    };
  }
  return {ok: true, json: async () => ({})};
};
require(scriptPath);
setTimeout(() => {
  process.stdout.write(JSON.stringify({
    logoutExists: nodes.has('#site-logout'),
    contextCalls,
  }));
}, 30);
"""
    completed = subprocess.run(
        [node, "-e", probe, str(STATIC / "session_controls_guard.js")],
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert json.loads(completed.stdout) == {
        "logoutExists": True,
        "contextCalls": 1,
    }


def test_session_guard_is_bounded_and_has_no_global_observer() -> None:
    source = (STATIC / "session_controls_guard.js").read_text(encoding="utf-8")

    assert "MutationObserver" not in source
    assert "setInterval" not in source
    assert "[0, 100, 300, 800, 1600]" in source
    assert "contextPromise" in source
