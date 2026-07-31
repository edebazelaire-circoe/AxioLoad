(() => {
  'use strict';

  const clientPalette = ['#007C91', '#E2743B', '#6A5ACD', '#2E8B57', '#B04A7A', '#A36B00', '#2474B5', '#7A5C3E'];
  const originalHexToRgba = typeof hexToRgba === 'function' ? hexToRgba : null;

  if (originalHexToRgba) {
    hexToRgba = function solidCargoColor(hex, alpha) {
      // Cargo faces used values between .82 and .92. They are now opaque,
      // while pale labels, grids and dimension backgrounds keep their transparency.
      return originalHexToRgba(hex, Number(alpha) >= 0.75 ? 1 : alpha);
    };
  }

  function currentSolution() {
    return state?.result?.solutions?.[state.selected] || null;
  }

  function clientColor(client, clients) {
    const index = Math.max(0, clients.indexOf(client));
    return clientPalette[index % clientPalette.length];
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
    section.innerHTML = `
      <div class="method-status-heading"><h3>État des méthodes de calcul</h3><p>Les méthodes valides restent consultables même lorsqu’une autre méthode n’a pas trouvé de plan.</p></div>
      <div class="method-status-list">
        ${successes.map(name => `<article class="method-status success"><strong>${escapeHtml(name)}</strong><span>Solution disponible</span></article>`).join('')}
        ${failures.map(failure => `<article class="method-status failure"><strong>${escapeHtml(failure.code || 'Méthode en échec')}</strong><span>${escapeHtml(failure.message || 'Aucun plan valide dans le temps imparti.')}</span></article>`).join('')}
        ${!successes.length && !failures.length ? '<article class="method-status failure"><strong>Aucune solution</strong><span>Aucune méthode n’a produit de plan exploitable. Vérifiez les dimensions, le poids, les règles de gerbage, les marges et la flotte disponible.</span></article>' : ''}
      </div>`;
  }

  function buildVehicleNavigator() {
    const solution = currentSolution();
    const diagnostics = document.querySelector('#diagnostics');
    if (!solution || !diagnostics) return;
    let nav = document.querySelector('#vehicle-result-navigator');
    if (!nav) {
      nav = document.createElement('section');
      nav.id = 'vehicle-result-navigator';
      nav.className = 'vehicle-result-navigator';
      diagnostics.parentNode.insertBefore(nav, diagnostics);
    }
    nav.innerHTML = `<h3>Véhicules de la solution</h3><div class="vehicle-nav-list">${solution.vehicle_plans.map((plan, index) => `
      <button type="button" class="vehicle-nav-item ${index === state.selectedVehicle ? 'active' : ''}" data-vehicle-index="${index}">
        <strong>Véhicule ${index + 1}</strong><span>${escapeHtml(plan.vehicle_name || 'Véhicule')}</span><small>${Number(plan.placements?.length || 0)} colis · ${Number(plan.weight?.total_weight_kg || 0).toLocaleString('fr-FR')} kg</small>
      </button>`).join('')}</div>`;
    nav.querySelectorAll('[data-vehicle-index]').forEach(button => button.addEventListener('click', () => {
      const index = Number(button.dataset.vehicleIndex);
      state.selectedVehicle = index;
      state.selectedPlacementId = null;
      const select = document.querySelector('#viewer-vehicle');
      if (select) select.value = String(index);
      renderResults();
    }));
  }

  function buildCargoManifest() {
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
    const allClients = [...new Set(solution.vehicle_plans.flatMap(plan => (plan.placements || []).map(p => p.destination || 'Client non renseigné')))];
    section.innerHTML = `<div class="manifest-heading"><div><h3>Contenu des véhicules</h3><p>Vue globale de la solution. Cliquez sur un véhicule pour l’afficher dans la vue 3D.</p></div><label>Filtrer<select id="manifest-vehicle-filter"><option value="all">Tous les véhicules</option>${solution.vehicle_plans.map((_, index) => `<option value="${index}" ${index === state.selectedVehicle ? 'selected' : ''}>Véhicule ${index + 1}</option>`).join('')}</select></label></div><div id="vehicle-overview-grid" class="vehicle-overview-grid"></div>`;
    const filter = section.querySelector('#manifest-vehicle-filter');
    filter.value = 'all';
    filter.addEventListener('change', () => {
      const value = filter.value;
      section.querySelectorAll('.vehicle-manifest-card').forEach(card => card.hidden = value !== 'all' && card.dataset.vehicleIndex !== value);
      if (value !== 'all') {
        state.selectedVehicle = Number(value);
        document.querySelector('#viewer-vehicle').value = value;
        renderResults();
      }
    });
    const overview = section.querySelector('#vehicle-overview-grid');
    solution.vehicle_plans.forEach((plan, index) => {
      const rows = plan.placements || [];
      const totalWeight = rows.reduce((sum, row) => sum + Number(row.weight_kg || 0), 0);
      const stacked = rows.filter(row => Number(row.z_mm || 0) > 0).length;
      const card = document.createElement('article');
      card.className = `vehicle-manifest-card ${index === state.selectedVehicle ? 'active' : ''}`;
      card.dataset.vehicleIndex = String(index);
      card.innerHTML = `<button class="manifest-focus" type="button"><strong>Véhicule ${index + 1} · ${escapeHtml(plan.vehicle_name || '')}</strong><span>${rows.length} colis · ${totalWeight.toLocaleString('fr-FR', {maximumFractionDigits:1})} kg · ${stacked} gerbé(s)</span></button>
        <div class="client-legend">${[...new Set(rows.map(row => row.destination || 'Client non renseigné'))].map(client => `<span><i style="background:${clientColor(client, allClients)}"></i>${escapeHtml(client)}</span>`).join('')}</div>
        <div class="manifest-table-wrap"><table><thead><tr><th>Référence</th><th>Client</th><th>Dimensions</th><th>Poids</th><th>Gerbé</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(row.item_id || row.source_id || '')}</td><td><i class="client-dot" style="background:${clientColor(row.destination || 'Client non renseigné', allClients)}"></i>${escapeHtml(row.destination || '')}</td><td>${row.actual_length_mm} × ${row.actual_width_mm} × ${row.actual_height_mm} mm</td><td>${Number(row.weight_kg || 0).toLocaleString('fr-FR')} kg</td><td>${Number(row.z_mm || 0) > 0 ? 'Oui' : 'Non'}</td></tr>`).join('')}</tbody></table></div>`;
      card.querySelector('.manifest-focus').addEventListener('click', () => {
        state.selectedVehicle = index;
        state.selectedPlacementId = null;
        document.querySelector('#viewer-vehicle').value = String(index);
        renderResults();
      });
      overview.append(card);
    });
    buildVehicleThumbnails();
  }

  async function buildVehicleThumbnails() {
    const solution = currentSolution();
    const canvas = document.querySelector('#viewer');
    if (!solution || !canvas || solution.vehicle_plans.length < 2) return;
    const previous = state.selectedVehicle;
    const cards = [...document.querySelectorAll('.vehicle-manifest-card')];
    for (let index = 0; index < solution.vehicle_plans.length; index += 1) {
      state.selectedVehicle = index;
      drawViewer();
      await waitFrame();
      const image = document.createElement('img');
      image.className = 'vehicle-thumbnail';
      image.alt = `Plan 3D du véhicule ${index + 1}`;
      image.src = canvas.toDataURL('image/png');
      cards[index]?.querySelector('.manifest-focus')?.insertAdjacentElement('afterend', image);
    }
    state.selectedVehicle = previous;
    drawViewer();
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
      const imageDataUrl = await captureFleetSheet();
      const response = await fetch(`/api/history/${encodeURIComponent(state.result.run_id)}/export-operational.pdf`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          image_data_url: imageDataUrl,
          solution_index: state.selected,
          vehicle_index: state.selectedVehicle,
          displayed_metrics: {},
        }),
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

  function renderNoSolution() {
    if (!state?.result || state.result.solutions?.length) return;
    document.querySelector('#empty-results')?.classList.remove('hidden');
    const empty = document.querySelector('#empty-results');
    if (empty) empty.innerHTML = '<strong>Aucune modélisation exploitable.</strong><br>Les méthodes testées n’ont pas trouvé de chargement valide. Vérifiez les dimensions, le poids, la hauteur gerbée, les marges, les incompatibilités et le nombre de véhicules disponibles.';
    buildMethodStatus();
  }

  function appendRoutingConstraintNotice() {
    const note = document.querySelector('#total-model-note');
    if (!note || note.dataset.truckRestrictionNotice === '1') return;
    note.dataset.truckRestrictionNotice = '1';
    const paragraph = document.createElement('p');
    paragraph.className = 'truck-routing-warning';
    paragraph.innerHTML = '<strong>Contraintes routières poids lourd :</strong> le service OSRM public actuel utilise un profil routier générique. Les hauteurs de pont, tonnages, largeurs, interdictions poids lourd et restrictions locales ne sont donc pas garantis. Lorsqu’aucun moteur poids lourd n’est connecté, AxioLoad affiche cette limite au lieu de présenter l’itinéraire comme validé pour le camion.';
    note.append(paragraph);
  }

  const originalRenderResults = typeof renderResults === 'function' ? renderResults : null;
  if (originalRenderResults) {
    renderResults = function enhancedRenderResults() {
      originalRenderResults();
      renderNoSolution();
      buildMethodStatus();
      buildVehicleNavigator();
      buildCargoManifest();
    };
  }

  const observer = new MutationObserver(() => {
    if (document.querySelector('#total-results:not(.hidden)')) appendRoutingConstraintNotice();
  });
  const totalRoot = document.querySelector('#tab-total');
  if (totalRoot) observer.observe(totalRoot, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});

  document.querySelectorAll('.version-badge').forEach(badge => {
    if (badge.textContent.toLowerCase().includes('global')) badge.remove();
  });
  const footer = document.querySelector('footer');
  if (footer) footer.remove();
})();
