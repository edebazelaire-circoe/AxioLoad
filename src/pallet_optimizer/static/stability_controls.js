(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  let contextPromise = null;
  let navigationInstalled = false;

  function loadContext() {
    if (!contextPromise) {
      contextPromise = fetch('/api/company/context', {credentials: 'same-origin'})
        .then(response => response.ok ? response.json() : null)
        .catch(() => null);
    }
    return contextPromise;
  }

  function isAuthenticated(context) {
    if (!context) return false;
    const directManagement = context.mode === 'assistance'
      && context.company?.id === 'local'
      && context.actor
      && context.actor !== 'Utilisateur local';
    const assistance = context.mode === 'assistance' && context.company?.id !== 'local';
    return Boolean(context.user) || directManagement || assistance;
  }

  function ensureLogoutButton(context) {
    const topbar = q('.topbar');
    if (!topbar) return false;
    if (q('#site-logout')) return true;

    const button = document.createElement('button');
    button.id = 'site-logout';
    button.type = 'button';
    button.className = 'settings-access auth-logout';
    button.setAttribute('aria-label', 'Se déconnecter');
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10"/></svg><span>Se déconnecter</span>';
    topbar.append(button);

    button.addEventListener('click', async () => {
      if (button.disabled) return;
      button.disabled = true;
      try {
        if (context.mode === 'assistance' && context.company?.id !== 'local') {
          await fetch('/api/admin/assistance/exit', {
            method: 'POST',
            credentials: 'same-origin',
          }).catch(() => null);
        }
        await fetch('/api/auth/logout', {
          method: 'POST',
          credentials: 'same-origin',
        });
      } finally {
        localStorage.removeItem('axioload.superadmin.active');
        sessionStorage.clear();
        window.location.replace('/login');
      }
    });
    return true;
  }

  function isUsable(element) {
    return Boolean(element && !element.disabled && element.getAttribute('aria-hidden') !== 'true');
  }

  function activateNativeTab(tabName) {
    const tab = q(`[data-tab="${tabName}"]`);
    const panel = q(`#tab-${tabName}`);
    if (!tab || !panel) return false;

    qa('[data-tab]').forEach(button => {
      const active = button === tab;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    qa('.tab-panel').forEach(candidate => candidate.classList.toggle('active', candidate === panel));
    tab.click();
    return panel.classList.contains('active');
  }

  function setWorkspaceVisual(workspace) {
    document.body.dataset.workspace = workspace;
    qa('[data-workspace]').forEach(button => {
      const active = button.dataset.workspace === workspace;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const nav = q('nav.tabs');
    if (nav) nav.dataset.workspace = workspace;
    qa('[data-workspace-group]').forEach(button => {
      button.classList.toggle('workspace-group-hidden', button.dataset.workspaceGroup !== workspace);
    });
  }

  function openWorkspace(workspace) {
    if (workspace === 'database') {
      setWorkspaceVisual('database');
      return activateNativeTab('vehicles');
    }
    if (workspace === 'optimization') {
      setWorkspaceVisual('optimization');
      const candidates = ['data', 'results', 'history', 'route', 'total'];
      const current = candidates.find(name => q(`[data-tab="${name}"]`)?.classList.contains('active'));
      return activateNativeTab(current || 'data');
    }
    if (workspace === 'documents') {
      const documentTab = q('[data-tab="document-control"]');
      if (!isUsable(documentTab)) return false;
      setWorkspaceVisual('documents');
      return activateNativeTab('document-control');
    }
    return false;
  }

  function installNavigation() {
    if (navigationInstalled) return true;
    const switcher = q('#workspace-switcher');
    if (!switcher) return false;

    switcher.addEventListener('click', event => {
      const button = event.target.closest?.('[data-workspace]');
      if (!button || button.disabled || button.hidden) return;
      const workspace = button.dataset.workspace;
      if (!workspace) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      openWorkspace(workspace);
    }, true);

    navigationInstalled = true;
    return true;
  }

  async function install() {
    const context = await loadContext();
    if (isAuthenticated(context)) ensureLogoutButton(context);
    installNavigation();
  }

  function start() {
    [0, 50, 150, 400, 900, 1800].forEach(delay => {
      window.setTimeout(() => { void install(); }, delay);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
})();
