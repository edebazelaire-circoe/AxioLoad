from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from pallet_optimizer.api import create_app
from pallet_optimizer.platform.composition import (
    RUNTIME_COMPOSITION_STEPS,
    CompositionPhase,
    compose_runtime,
    get_application_container,
    validate_runtime_composition,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "pallet_optimizer"
STATIC = PACKAGE / "static"


def _route_inventory(app) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Build a stable inventory from OpenAPI, compatible with nested APIRouters."""

    return tuple(
        sorted(
            (
                path,
                tuple(
                    sorted(
                        method.upper()
                        for method in operations
                        if method.lower()
                        in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
                    )
                ),
            )
            for path, operations in app.openapi()["paths"].items()
        )
    )


def test_runtime_composition_is_ordered_complete_and_resolvable() -> None:
    container = get_application_container()
    validate_runtime_composition(container.steps, container.module_registry)

    expected = tuple(step.name for step in RUNTIME_COMPOSITION_STEPS)
    assert container.composed is True
    assert container.executed_steps == expected
    assert all(item["executed"] is True for item in container.manifest())
    assert all(callable(step.resolve()) for step in container.steps)

    phase_order = {
        CompositionPhase.PERMISSIONS: 0,
        CompositionPhase.BACKEND: 10,
        CompositionPhase.FRONTEND: 20,
        CompositionPhase.ROUTES: 30,
    }
    phases = [phase_order[step.phase] for step in container.steps]
    assert phases == sorted(phases)


def test_runtime_composition_is_idempotent() -> None:
    container = get_application_container()
    executed = container.executed_steps
    fastapi_init = FastAPI.__init__
    template_response = Jinja2Templates.TemplateResponse

    assert compose_runtime() is container
    assert compose_runtime() is container
    assert container.executed_steps == executed
    assert FastAPI.__init__ is fastapi_init
    assert Jinja2Templates.TemplateResponse is template_response


def test_package_initialization_uses_only_the_composition_root() -> None:
    source = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    assert "compose_runtime()" in source
    assert "install_super_admin_routes" not in source
    assert "install_document_control_system" not in source
    assert "install_admin_panel_injection" not in source
    assert "FastAPI.__init__" not in source


def test_recomposing_does_not_change_the_http_route_inventory(tmp_path: Path) -> None:
    first = create_app(tmp_path / "first")
    before = _route_inventory(first)

    compose_runtime()
    second = create_app(tmp_path / "second")
    after = _route_inventory(second)

    assert after == before
    paths = {path for path, _methods in after}
    assert {
        "/",
        "/health",
        "/api/auth/login",
        "/api/auth/super-admin-login",
        "/api/company/context",
        "/api/vehicles",
        "/local/optimize",
        "/api/route/optimize",
        "/api/total/optimize",
        "/api/history",
        "/api/document-control/bootstrap",
        "/api/prompt-center",
        "/api/platform/modules",
    } <= paths


def _run_shell_probe(context: dict[str, object]) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")

    probe = r"""
const context = JSON.parse(process.argv[1]);
const scriptPath = process.argv[2];
const makeClassList = () => ({
  values: new Set(),
  add(value){ this.values.add(value); },
  remove(value){ this.values.delete(value); },
  toggle(value, force){
    if (force === undefined) force = !this.values.has(value);
    if (force) this.values.add(value); else this.values.delete(value);
    return force;
  },
  contains(value){ return this.values.has(value); }
});
const nodes = new Map();
const makeNode = id => ({
  id, hidden: false, disabled: false, tabIndex: 0, dataset: {}, classList: makeClassList(),
  textContent: '', innerHTML: '', childNodes: [],
  setAttribute(name, value){ this[name] = String(value); },
  addEventListener(){}, append(node){ if (node.id) nodes.set(`#${node.id}`, node); },
  before(){}, prepend(){}, closest(){ return null; }, focus(){},
  querySelector(){ return null; }, querySelectorAll(){ return []; }
});
const settings = makeNode('open-settings');
const management = makeNode('open-admin');
const topbar = makeNode('topbar');
const body = makeNode('body');
nodes.set('#open-settings', settings);
nodes.set('#open-admin', management);
nodes.set('.topbar', topbar);
global.document = {
  readyState: 'complete', body,
  querySelector(selector){ return nodes.get(selector) || null; },
  querySelectorAll(){ return []; },
  createElement(){ return makeNode(''); },
  addEventListener(){}
};
global.window = {
  setTimeout(callback){ callback(); return 1; }
};
global.location = {href: '', search: ''};
global.localStorage = {setItem(){}, removeItem(){}};
global.fetch = async url => ({
  ok: true,
  status: 200,
  json: async () => url === '/api/company/context' ? context : {}
});
require(scriptPath);
setTimeout(() => {
  process.stdout.write(JSON.stringify({
    settingsHidden: settings.hidden,
    managementHidden: management.hidden,
    managementAccess: body.dataset.managementAccess,
    settingsAriaHidden: settings['aria-hidden'],
    managementAriaHidden: management['aria-hidden']
  }));
}, 20);
"""
    completed = subprocess.run(
        [node, "-e", probe, json.dumps(context), str(STATIC / "auth_experience.js")],
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )
    return json.loads(completed.stdout)


def test_user_shell_keeps_settings_and_hides_management_center() -> None:
    result = _run_shell_probe(
        {
            "mode": "user",
            "company": {"id": "local"},
            "user": {"id": "test-user"},
            "actor": "Utilisateur test",
        }
    )
    assert result == {
        "settingsHidden": False,
        "managementHidden": True,
        "managementAccess": "false",
        "settingsAriaHidden": "false",
        "managementAriaHidden": "true",
    }


def test_management_shell_keeps_settings_and_management_center() -> None:
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
        "managementHidden": False,
        "managementAccess": "true",
        "settingsAriaHidden": "false",
        "managementAriaHidden": "false",
    }


def test_management_button_is_hidden_before_role_resolution() -> None:
    stylesheet = (STATIC / "auth_experience.css").read_text(encoding="utf-8")
    script = (STATIC / "auth_experience.js").read_text(encoding="utf-8")
    prompt_script = (STATIC / "prompt_center_experience.js").read_text(encoding="utf-8")

    assert 'body:not([data-management-access="true"]) #open-admin' in stylesheet
    assert "document.body.dataset.managementAccess = String(managementAllowed)" in script
    assert "setControlVisibility(q('#open-settings'), true)" in script
    assert "setControlVisibility(q('#open-admin'), managementAllowed)" in script
    assert "settings.classList.remove('hidden')" in prompt_script
    assert "settings.classList.toggle('hidden', Boolean(directManagement))" not in prompt_script
