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

  const state = {
    initialized: false,
    current: {kind: 'tab', name: 'vehicles', workspace: 'database'},
    returnRoute: {kind: 'tab', name: 'vehicles', workspace: 'database'},
    last: {
      database: {kind: 'tab', name: 'vehicles', workspace: 'database'},
      optimization: {kind: 'tab', name: 'data', workspace: 'optimization'},
      documents: {kind: 'document', name: 'document-new', workspace: 'documents'}
    },
    generation: 0,
    context: null,
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

  function cloneControl(source, shellControl, {strip = []} = {}) {
    if (!source || source.dataset.shellLegacy === '1' || source.dataset.shellControl) return null;
    const clone = source.cloneNode(true);
    const originalId = source.id;
    markLegacy(source);
    if (originalId) {
      source.id = `legacy-${originalId}`;
      clone.id = originalId;
    }
    strip.forEach(attribute => clone.removeAttribute(attribute));
    clone.dataset.shellControl = shellControl;
    clone.classList.remove('application-shell-legacy', 'workspace-group-hidden', 'hidden');
    clone.hidden = false;
    clone.removeAttribute('aria-hidden');
    clone.tabIndex = 0;
    source.after(clone);
    return clone;
  }

  function upgradeTopbarControls() {
    if (!state.visible.settings) {
      const source = q('#open-settings:not([data-shell-control])');
      if (source) {
        state.legacy.settings = source;
        state.visible.settings = cloneControl(source, 'settings');
      }
    }
    if (!state.visible.admin) {
      const source = q('#open-admin:not([data-shell-control])');
      if (source) {
        state.legacy.admin = source;
        state.visible.admin = cloneControl(source, 'admin');
        if (state.visible.admin) state.visible.admin.hidden = true;
      }
    }
    if (!state.visible.closeSettings) {
      const source = q('#close-settings:not([data-shell-control])');
      if (source) {
        state.legacy.closeSettings = source;
        state.visible.closeSettings = cloneControl(source, 'close-settings');
      }
    }
    if (!state.visible.closeAdmin) {
      const source = q('#close-admin:not([data-shell-control])');
      if (source) {
        state.legacy.closeAdmin = source;
        state.visible.closeAdmin = cloneControl(source, 'close-admin');
      }
    }
  }

  function upgradePrimaryTabs() {
    qa('nav.tabs .tab[data-tab]').forEach(source => {
      if (source.dataset.shellLegacy === '1' || source.dataset.shellControl) return;
      const name = source.dataset.tab;
      if (name === 'document-control') {
        state.legacy.documentTab = markLegacy(source);
        return;
      }
      if (!TAB_WORKSPACES[name]) return;
      state.legacy.tabs[name] = source;
      const clone = cloneControl(source, `tab:${name}`);
      if (!clone) return;
      clone.dataset.shellTab = name;
      clone.dataset.shellWorkspace = TAB_WORKSPACES[name];
      state.visible.tabs[name] = clone;
    });
  }

  function upgradeWorkspaceControls() {
    const switcher = q('#workspace-switcher');
    if (!switcher) return;
    qa('[data-workspace]', switcher).forEach(source => {
      if (source.dataset.shellLegacy === '1' || source.dataset.shellControl) return;
      const name = source.dataset.workspace;
      state.legacy.workspace[name] = source;
      const clone = cloneControl(source, `workspace:${name}`);
      if (!clone) return;
      clone.dataset.shellWorkspace = name;
      state.visible.workspace[name] = clone;
    });
  }

  function upgradeSyntheticTabs() {
    if (!state.visible.prompt) {
      const source = q('[data-workspace-tab="prompts"]:not([data-shell-control])');
      if (source) {
        state.legacy.prompt = source;
        state.visible.prompt = cloneControl(source, 'view:prompt-center', {strip: ['data-workspace-tab']});
        if (state.visible.prompt) state.visible.prompt.dataset.shellView = 'prompt-center';
      }
    }
    if (!state.visible.documentNew) {
      const source = q('[data-workspace-tab="document-new"]:not([data-shell-control])');
      if (source) {
        state.legacy.documentNew = source;
        state.visible.documentNew = cloneControl(source, 'view:document-new', {strip: ['data-workspace-tab']});
        if (state.visible.documentNew) state.visible.documentNew.dataset.shellView = 'document-new';
      }
    }
    if (!state.visible.documentHistory) {
      const source = q('[data-workspace-tab="document-history"]:not([data-shell-control])');
      if (source) {
        state.legacy.documentHistory = source;
        state.visible.documentHistory = cloneControl(source, 'view:document-history', {strip: ['data-workspace-tab']});
        if (state.visible.documentHistory) state.visible.documentHistory.dataset.shellView = 'document-history';
      }
    }
  }

  function upgradeControls() {
    upgradeTopbarControls();
    upgradePrimaryTabs();
    upgradeWorkspaceControls();
    upgradeSyntheticTabs();
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

  function activateOnlyPanel(panelId) {
    const target = q(`#${panelId}`);
    qa('.tab-panel').forEach(panel => panel.classList.toggle('active', panel === target));
    return target;
  }

  function baseRoute(route = state.current) {
    return route.kind === 'settings' || route.kind === 'admin' ? state.returnRoute : route;
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
      state.visible.prompt, state.visible.documentNew, state.visible.documentHistory
    ].filter(Boolean);
    normalControls.forEach(control => {
      const group = control.dataset.workspaceGroup || control.dataset.shellWorkspace;
      control.classList.toggle('workspace-group-hidden', group !== workspace);
      control.classList.remove('active');
      control.setAttribute('aria-selected', 'false');
    });

    let activeControl = null;
    if (route.kind === 'tab') activeControl = state.visible.tabs[route.name];
    if (route.kind === 'prompt') activeControl = state.visible.prompt;
    if (route.kind === 'document') {
      activeControl = route.name === 'document-history'
        ? state.visible.documentHistory
        : state.visible.documentNew;
    }
    if (activeControl) {
      activeControl.classList.add('active');
      activeControl.setAttribute('aria-selected', 'true');
    }

    state.visible.settings?.classList.toggle('active', route.kind === 'settings');
    state.visible.admin?.classList.toggle('active', route.kind === 'admin');
  }

  function remember(route) {
    if (route.kind === 'tab' || route.kind === 'prompt' || route.kind === 'document') {
      state.last[route.workspace] = route;
    }
  }

  function applyRoute(route) {
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
      activateOnlyPanel(`tab-${route.name}`);
    } else if (route.kind === 'prompt') {
      state.legacy.prompt?.click();
      activateOnlyPanel('tab-prompt-center');
    } else if (route.kind === 'document') {
      const legacy = route.name === 'document-history'
        ? state.legacy.documentHistory
        : state.legacy.documentNew;
      if (legacy) legacy.click();
      else state.legacy.documentTab?.click();
      activateOnlyPanel('tab-document-control');
      window.requestAnimationFrame(() => {
        if (generation !== state.generation || state.current.kind !== 'document') return;
        const inner = route.name === 'document-history' ? q('#dc-history-view') : q('#dc-new-view');
        if (inner && !inner.disabled && !inner.hidden) inner.click();
        activateOnlyPanel('tab-document-control');
        syncChrome(route);
      });
    } else if (route.kind === 'settings') {
      state.legacy.settings?.click();
      activateOnlyPanel('tab-settings');
    } else if (route.kind === 'admin') {
      state.legacy.admin?.click();
      activateOnlyPanel('tab-admin');
    }

    syncChrome(route);
    queueMicrotask(() => {
      if (generation !== state.generation) return;
      const panelId = route.kind === 'tab' ? `tab-${route.name}`
        : route.kind === 'prompt' ? 'tab-prompt-center'
          : route.kind === 'document' ? 'tab-document-control'
            : route.kind === 'settings' ? 'tab-settings' : 'tab-admin';
      activateOnlyPanel(panelId);
      syncChrome(route);
    });
  }

  const navigation = createLastWinsScheduler(applyRoute);

  function routeForWorkspace(name) {
    return state.last[name] || (name === 'optimization'
      ? {kind: 'tab', name: 'data', workspace: 'optimization'}
      : name === 'documents'
        ? {kind: 'document', name: 'document-new', workspace: 'documents'}
        : {kind: 'tab', name: 'vehicles', workspace: 'database'});
  }

  function handleNavigationClick(event) {
    const control = event.target.closest?.('[data-shell-workspace],[data-shell-tab],[data-shell-view],[data-shell-control]');
    if (!control || control.disabled || control.hidden || control.getAttribute('aria-hidden') === 'true') return;

    if (control.id === 'site-logout') {
      event.preventDefault();
      logout(control);
      return;
    }
    if (control.dataset.shellWorkspace && control.classList.contains('workspace-card')) {
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
    const denied = Boolean(state.legacy.documentTab?.hidden || state.legacy.documentTab?.hasAttribute('hidden'));
    setVisible(state.visible.workspace.documents, !denied);
    setVisible(state.visible.documentNew, !denied);
    setVisible(state.visible.documentHistory, !denied);
    const switcher = q('#workspace-switcher');
    if (switcher) {
      const visibleCount = Object.values(state.visible.workspace).filter(control => control && !control.hidden).length;
      switcher.dataset.visibleCount = String(visibleCount);
      switcher.classList.toggle('single-workspace', visibleCount === 1);
    }
    if (denied && baseRoute().workspace === 'documents') navigation.schedule(routeForWorkspace('optimization'));
  }

  function bindPermissionSync() {
    if (!state.legacy.documentTab || state.legacy.documentTab.dataset.shellPermissionObserved === '1') return;
    state.legacy.documentTab.dataset.shellPermissionObserved = '1';
    new MutationObserver(syncPermissions).observe(state.legacy.documentTab, {
      attributes: true,
      attributeFilter: ['hidden']
    });
    syncPermissions();
  }

  function syncRole(context) {
    state.context = context;
    const role = roleFromContext(context);
    document.body.dataset.shellRole = role;
    setVisible(state.visible.settings, true);
    setVisible(state.visible.admin, role === 'super_admin');
    setVisible(q('#site-logout'), true);
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

  function initialRoute() {
    const active = q('.tab-panel.active')?.id || 'tab-vehicles';
    if (active === 'tab-prompt-center') return {kind: 'prompt', name: 'prompt-center', workspace: 'database'};
    if (active === 'tab-document-control') return {kind: 'document', name: 'document-new', workspace: 'documents'};
    if (active === 'tab-settings') return {kind: 'settings', name: 'settings', workspace: 'database'};
    if (active === 'tab-admin') return {kind: 'admin', name: 'admin', workspace: 'database'};
    const name = active.replace(/^tab-/, '');
    return {kind: 'tab', name: TAB_WORKSPACES[name] ? name : 'vehicles', workspace: TAB_WORKSPACES[name] || 'database'};
  }

  function finalize() {
    if (state.initialized) return;
    state.initialized = true;
    arrangeTopbar();
    bindPermissionSync();
    document.addEventListener('click', handleNavigationClick);
    state.current = initialRoute();
    if (state.current.kind !== 'settings' && state.current.kind !== 'admin') state.returnRoute = state.current;
    remember(baseRoute());
    const panelId = state.current.kind === 'tab' ? `tab-${state.current.name}`
      : state.current.kind === 'prompt' ? 'tab-prompt-center'
        : state.current.kind === 'document' ? 'tab-document-control'
          : state.current.kind === 'settings' ? 'tab-settings' : 'tab-admin';
    activateOnlyPanel(panelId);
    syncChrome(state.current);
    setVisible(q('#site-logout'), true);
    loadContext();
    document.body.dataset.applicationShellReady = 'true';
    window.AxioLoadShell = {
      navigate: route => navigation.schedule(route),
      current: () => ({...state.current}),
      context: () => state.context
    };
  }

  function boot(attempt = 0) {
    upgradeControls();
    const ready = Boolean(state.visible.settings && Object.keys(state.visible.tabs).length);
    if (ready || attempt >= 3) {
      finalize();
      return;
    }
    window.requestAnimationFrame(() => boot(attempt + 1));
  }

  const init = () => boot();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
