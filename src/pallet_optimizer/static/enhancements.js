(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const nativeFetch = window.fetch.bind(window);
  const runtime = {
    loading: {request: null, result: null},
    route: {request: null, result: null},
    total: {request: null, result: null},
    history: new Map(),
    historyRequest: null,
    historyLoadedAt: 0,
    focusedRoute: null,
  };

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
  const numberValue = input => Number(input?.value || 0);

  function currentUser() {
    try {
      return JSON.parse(localStorage.getItem('axioload.settings.v1') || '{}')?.account?.username || 'Utilisateur local';
    } catch (_) {
      return 'Utilisateur local';
    }
  }

  function loadingSnapshot() {
    return {
      dimension_unit: 'mm',
      weight_unit: 'kg',
      seed: numberValue($('#seed')) || 1,
      budget_seconds: numberValue($('#budget-seconds')) || 30,
      default_margins: {
        left: numberValue($('#default-margin')),
        right: numberValue($('#default-margin')),
        front: numberValue($('#default-margin')),
        rear: numberValue($('#default-margin')),
        top: 0,
      },
      vehicle_policy: {
        mode: 'forced',
        forced_vehicle_id: $('#vehicle-id')?.value,
        max_vehicles: numberValue($('#max-vehicles')) || 1,
      },
      items: $$('#cargo-table tbody tr').map(row => {
        const item = {};
        row.querySelectorAll('[data-k]').forEach(input => {
          item[input.dataset.k] = input.type === 'checkbox'
            ? input.checked
            : input.type === 'number'
              ? Number(input.value)
              : input.value.trim();
        });
        return item;
      }),
    };
  }

  function augmentRoute(payload) {
    const loading = loadingSnapshot();
    const knownItems = new Set(loading.items.map(item => item.id));
    return {
      ...payload,
      vehicle_id: $('#vehicle-id')?.value,
      loading,
      jobs: (payload.jobs || []).map(job => ({
        ...job,
        item_ids: String(job.reference || '')
          .split(',')
          .map(value => value.trim())
          .filter(value => knownItems.has(value)),
      })),
    };
  }

  function publishHistory(rows, source = 'application') {
    if (!Array.isArray(rows)) return;
    runtime.history = new Map(rows.map(row => [String(row.id).slice(0, 8), row]));
    runtime.historyLoadedAt = Date.now();
    decorateHistory();
    document.dispatchEvent(new CustomEvent('axioload:history-loaded', {
      detail: {rows, source},
    }));
  }

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase();
    let options = init;
    let body = null;

    if (typeof init.body === 'string') {
      try { body = JSON.parse(init.body); } catch (_) { body = null; }
    }

    if ((url.includes('/api/route/optimize') || url.includes('/api/route/compare')) && body) {
      body = augmentRoute(body);
      options = {...init, body: JSON.stringify(body)};
      runtime.route.request = body;
    } else if (url.includes('/api/total/optimize') && body) {
      runtime.total.request = body;
    } else if (url.includes('/local/optimize') && body) {
      runtime.loading.request = body;
    }

    const response = await nativeFetch(input, options);

    if (response.ok && method === 'GET' && /\/api\/history(?:\?|$)/.test(url)) {
      response.clone().json().then(rows => publishHistory(rows, 'application')).catch(() => {});
    }

    if (response.ok && (
      url.includes('/local/optimize') ||
      url.includes('/api/route/optimize') ||
      url.includes('/api/route/compare') ||
      url.includes('/api/total/optimize')
    )) {
      response.clone().json().then(data => {
        if (url.includes('/local/optimize')) runtime.loading.result = data;
        else if (url.includes('/api/total/optimize')) runtime.total.result = data;
        else runtime.route.result = data;
        requestAnimationFrame(hydrateDynamicContent);
      }).catch(() => {});
    }

    return response;
  };

  async function refreshHistory(force = false, source = 'explicit') {
    if (runtime.historyRequest) return runtime.historyRequest;
    if (!force && runtime.history.size) {
      decorateHistory();
      return runtime.history;
    }
    if (!force && Date.now() - runtime.historyLoadedAt < 750) return runtime.history;

    runtime.historyRequest = nativeFetch('/api/history?limit=200', {credentials: 'same-origin'})
      .then(async response => {
        if (!response.ok) return runtime.history;
        const rows = await response.json();
        publishHistory(rows, source);
        return runtime.history;
      })
      .catch(() => runtime.history)
      .finally(() => { runtime.historyRequest = null; });
    return runtime.historyRequest;
  }

  function addHeaderAfter(reference, html, key) {
    if (!reference || reference.parentElement?.querySelector(`[data-enhanced-header="${key}"]`)) return;
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    reference.after(template.content.firstElementChild);
  }

  function exteriorDefaults(original) {
    return ({
      container_20ft: [6058, 2438, 2591],
      container_40ft: [12192, 2438, 2591],
      semi_trailer: [13800, 2550, 4000],
      rigid_20m3: [6500, 2200, 3200],
    })[original.model_id] || [
      Number(original.interior_length_mm || 6000) + 300,
      Number(original.interior_width_mm || 2400) + 100,
      Number(original.interior_height_mm || 2500) + 300,
    ];
  }

  function enhanceVehicles() {
    const heightHeader = $$('#vehicle-table thead th').find(header => header.textContent.includes('Hauteur int.'));
    addHeaderAfter(heightHeader, '<th data-enhanced-header="vehicle-exterior-length" class="col-num">Longueur ext. (mm)</th>', 'vehicle-exterior-length');
    addHeaderAfter($('[data-enhanced-header="vehicle-exterior-length"]'), '<th data-enhanced-header="vehicle-exterior-width" class="col-num">Largeur ext. (mm)</th>', 'vehicle-exterior-width');
    addHeaderAfter($('[data-enhanced-header="vehicle-exterior-width"]'), '<th data-enhanced-header="vehicle-exterior-height" class="col-num">Hauteur ext. (mm)</th>', 'vehicle-exterior-height');

    $$('#vehicle-table tbody tr').forEach(row => {
      if (row.dataset.exteriorEnhanced === '1') return;
      const anchor = row.querySelector('[data-v="interior_height_mm"]')?.closest('td');
      if (!anchor) return;
      let original = {};
      try { original = JSON.parse(row.dataset.original || '{}'); } catch (_) {}
      const defaults = exteriorDefaults(original);
      [
        ['exterior_height_mm', original.exterior_height_mm || defaults[2]],
        ['exterior_width_mm', original.exterior_width_mm || defaults[1]],
        ['exterior_length_mm', original.exterior_length_mm || defaults[0]],
      ].forEach(([key, value]) => {
        if (row.querySelector(`[data-v="${key}"]`)) return;
        const cell = document.createElement('td');
        cell.innerHTML = `<input data-v="${key}" type="number" min="1" value="${Number(value)}">`;
        anchor.after(cell);
      });
      row.dataset.exteriorEnhanced = '1';
    });
  }

  function syncStack(row) {
    const shape = row.querySelector('[data-k="shape"]');
    const stackable = row.querySelector('[data-k="stackable"]');
    if (!shape || !stackable) return;
    stackable.disabled = shape.value !== 'pallet';
    if (stackable.disabled) stackable.checked = false;
  }

  function enhanceCargo() {
    const rotationHeader = $$('#cargo-table thead th').find(header => header.textContent.includes('Rotation'));
    addHeaderAfter(rotationHeader, '<th data-enhanced-header="stackable" class="col-stackable">Gerbable</th>', 'stackable');
    $$('#cargo-table tbody tr').forEach(row => {
      if (row.dataset.stackEnhanced === '1') return;
      const anchor = row.querySelector('[data-k="rotation_allowed"]')?.closest('td');
      if (!anchor) return;
      let original = {};
      try { original = JSON.parse(row.dataset.original || '{}'); } catch (_) {}
      if (!row.querySelector('[data-k="stackable"]')) {
        const cell = document.createElement('td');
        cell.className = 'col-stackable';
        cell.innerHTML = `<input data-k="stackable" type="checkbox" ${original.stackable ? 'checked' : ''} aria-label="Palette gerbable">`;
        anchor.after(cell);
      }
      const shape = row.querySelector('[data-k="shape"]');
      if (shape && !shape.dataset.stackBound) {
        shape.dataset.stackBound = '1';
        shape.addEventListener('change', () => syncStack(row));
      }
      syncStack(row);
      row.dataset.stackEnhanced = '1';
    });
  }

  function addTemplate() {
    const box = $('#tab-data .import-box');
    if (!box || $('#download-excel-template')) return;
    const link = document.createElement('a');
    link.id = 'download-excel-template';
    link.href = '/api/import/template.xlsx';
    link.download = 'axioload-modele-import.xlsx';
    link.textContent = 'Modèle Excel identique au tableau';
    box.append(link);
  }

  function activeIndex(selector) {
    return Math.max(0, $$(selector).findIndex(element => element.classList.contains('active')));
  }

  function routeResult() {
    const result = runtime.route.result;
    return result?.results ? result.results[activeIndex('#route-result-cards .route-result-card')] || result.results[0] : result;
  }

  function ensureValidationBar(type, container, defaultTitle) {
    if (!container || $(`#validation-${type}`)) return;
    const element = document.createElement('section');
    element.id = `validation-${type}`;
    element.className = 'workflow-validation';
    element.innerHTML = `<label><span>Titre de l’optimisation</span><input class="workflow-title" value="${esc(defaultTitle)}" maxlength="180"></label><button type="button" class="primary workflow-validate">Valider et enregistrer</button><span class="workflow-validation-message"></span>`;
    container.prepend(element);
    $('button', element).addEventListener('click', () => validateOptimization(type, element));
  }

  function ensureValidationBars() {
    ensureValidationBar('loading', $('#tab-results .decision-panel') || $('#tab-results #results-content'), 'Optimisation de chargement');
    ensureValidationBar('route', $('#route-results'), 'Optimisation d’itinéraire');
    ensureValidationBar('total', $('#total-results'), 'Optimisation totale');
    $('#validate-optimization')?.classList.add('legacy-validation-button');
  }

  async function validateOptimization(type, bar) {
    const title = $('.workflow-title', bar)?.value.trim();
    const message = $('.workflow-validation-message', bar);
    if (!title) {
      message.textContent = 'Le titre est obligatoire.';
      message.className = 'workflow-validation-message error';
      return;
    }

    let request;
    let result;
    let runId = '';
    let selectedSolution = 0;
    if (type === 'loading') {
      request = runtime.loading.request;
      result = runtime.loading.result;
      runId = result?.run_id || '';
      selectedSolution = activeIndex('#solution-cards .solution-card');
    } else if (type === 'route') {
      request = runtime.route.request;
      result = routeResult();
      selectedSolution = activeIndex('#route-result-cards .route-result-card');
    } else {
      request = runtime.total.request;
      result = window.AxioTotalOptimization?.state?.result || runtime.total.result;
      selectedSolution = activeIndex('#total-method-cards .total-method-card');
    }

    if (!request || !result) {
      message.textContent = 'Lancez d’abord une optimisation.';
      message.className = 'workflow-validation-message error';
      return;
    }

    message.textContent = 'Enregistrement…';
    const response = await nativeFetch('/api/history/validate', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        run_id: runId,
        optimization_type: type,
        title,
        user: currentUser(),
        selected_solution: selectedSolution,
        request,
        result,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      message.textContent = data.detail || 'Validation impossible.';
      message.className = 'workflow-validation-message error';
      return;
    }

    message.textContent = `Validé sous le titre « ${title} ».`;
    message.className = 'workflow-validation-message success';
    await refreshHistory(true, 'validation');
  }

  function decorateHistory() {
    const labels = {loading: 'Chargement', route: 'Itinéraire', total: 'Optimisation totale'};
    $$('#history-list .history-item').forEach(item => {
      const text = item.textContent || '';
      const key = [...runtime.history.keys()].find(prefix => text.includes(prefix));
      if (!key) return;
      const metadata = runtime.history.get(key);
      const title = $('.history-top-row strong', item);
      if (title && metadata.title && title.textContent !== metadata.title) title.textContent = metadata.title;
      const badge = $('.status-badge', item);
      if (badge && metadata.validation_status === 'validated' && badge.textContent !== 'Validé') {
        badge.textContent = 'Validé';
        badge.className = 'status-badge status-validated';
      }
      const meta = $('.history-meta', item);
      const label = labels[metadata.optimization_type] || metadata.optimization_type;
      if (meta && label && !meta.dataset.optimizationTypeAdded) {
        meta.append(document.createTextNode(` · ${label}`));
        meta.dataset.optimizationTypeAdded = '1';
      }
    });
  }

  function formatNumber(value, digits = 1) {
    return Number(value || 0).toLocaleString('fr-FR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function addEmptyMetrics() {
    const routeResults = runtime.route.result?.results || (runtime.route.result ? [runtime.route.result] : []);
    $$('#route-result-cards .route-result-card').forEach((card, index) => {
      if (card.querySelector('.empty-distance-metric') || !routeResults[index]) return;
      const metric = document.createElement('span');
      metric.className = 'route-result-metric empty-distance-metric';
      metric.innerHTML = `<span>Trajet à vide</span><strong>${formatNumber(routeResults[index].empty_distance_percent)} %</strong>`;
      $('.route-result-metrics', card)?.append(metric);
    });
  }

  function drawFocusedRoute() {
    // Le dessin détaillé reste géré par le module d’optimisation totale.
    // Cette fonction est conservée comme point d’extension sans observer global.
  }

  function hydrateDynamicContent() {
    enhanceVehicles();
    enhanceCargo();
    addTemplate();
    ensureValidationBars();
    addEmptyMetrics();
    decorateHistory();
  }

  function observeContainer(selector, callback) {
    const root = $(selector);
    if (!root || root.dataset.axioloadObserved === '1') return;
    root.dataset.axioloadObserved = '1';
    let scheduled = false;
    const observer = new MutationObserver(records => {
      if (!records.some(record => record.addedNodes.length || record.removedNodes.length)) return;
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        callback();
      });
    });
    observer.observe(root, {childList: true, subtree: true});
  }

  function installTargetedObservers() {
    observeContainer('#vehicle-table tbody', enhanceVehicles);
    observeContainer('#cargo-table tbody', enhanceCargo);
    observeContainer('#tab-results', ensureValidationBars);
    observeContainer('#route-results', () => { ensureValidationBars(); addEmptyMetrics(); });
    observeContainer('#total-results', ensureValidationBars);
    observeContainer('#history-list', decorateHistory);
  }

  document.addEventListener('click', event => {
    const fillButton = event.target.closest('#total-fill-pickups');
    if (fillButton) {
      const depot = window.AxioTotalOptimization?.state?.depot;
      if (!depot) return;
      event.preventDefault();
      let count = 0;
      $$('#cargo-table tbody tr').forEach(row => {
        const input = row.querySelector('[data-total="pickup_address"]');
        if (!input || input.value.trim()) return;
        input.value = depot.label;
        row.dataset.totalPickupLat = depot.lat;
        row.dataset.totalPickupLon = depot.lon;
        row.dataset.totalPickupLabel = depot.label;
        count += 1;
      });
      const box = $('#data-errors');
      if (box) {
        box.textContent = `${count} point(s) d’enlèvement vide(s) ont été alignés sur le lieu de départ.`;
        box.classList.remove('hidden', 'error');
        box.classList.add('success');
      }
      return;
    }

    if (event.target.closest('.tab[data-tab="history"], #refresh-history, [data-history-refresh]')) {
      setTimeout(() => refreshHistory(false, 'user-action'), 50);
    }

    if (event.target.closest('.tab, button, [role="button"]')) {
      requestAnimationFrame(() => {
        installTargetedObservers();
        hydrateDynamicContent();
      });
    }
  }, true);

  window.addEventListener('axioload:history-refresh-request', () => refreshHistory(true, 'explicit-event'));

  function init() {
    installTargetedObservers();
    hydrateDynamicContent();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();

  window.AxioEnhancements = {
    runtime,
    drawFocusedRoute,
    refreshHistoryMetadata: (force = true) => refreshHistory(force, 'public-api'),
  };
})();
