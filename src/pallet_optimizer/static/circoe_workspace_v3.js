(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const STORAGE_KEY = 'axioload.circoe.workspace.v3';
  const CORE_WORKSPACES = new Set(['database', 'optimization', 'documents', 'facturx']);

  const icons = {
    database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    optimization: '<path d="M4 19V9M10 19V5M16 19v-7M3 19h18"/><path d="m17 6 2-2 2 2"/>',
    documents: '<path d="M6 2h8l4 4v16H6zM14 2v5h5M9 11h6M9 15h6M9 19h4"/>',
    regulatory: '<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5zM9 12l2 2 4-5"/>',
    facturx: '<path d="M6 2h8l4 4v16H6zM14 2v5h5M9 11h6M9 15h6"/><path d="M9 19h6"/>',
    history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"/>',
    settings: '<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/><path d="m4.9 4.9 2 2M17.1 17.1l2 2M19.1 4.9l-2 2M6.9 17.1l-2 2M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    admin: '<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z"/><path d="M9 16v-1a3 3 0 0 1 6 0v1M12 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z"/>'
  };

  const entries = [
    ['database', 'Base de données', 'Flotte, référentiels et prompts', 'Flotte'],
    ['optimization', 'Optimisation de chargement', 'Palettes, conteneurs, itinéraires et résultats', 'Chargement'],
    ['documents', 'Contrôle documentaire', 'Comparer, contrôler, corriger et exporter', 'Documents'],
    ['regulatory', 'Contrôle réglementaire', 'Espace préparé pour les futures règles validées', 'Préparé'],
    ['facturx', 'Facturation électronique / Factur-X', 'Créer, contrôler et exporter les flux Factur-X', 'Factur-X'],
    ['history', 'Historique & traçabilité', 'Retrouver les calculs, décisions et opérations', 'Historique'],
    ['settings', 'Paramètres & IA', 'Préférences, configuration et services IA', 'Réglages'],
    ['admin', 'Super Admin', 'Administration sécurisée des utilisateurs et services', 'Super User']
  ];

  const icon = name => `<span class="circoe-v3-icon"><svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]}</svg></span>`;
  const navSelector = '#workspace-switcher .circoe-v3-nav-item';

  function activePanelOnly(panel) {
    qa('main > .tab-panel').forEach(item => {
      const active = item === panel;
      item.classList.toggle('active', active);
      item.setAttribute('aria-hidden', String(!active));
      if ('inert' in item) item.inert = !active;
    });
  }

  function save(name) {
    try { sessionStorage.setItem(STORAGE_KEY, name); } catch (_) {}
  }

  function buttonWorkspace(button) {
    return button?.dataset.workspace || button?.dataset.circoeWorkspace || '';
  }

  function showModule(name) {
    document.body.classList.add('circoe-v3-module-open');
    document.body.dataset.circoeOpenModule = name;
    q('main')?.scrollIntoView({block: 'start'});
  }

  function showPortal() {
    document.body.classList.remove('circoe-v3-module-open');
    delete document.body.dataset.circoeOpenModule;
    q('#workspace-switcher')?.scrollIntoView({block: 'start'});
  }

  function selectNav(name) {
    qa(navSelector).forEach(button => {
      const active = buttonWorkspace(button) === name;
      button.classList.toggle('active', active);
      button.setAttribute('aria-current', active ? 'page' : 'false');
    });
    document.body.dataset.circoeWorkspace = name;
    save(name);
  }

  function clickVisible(selector) {
    const element = q(selector);
    if (!element || element.hidden || element.disabled || element.getAttribute('aria-disabled') === 'true') return false;
    element.click();
    return true;
  }

  function openCoreWorkspace(name) {
    const legacy = q(`#workspace-switcher [data-legacy-workspace="${name}"]`);
    if (legacy) {
      legacy.click();
      selectNav(name);
      return true;
    }
    return false;
  }

  function openDatabase() {
    if (openCoreWorkspace('database')) return;
    if (clickVisible('nav.tabs [data-tab="vehicles"]')) selectNav('database');
  }

  function openOptimization(target = 'data') {
    const openedCore = openCoreWorkspace('optimization');
    const selectTarget = () => {
      const selected = clickVisible(`nav.tabs [data-tab="${target}"]`);
      const panel = q(`#tab-${target}`);
      if (!selected && panel) activePanelOnly(panel);
      if (selected || panel) selectNav(target === 'history' ? 'history' : 'optimization');
      return selected || Boolean(panel);
    };

    if (!openedCore) {
      selectTarget();
      return;
    }
    if (target === 'data') {
      selectNav('optimization');
      return;
    }

    // The legacy workspace handler can rebuild tab visibility asynchronously.
    // Retry after it settles, then use the existing panel only as a final UI fallback.
    window.setTimeout(selectTarget, 80);
    window.setTimeout(() => {
      const panel = q(`#tab-${target}`);
      if (panel && !panel.classList.contains('active')) selectTarget();
    }, 260);
  }

  function openDocuments() {
    if (openCoreWorkspace('documents')) selectNav('documents');
  }

  function openFacturx() {
    if (openCoreWorkspace('facturx')) selectNav('facturx');
  }

  function ensureRegulatoryPanel() {
    let panel = q('#tab-regulatory');
    if (panel) return panel;
    panel = document.createElement('section');
    panel.id = 'tab-regulatory';
    panel.className = 'panel tab-panel circoe-regulatory-panel';
    panel.setAttribute('aria-hidden', 'true');
    panel.innerHTML = `
      <div class="panel-heading circoe-v3-heading">
        <div><div class="eyebrow">Module préparé</div><h2>Contrôle réglementaire</h2><p class="section-intro">Socle d’interface prévu pour centraliser les obligations, échéances et preuves de conformité sans inventer de données réglementaires tant que les règles métier ne sont pas développées.</p></div>
        <span class="circoe-v3-status planned">Préparé · non actif</span>
      </div>
      <div class="circoe-regulatory-grid">
        <section class="circoe-v3-card"><h3>Registres & obligations</h3><p>Future vue des obligations applicables par périmètre, responsable, source réglementaire et prochaine échéance.</p><div class="circoe-v3-empty">Aucune règle réglementaire n’est activée dans cette version.</div></section>
        <section class="circoe-v3-card"><h3>Calendrier des échéances</h3><p>Emplacement réservé aux échéances calculées depuis les futures règles validées.</p><div class="circoe-v3-calendar" aria-label="Calendrier préparé"><span>Lun</span><span>Mar</span><span>Mer</span><span>Jeu</span><span>Ven</span><span>Sam</span><span>Dim</span></div></section>
        <section class="circoe-v3-card"><h3>Flux de contrôle prévu</h3><ol class="circoe-v3-flow"><li>Collecte</li><li>Vérification</li><li>Validation</li><li>Archivage</li></ol><p>Les connecteurs avec Contrôle documentaire, Factur-X et Historique seront branchés sur les règles métier lorsqu’elles seront disponibles.</p></section>
        <section class="circoe-v3-card"><h3>Garde-fous de conception</h3><ul><li>Aucune conformité supposée sans règle versionnée.</li><li>Validation humaine pour les décisions sensibles.</li><li>Traçabilité de la règle, de la preuve et de la décision.</li><li>Pas d’impact sur les modules actuels tant que le module reste inactif.</li></ul></section>
      </div>`;
    q('main')?.append(panel);
    return panel;
  }

  function openRegulatory() {
    const panel = ensureRegulatoryPanel();
    activePanelOnly(panel);
    selectNav('regulatory');
    showModule('regulatory');
  }

  function openSettings() {
    if (clickVisible('#open-settings')) {
      selectNav('settings');
      showModule('settings');
    }
  }

  function openAdmin() {
    if (clickVisible('#open-admin')) {
      selectNav('admin');
      showModule('admin');
    }
  }

  async function route(name) {
    if (name === 'regulatory') { openRegulatory(); return; }
    if (name === 'settings') { openSettings(); return; }
    if (name === 'admin') { openAdmin(); return; }

    const target = name === 'history' ? 'history' : (name === 'optimization' ? 'data' : null);
    if (typeof window.axioloadOpenWorkspace === 'function') {
      await window.axioloadOpenWorkspace(name === 'history' ? 'optimization' : name, target);
      return;
    }

    if (name === 'database') openDatabase();
    else if (name === 'optimization') openOptimization('data');
    else if (name === 'documents') openDocuments();
    else if (name === 'facturx') openFacturx();
    else if (name === 'history') openOptimization('history');
  }

  function captureLegacyButtons(switcher) {
    qa(':scope > [data-workspace]', switcher).forEach(button => {
      button.dataset.legacyWorkspace = button.dataset.workspace;
      button.classList.add('circoe-v3-legacy-workspace');
      button.removeAttribute('data-workspace');
      button.hidden = true;
    });
  }

  function buildPortal() {
    const switcher = q('#workspace-switcher');
    if (!switcher || switcher.dataset.circoeV3 === '1') return false;
    switcher.dataset.circoeV3 = '1';
    captureLegacyButtons(switcher);
    switcher.classList.add('circoe-v3-portal');
    switcher.setAttribute('aria-label', 'Portail des modules AxioLoad');

    const hero = document.createElement('section');
    hero.className = 'circoe-v3-hero';
    hero.innerHTML = '<div><div class="eyebrow">Portail AxioLoad</div><h1>Bonjour,</h1><p>Accédez à vos modules AxioLoad pour optimiser et contrôler vos opérations de transport.</p></div><div class="circoe-v3-hero-art" aria-hidden="true"><span>AXIOLOAD</span></div>';
    switcher.append(hero);

    const nav = document.createElement('nav');
    nav.className = 'circoe-v3-grid';
    nav.innerHTML = entries.map(([name, label, description, kicker]) => {
      const attribute = CORE_WORKSPACES.has(name) ? `data-workspace="${name}"` : `data-circoe-workspace="${name}"`;
      const badge = name === 'regulatory' ? '<span class="circoe-card-badge">À venir</span>' : (name === 'admin' ? '<span class="circoe-card-badge">Réservé Super User</span>' : '');
      return `<button type="button" ${attribute} class="circoe-v3-nav-item circoe-card-${name}">${icon(name)}<span class="circoe-card-copy"><small>${kicker}</small><strong>${label}</strong><em>${description}</em></span><span class="circoe-card-arrow" aria-hidden="true">→</span>${badge}</button>`;
    }).join('');
    switcher.append(nav);

    const homeButton = document.createElement('button');
    homeButton.type = 'button';
    homeButton.className = 'circoe-v3-home';
    homeButton.textContent = '← Retour au portail';
    homeButton.addEventListener('click', showPortal);
    q('main')?.before(homeButton);

    qa('.circoe-v3-nav-item', nav).forEach(button => button.addEventListener('click', async () => {
      const name = buttonWorkspace(button);
      await route(name);
      showModule(name);
    }));
    const adminButton = q('[data-circoe-workspace="admin"]', nav);
    if (adminButton && !q('#open-admin')) {
      adminButton.disabled = true;
      adminButton.title = 'Disponible uniquement pour le Super Admin';
    }
    ensureRegulatoryPanel();
    return true;
  }

  function synchronizeExistingNavigation() {
    window.addEventListener('axioload:navigation:changed', event => {
      const detail = event.detail || {};
      if (detail.workspace === 'database') selectNav('database');
      else if (detail.workspace === 'documents') selectNav('documents');
      else if (detail.workspace === 'facturx') selectNav('facturx');
      else if (detail.workspace === 'optimization') selectNav(detail.tab === 'history' ? 'history' : 'optimization');
    });
    q('#open-settings')?.addEventListener('click', () => selectNav('settings'));
    q('#open-admin')?.addEventListener('click', () => selectNav('admin'));
  }

  function markOptimizationIntegrity() {
    const results = q('#tab-results');
    if (results) {
      results.dataset.preserveOptimizationModels = 'true';
      const content = q('#results-content', results);
      if (content && !q('.circoe-model-integrity-note', content)) {
        const note = document.createElement('div');
        note.className = 'circoe-model-integrity-note';
        note.innerHTML = '<strong>Portefeuille de modèles conservé</strong><span>Chaque plan reste lié à son modèle via son <code>method_code</code>. Le classement du moteur reste la source de vérité.</span>';
        content.prepend(note);
      }
    }
  }

  function restoreSelection() {
    let saved = null;
    try { saved = sessionStorage.getItem(STORAGE_KEY); } catch (_) {}
    const current = document.body.dataset.workspace;
    if (current === 'facturx') selectNav('facturx');
    else if (current === 'documents') selectNav('documents');
    else if (current === 'optimization') selectNav(q('#tab-history.active') ? 'history' : 'optimization');
    else if (saved === 'regulatory') openRegulatory();
    else selectNav('database');
  }

  function init() {
    const attempts = [0, 50, 200, 700, 1600];
    attempts.forEach(delay => window.setTimeout(() => {
      if (buildPortal()) {
        synchronizeExistingNavigation();
        restoreSelection();
      }
      markOptimizationIntegrity();
    }, delay));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
