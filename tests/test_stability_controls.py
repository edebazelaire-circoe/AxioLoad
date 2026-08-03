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


def test_application_loads_stability_controls_last(tmp_path: Path) -> None:
    page = TestClient(create_app(tmp_path)).get("/")
    assert page.status_code == 200
    auth = f"/static/auth_experience.js?v={APP_VERSION}"
    stability = f"/static/stability_controls.js?v={APP_VERSION}"
    assert auth in page.text
    assert stability in page.text
    assert page.text.index(auth) < page.text.index(stability)
    assert "session_controls_guard.js" not in page.text


def test_stability_controls_complete_real_user_flow() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")

    probe = r"""
const scriptPath = process.argv[1];
const listeners = new Map();
const nodes = new Map();
const classList = initial => ({
  values: new Set(initial || []),
  toggle(value, force){ if (force) this.values.add(value); else this.values.delete(value); return force; },
  contains(value){ return this.values.has(value); }
});
function node(id, dataset = {}, classes = []) {
  return {
    id, dataset, disabled: false, hidden: false, attributes: {}, classList: classList(classes), children: [],
    setAttribute(name, value){ this.attributes[name] = String(value); },
    getAttribute(name){ return this.attributes[name] ?? null; },
    addEventListener(type, handler){ listeners.set(`${this.id}:${type}`, handler); },
    append(child){ this.children.push(child); if (child.id) nodes.set(`#${child.id}`, child); },
    click(){ const handler = listeners.get(`${this.id}:click`); if (handler) handler({target: this, currentTarget: this, preventDefault(){}, stopImmediatePropagation(){}}); },
    closest(selector){ return selector === '[data-workspace]' && this.dataset.workspace ? this : null; }
  };
}
const topbar = node('topbar');
const switcher = node('workspace-switcher');
const optimization = node('workspace-optimization', {workspace: 'optimization'});
const database = node('workspace-database', {workspace: 'database'});
const documents = node('workspace-documents', {workspace: 'documents'});
const nav = node('tabs');
const body = node('body');
const names = ['vehicles', 'data', 'results', 'history', 'route', 'total', 'document-control'];
const tabs = {};
const panels = {};
for (const name of names) {
  tabs[name] = node(`button-${name}`, {tab: name, workspaceGroup: name === 'vehicles' ? 'database' : (name === 'document-control' ? 'documents' : 'optimization')});
  panels[name] = node(`tab-${name}`, {}, name === 'document-control' ? ['active'] : []);
  nodes.set(`[data-tab="${name}"]`, tabs[name]);
  nodes.set(`#tab-${name}`, panels[name]);
}
nodes.set('.topbar', topbar);
nodes.set('#workspace-switcher', switcher);
nodes.set('nav.tabs', nav);
global.document = {
  readyState: 'complete', body,
  querySelector(selector){ return nodes.get(selector) || null; },
  querySelectorAll(selector){
    if (selector === '[data-tab]' || selector === '[data-workspace-group]') return Object.values(tabs);
    if (selector === '.tab-panel') return Object.values(panels);
    if (selector === '[data-workspace]') return [database, optimization, documents];
    return [];
  },
  createElement(){ return node(''); },
  addEventListener(){}
};
global.window = {location: {replace(value){ global.redirected = value; }}, setTimeout(callback){ callback(); return 1; }};
global.location = global.window.location;
global.localStorage = {removeItem(){}};
global.sessionStorage = {clear(){ global.sessionCleared = true; }};
const calls = [];
global.fetch = async (url, options = {}) => {
  calls.push([url, options.method || 'GET']);
  if (url === '/api/company/context') return {ok: true, json: async () => ({mode: 'user', company: {id: 'local'}, user: {id: 'u1'}})};
  return {ok: true, json: async () => ({})};
};
require(scriptPath);
setTimeout(async () => {
  const switchHandler = listeners.get('workspace-switcher:click');
  switchHandler({target: optimization, preventDefault(){}, stopImmediatePropagation(){}});
  const logout = nodes.get('#site-logout');
  await listeners.get('site-logout:click')({});
  process.stdout.write(JSON.stringify({
    logoutExists: Boolean(logout),
    optimizationVisible: panels.data.classList.contains('active') && !panels['document-control'].classList.contains('active'),
    logoutCalled: calls.some(([url, method]) => url === '/api/auth/logout' && method === 'POST'),
    redirected: global.redirected,
    sessionCleared: global.sessionCleared === true,
    contextCalls: calls.filter(([url]) => url === '/api/company/context').length
  }));
}, 20);
"""
    completed = subprocess.run(
        [node, "-e", probe, str(STATIC / "stability_controls.js")],
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert json.loads(completed.stdout) == {
        "logoutExists": True,
        "optimizationVisible": True,
        "logoutCalled": True,
        "redirected": "/login",
        "sessionCleared": True,
        "contextCalls": 1,
    }


def test_stability_controls_are_bounded() -> None:
    source = (STATIC / "stability_controls.js").read_text(encoding="utf-8")
    assert "MutationObserver" not in source
    assert "setInterval" not in source
    assert "[0, 50, 150, 400, 900, 1800]" in source
    assert "activateNativeTab('document-control')" in source
    assert "activateNativeTab(current || 'data')" in source
