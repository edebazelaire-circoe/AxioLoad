(() => {
  'use strict';

  const STORAGE_KEY = 'axioload.navigation.v2';
  const TAB_PERMISSIONS = {
    vehicles: 'vehicles.view',
    data: 'data.view',
    results: 'results.view',
    history: 'history.view',
    route: 'route.view',
    total: 'total.view',
    'document-control': 'document_control.view'
  };
  const WORKSPACE_DEFAULTS = {
    database: 'vehicles',
    optimization: 'data',
    documents: 'document-new'
  };

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  let installed = false;
  let internalNavigation = false;
  let permissions = {};
  let state = readState();

  function readState() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
      if (saved && typeof saved === 'object') {
        return {
          workspace: saved.workspace || null,
          database: saved.database || 'vehicles',
          optimization: saved.optimization || 'data',
          documents: saved.documents || 'document-new'
        };
      }
    } catch (_) {}
    return {workspace: null, database: 'vehicles', optimization: 'data', documents: 'document-new'};
  }

  function persistState() {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (_) {}
  }

  const permissionsReady = fetch('/api/company/context', {credentials: 'same-origin'})
    .then(response => response.ok ? response.json() : null)
    .then(context => {
      permissions = context?.permissions || {};
      return permissions;
    })
    .catch(() => {
      permissions = {};
      return permissions;
    });

  function tabAllowed(name) {
    const permission = TAB_PERMISSIONS[name];
    return !permission || permissions[permission] !== false;
  }

  function workspaceAllowed(name) {
    if (name === 'documents') return tabAllowed('document-control');
    if (name === 'database') return tabAllowed('vehicles') || Boolean(q('[data-workspace-tab="prompts"]'));
    return ['data', 'results', 'history', 'route', 'total'].some(tabAllowed);
  }

  function workspaceForTab(name) {
    if (name === 'vehicles' || name === 'prompts') return 'database';
    if (name === 'document-control' || name === 'document-new' || name === 'document-history') return 'documents';
    return 'optimization';
  }

  function setWorkspaceVisual(name) {
    const switcher = q('#workspace-switcher');
    const nav = q('nav.tabs');
    if (!switcher || !nav) return;

    document.body.dataset.workspace = name;
    nav.dataset.workspace = name;
    qa('[data-workspace]', switcher).forEach(button => {
      const active = button.dataset.workspace === name;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });

    qa('[data-workspace-group]', nav).forEach(button => {
      const belongs = button.dataset.workspaceGroup === name;
      button.classList.toggle('workspace-group-hidden', !belongs);
      if (belongs) {
        const tabName = button.dataset.tab;
        const syntheticName = button.dataset.workspaceTab;
        const allowed = tabName ? tabAllowed(tabName) : syntheticName?.startsWith('document-') ? workspaceAllowed('documents') : true;
        if (allowed) button.hidden = false;
      }
    });
  }

  function setSubnavActive(activeButton) {
    const nav = q('nav.tabs');
    if (!nav) return;
    qa('.tab', nav).forEach(button => {
      const active = button === activeButton;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
  }

  function syncPanelAccessibility() {
    qa('main > .tab-panel').forEach(panel => {
      const active = panel.classList.contains('active');
      panel.setAttribute('aria-hidden', String(!active));
      if ('inert' in panel) panel.inert = !active;
    });
  }

  function emitNavigation(workspace, tab) {
    window.dispatchEvent(new CustomEvent('axioload:navigation:changed', {
      detail: {workspace, tab}
    }));
  }

  function directSwitchTab(name) {
    const panel = q(`#tab-${CSS.escape(name)}`);
    const button = q(`nav.tabs .tab[data-tab="${CSS.escape(name)}"]`);
    if (!panel || !tabAllowed(name)) return false;
    if (button) button.hidden = false;

    if (typeof window.switchTab === 'function') {
      window.switchTab(name);
    } else {
      qa('main > .tab-panel').forEach(item => item.classList.toggle('active', item === panel));
      qa('nav.tabs .tab[data-tab]').forEach(item => item.classList.toggle('active', item.dataset.tab === name));
      if (name === 'history' && typeof window.loadHistory === 'function') window.loadHistory();
      if (name === 'vehicles' && typeof window.renderVehicleRows === 'function') window.renderVehicleRows();
      if (name === 'settings' && typeof window.renderDashboard === 'function') window.renderDashboard();
    }

    if (button) setSubnavActive(button);
    syncPanelAccessibility();
    const workspace = workspaceForTab(name);
    state.workspace = workspace;
    if (workspace === 'database') state.database = name;
    if (workspace === 'optimization') state.optimization = name;
    persistState();
    emitNavigation(workspace, name);
    return true;
  }

  function allowedOptimizationTarget(preferred) {
    const order = [preferred, 'data', 'results', 'route', 'total', 'history'];
    return order.find(name => name && tabAllowed(name) && q(`#tab-${CSS.escape(name)}`)) || null;
  }

  function openPromptCenter() {
    const promptButton = q('[data-workspace-tab="prompts"]');
    if (!promptButton || promptButton.disabled) return false;
    setWorkspaceVisual('database');
    state.workspace = 'database';
    state.database = 'prompts';
    persistState();
    setSubnavActive(promptButton);

    internalNavigation = true;
    try { promptButton.click(); }
    finally { internalNavigation = false; }

    window.setTimeout(() => {
      syncPanelAccessibility();
      emitNavigation('database', 'prompts');
    }, 0);
    return true;
  }

  function openDocumentWorkspace(target = 'document-new') {
    if (!workspaceAllowed('documents')) return false;
    const documentTab = q('nav.tabs .tab[data-tab="document-control"]');
    const panel = q('#tab-document-control');
    if (!documentTab || !panel) return false;

    setWorkspaceVisual('documents');
    state.workspace = 'documents';
    state.documents = target === 'document-history' ? 'document-history' : 'document-new';
    persistState();

    documentTab.hidden = false;
    internalNavigation = true;
    try { documentTab.click(); }
    finally { internalNavigation = false; }

    if (!panel.classList.contains('active')) directSwitchTab('document-control');

    const synthetic = q(`[data-workspace-tab="${state.documents}"]`);
    if (synthetic) setSubnavActive(synthetic);
    window.setTimeout(() => {
      const action = state.documents === 'document-history' ? q('#dc-history-view') : q('#dc-new-view');
      if (action && !action.disabled) action.click();
      syncPanelAccessibility();
      emitNavigation('documents', state.documents);
    }, 0);
    return true;
  }

  async function openWorkspace(name, requestedTarget = null) {
    await permissionsReady;
    let workspace = name;
    if (!workspaceAllowed(workspace)) {
      workspace = ['optimization', 'database', 'documents'].find(workspaceAllowed) || 'database';
    }

    setWorkspaceVisual(workspace);
    if (workspace === 'database') {
      const target = requestedTarget || state.database || WORKSPACE_DEFAULTS.database;
      if (target === 'prompts' && openPromptCenter()) return;
      directSwitchTab('vehicles');
      return;
    }
    if (workspace === 'documents') {
      openDocumentWorkspace(requestedTarget || state.documents || WORKSPACE_DEFAULTS.documents);
      return;
    }

    const target = allowedOptimizationTarget(requestedTarget || state.optimization || WORKSPACE_DEFAULTS.optimization);
    if (target) directSwitchTab(target);
  }

  function stopLegacyNavigation(event) {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  }

  function handleNavigation(event) {
    if (!installed || internalNavigation) return;

    const workspaceCard = event.target.closest?.('#workspace-switcher [data-workspace]');
    if (workspaceCard) {
      if (workspaceCard.disabled || workspaceCard.hidden || workspaceCard.getAttribute('aria-disabled') === 'true') return;
      stopLegacyNavigation(event);
      void openWorkspace(workspaceCard.dataset.workspace);
      return;
    }

    const synthetic = event.target.closest?.('nav.tabs [data-workspace-tab]');
    if (synthetic) {
      if (synthetic.disabled || synthetic.hidden || synthetic.getAttribute('aria-disabled') === 'true') return;
      stopLegacyNavigation(event);
      const target = synthetic.dataset.workspaceTab;
      if (target === 'prompts') openPromptCenter();
      else openDocumentWorkspace(target);
      return;
    }

    const tab = event.target.closest?.('nav.tabs .tab[data-tab]');
    if (!tab || tab.dataset.tab === 'document-control') return;
    if (tab.disabled || tab.getAttribute('aria-disabled') === 'true' || !tabAllowed(tab.dataset.tab)) return;
    stopLegacyNavigation(event);
    setWorkspaceVisual(workspaceForTab(tab.dataset.tab));
    directSwitchTab(tab.dataset.tab);
  }

  function deriveInitialState() {
    const activeTab = q('nav.tabs .tab.active[data-tab]')?.dataset.tab;
    if (!state.workspace && activeTab) {
      state.workspace = workspaceForTab(activeTab);
      if (state.workspace === 'database') state.database = activeTab;
      if (state.workspace === 'optimization') state.optimization = activeTab;
    }
  }

  async function restoreNavigation() {
    await permissionsReady;
    deriveInitialState();
    const workspace = state.workspace || 'database';
    const target = workspace === 'database'
      ? state.database
      : workspace === 'optimization'
        ? state.optimization
        : state.documents;
    await openWorkspace(workspace, target);
  }

  function install() {
    if (installed) return true;
    if (!q('#workspace-switcher') || !q('nav.tabs') || !q('main')) return false;
    installed = true;
    window.addEventListener('click', handleNavigation, true);
    void restoreNavigation();
    return true;
  }

  function init() {
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(install, delay));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
