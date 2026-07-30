(() => {
  'use strict';

  const $r = selector => document.querySelector(selector);
  const $$r = selector => [...document.querySelectorAll(selector)];
  const routeState = {
    depot: null,
    results: [],
    selected: 0,
    jobsSnapshot: [],
    clientColors: new Map(),
    mapZoom: 6,
    mapCenter: { lat: 46.7, lon: 2.5 },
    mapPanX: 0,
    mapPanY: 0,
    drag: null,
    tileCache: new Map(),
    tileRedrawQueued: false,
  };

  const tableBody = $r('#route-jobs-table tbody');
  const mapCanvas = $r('#route-map');
  const mapContext = mapCanvas?.getContext('2d');
  const routeMessage = $r('#route-message');

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
  }

  function showMessage(message, error = false) {
    if (!routeMessage) return;
    routeMessage.textContent = message;
    routeMessage.classList.toggle('hidden', !message);
    routeMessage.classList.toggle('error', Boolean(error));
    routeMessage.classList.toggle('success', Boolean(message) && !error);
  }

  function fmt(value, digits = 1) {
    return Number(value || 0).toLocaleString('fr-FR', {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    });
  }

  const CLIENT_COLOR_PALETTE = [
    '#007A9C', '#E26D3D', '#7A5CC7', '#0C9A83', '#D04E8C', '#9A6B12',
    '#3C7DC4', '#A84A42', '#4E8B3A', '#B95B9A', '#6E7280', '#C3781D',
  ];

  function clientKey(value) {
    return String(value || 'Client sans nom').trim().toLocaleLowerCase('fr-FR');
  }

  function clientColor(client) {
    const key = clientKey(client);
    if (!routeState.clientColors.has(key)) {
      const used = new Set(routeState.clientColors.values());
      const available = CLIENT_COLOR_PALETTE.find(color => !used.has(color));
      if (available) routeState.clientColors.set(key, available);
      else {
        let hash = 0;
        for (const char of key) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
        routeState.clientColors.set(key, `hsl(${Math.abs(hash) % 360} 62% 43%)`);
      }
    }
    return routeState.clientColors.get(key);
  }

  function updateRowClientColor(row) {
    const client = row.querySelector('[data-route="client"]')?.value || row.dataset.id;
    const color = clientColor(client);
    row.dataset.clientColor = color;
    const swatch = row.querySelector('.route-client-swatch');
    if (swatch) {
      swatch.style.setProperty('--client-color', color);
      swatch.title = `Couleur de ${client || 'ce client'}`;
      swatch.setAttribute('aria-label', `Couleur associée au client ${client || ''}`);
    }
  }

  function quantityLabel(quantity, unitType) {
    const count = Number(quantity || 0);
    if (!count) return '0 unité';
    const singular = unitType === 'palette' ? 'palette' : unitType === 'colis' ? 'colis' : unitType === 'unités mixtes' ? 'unités mixtes' : 'unité';
    const plural = singular === 'palette' ? 'palettes' : singular === 'unité' ? 'unités' : singular;
    return `${count.toLocaleString('fr-FR')} ${count > 1 ? plural : singular}`;
  }

  function parseCoordinates(value) {
    const match = String(value || '').trim().match(/^\s*(-?\d{1,2}(?:[.,]\d+)?)\s*[,;]\s*(-?\d{1,3}(?:[.,]\d+)?)\s*$/);
    if (!match) return null;
    const lat = Number(match[1].replace(',', '.'));
    const lon = Number(match[2].replace(',', '.'));
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
    return { lat, lon, display_name: `${lat.toFixed(6)}, ${lon.toFixed(6)}` };
  }

  async function geocodeAddress(address) {
    const manual = parseCoordinates(address);
    if (manual) return manual;
    const response = await fetch(`/api/route/geocode?q=${encodeURIComponent(address)}`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'Adresse introuvable.');
    if (!body.results?.length) throw new Error(`Aucun résultat trouvé pour « ${address} ».`);
    return body.results[0];
  }

  function routeRowStatus(row) {
    const pickupReady = Number.isFinite(Number(row.dataset.pickupLat)) && Number.isFinite(Number(row.dataset.pickupLon));
    const deliveryReady = Number.isFinite(Number(row.dataset.deliveryLat)) && Number.isFinite(Number(row.dataset.deliveryLon));
    const status = row.querySelector('.route-row-status');
    status.className = 'route-row-status';
    if (pickupReady && deliveryReady) {
      status.classList.add('ready');
      status.textContent = 'Prête';
    } else if (pickupReady || deliveryReady) {
      status.classList.add('partial');
      status.textContent = 'Partielle';
    } else {
      status.textContent = 'À localiser';
    }
  }

  function invalidateCoordinates(row, type) {
    delete row.dataset[`${type}Lat`];
    delete row.dataset[`${type}Lon`];
    delete row.dataset[`${type}Label`];
    routeRowStatus(row);
  }

  function createRouteRow(data = {}) {
    const row = document.createElement('tr');
    row.dataset.id = data.id || `JOB-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    if (data.pickup?.lat != null) {
      row.dataset.pickupLat = data.pickup.lat;
      row.dataset.pickupLon = data.pickup.lon;
      row.dataset.pickupLabel = data.pickup.label || data.pickup.address || '';
    }
    if (data.delivery?.lat != null) {
      row.dataset.deliveryLat = data.delivery.lat;
      row.dataset.deliveryLon = data.delivery.lon;
      row.dataset.deliveryLabel = data.delivery.label || data.delivery.address || '';
    }
    row.innerHTML = `
      <td class="route-color-cell"><span class="route-client-swatch" aria-label="Couleur du client"></span></td>
      <td><input data-route="client" value="${escapeHtml(data.client || '')}" placeholder="Nom du client"></td>
      <td><input data-route="reference" value="${escapeHtml(data.reference || data.id || '')}" placeholder="Référence"></td>
      <td>
        <div class="route-job-address">
          <input data-route="pickup_address" value="${escapeHtml(data.pickup_address || data.pickup?.label || '')}" placeholder="Adresse d’enlèvement">
          <button type="button" class="secondary small route-locate" data-location="pickup">Localiser</button>
        </div>
      </td>
      <td>
        <div class="route-job-address">
          <input data-route="delivery_address" value="${escapeHtml(data.delivery_address || data.delivery?.label || '')}" placeholder="Adresse de livraison">
          <button type="button" class="secondary small route-locate" data-location="delivery">Localiser</button>
        </div>
      </td>
      <td><input data-route="quantity" type="number" min="0" step="1" value="${Number(data.quantity ?? 1)}"></td>
      <td><select data-route="unit_type">
        ${['palette','colis','unité','unités mixtes'].map(unit => `<option value="${unit}" ${String(data.unit_type || 'unité') === unit ? 'selected' : ''}>${unit}</option>`).join('')}
      </select></td>
      <td><input data-route="weight_kg" type="number" min="0" step="1" value="${Number(data.weight_kg || 0)}"></td>
      <td><span class="route-row-status">À localiser</span></td>
      <td><button type="button" class="row-delete route-delete" title="Supprimer">×</button></td>`;

    row.querySelectorAll('input[data-route$="_address"]').forEach(input => {
      input.addEventListener('input', () => invalidateCoordinates(row, input.dataset.route.startsWith('pickup') ? 'pickup' : 'delivery'));
    });
    row.querySelector('[data-route="client"]').addEventListener('input', () => updateRowClientColor(row));
    row.querySelectorAll('.route-locate').forEach(button => {
      button.addEventListener('click', () => locateRowAddress(row, button.dataset.location, button));
    });
    row.querySelector('.route-delete').addEventListener('click', () => row.remove());
    tableBody.append(row);
    updateRowClientColor(row);
    routeRowStatus(row);
    return row;
  }

  async function locateRowAddress(row, type, button) {
    const input = row.querySelector(`[data-route="${type}_address"]`);
    const address = input.value.trim();
    if (!address) {
      showMessage(`Renseignez l’adresse ${type === 'pickup' ? 'd’enlèvement' : 'de livraison'}.`, true);
      return false;
    }
    const original = button.textContent;
    button.disabled = true;
    button.textContent = '…';
    try {
      const result = await geocodeAddress(address);
      row.dataset[`${type}Lat`] = result.lat;
      row.dataset[`${type}Lon`] = result.lon;
      row.dataset[`${type}Label`] = result.display_name;
      input.value = result.display_name;
      routeRowStatus(row);
      showMessage('Adresse localisée.');
      return true;
    } catch (error) {
      const status = row.querySelector('.route-row-status');
      status.className = 'route-row-status error';
      status.textContent = 'Erreur';
      showMessage(error.message || String(error), true);
      return false;
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function locateDepot() {
    const address = $r('#route-depot-address').value.trim();
    const status = $r('#route-depot-status');
    if (!address) {
      showMessage('Renseignez le point de départ du camion.', true);
      return false;
    }
    const button = $r('#route-geocode-depot');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Localisation…';
    try {
      const result = await geocodeAddress(address);
      routeState.depot = { lat: result.lat, lon: result.lon, label: result.display_name };
      $r('#route-depot-address').value = result.display_name;
      status.textContent = `Localisé : ${result.lat.toFixed(5)}, ${result.lon.toFixed(5)}`;
      status.className = 'route-location-status located';
      showMessage('Point de départ localisé.');
      return true;
    } catch (error) {
      routeState.depot = null;
      status.textContent = error.message || String(error);
      status.className = 'route-location-status error';
      showMessage(status.textContent, true);
      return false;
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

  async function locateAll() {
    showMessage('Localisation des adresses en cours…');
    if (!routeState.depot && !(await locateDepot())) return false;
    const rows = [...tableBody.querySelectorAll('tr')];
    for (const row of rows) {
      for (const type of ['pickup', 'delivery']) {
        if (row.dataset[`${type}Lat`]) continue;
        const button = row.querySelector(`.route-locate[data-location="${type}"]`);
        const ok = await locateRowAddress(row, type, button);
        if (!ok) return false;
        // The public Nominatim service asks clients to avoid rapid bulk requests.
        await sleep(1050);
      }
    }
    showMessage('Toutes les adresses sont localisées.');
    return true;
  }

  function selectedVehicleCapacity() {
    const select = $r('#vehicle-id');
    const vehicles = window.PLO_VEHICLES || [];
    const vehicle = vehicles.find(item => item.model_id === select?.value) || vehicles[0];
    return Number(vehicle?.payload_kg || 24000);
  }

  function importClientsFromCargo() {
    const cargoRows = [...document.querySelectorAll('#cargo-table tbody tr')];
    if (!cargoRows.length) {
      showMessage('Aucune marchandise n’est présente dans l’onglet Données.', true);
      return;
    }
    const depotAddress = $r('#route-depot-address').value.trim();
    const grouped = new Map();
    cargoRows.forEach((cargo, index) => {
      const get = key => cargo.querySelector(`[data-k="${key}"]`);
      const reference = get('id')?.value.trim() || `REF-${index + 1}`;
      const destination = get('destination')?.value.trim() || `Client ${index + 1}`;
      const quantity = Number(get('quantity')?.value || 1);
      const weight = Number(get('weight')?.value || 0) * quantity;
      const shape = String(get('shape')?.value || 'box');
      const unitType = shape === 'pallet' ? 'palette' : 'colis';
      const key = destination.toLowerCase();
      if (!grouped.has(key)) {
        grouped.set(key, { client: destination, reference, weight_kg: weight, quantity, unit_types: new Set([unitType]) });
      } else {
        const item = grouped.get(key);
        item.reference += `, ${reference}`;
        item.weight_kg += weight;
        item.quantity += quantity;
        item.unit_types.add(unitType);
      }
    });
    tableBody.innerHTML = '';
    [...grouped.values()].forEach((item, index) => createRouteRow({
      id: `JOB-${String(index + 1).padStart(3, '0')}`,
      client: item.client,
      reference: item.reference,
      weight_kg: item.weight_kg,
      quantity: item.quantity,
      unit_type: item.unit_types.size > 1 ? 'unités mixtes' : [...item.unit_types][0],
      pickup_address: depotAddress,
      delivery_address: item.client,
    }));
    $r('#route-capacity').value = selectedVehicleCapacity();
    showMessage(`${grouped.size} client(s) récupéré(s). Complétez ou corrigez les adresses avant le calcul.`);
  }

  function rowPayload(row) {
    const field = name => row.querySelector(`[data-route="${name}"]`);
    const pickupLat = Number(row.dataset.pickupLat);
    const pickupLon = Number(row.dataset.pickupLon);
    const deliveryLat = Number(row.dataset.deliveryLat);
    const deliveryLon = Number(row.dataset.deliveryLon);
    if (![pickupLat, pickupLon, deliveryLat, deliveryLon].every(Number.isFinite)) {
      throw new Error(`La mission « ${field('client').value || field('reference').value || row.dataset.id} » n’est pas entièrement localisée.`);
    }
    return {
      id: row.dataset.id,
      client: field('client').value.trim() || row.dataset.id,
      reference: field('reference').value.trim() || row.dataset.id,
      weight_kg: Number(field('weight_kg').value || 0),
      quantity: Number(field('quantity').value || 0),
      unit_type: field('unit_type').value || 'unité',
      client_color: row.dataset.clientColor || clientColor(field('client').value),
      pickup: {
        lat: pickupLat,
        lon: pickupLon,
        label: row.dataset.pickupLabel || field('pickup_address').value.trim(),
      },
      delivery: {
        lat: deliveryLat,
        lon: deliveryLon,
        label: row.dataset.deliveryLabel || field('delivery_address').value.trim(),
      },
    };
  }

  function buildPayload(method) {
    if (!routeState.depot) throw new Error('Le point de départ doit être localisé avant le calcul.');
    const rows = [...tableBody.querySelectorAll('tr')];
    if (!rows.length) throw new Error('Ajoutez au moins une mission.');
    const jobs = rows.map(rowPayload);
    routeState.jobsSnapshot = jobs;
    return {
      method,
      depot: routeState.depot,
      jobs,
      capacity_kg: Number($r('#route-capacity').value || 0),
      time_limit_s: Number($r('#route-time-limit').value || 5),
      seed: Number($r('#route-seed').value || 1),
      return_to_depot: $r('#route-return-depot').checked,
    };
  }

  function setCalculationButtons(disabled, label = null) {
    const buttons = [
      $r('#route-optimize-hgs'),
      $r('#route-optimize-alns'),
      $r('#route-compare'),
    ];
    buttons.forEach(button => {
      if (!button) return;
      if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
      button.disabled = disabled;
      button.textContent = disabled && label ? label : button.dataset.originalText;
    });
  }

  async function runMethod(method) {
    showMessage('Calcul de la tournée en cours…');
    setCalculationButtons(true, 'Calcul en cours…');
    try {
      const payload = buildPayload(method);
      const response = await fetch('/api/route/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Le calcul d’itinéraire a échoué.');
      routeState.results = [body];
      routeState.selected = 0;
      resetMapView();
      renderRouteResults();
      showMessage('Itinéraire calculé.');
    } catch (error) {
      showMessage(error.message || String(error), true);
    } finally {
      setCalculationButtons(false);
    }
  }

  async function compareMethods() {
    showMessage('Comparaison HGS / ALNS en cours…');
    setCalculationButtons(true, 'Comparaison…');
    try {
      const payload = buildPayload('hgs');
      const response = await fetch('/api/route/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'La comparaison a échoué.');
      routeState.results = body.results || [];
      routeState.selected = routeState.results.reduce((best, result, index, results) => (
        Number(result.total_distance_km) < Number(results[best].total_distance_km) ? index : best
      ), 0);
      resetMapView();
      renderRouteResults();
      showMessage('Les deux méthodes ont été comparées avec la même matrice routière.');
    } catch (error) {
      showMessage(error.message || String(error), true);
    } finally {
      setCalculationButtons(false);
    }
  }

  function methodHelpText(result) {
    return `${result.method_description}\n\nAdaptation AxioLoad : chaque mission forme un couple enlèvement → livraison avec contrainte de précédence. Les couples peuvent être entrelacés lorsque cela réduit le trajet, sous réserve de la capacité du camion.`;
  }

  function bindDynamicHelp(button, text) {
    const tooltip = document.createElement('div');
    tooltip.className = 'route-map-tooltip';
    tooltip.hidden = true;
    tooltip.textContent = text;
    document.body.append(tooltip);
    const show = () => {
      const rect = button.getBoundingClientRect();
      tooltip.hidden = false;
      tooltip.style.left = `${Math.min(window.innerWidth - tooltip.offsetWidth - 12, Math.max(12, rect.left - tooltip.offsetWidth / 2))}px`;
      tooltip.style.top = `${Math.min(window.innerHeight - tooltip.offsetHeight - 12, rect.bottom + 8)}px`;
    };
    const hide = () => { tooltip.hidden = true; };
    button.addEventListener('mouseenter', show);
    button.addEventListener('mouseleave', hide);
    button.addEventListener('focus', show);
    button.addEventListener('blur', hide);
    button.addEventListener('click', event => {
      event.stopPropagation();
      tooltip.hidden ? show() : hide();
    });
  }

  function renderRouteResults() {
    const container = $r('#route-results');
    if (!routeState.results.length) {
      container.classList.add('hidden');
      return;
    }
    container.classList.remove('hidden');
    const shortest = Math.min(...routeState.results.map(result => Number(result.total_distance_km)));
    const cards = $r('#route-result-cards');
    cards.innerHTML = '';
    routeState.results.forEach((result, index) => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = `route-result-card ${index === routeState.selected ? 'active' : ''} ${Math.abs(result.total_distance_km - shortest) < 1e-6 && routeState.results.length > 1 ? 'best' : ''}`;
      card.innerHTML = `
        <div class="route-result-method">
          <strong>${escapeHtml(result.method_name)}</strong>
          <button type="button" class="route-method-help" aria-label="Définition de ${escapeHtml(result.method_name)}">?</button>
        </div>
        <div class="route-result-metrics">
          <span class="route-result-metric"><span>Distance</span><strong>${fmt(result.total_distance_km, 1)} km</strong></span>
          <span class="route-result-metric"><span>Durée estimée</span><strong>${fmt(result.total_duration_min / 60, 1)} h</strong></span>
          <span class="route-result-metric"><span>Calcul</span><strong>${fmt(result.elapsed_seconds, 2)} s</strong></span>
        </div>
        <div class="route-result-engine">${escapeHtml(result.engine)} · ${Number(result.iterations || 0).toLocaleString('fr-FR')} itérations · ${escapeHtml(result.provider)}</div>
        ${(result.warnings || []).map(warning => `<div class="route-result-warning">${escapeHtml(warning)}</div>`).join('')}`;
      card.addEventListener('click', event => {
        if (event.target.closest('.route-method-help')) return;
        routeState.selected = index;
        resetMapView();
        renderRouteResults();
      });
      cards.append(card);
      bindDynamicHelp(card.querySelector('.route-method-help'), methodHelpText(result));
    });
    const selected = routeState.results[routeState.selected];
    $r('#route-source-note').textContent = `${selected.model_note} Source de distance : ${selected.provider}.`;
    $r('#route-map-title').textContent = selected.method_name;
    $r('#route-map-subtitle').textContent = `${fmt(selected.total_distance_km, 1)} km · ${fmt(selected.total_duration_min, 0)} min · ${selected.job_count} mission(s)`;
    renderStopList(selected);
    renderMapLegend(selected);
    renderRecapTable(selected);
    drawRouteMap();
  }

  function renderStopList(result) {
    const list = $r('#route-stop-list');
    list.innerHTML = result.stops.map((stop, index) => {
      const leg = index > 0 ? result.legs[index - 1] : null;
      const typeLabel = stop.type === 'pickup' ? 'Enlèvement' : stop.type === 'delivery' ? 'Livraison' : stop.type === 'return' ? 'Retour' : 'Départ';
      const isClientStop = stop.type === 'pickup' || stop.type === 'delivery';
      const color = isClientStop ? clientColor(stop.client) : '#063B5B';
      return `<article class="route-stop ${escapeHtml(stop.type)}" style="--client-color:${color}">
        <span class="route-stop-number" style="background:${color}">${stop.sequence}</span>
        <div>
          <strong><span class="route-inline-swatch" style="--client-color:${color}"></span>${escapeHtml(typeLabel)}${stop.client ? ` · ${escapeHtml(stop.client)}` : ''}</strong>
          <small>${escapeHtml(stop.label || '')}</small>
          ${stop.reference ? `<small>Référence : ${escapeHtml(stop.reference)}</small>` : ''}
          ${stop.quantity ? `<small>Marchandise : ${escapeHtml(quantityLabel(stop.quantity, stop.unit_type))} · ${fmt(stop.weight_kg, 0)} kg</small>` : ''}
          ${stop.load_after_kg != null ? `<small>Charge après l’arrêt : ${fmt(stop.load_after_kg, 0)} kg</small>` : ''}
          ${leg ? `<div class="route-stop-leg">Depuis l’arrêt précédent : ${fmt(leg.distance_km, 1)} km · ${fmt(leg.duration_min, 0)} min</div>` : ''}
        </div>
      </article>`;
    }).join('');
  }

  function resultJobsSummary(result) {
    if (Array.isArray(result.jobs_summary) && result.jobs_summary.length) return result.jobs_summary;
    return routeState.jobsSnapshot.map(job => ({
      job_id: job.id,
      client: job.client,
      reference: job.reference,
      pickup_label: job.pickup?.label || '',
      delivery_label: job.delivery?.label || '',
      quantity: job.quantity || 0,
      unit_type: job.unit_type || 'unité',
      weight_kg: job.weight_kg || 0,
      direct_distance_km: 0,
      direct_duration_min: 0,
    }));
  }

  function renderMapLegend(result) {
    const legend = $r('#route-map-legend');
    const clients = [];
    const seen = new Set();
    resultJobsSummary(result).forEach(job => {
      const key = clientKey(job.client);
      if (seen.has(key)) return;
      seen.add(key);
      clients.push({ client: job.client, color: clientColor(job.client) });
    });
    legend.innerHTML = `
      <span><i class="route-dot start"></i>Départ / retour</span>
      <span><strong>P</strong> Enlèvement</span>
      <span><strong>L</strong> Livraison</span>
      ${clients.map(item => `<span><i class="route-client-legend" style="--client-color:${item.color}"></i>${escapeHtml(item.client)}</span>`).join('')}`;
  }

  function renderRecapTable(result) {
    const table = $r('#route-recap-table');
    if (!table) return;
    const jobs = resultJobsSummary(result);
    const body = table.querySelector('tbody');
    const foot = table.querySelector('tfoot');
    body.innerHTML = jobs.map(job => {
      const color = clientColor(job.client);
      return `<tr>
        <td class="route-recap-color"><span class="route-client-swatch" style="--client-color:${color}" aria-label="Couleur de ${escapeHtml(job.client)}"></span></td>
        <td><strong>${escapeHtml(job.client)}</strong><small>${escapeHtml(job.reference || '')}</small></td>
        <td>${escapeHtml(job.pickup_label || '—')}</td>
        <td>${escapeHtml(job.delivery_label || '—')}</td>
        <td class="route-recap-number"><strong>${fmt(job.direct_distance_km, 1)} km</strong><small>${fmt(job.direct_duration_min, 0)} min</small></td>
        <td class="route-recap-number">${escapeHtml(quantityLabel(job.quantity, job.unit_type))}</td>
        <td class="route-recap-number">${fmt(job.weight_kg, 0)} kg</td>
      </tr>`;
    }).join('');
    const totalWeight = Number(result.total_weight_kg ?? jobs.reduce((sum, job) => sum + Number(job.weight_kg || 0), 0));
    const totalUnits = Number(result.total_handling_units ?? jobs.reduce((sum, job) => sum + Number(job.quantity || 0), 0));
    foot.innerHTML = `<tr>
      <th colspan="4">Total de la tournée optimisée</th>
      <th class="route-recap-number">${fmt(result.total_distance_km, 1)} km</th>
      <th class="route-recap-number">${totalUnits.toLocaleString('fr-FR')} unité(s)</th>
      <th class="route-recap-number">${fmt(totalWeight, 0)} kg</th>
    </tr>`;
  }

  function mapTheme() {
    const dark = document.documentElement.dataset.theme === 'dark';
    return dark ? {
      background: '#071D27', route: '#32C6D4', shadow: 'rgba(0,0,0,.58)', text: '#ECF8FA',
      label: 'rgba(8,29,38,.94)', border: '#6EA9B9', tileOverlay: 'rgba(4,25,34,.28)',
    } : {
      background: '#E8F1F4', route: '#087FA2', shadow: 'rgba(5,46,70,.25)', text: '#063B5B',
      label: 'rgba(255,255,255,.96)', border: '#6E96A6', tileOverlay: 'rgba(255,255,255,.04)',
    };
  }

  const TILE_SIZE = 256;
  const MIN_MAP_ZOOM = 2;
  const MAX_MAP_ZOOM = 18;

  function clampLatitude(lat) {
    return Math.max(-85.05112878, Math.min(85.05112878, Number(lat)));
  }

  function latLonToWorld(lat, lon, zoom) {
    const latitude = clampLatitude(lat) * Math.PI / 180;
    const scale = TILE_SIZE * (2 ** zoom);
    return {
      x: (Number(lon) + 180) / 360 * scale,
      y: (0.5 - Math.log((1 + Math.sin(latitude)) / (1 - Math.sin(latitude))) / (4 * Math.PI)) * scale,
    };
  }

  function fitMapView(result) {
    const points = (result.geometry?.length ? result.geometry : result.stops.map(stop => [stop.lat, stop.lon]))
      .map(point => [Number(point[0]), Number(point[1])]);
    if (!points.length) return;
    const lats = points.map(point => point[0]);
    const lons = points.map(point => point[1]);
    const minLat = Math.min(...lats); const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons); const maxLon = Math.max(...lons);
    routeState.mapCenter = { lat: (minLat + maxLat) / 2, lon: (minLon + maxLon) / 2 };
    const availableWidth = Math.max(200, mapCanvas.width - 110);
    const availableHeight = Math.max(180, mapCanvas.height - 110);
    let selectedZoom = MIN_MAP_ZOOM;
    for (let zoom = MAX_MAP_ZOOM; zoom >= MIN_MAP_ZOOM; zoom -= 1) {
      const a = latLonToWorld(maxLat, minLon, zoom);
      const b = latLonToWorld(minLat, maxLon, zoom);
      if (Math.abs(b.x - a.x) <= availableWidth && Math.abs(b.y - a.y) <= availableHeight) {
        selectedZoom = zoom;
        break;
      }
    }
    routeState.mapZoom = selectedZoom;
    routeState.mapPanX = 0;
    routeState.mapPanY = 0;
  }

  function resetMapView() {
    const result = routeState.results[routeState.selected];
    if (result) fitMapView(result);
    else {
      routeState.mapZoom = 6;
      routeState.mapCenter = { lat: 46.7, lon: 2.5 };
      routeState.mapPanX = 0;
      routeState.mapPanY = 0;
    }
  }

  function drawRoundedLabel(ctx, text, x, y, theme, options = {}) {
    const font = options.font || '700 12px Segoe UI, Arial, sans-serif';
    ctx.save();
    ctx.font = font;
    ctx.textBaseline = 'middle';
    const width = ctx.measureText(text).width + 14;
    const height = 24;
    ctx.fillStyle = theme.label;
    ctx.strokeStyle = theme.border;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(x - width / 2, y - height / 2, width, height, 7);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = theme.text;
    ctx.textAlign = 'center';
    ctx.fillText(text, x, y + 0.5);
    ctx.restore();
  }

  function queueTileRedraw() {
    if (routeState.tileRedrawQueued) return;
    routeState.tileRedrawQueued = true;
    requestAnimationFrame(() => {
      routeState.tileRedrawQueued = false;
      drawRouteMap();
    });
  }

  function osmTileImage(zoom, tileX, tileY) {
    const tilesPerAxis = 2 ** zoom;
    if (tileY < 0 || tileY >= tilesPerAxis) return null;
    const wrappedX = ((tileX % tilesPerAxis) + tilesPerAxis) % tilesPerAxis;
    const key = `${zoom}/${wrappedX}/${tileY}`;
    if (routeState.tileCache.has(key)) return routeState.tileCache.get(key);
    const image = new Image();
    const entry = { image, loaded: false, failed: false };
    routeState.tileCache.set(key, entry);
    image.onload = () => { entry.loaded = true; queueTileRedraw(); };
    image.onerror = () => { entry.failed = true; queueTileRedraw(); };
    image.src = `https://tile.openstreetmap.org/${zoom}/${wrappedX}/${tileY}.png`;
    if (routeState.tileCache.size > 220) {
      const oldest = routeState.tileCache.keys().next().value;
      routeState.tileCache.delete(oldest);
    }
    return entry;
  }

  function drawBaseMapTiles(ctx, canvas, centerWorld, theme) {
    const leftWorld = centerWorld.x - canvas.width / 2 - routeState.mapPanX;
    const topWorld = centerWorld.y - canvas.height / 2 - routeState.mapPanY;
    const firstTileX = Math.floor(leftWorld / TILE_SIZE);
    const lastTileX = Math.floor((leftWorld + canvas.width) / TILE_SIZE);
    const firstTileY = Math.floor(topWorld / TILE_SIZE);
    const lastTileY = Math.floor((topWorld + canvas.height) / TILE_SIZE);
    for (let tileX = firstTileX; tileX <= lastTileX; tileX += 1) {
      for (let tileY = firstTileY; tileY <= lastTileY; tileY += 1) {
        const screenX = Math.round(tileX * TILE_SIZE - leftWorld);
        const screenY = Math.round(tileY * TILE_SIZE - topWorld);
        const tile = osmTileImage(routeState.mapZoom, tileX, tileY);
        if (tile?.loaded) ctx.drawImage(tile.image, screenX, screenY, TILE_SIZE + 1, TILE_SIZE + 1);
        else {
          ctx.fillStyle = theme.background;
          ctx.fillRect(screenX, screenY, TILE_SIZE + 1, TILE_SIZE + 1);
        }
      }
    }
    ctx.fillStyle = theme.tileOverlay;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  function drawRouteMap() {
    if (!mapContext || !routeState.results.length) return;
    const result = routeState.results[routeState.selected];
    const points = result.geometry?.length ? result.geometry : result.stops.map(stop => [stop.lat, stop.lon]);
    if (!points.length) return;
    const ctx = mapContext;
    const canvas = mapCanvas;
    const theme = mapTheme();
    const centerWorld = latLonToWorld(routeState.mapCenter.lat, routeState.mapCenter.lon, routeState.mapZoom);
    const project = ([lat, lon]) => {
      const world = latLonToWorld(lat, lon, routeState.mapZoom);
      return [
        canvas.width / 2 + routeState.mapPanX + world.x - centerWorld.x,
        canvas.height / 2 + routeState.mapPanY + world.y - centerWorld.y,
      ];
    };
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = theme.background;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawBaseMapTiles(ctx, canvas, centerWorld, theme);

    const screenPoints = points.map(project);
    ctx.save();
    ctx.strokeStyle = theme.shadow;
    ctx.lineWidth = 9;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    screenPoints.forEach((point, index) => index ? ctx.lineTo(...point) : ctx.moveTo(...point));
    ctx.stroke();
    ctx.strokeStyle = theme.route;
    ctx.lineWidth = 4;
    ctx.beginPath();
    screenPoints.forEach((point, index) => index ? ctx.lineTo(...point) : ctx.moveTo(...point));
    ctx.stroke();
    ctx.restore();

    result.stops.forEach((stop, index) => {
      const [x, y] = project([stop.lat, stop.lon]);
      const isDepot = stop.type === 'start' || stop.type === 'return';
      const color = isDepot ? '#063B5B' : clientColor(stop.client);
      ctx.save();
      ctx.fillStyle = color;
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(x, y, isDepot ? 11 : 10, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#FFFFFF';
      ctx.font = '800 10px Segoe UI, Arial, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const markerText = isDepot ? String(stop.sequence) : stop.type === 'pickup' ? 'P' : 'L';
      ctx.fillText(markerText, x, y + 0.5);
      ctx.restore();
      if (index === 0 || stop.type === 'delivery') {
        const label = index === 0 ? 'Départ' : stop.client;
        drawRoundedLabel(ctx, label, x, y - 24, theme, { font: '800 11px Segoe UI, Arial, sans-serif' });
      }
    });

    drawRoundedLabel(ctx, `${fmt(result.total_distance_km, 1)} km · ${fmt(result.total_duration_min, 0)} min`, canvas.width - 150, 30, theme, { font: '800 13px Segoe UI, Arial, sans-serif' });
  }

  function bindMapInteraction() {
    if (!mapCanvas) return;
    mapCanvas.addEventListener('pointerdown', event => {
      routeState.drag = { x: event.clientX, y: event.clientY, panX: routeState.mapPanX, panY: routeState.mapPanY };
      mapCanvas.setPointerCapture(event.pointerId);
    });
    mapCanvas.addEventListener('pointermove', event => {
      if (!routeState.drag) return;
      routeState.mapPanX = routeState.drag.panX + event.clientX - routeState.drag.x;
      routeState.mapPanY = routeState.drag.panY + event.clientY - routeState.drag.y;
      drawRouteMap();
    });
    mapCanvas.addEventListener('pointerup', () => { routeState.drag = null; });
    mapCanvas.addEventListener('pointercancel', () => { routeState.drag = null; });
    mapCanvas.addEventListener('wheel', event => {
      event.preventDefault();
      const nextZoom = Math.max(MIN_MAP_ZOOM, Math.min(MAX_MAP_ZOOM, routeState.mapZoom + (event.deltaY > 0 ? -1 : 1)));
      if (nextZoom !== routeState.mapZoom) {
        routeState.mapZoom = nextZoom;
        routeState.mapPanX = 0;
        routeState.mapPanY = 0;
        drawRouteMap();
      }
    }, { passive: false });
  }

  $r('#route-add-job')?.addEventListener('click', () => createRouteRow({ pickup_address: $r('#route-depot-address').value.trim() }));
  $r('#route-import-clients')?.addEventListener('click', importClientsFromCargo);
  $r('#route-geocode-depot')?.addEventListener('click', locateDepot);
  $r('#route-depot-address')?.addEventListener('input', () => {
    routeState.depot = null;
    const status = $r('#route-depot-status');
    status.textContent = 'Adresse modifiée : relancez la localisation.';
    status.className = 'route-location-status';
  });
  $r('#route-geocode-all')?.addEventListener('click', locateAll);
  $r('#route-optimize-hgs')?.addEventListener('click', () => runMethod('hgs'));
  $r('#route-optimize-alns')?.addEventListener('click', () => runMethod('alns'));
  $r('#route-compare')?.addEventListener('click', compareMethods);
  $r('#route-map-reset')?.addEventListener('click', () => { resetMapView(); drawRouteMap(); });

  const routeTab = $r('.tab[data-tab="route"]');
  routeTab?.addEventListener('click', () => {
    $r('#route-capacity').value = selectedVehicleCapacity();
    if (!tableBody.children.length) createRouteRow({ pickup_address: $r('#route-depot-address').value.trim() });
    setTimeout(drawRouteMap, 50);
  });

  new MutationObserver(() => drawRouteMap()).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  bindMapInteraction();
  if (!tableBody.children.length) createRouteRow();
})();
