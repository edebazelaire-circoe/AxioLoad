(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  const icons = {
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

  function icon(name, className = '') {
    return `<span class="ax-icon ${className}">${icons[name] || icons.spark}</span>`;
  }

  function adminHeaders() {
    const token = sessionStorage.getItem('axioload.admin.token') || '';
    return {
      'Content-Type': 'application/json',
      ...(token ? {'X-AxioLoad-Super-Admin': token} : {})
    };
  }

  async function adminApi(url, options = {}, retry = true) {
    const response = await fetch(url, {
      ...options,
      headers: {...adminHeaders(), ...(options.headers || {})}
    });
    if (response.status === 401 && retry) {
      const token = prompt('Saisissez le jeton super administrateur.');
      if (token) {
        sessionStorage.setItem('axioload.admin.token', token.trim());
        return adminApi(url, options, false);
      }
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Erreur ${response.status}`);
    }
    return response.status === 204 ? null : response.json();
  }

  function decorateOptimizationTabs() {
    const map = {vehicles: 'vehicles', data: 'data', results: 'results', history: 'history', route: 'route', total: 'total'};
    qa('nav.tabs .tab[data-tab]').forEach(button => {
      const name = map[button.dataset.tab];
      if (!name || q('.ax-tab-icon', button)) return;
      const label = button.textContent.trim();
      button.innerHTML = `${icon(name, 'ax-tab-icon')}<span>${escapeHtml(label)}</span>`;
    });
  }

  function installWorkspaceSwitcher() {
    const nav = q('nav.tabs');
    const documentTab = q('[data-tab="document-control"]');
    const documentPanel = q('#tab-document-control');
    if (!nav || !documentTab || !documentPanel || q('#workspace-switcher')) return false;

    decorateOptimizationTabs();
    documentTab.classList.add('ax-hidden-document-tab');
    documentTab.setAttribute('aria-hidden', 'true');

    const switcher = document.createElement('section');
    switcher.id = 'workspace-switcher';
    switcher.className = 'workspace-switcher';
    switcher.setAttribute('aria-label', 'Choisir un espace de travail');
    switcher.innerHTML = `
      <button type="button" class="workspace-card active" data-workspace="optimization">
        ${icon('truck')}
        <span><strong>Optimisation</strong><small>Chargement, itinéraires et flotte</small></span>
      </button>
      <button type="button" class="workspace-card" data-workspace="documents">
        ${icon('shield')}
        <span><strong>Contrôle documentaire</strong><small>Comparer, corriger et exporter</small></span>
      </button>`;
    nav.before(switcher);
    nav.classList.add('optimization-subnav');

    let lastOptimizationTab = q('nav.tabs .tab.active:not([data-tab="document-control"])')?.dataset.tab || 'vehicles';
    let workspace = 'optimization';

    const setWorkspaceVisual = name => {
      workspace = name;
      document.body.dataset.workspace = name;
      qa('[data-workspace]', switcher).forEach(button => {
        const active = button.dataset.workspace === name;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
      });
      nav.classList.toggle('workspace-nav-hidden', name === 'documents');
    };

    const openOptimization = () => {
      setWorkspaceVisual('optimization');
      const target = q(`nav.tabs .tab[data-tab="${lastOptimizationTab}"]`) || q('nav.tabs .tab[data-tab="vehicles"]');
      target?.click();
    };

    const openDocuments = () => {
      const current = q('nav.tabs .tab.active:not([data-tab="document-control"])');
      if (current?.dataset.tab) lastOptimizationTab = current.dataset.tab;
      setWorkspaceVisual('documents');
      documentTab.click();
    };

    q('[data-workspace="optimization"]', switcher).addEventListener('click', openOptimization);
    q('[data-workspace="documents"]', switcher).addEventListener('click', openDocuments);
    qa('nav.tabs .tab:not([data-tab="document-control"])').forEach(tab => {
      tab.addEventListener('click', () => {
        lastOptimizationTab = tab.dataset.tab || lastOptimizationTab;
        setWorkspaceVisual('optimization');
      });
    });
    q('#close-settings')?.addEventListener('click', () => {
      if (workspace === 'documents') setTimeout(openDocuments, 0);
    });
    return true;
  }

  function polishDocumentModule() {
    const panel = q('#tab-document-control');
    if (!panel || panel.dataset.experienceReady === '1') return false;
    panel.dataset.experienceReady = '1';

    const heading = q('.panel-heading > div:first-child', panel);
    if (heading) heading.insertAdjacentHTML('afterbegin', `<div class="dc-module-brand">${icon('shield')}<span>AxioLoad Documents</span></div>`);
    const title = q('.panel-heading h2', panel);
    const intro = q('.panel-heading .section-intro', panel);
    if (title) title.textContent = 'Comparer deux documents';
    if (intro) intro.textContent = 'Déposez les fichiers, lancez l’analyse, puis validez les écarts.';
    const security = q('.dc-security span', panel);
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
        state.textContent = input.files?.[0]?.name || 'PDF, JPG ou PNG';
        label.classList.toggle('has-file', Boolean(input.files?.length));
      });
      ['dragenter', 'dragover'].forEach(eventName => label.addEventListener(eventName, event => {
        event.preventDefault(); label.classList.add('dragging');
      }));
      ['dragleave', 'drop'].forEach(eventName => label.addEventListener(eventName, event => {
        event.preventDefault(); label.classList.remove('dragging');
      }));
    });

    const newButton = q('#dc-new-view', panel);
    const historyButton = q('#dc-history-view', panel);
    if (newButton) newButton.innerHTML = `${icon('document')}<span>Nouveau</span>`;
    if (historyButton) historyButton.innerHTML = `${icon('history')}<span>Historique</span>`;
    return true;
  }

  function promptAccordion(profile) {
    const status = profile.is_default ? 'Base fournie' : `Personnalisé · v${profile.version}`;
    return `
      <details class="system-prompt-accordion" data-profile="${escapeHtml(profile.key)}" ${profile.key === 'generic' ? 'open' : ''}>
        <summary>
          <span class="system-prompt-summary">${icon('prompt')}<span><strong>${escapeHtml(profile.title)}</strong><small>${escapeHtml(profile.description)}</small></span></span>
          <span class="system-prompt-badge">${escapeHtml(status)}</span>
        </summary>
        <div class="system-prompt-panel">
          <label>Prompt de base<textarea rows="9" maxlength="16000" data-system-prompt>${escapeHtml(profile.instructions)}</textarea></label>
          <div class="system-prompt-actions">
            <span data-system-meta>Version ${profile.version} · ${escapeHtml(profile.updated_by || 'system')}</span>
            <button type="button" class="primary" data-save-system-prompt>Enregistrer</button>
          </div>
          <div class="message hidden" data-system-message></div>
        </div>
      </details>`;
  }

  async function loadSystemPrompts(view) {
    const root = q('[data-system-prompt-list]', view);
    root.innerHTML = '<div class="admin-empty">Chargement des prompts…</div>';
    try {
      const data = await adminApi('/api/admin/document-prompts');
      q('[data-system-version]', view).textContent = data.system_prompt_version;
      q('[data-locked-core]', view).textContent = data.locked_core_prompt;
      root.innerHTML = data.profiles.map(promptAccordion).join('');
      qa('[data-save-system-prompt]', root).forEach(button => {
        button.addEventListener('click', async () => {
          const details = button.closest('[data-profile]');
          const message = q('[data-system-message]', details);
          button.disabled = true;
          button.textContent = 'Enregistrement…';
          try {
            const result = await adminApi(`/api/admin/document-prompts/${encodeURIComponent(details.dataset.profile)}`, {
              method: 'PUT', body: JSON.stringify({instructions: q('[data-system-prompt]', details).value})
            });
            q('[data-system-meta]', details).textContent = `Version ${result.version} · ${result.updated_by}`;
            q('.system-prompt-badge', details).textContent = `Personnalisé · v${result.version}`;
            message.textContent = 'Prompt de base enregistré et versionné.';
            message.className = 'message success';
          } catch (error) {
            message.textContent = error.message;
            message.className = 'message error';
          } finally {
            message.classList.remove('hidden');
            button.disabled = false;
            button.textContent = 'Enregistrer';
          }
        });
      });
    } catch (error) {
      root.innerHTML = `<div class="admin-notice warning">${escapeHtml(error.message)}</div>`;
    }
  }

  function installSuperAdminPromptView() {
    const panel = q('#tab-admin');
    const nav = q('.admin-nav', panel);
    const content = q('.admin-content', panel);
    if (!panel || !nav || !content || q('[data-admin-view="document-prompts"]', nav)) return false;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary admin-nav-rich';
    button.dataset.adminView = 'document-prompts';
    button.innerHTML = `${icon('prompt')}<span>Prompts documentaires</span>`;
    nav.append(button);

    const view = document.createElement('section');
    view.id = 'admin-view-document-prompts';
    view.className = 'admin-view';
    view.innerHTML = `
      <div class="admin-toolbar system-prompt-header">
        <div><div class="dc-module-brand">${icon('prompt')}<span>Bibliothèque système</span></div><h3>Prompts de base documentaires</h3><p>Une base par cas, complétée ensuite par l’entreprise.</p></div>
        <span class="system-version-pill">Moteur <b data-system-version>…</b></span>
      </div>
      <section class="admin-card locked-core-card">
        <details><summary>${icon('shield')}<span><strong>Socle de sécurité verrouillé</strong><small>Objectif, méthode de lecture et garde-fous communs.</small></span></summary><pre data-locked-core></pre></details>
      </section>
      <div class="system-prompt-list" data-system-prompt-list></div>`;
    content.append(view);

    button.addEventListener('click', async () => {
      qa('[data-admin-view]', nav).forEach(item => item.classList.toggle('active', item === button));
      qa('.admin-view', content).forEach(item => item.classList.toggle('active', item === view));
      await loadSystemPrompts(view);
    });
    return true;
  }

  function enhanceApiTester() {
    const card = q('#dc-admin-ai');
    if (!card || q('#dc-a-test', card)) return false;
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
      const resolvedTenant = q('#admin-company-detail')?.dataset?.tenantId || window.__axioloadSelectedTenant;
      if (!resolvedTenant) {
        detail.textContent = 'Entreprise introuvable. Revenez à la liste puis rouvrez sa fiche.';
        detail.className = 'api-test-detail error';
        return;
      }
      testButton.disabled = true;
      testButton.innerHTML = `${icon('spark')}<span>Test en cours…</span>`;
      detail.className = 'api-test-detail loading';
      detail.textContent = 'Connexion au fournisseur et vérification du modèle…';
      try {
        const result = await adminApi(`/api/admin/companies/${encodeURIComponent(resolvedTenant)}/document-ai/test`, {
          method: 'POST', body: JSON.stringify({provider: q('#dc-a-provider')?.value || 'openai', model: q('#dc-a-model')?.value || '', api_key: q('#dc-a-key')?.value || ''})
        });
        detail.innerHTML = `${icon('check')}<span><strong>Connexion opérationnelle</strong><small>${escapeHtml(result.model)} · ${result.latency_ms} ms</small></span>`;
        detail.className = 'api-test-detail success';
      } catch (error) {
        detail.innerHTML = `<span class="api-test-error">!</span><span><strong>Test refusé</strong><small>${escapeHtml(error.message)}</small></span>`;
        detail.className = 'api-test-detail error';
      } finally {
        testButton.disabled = false;
        testButton.innerHTML = `${icon('api')}<span>Tester la connexion</span>`;
      }
    });
    return true;
  }

  function rememberSelectedTenant() {
    document.addEventListener('click', event => {
      const row = event.target.closest('[data-company]');
      if (row?.dataset.company) {
        window.__axioloadSelectedTenant = row.dataset.company;
        const detail = q('#admin-company-detail');
        if (detail) detail.dataset.tenantId = row.dataset.company;
      }
    });
  }

  function init() {
    rememberSelectedTenant();
    const installAll = () => {
      installWorkspaceSwitcher();
      polishDocumentModule();
      installSuperAdminPromptView();
      enhanceApiTester();
    };
    installAll();
    new MutationObserver(installAll).observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
