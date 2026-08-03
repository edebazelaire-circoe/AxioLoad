from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def test_application_loads_the_role_shell_assets(tmp_path: Path) -> None:
    page = TestClient(create_app(tmp_path)).get("/")
    assert page.status_code == 200
    assert '/static/auth_experience.css?v=0.19.4' in page.text
    assert '/static/auth_experience.js?v=0.19.4' in page.text
    assert '/static/auth_experience.js?v=0.19.3' not in page.text


def _run_shell_probe(context: dict[str, object]) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")

    probe = r"""
const context = JSON.parse(process.argv[1]);
const scriptPath = process.argv[2];
const listeners = [];
const nodes = new Map();
const classList = initial => ({
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
function makeNode(id, classes = []) {
  return {
    id, hidden: false, disabled: false, tabIndex: 0, dataset: {}, attributes: {},
    classList: classList(classes), children: [], innerHTML: '',
    setAttribute(name, value){ this.attributes[name] = String(value); },
    getAttribute(name){ return this.attributes[name] ?? null; },
    addEventListener(type, handler, options){ listeners.push({type, handler, options, node: this}); },
    append(child){ this.children.push(child); if (child.id) nodes.set(`#${child.id}`, child); },
    closest(selector){
      if (selector === '[data-workspace]' && this.dataset.workspace) return this;
      if (selector === '#open-admin' && this.id === 'open-admin') return this;
      return null;
    }
  };
}
const body = makeNode('body');
const settings = makeNode('open-settings', ['hidden']);
settings.hidden = true;
const admin = makeNode('open-admin', ['active']);
const adminPanel = makeNode('tab-admin', ['active']);
const topbar = makeNode('topbar');
const workspace = makeNode('workspace-optimization');
workspace.dataset.workspace = 'optimization';
nodes.set('#open-settings', settings);
nodes.set('#open-admin', admin);
nodes.set('#tab-admin', adminPanel);
nodes.set('.topbar', topbar);

global.Node = {TEXT_NODE: 3};
global.document = {
  readyState: 'complete', body,
  querySelector(selector){ return nodes.get(selector) || null; },
  querySelectorAll(){ return []; },
  createElement(){ return makeNode(''); },
  addEventListener(type, handler, options){ listeners.push({type, handler, options, node: document}); }
};
global.window = {setTimeout(callback){ callback(); return 1; }};
global.location = {href: '', search: ''};
global.localStorage = {setItem(){}, removeItem(){}};
global.fetch = async url => ({
  ok: true,
  json: async () => url === '/api/company/context' ? context : {}
});
require(scriptPath);
setTimeout(() => {
  const navigation = listeners.find(item => item.type === 'click' && item.node === document && item.options === true && body.dataset.superAdminNavigationBound === 'true');
  if (navigation) navigation.handler({target: workspace});
  process.stdout.write(JSON.stringify({
    settingsHidden: settings.hidden,
    settingsClassHidden: settings.classList.contains('hidden'),
    adminHidden: admin.hidden,
    adminClassHidden: admin.classList.contains('hidden'),
    adminPanelActive: adminPanel.classList.contains('active'),
    superAdminShell: body.dataset.superAdminShell || null,
    userShell: body.dataset.userShell || null,
    navigationBound: body.dataset.superAdminNavigationBound || null
  }));
}, 20);
"""
    completed = subprocess.run(
        [node, "-e", probe, json.dumps(context), str(STATIC / "auth_experience.js")],
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    )
    return json.loads(completed.stdout)


def test_super_admin_keeps_settings_and_management_and_closes_admin_panel() -> None:
    result = _run_shell_probe(
        {
            "mode": "assistance",
            "company": {"id": "local"},
            "user": None,
            "actor": "b.olivier@circoe.com",
        }
    )
    assert result == {
        "settingsHidden": False,
        "settingsClassHidden": False,
        "adminHidden": False,
        "adminClassHidden": False,
        "adminPanelActive": False,
        "superAdminShell": "true",
        "userShell": "false",
        "navigationBound": "true",
    }


def test_standard_user_keeps_settings_and_hides_management() -> None:
    result = _run_shell_probe(
        {
            "mode": "user",
            "company": {"id": "local"},
            "user": {"id": "axioload-test-user"},
            "actor": "Utilisateur test",
        }
    )
    assert result["settingsHidden"] is False
    assert result["settingsClassHidden"] is False
    assert result["adminHidden"] is True
    assert result["adminClassHidden"] is True
    assert result["superAdminShell"] == "false"
    assert result["userShell"] == "true"
    assert result["navigationBound"] is None


def test_super_admin_navigation_does_not_block_existing_handlers() -> None:
    source = (STATIC / "auth_experience.js").read_text(encoding="utf-8")
    css = (STATIC / "auth_experience.css").read_text(encoding="utf-8")

    navigation_block = source.split("function applySuperAdminShell()", 1)[1].split("function applyUserShell()", 1)[0]
    assert "preventDefault" not in navigation_block
    assert "stopPropagation" not in navigation_block
    assert "stopImmediatePropagation" not in navigation_block
    assert 'body[data-super-admin-shell="true"] #open-settings' in css
    assert 'body[data-super-admin-shell="true"] #open-admin' in css
    assert 'body[data-user-shell="true"] #open-admin' in css
