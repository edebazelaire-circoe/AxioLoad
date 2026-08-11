(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const fmt = (value, digits = 1) => Number.isFinite(Number(value))
    ? Number(value).toLocaleString('fr-FR', {maximumFractionDigits: digits})
    : '—';

  let latestResult = null;
  let latestRequest = null;
  let observer = null;
  let arranging = false;

  const icon = name => {
    const paths = {
      input: '<path d="M4 4h16v16H4zM4 9h16M9 4v16"/>',
      model: '<path d="M5 19V9M12 19V5M19 19v-7"/>',
      truck: '<path d="M3 5h11v10H3zM14 9h4l3 3v3h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm11 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/>',
      route: '<path d="M6 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm12-8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM8 15c4 0 4-6 8-6"/>',
      edit: '<path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/>',
      shield: '<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5zM9 12l2 2 4-5"/>',
      chevron: '<path d="m9 6 6 6-6 6"/>',
      package: '<path d="m4 7 8-4 8 4-8 4zM4 7v10l8 4 8-4V7M12 11v10"/>',
      weight: '<path d="M7 8h10l2 12H5zM9 8a3 3 0 0 1 6 0"/>'
    };
    return `<span class="opx4-icon"><svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.model}</svg></span>`;
  };

  function resultFromPayload(payload) {
    if (Array.isArray(payload?.solutions)) return payload;
    if (Array.isArray(payload?.result?.solutions)) {
      return {...payload.result, run_id: payload.result.run_id || payload.id || payload.run_id};
    }
    return null;
  }

  function requestFromDom() {
    const vehicle = q('#vehicle-id');
    const items = qa('#cargo-table tbody tr').map(row => ({
      id: q('[data-k="id"]', row)?.value?.trim() || '',
      quantity: number(q('[data-k="quantity"]', row)?.value),
      weight: number(q('[data-k="weight"]', row)?.value),
      destination: q('[data-k="destination"]', row)?.value?.trim() || 'Sans destination',
      delivery_order: number(q('[data-k="delivery_order"]', row)?.value),
      keep_together_group: q('[data-k="keep_together_group"]', row)?.value?.trim() || '',
      separate_group: q('[data-k="separate_group"]', row)?.value?.trim() || '',
      incompatible_tags: q('[data-k="incompatible_tags"]', row)?.value?.trim() || '',
      separation: number(q('[data-k="separation"]', row)?.value)
    }));
    return {
      items,
      vehicle_policy: {
        forced_vehicle_id: vehicle?.value || '',
        max_vehicles: number(q('#max-vehicles')?.value)
      },
      budget_seconds: number(q('#budget-seconds')?.value),
      default_margins: {left: number(q('#default-margin')?.value)},
      total_optimization_enabled: Boolean(q('#total-optimization-enabled')?.checked)
    };
  }

  function requestSnapshot() {
    return latestRequest || requestFromDom();
  }

  function vehicleLabel(request) {
    const forcedId = request?.vehicle_policy?.forced_vehicle_id;
    const selected = q('#vehicle-id');
    if (selected && (!forcedId || selected.value === forcedId)) {
      return selected.selectedOptions?.[0]?.textContent?.trim() || forcedId || 'Véhicule sélectionné';
    }
    return forcedId || 'Véhicule sélectionné';
  }

  function groupedDestinations(items) {
    const groups = new Map();
    (items || []).forEach(item => {
      const destination = String(item.destination || 'Sans destination').trim() || 'Sans destination';
      const current = groups.get(destination) || {destination, quantity: 0, order: Number.MAX_SAFE_INTEGER};
      current.quantity += Math.max(1, number(item.quantity) || 1);
      const order = number(item.delivery_order);
      if (order > 0) current.order = Math.min(current.order, order);
      groups.set(destination, current);
    });
    return [...groups.values()].sort((left, right) => left.order - right.order || left.destination.localeCompare(right.destination, 'fr'));
  }

  function renderInputSummary() {
    const target = q('#opx4-input-summary');
    if (!target) return;
    const request = requestSnapshot();
    const items = Array.isArray(request?.items) ? request.items : [];
    const destinations = groupedDestinations(items);
    const totalUnits = items.reduce((sum, item) => sum + Math.max(1, number(item.quantity) || 1), 0);
    const totalWeight = items.reduce((sum, item) => sum + Math.max(1, number(item.quantity) || 1) * number(item.weight ?? item.weight_kg), 0);
    const margin = number(request?.default_margins?.left ?? q('#default-margin')?.value);
    const budget = number(request?.budget_seconds ?? q('#budget-seconds')?.value);
    const maxVehicles = number(request?.vehicle_policy?.max_vehicles ?? q('#max-vehicles')?.value);
    const totalMode = Boolean(request?.total_optimization_enabled ?? q('#total-optimization-enabled')?.checked);
    const grouped = items.some(item => String(item.keep_together_group || '').trim());
    const separated = items.some(item => String(item.separate_group || '').trim() || number(item.separation) > 0);
    const incompatible = items.some(item => String(item.incompatible_tags || '').trim());

    target.innerHTML = `
      <section class="opx4-card opx4-orders-card">
        <div class="opx4-card-heading"><span>${icon('package')}</span><div><h3>Commandes à livrer</h3><small>${destinations.length} destination(s) · ${totalUnits} unité(s)</small></div></div>
        <div class="opx4-destination-list">
          ${destinations.length ? destinations.slice(0, 7).map((entry, index) => `<div class="opx4-destination"><span class="opx4-stop">${index + 1}</span><strong>${escapeHtml(entry.destination)}</strong><small>${entry.quantity} unité(s)</small></div>`).join('') : '<div class="opx4-empty-line">Aucune marchandise saisie.</div>'}
        </div>
        ${destinations.length > 7 ? `<div class="opx4-more">+ ${destinations.length - 7} destination(s) supplémentaires</div>` : ''}
      </section>
      <section class="opx4-card">
        <div class="opx4-card-heading"><span>${icon('truck')}</span><div><h3>Flotte sélectionnée</h3><small>Paramètres réellement envoyés au moteur</small></div></div>
        <div class="opx4-vehicle-name">${escapeHtml(vehicleLabel(request))}</div>
        <div class="opx4-inline-metrics"><span><small>Poids saisi</small><strong>${fmt(totalWeight, 0)} kg</strong></span><span><small>Véhicules max.</small><strong>${maxVehicles || '—'}</strong></span></div>
      </section>
      <section class="opx4-card">
        <div class="opx4-card-heading"><span>${icon('shield')}</span><div><h3>Contraintes principales</h3><small>Aucune contrainte n’est recalculée dans l’interface</small></div></div>
        <div class="opx4-constraint-list">
          <span>Budget moteur <strong>${budget ? `${fmt(budget, 0)} s` : '—'}</strong></span>
          <span>Marge globale <strong>${fmt(margin, 0)} mm</strong></span>
          <span>Groupes à conserver <strong>${grouped ? 'Oui' : 'Non'}</strong></span>
          <span>Séparations <strong>${separated ? 'Oui' : 'Non'}</strong></span>
          <span>Incompatibilités <strong>${incompatible ? 'Oui' : 'Non'}</strong></span>
          <span>Chargement + route <strong>${totalMode ? 'Activé' : 'Non'}</strong></span>
        </div>
      </section>
      <button type="button" class="opx4-primary-action" data-opx4-open="data">${icon('edit')}<span>Modifier les données d’entrée</span></button>`;
  }

  function outcomes() {
    const solutions = Array.isArray(latestResult?.solutions) ? latestResult.solutions : [];
    const raw = Array.isArray(latestResult?.method_outcomes) && latestResult.method_outcomes.length
      ? latestResult.method_outcomes
      : solutions.map((solution, index) => ({
          index: index + 1,
          code: solution.method_code || `solution-${index + 1}`,
          name: solution.method_name || `Modèle ${index + 1}`,
          short_label: '',
          status: 'success',
          vehicle_count: solution.vehicle_count,
          occupied_length_m: solution.occupied_length_m
        }));
    return [...raw].sort((left, right) => number(left.index) - number(right.index));
  }

  function activeMethodCode() {
    const active = q('#opx-solution-row .solution-card.active, #solution-cards .solution-card.active');
    if (active?.dataset.method) return active.dataset.method;
    const first = [...(latestResult?.solutions || [])].sort((left, right) => number(left.rank) - number(right.rank))[0];
    return first?.method_code || '';
  }

  function solutionByMethod(code) {
    return (latestResult?.solutions || []).find(solution => String(solution.method_code || '') === String(code || '')) || null;
  }

  function renderScenarioRows() {
    const list = q('#opx4-scenario-list');
    const count = q('#opx4-scenario-count');
    if (!list) return;
    const ordered = outcomes();
    const activeMethod = activeMethodCode();
    if (count) count.textContent = `${ordered.length} modèle(s)`;
    list.innerHTML = ordered.map(outcome => {
      const solution = solutionByMethod(outcome.code);
      const rank = number(solution?.rank);
      const status = outcome.status || (solution ? 'success' : 'failure');
      const active = activeMethod && activeMethod === outcome.code;
      const linear = solution?.total_linear_meters;
      const occupied = solution?.occupied_length_m ?? outcome.occupied_length_m;
      return `<button type="button" class="opx4-scenario-row ${active ? 'active' : ''} status-${escapeHtml(status)}" data-method="${escapeHtml(outcome.code || '')}" ${solution ? '' : 'disabled'}>
        <span class="opx4-rank">${rank || outcome.index || '—'}</span>
        <span class="opx4-model-name"><strong>${escapeHtml(outcome.name || solution?.method_name || outcome.code || 'Modèle')}</strong><small>${escapeHtml(outcome.short_label || (status === 'success' ? 'Plan valide produit' : outcome.reason || 'Aucun plan'))}</small></span>
        <span class="opx4-score"><small>Statut</small><strong>${status === 'success' ? 'Réussi' : status === 'timeout' ? 'Temps atteint' : 'Échec'}</strong></span>
        <span class="opx4-metric"><small>Véhicules</small><strong>${solution?.vehicle_count ?? outcome.vehicle_count ?? '—'}</strong></span>
        <span class="opx4-metric"><small>m.l.</small><strong>${linear == null ? '—' : fmt(linear, 2)}</strong></span>
        <span class="opx4-metric"><small>Longueur</small><strong>${occupied == null ? '—' : `${fmt(occupied, 2)} m`}</strong></span>
        <span class="opx4-inspect">${solution ? `Inspecter ${icon('chevron')}` : 'Indisponible'}</span>
      </button>`;
    }).join('');
  }

  function selectedSolution() {
    const method = activeMethodCode();
    return solutionByMethod(method) || [...(latestResult?.solutions || [])].sort((left, right) => number(left.rank) - number(right.rank))[0] || null;
  }

  function renderKpis() {
    const target = q('#opx4-kpis');
    const badge = q('#opx4-selected-model');
    if (!target) return;
    const solution = selectedSolution();
    if (!solution) {
      target.innerHTML = '<div class="opx4-empty-line">Lancez un calcul pour afficher les indicateurs du scénario sélectionné.</div>';
      if (badge) badge.textContent = 'Aucun scénario';
      return;
    }
    const vehicleIndex = number(q('#viewer-vehicle')?.value);
    const plan = solution.vehicle_plans?.[vehicleIndex] || solution.vehicle_plans?.[0] || null;
    const placements = Array.isArray(plan?.placements) ? plan.placements : [];
    const loadedWeight = placements.reduce((sum, placement) => sum + number(placement.weight_kg), 0);
    if (badge) badge.textContent = `Modèle ${solution.rank || '—'} · ${solution.method_name || solution.method_code || 'Sélection'}`;
    target.innerHTML = `
      <article><small>Mètres linéaires</small><strong>${fmt(solution.total_linear_meters, 2)} m.l.</strong><span>Valeur renvoyée par le moteur</span></article>
      <article><small>Longueur occupée</small><strong>${fmt(solution.occupied_length_m, 2)} m</strong><span>Pour la solution sélectionnée</span></article>
      <article><small>Véhicules</small><strong>${solution.vehicle_count ?? '—'}</strong><span>Plan(s) réellement généré(s)</span></article>
      <article><small>Chargement affiché</small><strong>${placements.length || '—'}</strong><span>${placements.length ? `${fmt(loadedWeight, 0)} kg dans le véhicule affiché` : 'Sélectionnez un véhicule'}</span></article>`;
  }

  function ensureCockpit() {
    const content = q('#results-content');
    if (!content) return null;
    let cockpit = q('#opx4-cockpit', content);
    if (!cockpit) {
      cockpit = document.createElement('section');
      cockpit.id = 'opx4-cockpit';
      cockpit.className = 'opx4-cockpit';
      cockpit.innerHTML = `
        <header class="opx4-hero">
          <div><span class="opx4-eyebrow">Cockpit opérationnel</span><h2>Optimisation</h2><p>Préparez vos chargements, comparez les modèles calculés et inspectez le plan retenu sans modifier la logique des moteurs.</p></div>
          <div class="opx4-engine-badge">${icon('shield')}<span><strong>Source de vérité : moteurs AxioLoad</strong><small>method_code → solution → plan</small></span></div>
        </header>
        <div class="opx4-grid">
          <aside class="opx4-input-lane"><div class="opx4-lane-title">${icon('input')}<span><strong>Données d’entrée</strong><small>Contexte exact du calcul</small></span></div><div id="opx4-input-summary"></div></aside>
          <section class="opx4-scenario-lane"><div class="opx4-lane-title">${icon('model')}<span><strong>Scénarios calculés</strong><small>Les cinq modèles restent indépendants</small></span><b id="opx4-scenario-count"></b></div><div id="opx4-scenario-list" class="opx4-scenario-list"></div><div class="opx4-detail-heading"><strong>Détail technique des modèles et plans</strong><small>Comparaison historique conservée à l’identique</small></div><div id="opx4-model-detail-slot"></div></section>
          <section class="opx4-plan-lane"><div class="opx4-lane-title">${icon('truck')}<span><strong>Plan de chargement</strong><small id="opx4-selected-model">Scénario sélectionné</small></span></div><div id="opx4-viewer-slot"></div><div class="opx4-route-card"><div>${icon('route')}<span><strong>Optimisation transport</strong><small>Le routage et l’optimisation complète utilisent toujours leurs moteurs existants.</small></span></div><div><button type="button" class="secondary" data-opx4-open="route">Ouvrir l’itinéraire</button><button type="button" class="secondary" data-opx4-open="total">Optimisation complète</button></div></div><div class="opx4-kpi-heading"><strong>Indicateurs du scénario sélectionné</strong></div><div id="opx4-kpis" class="opx4-kpis"></div></section>
        </div>
        <footer id="opx4-decision-slot" class="opx4-decision-slot"></footer>`;
      content.prepend(cockpit);
    }

    const detailSlot = q('#opx4-model-detail-slot', cockpit);
    const portfolio = q('#opx-method-portfolio', content);
    const source = q('#solution-cards', content);
    if (portfolio && portfolio.parentElement !== detailSlot) detailSlot.append(portfolio);
    if (source && source.parentElement !== detailSlot) detailSlot.append(source);

    const viewerSlot = q('#opx4-viewer-slot', cockpit);
    const viewer = q('.viewer-grid', content);
    if (viewer && viewer.parentElement !== viewerSlot) viewerSlot.append(viewer);

    const decisionSlot = q('#opx4-decision-slot', cockpit);
    const decision = q('.decision-panel', content);
    if (decision && decision.parentElement !== decisionSlot) decisionSlot.append(decision);

    return cockpit;
  }

  function openExistingTab(name) {
    const tab = q(`nav.tabs [data-tab="${name}"]`);
    if (tab && !tab.hidden && !tab.disabled) tab.click();
  }

  function bindActions(cockpit) {
    if (!cockpit || cockpit.dataset.actionsReady === '1') return;
    cockpit.dataset.actionsReady = '1';
    cockpit.addEventListener('click', event => {
      const open = event.target.closest('[data-opx4-open]');
      if (open) {
        openExistingTab(open.dataset.opx4Open);
        return;
      }
      const scenario = event.target.closest('.opx4-scenario-row[data-method]');
      if (!scenario || scenario.disabled) return;
      const method = scenario.dataset.method;
      const card = q(`#opx-solution-row .solution-card[data-method="${CSS.escape(method)}"], #solution-cards .solution-card[data-method="${CSS.escape(method)}"]`);
      if (card) {
        card.click();
        [0, 30, 120].forEach(delay => window.setTimeout(renderAll, delay));
      }
    });
  }

  function renderAll() {
    if (arranging) return;
    arranging = true;
    try {
      const cockpit = ensureCockpit();
      if (!cockpit) return;
      bindActions(cockpit);
      renderInputSummary();
      renderScenarioRows();
      renderKpis();
    } finally {
      arranging = false;
    }
  }

  function remember(payload, request = null) {
    const result = resultFromPayload(payload);
    if (!result) return;
    latestResult = result;
    if (request) latestRequest = request;
    else if (payload?.request) latestRequest = payload.request;
    [0, 40, 120, 320].forEach(delay => window.setTimeout(renderAll, delay));
  }

  function installFetchCapture() {
    if (window.__axioloadOptimizationCockpitV4Fetch) return;
    window.__axioloadOptimizationCockpitV4Fetch = true;
    const previous = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const url = typeof input === 'string' ? input : input?.url || '';
      let request = null;
      if (url.includes('/local/optimize') && typeof init.body === 'string') {
        try { request = JSON.parse(init.body); } catch (_) {}
      }
      const response = await previous(input, init);
      if (response.ok && (url.includes('/local/optimize') || /\/api\/history\/[^/?]+(?:\?.*)?$/.test(url))) {
        response.clone().json().then(payload => remember(payload, request || payload?.request || null)).catch(() => {});
      }
      return response;
    };
  }

  function observeResults() {
    const content = q('#results-content');
    if (!content || observer) return Boolean(content);
    observer = new MutationObserver(() => window.setTimeout(renderAll, 0));
    observer.observe(content, {childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'aria-pressed']});
    return true;
  }

  function init() {
    installFetchCapture();
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(() => {
      observeResults();
      if (!q('#results-content')?.classList.contains('hidden')) renderAll();
    }, delay));
  }

  window.AxioOptimizationCockpit = {
    render(payload, request = null) { remember(payload, request); },
    refresh() { renderAll(); },
    getLatest() { return latestResult; }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
