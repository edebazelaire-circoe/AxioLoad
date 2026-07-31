(() => {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const originalFetch = window.fetch.bind(window);
  const runtime = {
    loading: {request: null, result: null},
    route: {request: null, result: null},
    total: {request: null, result: null},
    focusedRoute: null,
    history: new Map(),
    historyRequest: null,
    domRefreshScheduled: false,
  };

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
  const num = input => Number(input?.value || 0);

  function user() {
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
      seed: num($('#seed')) || 1,
      budget_seconds: num($('#budget-seconds')) || 30,
      default_margins: {
        left: num($('#default-margin')),
        right: num($('#default-margin')),
        front: num($('#default-margin')),
        rear: num($('#default-margin')),
        top: 0,
      },
      vehicle_policy: {
        mode: 'forced',
        forced_vehicle_id: $('#vehicle-id')?.value,
        max_vehicles: num($('#max-vehicles')) || 1,
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
    const known = new Set(loading.items.map(item => item.id));
    return {
      ...payload,
      vehicle_id: $('#vehicle-id')?.value,
      loading,
      jobs: (payload.jobs || []).map(job => ({
        ...job,
        item_ids: String(job.reference || '').split(',').map(value => value.trim()).filter(value => known.has(value)),
      })),
    };
  }

  function publishHistory(rows) {
    runtime.history = new Map(rows.map(row => [String(row.id).slice(0, 8), row]));
    document.dispatchEvent(new CustomEvent('axioload:history-loaded', {detail: {rows}}));
    scheduleEnhancements();
  }

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase();
    let options = init;
    let body = null;

    if (typeof init.body === 'string') {
      try {
        body = JSON.parse(init.body);
      } catch (_) {
        body = null;
      }
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

    const response = await originalFetch(input, options);

    if (response.ok && (
      url.includes('/local/optimize') ||
      url.includes('/api/route/optimize') ||
      url.includes('/api/route/compare') ||
      url.includes('/api/total/optimize')
    )) {
      try {
        const data = await response.clone().json();
        if (url.includes('/local/optimize')) runtime.loading.result = data;
        else if (url.includes('/api/total/optimize')) runtime.total.result = data;
        else runtime.route.result = data;
      } catch (_) {}
    }

    const isHistoryList = method === 'GET' && /\/api\/history(?:\?|$)/.test(url);
    if (response.ok && isHistoryList) {
      try {
        const rows = await response.clone().json();
        if (Array.isArray(rows)) publishHistory(rows);
      } catch (_) {}
    }

    return response;
  };

  function addHeaderAfter(reference, html, key) {
    if (!reference || reference.parentElement.querySelector(`[data-enhanced-header="${key}"]`)) return;
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    reference.after(template.content.firstElementChild);
  }

  function enhanceVehicleHeaders() {
    const heightHeader = $$('#vehicle-table thead th').find(header => header.textContent.includes('Hauteur int.'));
    addHeaderAfter(heightHeader, '<th data-enhanced-header="vehicle-exterior-length" class="col-num">Longueur ext. (mm)</th>', 'vehicle-exterior-length');
    addHeaderAfter($('[data-enhanced-header="vehicle-exterior-length"]'), '<th data-enhanced-header="vehicle-exterior-width" class="col-num">Largeur ext. (mm)</th>', 'vehicle-exterior-width');
    addHeaderAfter($('[data-enhanced-header="vehicle-exterior-width"]'), '<th data-enhanced-header="vehicle-exterior-height" class="col-num">Hauteur ext. (mm) <button type="button" class="help-tip small-tip" data-tooltip="Hauteur extérieure documentée pour les contrôles de gabarit. OSRM public ne garantit pas les restrictions poids lourd." aria-label="Aide hauteur extérieure">?</button></th>', 'vehicle-exterior-height');
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

  function enhanceVehicleRow(row) {
    if (row.querySelector('[data-v="exterior_length_mm"]')) return;
    let original = {};
    try {
      original = JSON.parse(row.dataset.original || '{}');
    } catch (_) {}
    const defaults = exteriorDefaults(original);
    const anchor = row.querySelector('[data-v="interior_height_mm"]')?.closest('td');
    if (!anchor) return;
    [
      ['exterior_height_mm', original.exterior_height_mm || defaults[2]],
      ['exterior_width_mm', original.exterior_width_mm || defaults[1]],
      ['exterior_length_mm', original.exterior_length_mm || defaults[0]],
    ].forEach(([key, value]) => {
      const cell = document.createElement('td');
      cell.innerHTML = `<input data-v="${key}" type="number" min="1" value="${Number(value)}">`;
      anchor.after(cell);
    });
  }

  function enhanceVehicles() {
    enhanceVehicleHeaders();
    $$('#vehicle-table tbody tr').forEach(enhanceVehicleRow);
  }

  function enhanceCargoHeader() {
    const rotationHeader = $$('#cargo-table thead th').find(header => header.textContent.includes('Rotation'));
    addHeaderAfter(rotationHeader, '<th data-enhanced-header="stackable" class="col-stackable">Gerbable <button type="button" class="help-tip small-tip" data-tooltip="Autorise la superposition de palettes identiques lorsque la hauteur et la concentration de poids le permettent." aria-label="Aide gerbage">?</button></th>', 'stackable');
  }

  function syncStack(row) {
    const shape = row.querySelector('[data-k="shape"]');
    const stackable = row.querySelector('[data-k="stackable"]');
    if (!shape || !stackable) return;
    stackable.disabled = shape.value !== 'pallet';
    if (stackable.disabled) stackable.checked = false;
  }

  function enhanceCargoRow(row) {
    if (row.querySelector('[data-k="stackable"]')) return;
    const anchor = row.querySelector('[data-k="rotation_allowed"]')?.closest('td');
    if (!anchor) return;
    let original = {};
    try {
      original = JSON.parse(row.dataset.original || '{}');
    } catch (_) {}
    const cell = document.createElement('td');
    cell.className = 'col-stackable';
    cell.innerHTML = `<input data-k="stackable" type="checkbox" ${original.stackable ? 'checked' : ''} aria-label="Palette gerbable">`;
    anchor.after(cell);
    row.querySelector('[data-k="shape"]')?.addEventListener('change', () => syncStack(row));
    syncStack(row);
  }

  function enhanceCargo() {
    enhanceCargoHeader();
    $$('#cargo-table tbody tr').forEach(enhanceCargoRow);
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

  document.addEventListener('click', event => {
    const button = event.target.closest('#total-fill-pickups');
    if (!button) return;
    const depot = window.AxioTotalOptimization?.state?.depot;
    if (!depot) return;
    event.preventDefault();
    event.stopImmediatePropagation();
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
  }, true);

  function validationBar(type, container, title) {
    if (!container || $(`#validation-${type}`)) return;
    const element = document.createElement('section');
    element.id = `validation-${type}`;
    element.className = 'workflow-validation';
    element.innerHTML = `<label><span>Titre de l’optimisation</span><input class="workflow-title" value="${esc(title)}" maxlength="180"></label><button type="button" class="primary workflow-validate">Valider et enregistrer</button><span class="workflow-validation-message"></span>`;
    container.prepend(element);
    element.querySelector('button').addEventListener('click', () => validate(type, element));
  }

  const activeIndex = selector => Math.max(0, $$(selector).findIndex(element => element.classList.contains('active')));

  function routeResult() {
    const result = runtime.route.result;
    return result?.results ? result.results[activeIndex('#route-result-cards .route-result-card')] || result.results[0] : result;
  }

  async function validate(type, barElement) {
    const title = barElement.querySelector('input').value.trim();
    const message = barElement.querySelector('.workflow-validation-message');
    if (!title) {
      message.textContent = 'Le titre est obligatoire.';
      message.className = 'workflow-validation-message error';
      return;
    }

    let request;
    let result;
    let runId = '';
    let selected = 0;
    if (type === 'loading') {
      request = runtime.loading.request;
      result = runtime.loading.result;
      runId = result?.run_id || '';
      selected = activeIndex('#solution-cards .solution-card');
    } else if (type === 'route') {
      request = runtime.route.request;
      result = routeResult();
      selected = activeIndex('#route-result-cards .route-result-card');
    } else {
      request = runtime.total.request;
      result = window.AxioTotalOptimization?.state?.result || runtime.total.result;
      selected = activeIndex('#total-method-cards .total-method-card');
    }

    if (!request || !result) {
      message.textContent = 'Lancez d’abord une optimisation.';
      message.className = 'workflow-validation-message error';
      return;
    }

    message.textContent = 'Enregistrement…';
    const response = await originalFetch('/api/history/validate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        run_id: runId,
        optimization_type: type,
        title,
        user: user(),
        selected_solution: selected,
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

    try {
      const key = 'axioload.decisions.v1';
      const decisions = JSON.parse(localStorage.getItem(key) || '{}');
      decisions[data.id] = {
        status: 'validated',
        selectedSolution: selected,
        user: user(),
        decisionAt: data.validated_at || new Date().toISOString(),
        reason: '',
        comment: '',
      };
      localStorage.setItem(key, JSON.stringify(decisions));
    } catch (_) {}

    message.textContent = `Validé sous le titre « ${title} ».`;
    message.className = 'workflow-validation-message success';
    await refreshHistory(true);
  }

  function ensureBars() {
    validationBar('loading', $('#tab-results .decision-panel') || $('#tab-results #results-content'), 'Optimisation de chargement');
    validationBar('route', $('#route-results'), 'Optimisation d’itinéraire');
    validationBar('total', $('#total-results'), 'Optimisation totale');
    $('#validate-optimization')?.classList.add('legacy-validation-button');
  }

  async function refreshHistory(force = false) {
    if (runtime.historyRequest) return runtime.historyRequest;
    if (!force && runtime.history.size) {
      decorateHistory();
      return runtime.history;
    }
    runtime.historyRequest = (async () => {
      try {
        const response = await originalFetch('/api/history?limit=200');
        if (!response.ok) return runtime.history;
        const rows = await response.json();
        if (Array.isArray(rows)) publishHistory(rows);
      } catch (_) {}
      return runtime.history;
    })().finally(() => {
      runtime.historyRequest = null;
    });
    return runtime.historyRequest;
  }

  function decorateHistory() {
    const labels = {loading: 'Chargement', route: 'Itinéraire', total: 'Optimisation totale'};
    $$('#history-list .history-item').forEach(item => {
      const text = item.textContent || '';
      const key = [...runtime.history.keys()].find(prefix => text.includes(prefix));
      if (!key) return;
      const metadata = runtime.history.get(key);
      const title = item.querySelector('.history-top-row strong');
      const nextTitle = metadata.title || title?.textContent || '';
      if (title && title.textContent !== nextTitle) title.textContent = nextTitle;

      const badge = item.querySelector('.status-badge');
      if (badge && metadata.validation_status === 'validated') {
        if (badge.textContent !== 'Validé') badge.textContent = 'Validé';
        if (badge.className !== 'status-badge status-validated') badge.className = 'status-badge status-validated';
      }

      const meta = item.querySelector('.history-meta');
      const label = labels[metadata.optimization_type] || metadata.optimization_type;
      if (meta && label && !meta.textContent.includes(label)) meta.textContent += ` · ${label}`;

      if (metadata.optimization_type !== 'loading') {
        item.querySelectorAll('[data-action="open"],[data-action="duplicate"]').forEach(button => {
          if (!button.disabled) button.disabled = true;
          if (button.title !== 'Réouverture non disponible pour ce type.') button.title = 'Réouverture non disponible pour ce type.';
        });
      }
    });
  }

  const formatNumber = (value, digits = 1) => Number(value || 0).toLocaleString('fr-FR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

  function emptyMetrics() {
    const routeResults = runtime.route.result?.results || (runtime.route.result ? [runtime.route.result] : []);
    $$('#route-result-cards .route-result-card').forEach((card, index) => {
      if (card.querySelector('.empty-distance-metric') || !routeResults[index]) return;
      const span = document.createElement('span');
      span.className = 'route-result-metric empty-distance-metric';
      span.innerHTML = `<span>Trajet à vide</span><strong>${formatNumber(routeResults[index].empty_distance_percent)} %</strong>`;
      card.querySelector('.route-result-metrics')?.append(span);
    });

    const totalState = window.AxioTotalOptimization?.state;
    const solution = totalState?.result?.solutions?.[totalState.selected || 0];
    $$('#total-route-list .total-route-card').forEach((card, index) => {
      let badge = card.querySelector('.empty-distance-badge');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'empty-distance-badge';
        card.querySelector('.total-route-heading > div:last-child')?.append(badge);
      }
      const data = solution?.routes?.[index];
      if (!data) return;
      const nextText = `${formatNumber(data.empty_distance_percent)} % à vide · ${formatNumber(data.empty_distance_km)} km`;
      if (badge.textContent !== nextText) badge.textContent = nextText;
    });
  }

  const colors = ['#007A9C', '#E26D3D', '#7A5CC7', '#0C9A83', '#D04E8C', '#9A6B12', '#3C7DC4', '#A84A42'];
  let overlay = null;

  function ensureOverlay() {
    const base = $('#total-map');
    if (!base || overlay) return;
    base.parentElement.style.position = 'relative';
    overlay = document.createElement('canvas');
    overlay.className = 'total-focus-map';
    overlay.width = base.width;
    overlay.height = base.height;
    base.after(overlay);
  }

  function world(latitude, longitude, zoom) {
    const clampedLatitude = Math.max(-85.0511, Math.min(85.0511, Number(latitude)));
    const sine = Math.sin(clampedLatitude * Math.PI / 180);
    const scale = 256 * (2 ** zoom);
    return {
      x: (Number(longitude) + 180) / 360 * scale,
      y: (0.5 - Math.log((1 + sine) / (1 - sine)) / (4 * Math.PI)) * scale,
    };
  }

  function drawFocus() {
    ensureOverlay();
    const base = $('#total-map');
    if (!overlay || !base) return;
    const context = overlay.getContext('2d');
    context.clearRect(0, 0, overlay.width, overlay.height);
    const totalState = window.AxioTotalOptimization?.state;
    const solution = totalState?.result?.solutions?.[totalState.selected || 0];
    const route = solution?.routes?.[runtime.focusedRoute];
    base.classList.toggle('routes-dimmed', Boolean(route));
    $$('#total-route-list .total-route-card').forEach((card, index) => card.classList.toggle('vehicle-focused', index === runtime.focusedRoute));
    if (!route) return;

    const zoom = totalState.zoom;
    const center = world(totalState.center.lat, totalState.center.lon, zoom);
    const screen = point => {
      const projected = world(point[0], point[1], zoom);
      return {
        x: overlay.width / 2 + (totalState.panX || 0) + projected.x - center.x,
        y: overlay.height / 2 + (totalState.panY || 0) + projected.y - center.y,
      };
    };
    const geometry = route.geometry?.length ? route.geometry : route.stops.map(stop => [stop.lat, stop.lon]);
    context.lineJoin = 'round';
    context.lineCap = 'round';
    context.strokeStyle = 'rgba(255,255,255,.92)';
    context.lineWidth = 11;
    context.beginPath();
    geometry.forEach((point, index) => {
      const projected = screen(point);
      if (index) context.lineTo(projected.x, projected.y);
      else context.moveTo(projected.x, projected.y);
    });
    context.stroke();
    context.strokeStyle = colors[runtime.focusedRoute % colors.length];
    context.lineWidth = 6;
    context.stroke();
    route.stops.forEach(stop => {
      const projected = screen([stop.lat, stop.lon]);
      context.beginPath();
      context.arc(projected.x, projected.y, 8, 0, Math.PI * 2);
      context.fillStyle = stop.type === 'delivery' ? '#E26D3D' : '#007A9C';
      context.fill();
      context.strokeStyle = '#fff';
      context.lineWidth = 2;
      context.stroke();
    });
  }

  function bindFocus() {
    ensureOverlay();
    $$('#total-route-list .total-route-card').forEach((card, index) => {
      if (card.dataset.focusBound) return;
      card.dataset.focusBound = '1';
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      const activate = () => {
        runtime.focusedRoute = runtime.focusedRoute === index ? null : index;
        drawFocus();
      };
      card.addEventListener('click', event => {
        if (!event.target.closest('details,table,button,a,input,select')) activate();
      });
      card.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          activate();
        }
      });
    });

    $$('#total-map-legend span').forEach((item, index) => {
      if (item.classList.contains('total-operation-legend') || item.dataset.focusBound) return;
      item.dataset.focusBound = '1';
      item.classList.add('vehicle-map-filter');
      item.addEventListener('click', () => {
        runtime.focusedRoute = runtime.focusedRoute === index ? null : index;
        drawFocus();
      });
    });
  }

  function runEnhancements() {
    runtime.domRefreshScheduled = false;
    enhanceVehicles();
    enhanceCargo();
    ensureBars();
    emptyMetrics();
    bindFocus();
    decorateHistory();
    if (runtime.focusedRoute !== null) requestAnimationFrame(drawFocus);
  }

  function scheduleEnhancements() {
    if (runtime.domRefreshScheduled) return;
    runtime.domRefreshScheduled = true;
    requestAnimationFrame(runEnhancements);
  }

  const observer = new MutationObserver(records => {
    const containsNewElement = records.some(record => [...record.addedNodes].some(node => node.nodeType === Node.ELEMENT_NODE));
    if (containsNewElement) scheduleEnhancements();
  });
  observer.observe(document.body, {childList: true, subtree: true});

  ['pointermove', 'pointerup', 'wheel'].forEach(name => $('#total-map')?.addEventListener(name, () => requestAnimationFrame(drawFocus)));
  $('#total-map-reset')?.addEventListener('click', () => requestAnimationFrame(drawFocus));

  enhanceVehicles();
  enhanceCargo();
  addTemplate();
  ensureBars();
  scheduleEnhancements();
  window.AxioEnhancements = {
    runtime,
    drawFocusedRoute: drawFocus,
    refreshHistoryMetadata: refreshHistory,
  };
})();
