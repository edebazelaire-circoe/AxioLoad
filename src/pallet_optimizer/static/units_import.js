(() => {
  'use strict';

  const STORAGE_KEY = 'axioload.dimension-unit.v1';
  const FACTORS_TO_MM = {mm: 1, m: 1000};
  const DIMENSION_FIELDS = new Set(['length', 'width', 'height', 'separation']);
  const MAX_IMPORT_SIZE = 20 * 1024 * 1024;
  const rawFetch = window.fetch.bind(window);

  function storedUnit() {
    try { return localStorage.getItem(STORAGE_KEY) === 'm' ? 'm' : 'mm'; }
    catch (_) { return 'mm'; }
  }

  let currentUnit = storedUnit();

  function saveUnit() {
    try { localStorage.setItem(STORAGE_KEY, currentUnit); } catch (_) {}
  }

  function convert(value, fromUnit, toUnit) {
    const number = Number(value);
    if (!Number.isFinite(number)) return value;
    return number * FACTORS_TO_MM[fromUnit] / FACTORS_TO_MM[toUnit];
  }

  function displayNumber(value, unit) {
    const number = Number(value);
    if (!Number.isFinite(number)) return value;
    return unit === 'mm' ? String(Math.round(number)) : String(Math.round(number * 1000) / 1000);
  }

  const dimensionSelector = [
    '#default-margin',
    '#cargo-table [data-k="length"]',
    '#cargo-table [data-k="width"]',
    '#cargo-table [data-k="height"]',
    '#cargo-table [data-k="separation"]',
    '#vehicle-table [data-v$="_mm"]',
  ].join(',');

  function prepareInput(input, sourceUnit = 'mm') {
    if (!(input instanceof HTMLInputElement) || input.type !== 'number' || input.dataset.dimensionUnit) return;
    input.value = displayNumber(convert(input.value, sourceUnit, currentUnit), currentUnit);
    input.dataset.dimensionUnit = currentUnit;
    input.step = currentUnit === 'm' ? '0.001' : '1';
    if (input.min && Number(input.min) > 0) input.min = currentUnit === 'm' ? '0.001' : '1';
  }

  function prepareInputs(root = document, sourceUnit = 'mm') {
    if (root.matches?.(dimensionSelector)) prepareInput(root, sourceUnit);
    root.querySelectorAll?.(dimensionSelector).forEach(input => prepareInput(input, sourceUnit));
  }

  function convertInputs(fromUnit, toUnit) {
    document.querySelectorAll(dimensionSelector).forEach(input => {
      const source = input.dataset.dimensionUnit || fromUnit;
      input.value = displayNumber(convert(input.value, source, toUnit), toUnit);
      input.dataset.dimensionUnit = toUnit;
      input.step = toUnit === 'm' ? '0.001' : '1';
      if (input.min && Number(input.min) > 0) input.min = toUnit === 'm' ? '0.001' : '1';
    });
  }

  function replaceUnitLabel(element) {
    if (!element) return;
    [...element.childNodes].forEach(node => {
      if (node.nodeType === Node.TEXT_NODE) node.textContent = node.textContent.replace(/\((?:mm|m)\)/g, `(${currentUnit})`);
    });
  }

  function updateLabels() {
    document.querySelectorAll('#vehicle-table th, #cargo-table th').forEach(replaceUnitLabel);
    const margin = [...document.querySelectorAll('#tab-data .field-label')]
      .find(label => label.textContent.includes('Marge de sécurité globale'));
    replaceUnitLabel(margin);
    const hint = document.querySelector('#dimension-unit-live-hint');
    if (hint) {
      hint.textContent = currentUnit === 'm'
        ? 'Les dimensions sont saisies et affichées en mètres. AxioLoad les convertit en millimètres pour les calculs internes.'
        : 'Les dimensions sont saisies et affichées en millimètres.';
    }
    const templateLink = document.querySelector('#download-excel-template');
    if (templateLink) templateLink.textContent = 'Modèle Excel AxioLoad (dimensions en mm)';
  }

  function unitMessage(message) {
    const box = document.querySelector('#dimension-unit-message');
    if (!box) return;
    box.textContent = message;
    box.className = 'message success';
    box.classList.remove('hidden');
  }

  function applyUnit(nextUnit, announce = true) {
    const normalized = nextUnit === 'm' ? 'm' : 'mm';
    if (normalized !== currentUnit) convertInputs(currentUnit, normalized);
    currentUnit = normalized;
    saveUnit();
    document.querySelectorAll('input[name="dimension-unit"]').forEach(input => {
      input.checked = input.value === currentUnit;
    });
    updateLabels();
    if (announce) unitMessage(`L’unité de travail est maintenant ${currentUnit === 'm' ? 'le mètre' : 'le millimètre'}.`);
  }

  function installSettingsCard() {
    const settings = document.querySelector('#tab-settings .settings-sections');
    if (!settings || document.querySelector('#dimension-unit-settings')) return;
    const card = document.createElement('section');
    card.id = 'dimension-unit-settings';
    card.className = 'settings-card';
    card.innerHTML = `
      <div class="settings-card-heading">
        <div class="settings-icon" aria-hidden="true">↔</div>
        <div><h3>Unité des dimensions</h3><p>Choisissez l’unité utilisée pour les véhicules, les marchandises et les marges.</p></div>
      </div>
      <div class="theme-options" role="radiogroup" aria-label="Unité des dimensions">
        <label class="theme-choice"><input type="radio" name="dimension-unit" value="mm"><span><strong>Millimètres</strong><small>Exemple : 1 200 × 800 × 1 400 mm.</small></span></label>
        <label class="theme-choice"><input type="radio" name="dimension-unit" value="m"><span><strong>Mètres</strong><small>Exemple : 1,200 × 0,800 × 1,400 m.</small></span></label>
      </div>
      <div id="dimension-unit-live-hint" class="notice neutral-notice"></div>
      <div class="settings-actions"><button id="save-dimension-unit" class="primary" type="button">Enregistrer l’unité</button></div>
      <div id="dimension-unit-message" class="message hidden" role="status" aria-live="polite"></div>`;
    const appearance = document.querySelector('#appearance-settings-title')?.closest('.settings-card');
    if (appearance) appearance.after(card); else settings.prepend(card);
    card.querySelector('#save-dimension-unit').addEventListener('click', () => {
      applyUnit(card.querySelector('input[name="dimension-unit"]:checked')?.value || 'mm');
    });
  }

  function installImportHelp() {
    const box = document.querySelector('#tab-data .import-box');
    if (!box || document.querySelector('#import-format-help')) return;
    const help = document.createElement('small');
    help.id = 'import-format-help';
    help.style.display = 'block';
    help.style.maxWidth = '380px';
    help.textContent = 'Formats acceptés : .xlsx et .csv. L’ancien format .xls doit être réenregistré en .xlsx. Le modèle AxioLoad est en mm et l’affichage est ensuite converti automatiquement.';
    box.append(help);
  }

  function addUnitToPayload(payload) {
    if (!payload || typeof payload !== 'object') return payload;
    if (Array.isArray(payload.items)) payload.dimension_unit = currentUnit;
    if (payload.loading && typeof payload.loading === 'object') payload.loading.dimension_unit = currentUnit;
    return payload;
  }

  const originalBuildPayload = window.buildPayload;
  if (typeof originalBuildPayload === 'function') {
    window.buildPayload = function buildPayloadWithUnit() {
      return addUnitToPayload(originalBuildPayload());
    };
  }

  function temporarilyConvertVehiclesToMillimetres() {
    if (currentUnit === 'mm') return () => {};
    const inputs = [...document.querySelectorAll('#vehicle-table [data-v$="_mm"]')];
    inputs.forEach(input => {
      input.value = displayNumber(convert(input.value, currentUnit, 'mm'), 'mm');
      input.dataset.dimensionUnit = 'mm';
    });
    return () => {
      inputs.forEach(input => {
        input.value = displayNumber(convert(input.value, 'mm', currentUnit), currentUnit);
        input.dataset.dimensionUnit = currentUnit;
      });
    };
  }

  document.addEventListener('click', event => {
    if (!event.target.closest?.('#save-vehicles')) return;
    const restore = temporarilyConvertVehiclesToMillimetres();
    window.setTimeout(restore, 0);
  }, true);

  function importMessage(message, kind = 'error') {
    const box = document.querySelector('#data-errors');
    if (!box) return;
    box.textContent = message;
    box.classList.remove('hidden', 'error', 'success', 'warning');
    box.classList.add(kind);
  }

  function importError(file, status, body) {
    const extension = (file.name.match(/\.[^.]+$/)?.[0] || '').toLowerCase();
    if (extension === '.xls') {
      return 'Le fichier utilise l’ancien format Excel .xls. Ouvrez-le dans Excel ou LibreOffice, choisissez « Enregistrer sous », puis sélectionnez le format Classeur Excel .xlsx.';
    }
    if (!['.xlsx', '.csv'].includes(extension)) {
      return `Le format « ${extension || 'sans extension'} » n’est pas accepté. Sélectionnez un fichier .xlsx ou .csv.`;
    }
    if (status === 415) return 'Le serveur accepte uniquement les fichiers .xlsx et .csv. Un fichier renommé ou un ancien .xls ne peut pas être lu.';
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    if (detail?.message) return detail.message;
    if (Array.isArray(detail)) return detail.map(item => item.msg || String(item)).join('\n');
    if (status >= 500) return 'Le fichier n’a pas pu être lu. Vérifiez qu’il s’ouvre dans Excel, qu’il n’est pas protégé par un mot de passe et qu’il est bien enregistré au format .xlsx.';
    return 'Le fichier a été refusé. Vérifiez les colonnes obligatoires et utilisez le modèle AxioLoad.';
  }

  function itemToMillimetres(item, sourceUnit) {
    const converted = {...item};
    DIMENSION_FIELDS.forEach(field => {
      if (converted[field] === undefined || converted[field] === null || converted[field] === '') return;
      converted[field] = convert(converted[field], sourceUnit, 'mm');
    });
    return converted;
  }

  function missingTotalData(items) {
    if (!document.querySelector('#total-optimization-enabled')?.checked) return [];
    const missingPickup = [];
    const missingDelivery = [];
    const missingClient = [];
    items.forEach((item, index) => {
      const row = item._source_row || index + 2;
      if (!String(item.pickup_address || '').trim()) missingPickup.push(row);
      if (!String(item.delivery_address || '').trim()) missingDelivery.push(row);
      if (!String(item.destination || '').trim()) missingClient.push(row);
    });
    const messages = [];
    if (missingClient.length) messages.push(`client/destination absent ligne(s) ${missingClient.join(', ')}`);
    if (missingPickup.length) messages.push(`point d’enlèvement absent ligne(s) ${missingPickup.join(', ')}`);
    if (missingDelivery.length) messages.push(`point de livraison absent ligne(s) ${missingDelivery.join(', ')}`);
    return messages;
  }

  async function handleImport(input) {
    const file = input.files?.[0];
    if (!file) return;
    const extension = (file.name.match(/\.[^.]+$/)?.[0] || '').toLowerCase();
    try {
      if (file.size === 0) throw new Error('Le fichier sélectionné est vide.');
      if (file.size > MAX_IMPORT_SIZE) throw new Error('Le fichier dépasse 20 Mo. Réduisez-le ou scindez les données en plusieurs imports.');
      if (extension === '.xls' || !['.xlsx', '.csv'].includes(extension)) throw new Error(importError(file, 415, {}));
      importMessage(`Lecture de « ${file.name} » en cours…`, 'warning');
      const data = new FormData();
      data.append('file', file);
      const response = await rawFetch(`/api/import/preview?vehicle_id=${encodeURIComponent(document.querySelector('#vehicle-id')?.value || 'semi_trailer')}`, {method: 'POST', body: data});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(importError(file, response.status, body));

      const payload = body.payload || {};
      const sourceUnit = ['mm', 'm'].includes(payload.dimension_unit) ? payload.dimension_unit : 'mm';
      const sourceItems = Array.isArray(payload.items) ? payload.items : [];
      const tableBody = document.querySelector('#cargo-table tbody');
      if (!tableBody || typeof window.addRow !== 'function') throw new Error('Le tableau des marchandises n’est pas disponible.');
      tableBody.innerHTML = '';
      sourceItems.map(item => itemToMillimetres(item, sourceUnit)).forEach(item => window.addRow(item));
      prepareInputs(tableBody, 'mm');
      updateLabels();

      const sheet = payload._import_sheet ? ` depuis la feuille « ${payload._import_sheet} »` : '';
      const base = `${sourceItems.length} ligne(s) importée(s)${sheet}. ${body.expanded_items || sourceItems.length} objet(s) seront pris en compte après application des quantités.`;
      const missing = missingTotalData(sourceItems);
      if (missing.length) importMessage(`${base}\nImport accepté, mais l’optimisation totale nécessite encore : ${missing.join(' ; ')}.`, 'warning');
      else importMessage(`${base} Les dimensions sont affichées en ${currentUnit === 'm' ? 'mètres' : 'millimètres'}.`, 'success');
    } catch (error) {
      importMessage(error.message || String(error), 'error');
    } finally {
      input.value = '';
    }
  }

  function replaceImportInput() {
    const existing = document.querySelector('#import-file');
    if (!existing || existing.dataset.preciseImport === '1') return;
    const replacement = existing.cloneNode(true);
    replacement.dataset.preciseImport = '1';
    existing.replaceWith(replacement);
    replacement.addEventListener('change', () => handleImport(replacement));
  }

  const observer = new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType === Node.ELEMENT_NODE) prepareInputs(node, 'mm');
    }));
    updateLabels();
  });

  function init() {
    installSettingsCard();
    installImportHelp();
    replaceImportInput();
    prepareInputs(document, 'mm');
    ['#vehicle-table tbody', '#cargo-table tbody'].forEach(selector => {
      const target = document.querySelector(selector);
      if (target) observer.observe(target, {childList: true, subtree: true});
    });
    applyUnit(currentUnit, false);
  }

  window.AxioUnits = {
    current: () => currentUnit,
    apply: unit => applyUnit(unit),
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
