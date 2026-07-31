(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  const icons = {
    database: '<svg viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>',
    truck: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h11v10H3zM14 9h4l3 3v3h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm11 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/></svg>',
    document: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2h8l4 4v16H6zM14 2v5h5M9 11h6M9 15h6M9 19h4"/></svg>',
    shield: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5zM9 12l2 2 4-5"/></svg>',
    vehicles: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h12v9H3zM15 10h3l3 3v3h-6M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm11 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/></svg>',
    data: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v16H4zM4 9h16M9 4v16"/></svg>',
    results: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19V9M12 19V5M19 19v-7"/></svg>',
    history: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"/></svg>',
    route: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm12-8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM8 15c4 0 4-6 8-6"/></svg>',
    total: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16M4 12h16M4 19h16M7 2v6M17 9v6M10 16v6"/></svg>',
    api: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 9 4 12l4 3M16 9l4 3-4 3M14 5l-4 14"/></svg>',
    prompt: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v12H8l-3 3zM8 8h8M8 12h6"/></svg>',
    upload: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>',
    spark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 1.4 5.6L19 9l-5.6 1.4L12 16l-1.4-5.6L5 9l5.6-1.4zM19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7z"/></svg>'
  };

  const icon = (name, className = '') => `<span class="ax-icon ${className}">${icons[name] || icons.spark}</span>`;

  async function adminApi(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body?.detail || `Erreur ${response.status}`);
    return body;
  }

  function decorateTab(button, iconName) {
    if (!button || q('.ax-tab-icon', button)) return;
    const label = button.textContent.trim();
    button.innerHTML = `${icon(iconName, 'ax-tab-icon')}<span>${escapeHtml(label)}</span>`;
  }

  function setSubnavActive(nav, activeButton) {
    qa('.tab', nav).forEach(button => {
      const active = button === activeButton;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
  }

  function isUsable(button) {
    return Boolean(button && !button.hidden && !button.disabled && button.getAttribute('aria-hidden') !== 'true');
  }

  function installWorkspaceSwitcher() {
    const nav = q('nav.tabs');
    const documentTab = q('[data-tab="document-control"]', nav || document);
    const documentPanel = q('#tab-document-control');
    if (!nav || !documentTab || !documentPanel) return false;
    if (q('#workspace-switcher')) return true;

    const originalTabs = {
      vehicles: q('[data-tab="vehicles"]', nav),
      data: q('[data-tab="data"]', nav),
      results: q('[data-tab="results"]', nav),
      route: q('[data-tab="route"]', nav),
      total: q('[data-tab="total"]', nav),
      history: q('[data-tab="history"]', nav)
    };
    const tabIcons = {vehicles: 'vehicles', data: 'data', results: 'results', route: 'route', total: 'total', history: 'history'};
    Object.entries(originalTabs).forEach(([name, button]) => decorateTab(button, tabIcons[name]));

    documentTab.classList.add('ax-hidden-document-tab');
    documentTab.setAttribute('aria-hidden', 'true');
    Object.entries(originalTabs).forEach(([name, button]) => {
      if (button) button.dataset.workspaceGroup = name === 'vehicles' ? 'database' : 'optimization';
    });

    const promptButton = document.createElement('button');
    promptButton.type = 'button';
    promptButton.className = 'tab workspace-synthetic-tab';
    promptButton.dataset.workspaceGroup = 'database';
    promptButton.dataset.workspaceTab = 'prompts';
    promptButton.innerHTML = `${icon('prompt', 'ax-tab-icon')}<span>Prompts</span>`;

    const documentNewButton = document.createElement('button');
    documentNewButton.type = 'button';
    documentNewButton.className = 'tab workspace-synthetic-tab';
    documentNewButton.dataset.workspaceGroup = 'documents';
    documentNewButton.dataset.workspaceTab = 'document-new';
    documentNewButton.innerHTML = `${icon('document', 'ax-tab-icon')}<span>Nouveau contrôle</span>`;

    const documentHistoryButton = document.createElement('button');
    documentHistoryButton.type = 'button';
    documentHistoryButton.className = 'tab workspace-synthetic-tab';
    documentHistoryButton.dataset.workspaceGroup = 'documents';
    documentHistoryButton.dataset.workspaceTab = 'document-history';
    documentHistoryButton.innerHTML = `${icon('history', 'ax-tab-icon')}<span>Historique</span>`;

    nav.append(promptButton, documentNewButton, documentHistoryButton);
    nav.classList.add('workspace-subnav');

    const switcher = document.createElement('section');
    switcher.id = 'workspace-switcher';
    switcher.className = 'workspace-switcher';
    switcher.setAttribute('aria-label', 'Choisir un espace de travail');
    switcher.innerHTML = `
      <button type="button" class="workspace-card workspace-database active" data-workspace="database">
        ${icon('database')}<span><strong>Base de données</strong><small>Flotte et prompts</small></span>
      </button>
      <button type="button" class="workspace-card workspace-optimization" data-workspace="optimization">
        ${icon('truck')}<span><strong>Optimisation</strong><small>Chargement, itinéraires et historique</small></span>
      </button>
      <button type="button" class="workspace-card workspace-documents" data-workspace="documents">
        ${icon('shield')}<span><strong>Contrôle documentaire</strong><small>Comparer, corriger et exporter</small></span>
      </button>`;
    nav.before(switcher);

    let workspace = 'database';
    let lastDatabaseTab = 'vehicles';
    let lastOptimizationTab = 'data';
    let lastDocumentTab = 'document-new';
    const workspaceButtons = () => qa('[data-workspace-group]', nav);

    const setWorkspaceVisual = name => {
      workspace = name;
      document.body.dataset.workspace = name;
      qa('[data-workspace]', switcher).forEach(button => {
        const active = button.dataset.workspace === name;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
      });
      workspaceButtons().forEach(button => {
        button.classList.toggle('workspace-group-hidden', button.dataset.workspaceGroup !== name);
      });
      nav.dataset.workspace = name;
    };

    const openDatabase = targetName => {
      setWorkspaceVisual('database');
      const target = targetName || lastDatabaseTab;
      if (target === 'prompts') {
        lastDatabaseTab = 'prompts';
        setSubnavActive(nav, promptButton);
        return;
      }
      const vehicleTab = isUsable(originalTabs.vehicles) ? originalTabs.vehicles : null;
      if (vehicleTab) {
        lastDatabaseTab = 'vehicles';
        vehicleTab.click();
        setSubnavActive(nav, vehicleTab);
      } else if (isUsable(promptButton)) {
        promptButton.click();
      }
    };

    const openOptimization = targetName => {
      setWorkspaceVisual('optimization');
      const preferred = originalTabs[targetName || lastOptimizationTab];
      const target = isUsable(preferred)
        ? preferred
        : Object.values(originalTabs).find(button => button?.dataset.workspaceGroup === 'optimization' && isUsable(button));
      if (!target) return;
      lastOptimizationTab = target.dataset.tab;
      target.click();
      setSubnavActive(nav, target);
    };

    const openDocuments = targetName => {
      if (!isUsable(q('[data-workspace="documents"]', switcher))) return;
      setWorkspaceVisual('documents');
      lastDocumentTab = targetName || lastDocumentTab;
      documentTab.click();
      const synthetic = lastDocumentTab === 'document-history' ? documentHistoryButton : documentNewButton;
      setSubnavActive(nav, synthetic);
      window.setTimeout(() => {
        const action = lastDocumentTab === 'document-history' ? q('#dc-history-view') : q('#dc-new-view');
        if (isUsable(action)) action.click();
      }, 0);
    };

    q('[data-workspace="database"]', switcher)?.addEventListener('click', event => {
      if (!event.currentTarget.disabled && !event.currentTarget.hidden) openDatabase();
    });
    q('[data-workspace="optimization"]', switcher)?.addEventListener('click', event => {
      if (!event.currentTarget.disabled && !event.currentTarget.hidden) openOptimization();
    });
    q('[data-workspace="documents"]', switcher)?.addEventListener('click', event => {
      if (!event.currentTarget.disabled && !event.currentTarget.hidden) openDocuments();
    });

    promptButton.addEventListener('click', () => {
      if (!promptButton.disabled && !promptButton.hidden) {
        setWorkspaceVisual('database');
        lastDatabaseTab = 'prompts';
        setSubnavActive(nav, promptButton);
      }
    });
    documentNewButton.addEventListener('click', () => {
      if (!documentNewButton.disabled && !documentNewButton.hidden) openDocuments('document-new');
    });
    documentHistoryButton.addEventListener('click', () => {
      if (!documentHistoryButton.disabled && !documentHistoryButton.hidden) openDocuments('document-history');
    });

    Object.entries(originalTabs).forEach(([name, button]) => {
      if (!button) return;
      button.addEventListener('click', () => {
        if (button.disabled || button.hidden) return;
        const group = button.dataset.workspaceGroup;
        if (group === 'database') lastDatabaseTab = name;
        else lastOptimizationTab = name;
        setWorkspaceVisual(group);
        setSubnavActive(nav, button);
      });
    });

    q('#close-settings')?.addEventListener('click', () => {
      if (workspace === 'documents') window.setTimeout(() => openDocuments(lastDocumentTab), 0);
    });

    openDatabase('vehicles');
    return true;
  }

  function polishDocumentModule() {
    const panel = q('#tab-document-control');
    if (!panel) return false;
    if (panel.dataset.experienceReady === '1') return true;
    panel.dataset.experienceReady = '1';

    const heading = q('.panel-heading > div:first-child', panel);
    if (heading && !q('.dc-module-brand', heading)) {
      heading.insertAdjacentHTML('afterbegin', `<div class="dc-module-brand">${icon('shield')}<span>AxioLoad Documents</span></div>`);
    }
    const title = q('.panel-heading h2', panel);
    const intro = q('.panel-heading .section-intro', panel);
    const security = q('.dc-security span', panel);
    if (title) title.textContent = 'Comparer deux documents';
    if (intro) intro.textContent = 'Déposez les fichiers, lancez l’analyse, puis validez les écarts.';
    if (security) security.textContent = 'Fichiers supprimés après analyse. Seuls les résultats et décisions sont conservés.';

    const form = q('#dc-form', panel);
    if (form && !q('.dc-progress-strip', panel)) {
      form.insertAdjacentHTML('beforebegin', `
        <ol class="dc-progress-strip" aria-label="Étapes du contrôle">
          <li class="active">${icon('upload')}<span>1. Documents</span></li>
          <li>${icon('spark')}<span>2. Analyse</span></li>
          <li>${icon('check')}<span>3. Validation</span></li>
        </ol>`);
    }

    qa('input[type="file"]', panel).forEach(input => {
      const label = input.closest('label');
      if (!label || label.classList.contains('dc-dropzone')) return;
      label.classList.add('dc-dropzone');
      const originalText = [...label.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
      if (originalText) originalText.textContent = '';
      input.insertAdjacentHTML('beforebegin', `${icon('upload')}<strong>Déposer un fichier</strong><span class="dc-file-state">PDF, JPG ou PNG</span>`);
      const state = q('.dc-file-state', label);
      input.addEventListener('change', () => {
        if (state) state.textContent = input.files?.[0]?.name || 'PDF, JPG ou PNG';
        label.classList.toggle('has-file', Boolean(input.files?.length));
      });
      ['dragenter', 'dragover'].forEach(eventName => label.addEventListener(eventName, event => {
        event.preventDefault();
        label.classList.add('dragging');
      }));
      ['dragleave', 'drop'].forEach(eventName => label.addEventListener(eventName, event => {
        event.preventDefault();
        label.classList.remove('dragging');
      }));
    });

    const newButton = q('#dc-new-view', panel);
    const historyButton = q('#dc-history-view', panel);
    if (newButton && !q('.ax-icon', newButton)) newButton.innerHTML = `${icon('document')}<span>Nouveau</span>`;
    if (historyButton && !q('.ax-icon', historyButton)) historyButton.innerHTML = `${icon('history')}<span>Historique</span>`;
    return true;
  }

  function enhanceApiTester() {
    const card = q('#dc-admin-ai');
    if (!card) return false;
    if (q('#dc-a-test', card)) return true;
    const actions = q('.admin-actions', card);
    const state = q('#dc-a-state', card);
    if (!actions || !state) return false;

    const testButton = document.createElement('button');
    testButton.type = 'button';
    testButton.id = 'dc-a-test';
    testButton.className = 'secondary api-test-button';
    testButton.innerHTML = `${icon('api')}<span>Tester la connexion</span>`;
    actions.prepend(testButton);

    const detail = document.createElement('div');
    detail.id = 'dc-a-test-detail';
    detail.className = 'api-test-detail hidden';
    state.after(detail);

    testButton.addEventListener('click', async () => {
      if (testButton.disabled) return;
      const tenantId = q('#admin-company-detail')?.dataset?.tenantId || window.__axioloadSelectedTenant;
      if (!tenantId) {
        detail.textContent = 'Entreprise introuvable. Revenez à la liste puis rouvrez sa fiche.';
        detail.className = 'api-test-detail error';
        return;
      }
      testButton.disabled = true;
      testButton.innerHTML = `${icon('spark')}<span>Test en cours…</span>`;
      detail.className = 'api-test-detail loading';
      detail.textContent = 'Connexion au fournisseur et vérification du modèle…';
      try {
        const result = await adminApi(`/api/admin/companies/${encodeURIComponent(tenantId)}/document-ai/test`, {
          method: 'POST',
          body: JSON.stringify({
            provider: q('#dc-a-provider')?.value || 'openai',
            model: q('#dc-a-model')?.value || '',
            api_key: q('#dc-a-key')?.value || ''
          })
        });
        detail.innerHTML = `${icon('check')}<span><strong>Connexion opérationnelle</strong><small>${escapeHtml(result.model)} · ${result.latency_ms} ms</small></span>`;
        detail.className = 'api-test-detail success';
      } catch (error) {
        detail.innerHTML = `<span class="api-test-error">!</span><span><strong>Test refusé</strong><small>${escapeHtml(error.message || String(error))}</small></span>`;
        detail.className = 'api-test-detail error';
      } finally {
        testButton.disabled = false;
        testButton.innerHTML = `${icon('api')}<span>Tester la connexion</span>`;
      }
    });
    return true;
  }

  function bindAdminNavigationHints() {
    if (document.body.dataset.dcAdminHintsReady === '1') return;
    document.body.dataset.dcAdminHintsReady = '1';
    document.addEventListener('click', event => {
      const row = event.target.closest?.('[data-company]');
      if (row?.dataset.company) {
        window.__axioloadSelectedTenant = row.dataset.company;
        const detail = q('#admin-company-detail');
        if (detail) detail.dataset.tenantId = row.dataset.company;
        [0, 100, 350, 800].forEach(delay => window.setTimeout(enhanceApiTester, delay));
      }
      if (event.target.closest?.('[data-detail-tab], #open-admin')) {
        [0, 100, 350].forEach(delay => window.setTimeout(enhanceApiTester, delay));
      }
    }, true);
  }

  function installAll() {
    installWorkspaceSwitcher();
    polishDocumentModule();
    enhanceApiTester();
  }

  function init() {
    bindAdminNavigationHints();
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(installAll, delay));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
