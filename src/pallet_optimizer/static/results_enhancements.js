(() => {
  'use strict';

  const originalHexToRgba = typeof hexToRgba === 'function' ? hexToRgba : null;
  if (originalHexToRgba) {
    hexToRgba = function solidCargoColor(hex, alpha) {
      return originalHexToRgba(hex, Number(alpha) >= 0.5 ? 1 : alpha);
    };
  }

  function currentSolution() {
    return state?.result?.solutions?.[state.selected] || null;
  }

  function waitFrame() {
    return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function addSixtySecondOptions() {
    ['#time-limit', '#route-time-limit', '#total-time-limit'].forEach(selector => {
      const select = document.querySelector(selector);
      if (!select || [...select.options].some(option => option.value === '60')) return;
      const option = document.createElement('option');
      option.value = '60';
      option.textContent = '60 s';
      select.append(option);
    });
  }

  function buildMethodStatus() {
    const host = document.querySelector('#results-content');
    if (!host || !state?.result) return;
    let section = document.querySelector('#method-status-panel');
    if (!section) {
      section = document.createElement('section');
      section.id = 'method-status-panel';
      section.className = 'method-status-panel';
      host.insertBefore(section, host.querySelector('.decision-panel') || host.firstChild);
    }
    const successes = [...new Set((state.result.solutions || []).map(solution => solution.method_name || solution.method_code || 'Méthode historique'))];
    const failures = (state.result.diagnostics || []).filter(diagnostic => String(diagnostic.code || '').includes('METHOD_NO_SOLUTION'));
    section.innerHTML = `<div class="method-status-heading"><h3>État des méthodes de calcul</h3><p>Une méthode en échec ne masque jamais les solutions produites par les autres méthodes.</p></div><div class="method-status-list">${successes.map(name => `<article class="method-status success"><strong>${escapeHtml(name)}</strong><span>Solution disponible</span></article>`).join('')}${failures.map(failure => `<article class="method-status failure"><strong>${escapeHtml(failure.code || 'Méthode en échec')}</strong><span>${escapeHtml(failure.message || 'Aucun plan valide dans le temps imparti.')}</span></article>`).join('')}${!successes.length ? '<article class="method-status failure"><strong>Aucune solution</strong><span>Aucune méthode n’a produit de chargement exploitable. Vérifiez les dimensions, le poids, le gerbage, les marges, les clients et la flotte disponible.</span></article>' : ''}</div>`;
  }

  function vehicleIndexForDiagnostic(diagnostic, solution) {
    const text = `${diagnostic?.message || ''} ${diagnostic?.field_path || ''}`;
    const ids = [...text.matchAll(/[A-Za-z0-9_-]+(?:#[0-9]+)?/g)].map(match => match[0]);
    return solution.vehicle_plans.findIndex(plan => (plan.placements || []).some(placement => ids.includes(String(placement.item_id)) || ids.includes(String(placement.source_id))));
  }

  function makeDiagnosticsClickable() {
    const solution = currentSolution();
    const host = document.querySelector('#diagnostics');
    if (!solution || !host) return;
    const diagnostics = [...(state.result?.diagnostics || []), ...(solution.diagnostics || [])];
    [...host.querySelectorAll('.diag')].forEach((node, index) => {
      const diagnostic = diagnostics[index];
      const vehicleIndex = vehicleIndexForDiagnostic(diagnostic, solution);
      if (vehicleIndex < 0 || node.dataset.vehicleLinkReady === '1') return;
      node.dataset.vehicleLinkReady = '1';
      node.classList.add('diag-clickable');
      node.tabIndex = 0;
      node.setAttribute('role', 'button');
      node.title = `Afficher le véhicule ${vehicleIndex + 1}`;
      const focus = () => {
        state.selectedVehicle = vehicleIndex;
        state.selectedPlacementId = null;
        const select = document.querySelector('#viewer-vehicle');
        if (select) select.value = String(vehicleIndex);
        renderResults();
      };
      node.addEventListener('click', focus);
      node.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          focus();
        }
      });
    });
  }

  function arrangeResultWorkflow() {
    const host = document.querySelector('#results-content');
    if (!host) return;

    const decision = host.querySelector('.decision-panel');
    if (decision) {
      decision.classList.add('decision-panel-compact');
      if (host.lastElementChild !== decision) host.append(decision);
    }

    const inspector = host.querySelector('.inspection-card');
    if (!inspector) return;
    inspector.classList.add('inspection-card-refined');

    const headings = [...inspector.querySelectorAll(':scope > h3')];
    const diagnosticsHeading = headings.find(heading => heading.textContent.trim() === 'Diagnostics');
    const exportsHeading = headings.find(heading => heading.textContent.trim() === 'Exports opérationnels');
    const diagnostics = inspector.querySelector('#diagnostics');
    const exports = inspector.querySelector('#exports');
    const exportNote = inspector.querySelector('.export-note');

    diagnosticsHeading?.classList.add('inspection-secondary-heading');
    exportsHeading?.classList.add('inspection-exports-heading');
    exports?.classList.add('inspection-exports-actions');
    exportNote?.classList.add('inspection-exports-note');

    if (diagnosticsHeading && diagnostics && !inspector.querySelector('[data-diagnostics-toggle]')) {
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'diagnostics-toggle';
      toggle.dataset.diagnosticsToggle = '1';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-controls', 'diagnostics');
      toggle.textContent = 'Afficher les informations techniques';
      diagnosticsHeading.insertAdjacentElement('afterend', toggle);
      diagnostics.classList.add('diagnostics-collapsed');
      toggle.addEventListener('click', () => {
        const expanded = toggle.getAttribute('aria-expanded') !== 'true';
        toggle.setAttribute('aria-expanded', String(expanded));
        diagnostics.classList.toggle('diagnostics-collapsed', !expanded);
        toggle.textContent = expanded
          ? 'Masquer les informations techniques'
          : 'Afficher les informations techniques';
      });
    }
  }

  function buildCargoAccordion() {
    const solution = currentSolution();
    const grid = document.querySelector('.viewer-grid');
    if (!solution || !grid) return;
    let section = document.querySelector('#vehicle-cargo-manifest');
    if (!section) {
      section = document.createElement('section');
      section.id = 'vehicle-cargo-manifest';
      section.className = 'vehicle-cargo-manifest';
      grid.insertAdjacentElement('afterend', section);
    }
    section.innerHTML = `<div class="manifest-heading"><div><h3>Contenu des véhicules</h3><p>Cliquez sur un en-tête pour afficher ce camion dans la vue 3D et ouvrir sa liste de palettes.</p></div></div><div class="vehicle-accordion"></div>`;
    const accordion = section.querySelector('.vehicle-accordion');
    solution.vehicle_plans.forEach((plan, index) => {
      const rows = plan.placements || [];
      const totalWeight = rows.reduce((sum, row) => sum + Number(row.weight_kg || 0), 0);
      const stacked = rows.filter(row => Number(row.z_mm || 0) > 0).length;
      const item = document.createElement('article');
      item.className = `vehicle-accordion-item ${index === state.selectedVehicle ? 'open' : ''}`;
      item.innerHTML = `<button class="vehicle-accordion-header" type="button" aria-expanded="${index === state.selectedVehicle}"><span><strong>Véhicule ${index + 1} · ${escapeHtml(plan.vehicle_name || '')}</strong><small>${rows.length} colis · ${totalWeight.toLocaleString('fr-FR', {maximumFractionDigits: 1})} kg · ${stacked} gerbé(s)</small></span><b aria-hidden="true">⌄</b></button><div class="vehicle-accordion-content"><table><thead><tr><th>Référence</th><th>Client</th><th>Dimensions</th><th>Poids</th><th>Gerbé</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(row.item_id || row.source_id || '')}</td><td>${escapeHtml(row.destination || '')}</td><td>${row.actual_length_mm} × ${row.actual_width_mm} × ${row.actual_height_mm} mm</td><td>${Number(row.weight_kg || 0).toLocaleString('fr-FR')} kg</td><td>${Number(row.z_mm || 0) > 0 ? 'Oui' : 'Non'}</td></tr>`).join('')}</tbody></table></div>`;
      item.querySelector('.vehicle-accordion-header').addEventListener('click', () => {
        state.selectedVehicle = index;
        state.selectedPlacementId = null;
        const select = document.querySelector('#viewer-vehicle');
        if (select) select.value = String(index);
        renderResults();
      });
      accordion.append(item);
    });
  }

  async function captureFleetSheet() {
    const solution = currentSolution();
    const viewer = document.querySelector('#viewer');
    if (!solution || !viewer) throw new Error('Aucun plan 3D disponible.');
    const previous = state.selectedVehicle;
    const captures = [];
    for (let index = 0; index < solution.vehicle_plans.length; index += 1) {
      state.selectedVehicle = index;
      drawViewer();
      await waitFrame();
      const image = new Image();
      image.src = viewer.toDataURL('image/png');
      await image.decode();
      captures.push(image);
    }
    state.selectedVehicle = previous;
    drawViewer();
    const width = 1200;
    const cellHeight = 520;
    const sheet = document.createElement('canvas');
    sheet.width = width;
    sheet.height = cellHeight * captures.length;
    const context = sheet.getContext('2d');
    context.fillStyle = '#FFFFFF';
    context.fillRect(0, 0, sheet.width, sheet.height);
    captures.forEach((image, index) => {
      context.fillStyle = '#063B5B';
      context.font = '700 24px Segoe UI, Arial, sans-serif';
      context.fillText(`Véhicule ${index + 1} · ${solution.vehicle_plans[index].vehicle_name || ''}`, 24, index * cellHeight + 34);
      context.drawImage(image, 20, index * cellHeight + 48, width - 40, cellHeight - 65);
    });
    return sheet.toDataURL('image/png');
  }

  exportOperationalPdf = async function exportFleetOperationalPdf(event) {
    event?.preventDefault();
    const link = document.querySelector('#export-operational-pdf');
    if (!state?.result?.run_id || !currentSolution()) return;
    const oldText = link?.textContent;
    if (link) { link.textContent = 'Préparation du PDF…'; link.setAttribute('aria-busy', 'true'); }
    try {
      const response = await fetch(`/api/history/${encodeURIComponent(state.result.run_id)}/export-operational.pdf`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({image_data_url: await captureFleetSheet(), solution_index: state.selected, vehicle_index: state.selectedVehicle, displayed_metrics: {}}),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || 'Le PDF n’a pas pu être généré.');
      }
      downloadBlob(await response.blob(), `axioload-plan-${state.result.run_id}.pdf`);
    } catch (error) {
      alert(error.message || String(error));
    } finally {
      if (link) { link.textContent = oldText || 'PDF opérationnel avec vue 3D'; link.removeAttribute('aria-busy'); }
    }
  };

  function appendRoutingConstraintNotice() {
    const note = document.querySelector('#total-model-note');
    if (!note || note.dataset.truckRestrictionNotice === '1') return;
    note.dataset.truckRestrictionNotice = '1';
    const paragraph = document.createElement('p');
    paragraph.className = 'truck-routing-warning';
    paragraph.innerHTML = '<strong>Contraintes routières poids lourd :</strong> le profil routier générique actuel ne garantit pas les hauteurs de pont, tonnages, largeurs, interdictions poids lourd et restrictions locales. AxioLoad signale cette limite tant qu’un moteur poids lourd spécialisé n’est pas connecté.';
    note.append(paragraph);
  }

  const originalRenderResults = typeof renderResults === 'function' ? renderResults : null;
  if (originalRenderResults) {
    renderResults = function enhancedRenderResults() {
      originalRenderResults();
      buildMethodStatus();
      makeDiagnosticsClickable();
      buildCargoAccordion();
      arrangeResultWorkflow();
      addSixtySecondOptions();
    };
  }

  const observer = new MutationObserver(() => {
    if (document.querySelector('#total-results:not(.hidden)')) appendRoutingConstraintNotice();
  });
  const totalRoot = document.querySelector('#tab-total');
  if (totalRoot) observer.observe(totalRoot, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});

  arrangeResultWorkflow();
  addSixtySecondOptions();
  document.querySelectorAll('.version-badge').forEach(badge => {
    if (badge.textContent.toLowerCase().includes('global')) badge.remove();
  });
  document.querySelector('footer')?.remove();
})();
