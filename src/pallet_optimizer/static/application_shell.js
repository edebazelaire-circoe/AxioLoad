(() => {
  'use strict';

  function roleFromContext(context) {
    if (!context) return 'anonymous';
    const directAdmin = context.mode === 'assistance'
      && context.company?.id === 'local'
      && context.actor
      && context.actor !== 'Utilisateur local';
    if (directAdmin) return 'super_admin';
    if (context.mode === 'assistance') return 'assistance';
    if (context.user) return 'user';
    return 'anonymous';
  }

  function createLastWinsScheduler(apply, scheduleFrame = callback => window.requestAnimationFrame(callback)) {
    let pending = null;
    let scheduled = false;
    const schedule = value => {
      pending = value;
      if (scheduled) return;
      scheduled = true;
      scheduleFrame(() => {
        scheduled = false;
        const next = pending;
        pending = null;
        apply(next);
        if (pending !== null) schedule(pending);
      });
    };
    return {schedule, hasPending: () => scheduled || pending !== null};
  }

  if (window.__AXIOLOAD_SHELL_TEST_ONLY__) {
    window.AxioLoadShellTest = {roleFromContext, createLastWinsScheduler};
    return;
  }

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const TAB_WORKSPACES = {
    vehicles: 'database',
    data: 'optimization',
    results: 'optimization',
    history: 'optimization',
    route: 'optimization',
    total: 'optimization'
  };
  const DEFAULT_ROUTES = {
    database: {kind: 'tab', name: 'vehicles', workspace: 'database'},
    optimization: {kind: 'tab', name: 'data', workspace: 'optimization'},
    documents: {kind: 'document', name: 'document-new', workspace: 'documents'}
  };
  const OPTIMIZATION_ORDER = ['data', 'results', 'history', 'route', 'total'];

  const state = {
    initialized: false,
    current: {...DEFAULT_ROUTES.database},
    returnRoute: {...DEFAULT_ROUTES.database},
    last: {
      database: {...DEFAULT_ROUTES.database},
      optimization: {...DEFAULT_ROUTES.optimization},
      documents: {...DEFAULT_ROUTES.documents}
    },
    generation: 0,
    context: null,
    bootObserver: null,
    permissionObserver: null,
    legacy: {
      tabs: {}, workspace: {}, settings: null, admin: null,
      closeSettings: null, closeAdmin: null,
      prompt: null, documentNew: null, documentHistory: null, documentTab: null
    },
    visible: {
      tabs: {}, workspace: {}, settings: null, admin: null,
      closeSettings: null, closeAdmin: null,
      prompt: null, documentNew: null, documentHistory: null
    }
  };

  function markLegacy(control) {
    if (!control || control.dataset.shellLegacy === '1') return control;
    control.dataset.shellLegacy = '1';
    control.classList.add('application-shell-legacy');
    control.setAttribute('aria-hidden', 'true');
    control.tabIndex = -1;
    return control;
  }

  function shellId(source, shellControl) {
    if (source?.id) return `shell-${source.id}`;
    return `shell-${String(shellControl).replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`;
  }

  function cloneControl(source, shellControl, {strip = []} = {}) {
    if (!source || source.dataset.shellLegacy === '1' || source.dataset.shellControl) return null;
    const clone = source.cloneNode(true);
    markLegacy(source);
    clone.id = shellId(source, shellControl);
    strip.forEach(attribute => clone.removeAttribute(attribute));
    clone.dataset.shellControl = shellControl;
    clone.classList.remove('application-shell-legacy', 'workspace-group-hidden', 'hidden', 'active');
    clone.hidden = false;
    clone.removeAttribute('aria-hidden');
    clone.tabIndex = 0;
    source.after(clone);
    return clone;
  }

  function upgradeTopbarControls() {
    if (!state.visible.settings) {
      const source = q('#open-settings:not([data-shell-legacy])');
      if (source) {
        state.legacy.settings = source;
        state.visible.settings = cloneControl(source, 'settings');
      }
    }
    if (!state.visible.admin) {
      const source = q('#open-admin:not([data-shell-legacy])');
      if (source) {
        state.legacy.admin = source;
        state.visible.admin = cloneControl(source, 'admin');
        if (state.visible.admin) state.visible.admin.hidden = true;
      }
    }
    if (!state.visible.closeSettings) {
      const source = q('#close-settings:not([data-shell-legacy])');
      if (source) {
        state.legacy.closeSettings = source;
        state.visible.closeSettings = cloneControl(source, 'close-settings');
      }
    }
    if (!state.visible.closeAdmin) {
      const source = q('#close-admin:not([data-shell-legacy])');
      if (source) {
        state.legacy.closeAdmin = source;
        state.visible.closeAdmin = cloneControl(source, 'close-admin');
      }
    }
  }

  function upgradePrimaryTabs() {
    qa('nav.tabs .tab[data-tab]:not([data-shell-legacy])').forEach(source => {
      const name = source.dataset.tab;
      if (name === 'document-control') {
        state.legacy.documentTab = markLegacy(source);
        return;
      }
      if (!TAB_WORKSPACES[name] || state.visible.tabs[name]) return;
      state.legacy.tabs[name] = source;
      const clone = cloneControl(source, `tab:${name}`, {strip: ['data-tab', 'data-workspace-group']});
      if (!clone) return;
      clone.dataset.shellTab = name;
      clone.dataset.shellWorkspace = TAB_WORKSPACES[name];
      state.visible.tabs[name] = clone;
    });
  }

  function upgradeWorkspaceControls() {
    const switcher = q('#workspace-switcher');
    if (!switcher) return;
    qa('[data-workspace]:not([data-shell-legacy])', switcher).forEach(source => {
      const name = source.dataset.workspace;
      if (!name || state.visible.workspace[name]) return;
      state.legacy.workspace[name] = source;
      const clone = cloneControl(source, `workspace:${name}`, {strip: ['data-workspace']});
      if (!clone) return;
      clone.dataset.shellWorkspace = name;
      state.visible.workspace[name] = clone;
    });
  }

  function upgradeSyntheticTabs() {
    if (!state.visible.prompt) {
      const source = q('[data-workspace-tab="prompts"]:not([data-shell-legacy])');
      if (source) {
        state.legacy.prompt = source;
        state.visible.prompt = cloneControl(source, 'view:prompt-center', {
          strip: ['data-workspace-tab', 'data-workspace-group']
        });
        if (state.visible.prompt) {
          state.visible.prompt.dataset.shellView = 'prompt-center';
          state.visible.prompt.dataset.shellWorkspace = 'database';
        }
      }
    }
    if (!state.visible.documentNew) {
      const source = q('[data-workspace-tab="document-new"]:not([data-shell-legacy])');
      if (source) {
        state.legacy.documentNew = source;
        state.visible.documentNew = cloneControl(source, 'view:document-new', {
          strip: ['data-workspace-tab', 'data-workspace-group']
        });
        if (state.visible.documentNew) {
          state.visible.documentNew.dataset.shellView = 'document-new';
          state.visible.documentNew.dataset.shellWorkspace = 'documents';
        }
      }
    }
    if (!state.visible.documentHistory) {
      const source = q('[data-workspace-tab="document-history"]:not([data-shell-legacy])');
      if (source) {
        state.legacy.documentHistory = source;
        state.visible.documentHistory = cloneControl(source, 'view:document-history', {
          strip: ['data-workspace-tab', 'data-workspace-group']
        });
        if (state.visible.documentHistory) {
          state.visible.documentHistory.dataset.shellView = 'document-history';
          state.visible.documentHistory.dataset.shellWorkspace = 'documents';
        }
      }
    }
  }

  function upgradeControls() {
    upgradeTopbarControls();
    upgradePrimaryTabs();
    upgradeWorkspaceControls();
    upgradeSyntheticTabs();
  }

  function controlsReady() {
    return Boolean(
      state.visible.settings
      && state.visible.admin
      && state.visible.closeSettings
      && state.visible.closeAdmin
      && state.legacy.documentTab
      && Object.keys(state.visible.tabs).length === Object.keys(TAB_WORKSPACES).length
      && Object.keys(state.visible.workspace).length === 3
      && state.visible.prompt
      && state.visible.documentNew
      && state.visible.documentHistory
    );
  }

  function arrangeTopbar() {
    const topbar = q('.topbar');
    if (!topbar) return;
    let actions = q('.application-shell-actions', topbar);
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'application-shell-actions';
      topbar.append(actions);
    }
    [state.visible.settings, state.visible.admin, q('#site-logout')].forEach(control => {
      if (control && control.parentElement !== actions) actions.append(control);
    });
  }

  function setVisible(control, visible) {
    if (!control) return;
    control.hidden = !visible;
    control.classList.toggle('hidden', !visible);
    control.setAttribute('aria-hidden', String(!visible));
    control.tabIndex = visible ? 0 : -1;
  }

  function controlAllowed(control) {
    return Boolean(
      control
      && !control.hidden
      && !control.disabled
      && control.getAttribute('aria-hidden') !== 'true'
      && !control.classList.contains('hidden')
    );
  }

  function sourceDenied(source) {
    return !source
      || source.hidden
      || source.disabled
      || source.hasAttribute('hidden')
      || source.getAttribute('aria-hidden') === 'true'
      || source.classList.contains('hidden');
  }

  function activateOnlyPanel(panelId) {
    const target = q(`#${panelId}`);
    qa('.tab-panel').forEach(panel => panel.classList.toggle('active', panel === target));
    return target;
  }

  function baseRoute(route = state.current) {
    return route.kind === 'settings' || route.kind === 'admin' ? state.returnRoute : route;
  }

  function panelIdFor(route) {
    if (route.kind === 'tab') return `tab-${route.name}`;
    if (route.kind === 'prompt') return 'tab-prompt-center';
    if (route.kind === 'document') return 'tab-document-control';
    if (route.kind === 'settings') return 'tab-settings';
    return 'tab-admin';
  }

  function visibleControlForRoute(route) {
    if (!route) return null;
    if (route.kind === 'tab') return state.visible.tabs[route.name];
    if (route.kind === 'prompt') return state.visible.prompt;
    if (route.kind === 'document') {
      return route.name === 'document-history'
        ? state.visible.documentHistory
        : state.visible.documentNew;
    }
    if (route.kind === 'settings') return state.visible.settings;
    if (route.kind === 'admin') return state.visible.admin;
    return null;
  }

  function firstAllowedRoute(workspace) {
    if (workspace === 'database') {
      if (controlAllowed(state.visible.tabs.vehicles)) return {...DEFAULT_ROUTES.database};
      if (controlAllowed(state.visible.prompt)) return {kind: 'prompt', name: 'prompt-center', workspace: 'database'};
      return null;
    }
    if (workspace === 'optimization') {
      const name = OPTIMIZATION_ORDER.find(tabName => controlAllowed(state.visible.tabs[tabName]));
      return name ? {kind: 'tab', name, workspace: 'optimization'} : null;
    }
    if (workspace === 'documents' && controlAllowed(state.visible.documentNew)) {
      return {...DEFAULT_ROUTES.documents};
    }
    return null;
  }

  function fallbackRoute(excludedWorkspace = null) {
    return ['database', 'optimization', 'documents']
      .filter(name => name !== excludedWorkspace)
      .map(firstAllowedRoute)
      .find(Boolean) || {...DEFAULT_ROUTES.database};
  }

  function syncChrome(route = state.current) {
    const base = baseRoute(route);
    const workspace = base.workspace || 'database';
    document.body.dataset.workspace = workspace;
    const nav = q('nav.tabs');
    if (nav) nav.dataset.workspace = workspace;

    Object.entries(state.visible.workspace).forEach(([name, control]) => {
      const active = name === workspace;
      control.classList.toggle('active', active);
      control.setAttribute('aria-pressed', String(active));
    });

    const normalControls = [
      ...Object.values(state.visible.tabs),
      state.visible.prompt,
      state.visible.documentNew,
      state.visible.documentHistory
    ].filter(Boolean);
    normalControls.forEach(control => {
      const group = control.dataset.shellWorkspace;
      control.classList.toggle('workspace-group-hidden', group !== workspace);
      control.classList.remove('active');
      control.setAttribute('aria-selected', 'false');
    });

    const activeControl = visibleControlForRoute(route);
    if (activeControl) {
      activeControl.classList.add('active');
      activeControl.setAttribute('aria-selected', 'true');
    }

    state.visible.settings?.classList.toggle('active', route.kind === 'settings');
    state.visible.admin?.classList.toggle('active', route.kind === 'admin');
  }

  function enforceRoute(route, generation) {
    if (generation !== state.generation) return;
    activateOnlyPanel(panelIdFor(route));
    syncChrome(route);
  }

  function remember(route) {
    if (route.kind === 'tab' || route.kind === 'prompt' || route.kind === 'document') {
      state.last[route.workspace] = route;
    }
  }

  function applyRoute(route) {
    if (!route || !controlAllowed(visibleControlForRoute(route))) {
      const workspace = route?.workspace || 'database';
      route = firstAllowedRoute(workspace) || fallbackRoute(workspace);
    }
    if (!route) return;

    const generation = ++state.generation;
    if (route.kind === 'settings' || route.kind === 'admin') {
      if (state.current.kind !== 'settings' && state.current.kind !== 'admin') state.returnRoute = state.current;
    } else {
      remember(route);
    }
    state.current = route;

    if (route.kind === 'tab') {
      state.legacy.tabs[route.name]?.click();
    } else if (route.kind === 'prompt') {
      state.legacy.prompt?.click();
    } else if (route.kind === 'document') {
      const legacy = route.name === 'document-history'
        ? state.legacy.documentHistory
        : state.legacy.documentNew;
      if (legacy) legacy.click();
      else state.legacy.documentTab?.click();
    } else if (route.kind === 'settings') {
      state.legacy.settings?.click();
    } else if (route.kind === 'admin') {
      state.legacy.admin?.click();
    }

    enforceRoute(route, generation);
    queueMicrotask(() => enforceRoute(route, generation));
    window.requestAnimationFrame(() => {
      if (route.kind === 'document' && generation === state.generation) {
        const inner = route.name === 'document-history' ? q('#dc-history-view') : q('#dc-new-view');
        if (inner && !inner.disabled && !inner.hidden) inner.click();
      }
      enforceRoute(route, generation);
    });
  }

  const navigation = createLastWinsScheduler(applyRoute);

  function routeForWorkspace(name) {
    return firstAllowedRoute(name) || fallbackRoute(name);
  }

  function handleNavigationClick(event) {
    const control = event.target.closest?.('[data-shell-workspace],[data-shell-tab],[data-shell-view],[data-shell-control]');
    if (!controlAllowed(control)) return;

    if (control.dataset.shellControl === 'logout') {
      event.preventDefault();
      logout(control);
      return;
    }
    if (control.dataset.shellControl?.startsWith('workspace:')) {
      event.preventDefault();
      navigation.schedule(routeForWorkspace(control.dataset.shellWorkspace));
      return;
    }
    if (control.dataset.shellTab) {
      event.preventDefault();
      navigation.schedule({kind: 'tab', name: control.dataset.shellTab, workspace: control.dataset.shellWorkspace});
      return;
    }
    if (control.dataset.shellView === 'prompt-center') {
      event.preventDefault();
      navigation.schedule({kind: 'prompt', name: 'prompt-center', workspace: 'database'});
      return;
    }
    if (control.dataset.shellView === 'document-new' || control.dataset.shellView === 'document-history') {
      event.preventDefault();
      navigation.schedule({kind: 'document', name: control.dataset.shellView, workspace: 'documents'});
      return;
    }
    if (control.dataset.shellControl === 'settings') {
      event.preventDefault();
      navigation.schedule({kind: 'settings', name: 'settings', workspace: baseRoute().workspace});
      return;
    }
    if (control.dataset.shellControl === 'admin') {
      event.preventDefault();
      navigation.schedule({kind: 'admin', name: 'admin', workspace: baseRoute().workspace});
      return;
    }
    if (control.dataset.shellControl === 'close-settings' || control.dataset.shellControl === 'close-admin') {
      event.preventDefault();
      navigation.schedule(state.returnRoute);
    }
  }

  async function logout(button) {
    if (button.disabled) return;
    button.disabled = true;
    try {
      if (state.context?.mode === 'assistance' && state.context.company?.id !== 'local') {
        await fetch('/api/admin/assistance/exit', {method: 'POST', credentials: 'same-origin'}).catch(() => null);
      }
      await fetch('/api/auth/logout', {method: 'POST', credentials: 'same-origin'}).catch(() => null);
    } finally {
      localStorage.removeItem('axioload.superadmin.active');
      if (typeof location.replace === 'function') location.replace('/login');
      else location.href = '/login';
    }
  }

  function syncPermissions() {
    Object.entries(state.legacy.tabs).forEach(([name, source]) => {
      setVisible(state.visible.tabs[name], !sourceDenied(source));
    });

    setVisible(state.visible.prompt, !sourceDenied(state.legacy.prompt));

    const documentsDenied = sourceDenied(state.legacy.documentTab);
    setVisible(state.visible.documentNew, !documentsDenied && !sourceDenied(state.legacy.documentNew));
    setVisible(state.visible.documentHistory, !documentsDenied && !sourceDenied(state.legacy.documentHistory));

    const workspaceAllowed = {
      database: controlAllowed(state.visible.tabs.vehicles) || controlAllowed(state.visible.prompt),
      optimization: OPTIMIZATION_ORDER.some(name => controlAllowed(state.visible.tabs[name])),
      documents: controlAllowed(state.visible.documentNew) || controlAllowed(state.visible.documentHistory)
    };
    Object.entries(workspaceAllowed).forEach(([name, allowed]) => {
      setVisible(state.visible.workspace[name], allowed);
    });

    const switcher = q('#workspace-switcher');
    if (switcher) {
      const visibleCount = Object.values(state.visible.workspace).filter(controlAllowed).length;
      switcher.dataset.visibleCount = String(visibleCount);
      switcher.classList.toggle('single-workspace', visibleCount === 1);
    }

    const currentBase = baseRoute();
    if (!controlAllowed(visibleControlForRoute(currentBase))) {
      const next = firstAllowedRoute(currentBase.workspace) || fallbackRoute(currentBase.workspace);
      if (next) navigation.schedule(next);
    } else {
      syncChrome(state.current);
    }
  }

  function bindPermissionSync() {
    if (state.permissionObserver) return;
    const sources = [
      ...Object.values(state.legacy.tabs),
      state.legacy.documentTab,
      state.legacy.prompt,
      state.legacy.documentNew,
      state.legacy.documentHistory
    ].filter(Boolean);
    state.permissionObserver = new MutationObserver(syncPermissions);
    sources.forEach(source => state.permissionObserver.observe(source, {
      attributes: true,
      attributeFilter: ['hidden', 'disabled', 'aria-hidden', 'class']
    }));
    syncPermissions();
  }

  function syncRole(context) {
    state.context = context;
    const role = roleFromContext(context);
    document.body.dataset.shellRole = role;
    setVisible(state.visible.settings, role !== 'anonymous');
    setVisible(state.visible.admin, role === 'super_admin');
    setVisible(q('#site-logout'), role !== 'anonymous');
    arrangeTopbar();
  }

  async function loadContext() {
    try {
      const response = await fetch('/api/company/context', {credentials: 'same-origin'});
      syncRole(response.ok ? await response.json() : null);
    } catch (_) {
      syncRole(null);
    }
  }

  function finalize() {
    if (state.initialized || !controlsReady()) return false;
    state.initialized = true;
    state.bootObserver?.disconnect();
    state.bootObserver = null;
    arrangeTopbar();
    bindPermissionSync();
    document.addEventListener('click', handleNavigationClick);
    state.current = firstAllowedRoute('database') || fallbackRoute();
    state.returnRoute = {...state.current};
    state.last.database = {...state.current};
    enforceRoute(state.current, state.generation);
    setVisible(q('#site-logout'), true);
    loadContext();
    document.body.dataset.applicationShellReady = 'true';
    window.AxioLoadShell = {
      navigate: route => navigation.schedule(route),
      current: () => ({...state.current}),
      context: () => state.context,
      audit: () => ({
        activePanels: qa('.tab-panel.active').map(panel => panel.id),
        role: document.body.dataset.shellRole || null,
        workspace: document.body.dataset.workspace || null,
        visibleTabs: Object.entries(state.visible.tabs)
          .filter(([, control]) => controlAllowed(control))
          .map(([name]) => name)
      })
    };
    return true;
  }

  function tryBoot() {
    upgradeControls();
    return finalize();
  }

  function boot() {
    if (tryBoot() || state.bootObserver) return;
    const nav = q('nav.tabs');
    const root = nav?.parentElement || document.documentElement;
    state.bootObserver = new MutationObserver(() => tryBoot());
    state.bootObserver.observe(root, {childList: true, subtree: true});
    window.addEventListener('load', tryBoot, {once: true});
  }

  const init = () => boot();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
