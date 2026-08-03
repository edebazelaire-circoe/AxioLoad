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
const makeClassList = initial => ({
  values: new Set(initial || []),
  add(value){ this.values.add(value); },
  remove(value){ this.values.delete(value); },
  toggle(value, force){
    if (force === undefined) force = !this.values.has(value);
    if (force) this.values.add(value); else this.values.delete(value);
    return force;
  },
  contains(value){ return this.values.has(value); }
});
const makeNode = (id, attrs = {}) => ({
  id, dataset: attrs.dataset || {}, disabled: false, hidden: false,
  classList: makeClassList(attrs.classes || []), attributes: {}, children: [],
  setAttribute(name, value){ this.attributes[name] = String(value); },
  getAttribute(name){ return this.attributes[name] ?? null; },
  addEventListener(type, handler){ listeners.set(`${id}:${type}`, handler); },
  append(node){ this.children.push(node); if (node.id) nodes.set(`#${node.id}`, node); },
  click(){ const handler = listeners.get(`${id}:click`); if (handler) handler({target: this, currentTarget: this, preventDefault(){}, stopImmediatePropagation(){}}); },
  closest(selector){ return selector === '[data-workspace]' && this.dataset.workspace ? this : null; }
});
const nodes = new Map();
const topbar = makeNode('topbar');
const switcher = makeNode('workspace-switcher');
const optimization = makeNode('workspace-optimization', {dataset: {workspace: 'optimization'}});
const documents = makeNode('workspace-documents', {dataset: {workspace: 'documents'}});
const database = makeNode('workspace-database', {dataset: {workspace: 'database'}});
const nav = makeNode('tabs');
const body = makeNode('body');
const tabNames = ['vehicles', 'data', 'results', 'history', 'route', 'total', 'document-control'];
const tabs = {};
const panels = {};
for (const name of tabNames) {
  tabs[name] = makeNode(`tab-${name}-button`, {dataset: {tab: name, workspaceGroup: name === 'vehicles' ? 'database' : (name === 'document-control' ? 'documents' : 'optimization')}});
  panels[name] = makeNode(`tab-${name}`, {classes: name === 'document-control' ? ['active'] : []});
}
nodes.set('.topbar', topbar);
nodes.set('#workspace-switcher', switcher);
nodes.set('nav.tabs', nav);
nodes.set('body', body);
nodes.set('[data-workspace="optimization"]', optimization);
nodes.set('[data-workspace="documents"]', documents);
nodes.set('[data-workspace="database"]', database);
for (const name of tabNames) {
  nodes.set(`[data-tab="${name}"]`, tabs[name]);
  nodes.set(`#tab-${name}`, panels[name]);
}
const allNodes = () => [...nodes.values()];
global.document = {
  readyState: 'complete', body,
  querySelector(selector){ return nodes.get(selector) || null; },
  querySelectorAll(selector){
    if (selector === '[data-tab]') return Object.values(tabs);
    if (selector === '.tab-panel') return Object.values(panels);
    if (selector === '[data-workspace]') return [database, optimization, documents];
    if (selector === '[data-workspace-group]') return Object.values(tabs);
    return [];
  },
  createElement(){ return makeNode(''); },
  addEventListener(){}
};
global.window = {
  location: {replace(value){ global.redirected = value; }},
  setTimeout(callback){ callback(); return 1; }
};
global.location = global.window.location;
global.localStorage = {removeItem(){}};
global.sessionStorage = {clear(){ global.sessionCleared = true; }};
const calls = [];
global.fetch = async (url, options = {}) => {
  calls.push([url, options.method || 'GET']);
  if (url === '/api/company/context') {
    return {ok: true, json: async () => ({mode: 'user', company: {id: 'local'}, user: {id: 'user-1'}, actor: 'Utilisateur test'})};
  }
  return {ok: true, json: async () => ({})};
};
require(scriptPath);
setTimeout(async () => {
  const logout = nodes.get('#site-logout');
  const switchHandler = listeners.get('workspace-switcher:click');
  switchHandler({target: optimization, preventDefault(){}, stopImmediatePropagation(){}});
  const optimizationVisible = panels.data.classList.contains('active') && !panels['document-control'].classList.contains('active');
  const logoutHandler = listeners.get('site-logout:click');
  await logoutHandler({});
  process.stdout.write(JSON.stringify({
    logoutExists: Boolean(logout),
    optimizationVisible,
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


def test_stability_controls_are_bounded_and_do_not_observe_the_whole_page() -> None:
    source = (STATIC / "stability_controls.js").read_text(encoding="utf-8")

    assert "MutationObserver" not in source
    assert "setInterval" not in source
    assert "[0, 50, 150, 400, 900, 1800]" in source
    assert "event.stopImmediatePropagation()" in source
    assert "activateNativeTab('document-control')" in source
    assert "activateNativeTab(current || 'data')" in source
