(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  const icon = name => {
    const paths = {
      upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
      file: '<path d="M6 2h8l4 4v16H6zM14 2v5h5M9 12h6M9 16h6"/>',
      plus: '<path d="M12 5v14M5 12h14"/>',
      duplicate: '<path d="M8 8h11v11H8zM5 16H3V3h13v2"/>',
      calculate: '<path d="M5 4h14v16H5zM8 8h8M8 12h3M13 12h3M8 16h3M13 16h3"/>',
      clock: '<path d="M12 3a9 9 0 1 0 9 9M12 7v5l3 2"/>',
      check: '<path d="m5 12 4 4L19 6"/>',
      error: '<path d="M12 3 2 21h20zM12 9v5M12 18h.01"/>',
      experiment: '<path d="M9 3h6M10 3v5l-5 9a3 3 0 0 0 2.6 4h8.8a3 3 0 0 0 2.6-4l-5-9V3M8 15h8"/>'
    };
    return `<span class="opx-icon"><svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.check}</svg></span>`;
  };

  function distinguishWorkspaces() {
    const optimization = q('[data-workspace="optimization"]');
    const documents = q('[data-workspace="documents"]');
    optimization?.classList.add('workspace-optimization');
    documents?.classList.add('workspace-documents');
  }

  function removeLockedLabels(root = document) {
    qa('.vehicle-origin-badge, .global-lock-badge, [data-global-lock]', root).forEach(element => element.remove());
    qa('span, small, em, strong, div', root).forEach(element => {
      if (element.children.length) return;
      const text = element.textContent.trim().toLocaleLowerCase('fr');
      if (text === 'global verrouillé' || text === 'global verrouille') element.remove();
    });
  }

  function setButtonContent(element, iconName, label) {
    if (!element) return;
    element.innerHTML = `${icon(iconName)}<span>${escapeHtml(label)}</span>`;
  }

  function polishImportActions() {
    const box = q('#tab-data .import-box');
    if (!box || box.dataset.opxReady === '1') return;
    box.dataset.opxReady = '1';
    box.classList.add('opx-import-actions');

    q('#import-format-help')?.remove();
    qa('small, p', box).forEach(element => {
      if (element.textContent.includes('Formats acceptés')) element.remove();
    });
    [...box.childNodes].forEach(node => {
      if (node.nodeType === Node.TEXT_NODE && node.textContent.includes('Formats acceptés')) node.remove();
    });

    const importer = q('.file-button', box);
    const csv = [...box.querySelectorAll('a')].find(link => link.href.includes('import-template.csv'));
    const excel = q('#download-excel-template', box) || [...box.querySelectorAll('a')].find(link => link.href.includes('template.xlsx'));
    setButtonContent(importer, 'upload', 'Importer CSV/XLSX');
    setButtonContent(csv, 'file', 'Modèle CSV');
    setButtonContent(excel, 'file', 'Modèle Excel AxioLoad');
    if (excel) excel.setAttribute('title', 'Télécharger le modèle Excel AxioLoad');
  }

  function normalizeBudgetSelect(select) {
    if (!select) return;
    const current = ['5', '15', '30', '60'].includes(select.value) ? select.value : '30';
    select.innerHTML = [5, 15, 30, 60]
      .map(value => `<option value="${value}" ${String(value) === current ? 'selected' : ''}>${value} s</option>`)
      .join('');
    select.value = current;
  }

  function arrangeLoadingActions() {
    const panel = q('#tab-data');
    const actions = q('.form-actions', panel);
    const add = q('#add-row', panel);
    const duplicate = q('#duplicate-row', panel);
    const optimize = q('#optimize', panel);
    const budgetLabel = q('#budget-seconds', panel)?.closest('label');
    if (!actions || !add || !duplicate || !optimize || !budgetLabel) return;

    actions.classList.add('opx-loading-actions');
    if (add.parentElement !== actions) actions.append(add);
    if (duplicate.parentElement !== actions) actions.append(duplicate);
    if (optimize.parentElement !== actions) actions.append(optimize);
    actions.append(add, duplicate, optimize);

    setButtonContent(add, 'plus', 'Ajouter une ligne');
    setButtonContent(duplicate, 'duplicate', 'Dupliquer la dernière');
    setButtonContent(optimize, 'calculate', 'Optimiser le chargement');

    normalizeBudgetSelect(q('#budget-seconds', panel));
    let budgetRow = q('#opx-budget-row', panel);
    if (!budgetRow) {
      budgetRow = document.createElement('div');
      budgetRow.id = 'opx-budget-row';
      budgetRow.className = 'opx-budget-row';
      actions.after(budgetRow);
    }
    budgetLabel.classList.add('opx-budget-control');
    const labelText = q('.field-label', budgetLabel) || q('span', budgetLabel);
    if (labelText) labelText.innerHTML = `${icon('clock')}<span>Temps de calcul</span>`;
    budgetRow.append(budgetLabel);

    qa('.calculation-toolbar', panel).forEach(toolbar => {
      if (!toolbar.children.length) toolbar.remove();
    });
  }

  function prepareClientGroups() {
    qa('#cargo-table tbody tr').forEach(row => {
      const destination = q('[data-k="destination"]', row)?.value.trim();
      const group = q('[data-k="keep_together_group"]', row);
      if (destination && group && !group.value.trim()) {
        group.value = `CLIENT::${destination.toLocaleLowerCase('fr').replace(/\s+/g, '_')}`;
      }
    });
  }

  const statusLabels = {
    success: 'Réussi', failure: 'Échec', timeout: 'Temps atteint', not_run: 'Non lancé'
  };

  function formatMetric(value, suffix = '') {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'Non disponible';
    return `${Number(value).toLocaleString('fr-FR', {maximumFractionDigits: 2})}${suffix}`;
  }

  function outcomeCard(outcome) {
    const status = outcome.status || 'failure';
    const experimental = outcome.execution_mode === 'experimental';
    const iconName = status === 'success' ? (experimental ? 'experiment' : 'check') : 'error';
    const reason = outcome.reason || (status === 'success' ? 'Plan valide produit.' : 'Aucun résultat exploitable.');
    return `
      <article class="opx-model-card status-${escapeHtml(status)}" data-method="${escapeHtml(outcome.code)}">
        <header>
          <span class="opx-model-number">${outcome.index}</span>
          <span class="opx-model-heading">
            <strong>${escapeHtml(outcome.name)}</strong>
            <small>${escapeHtml(outcome.short_label || '')}</small>
          </span>
          <span class="opx-model-status">${icon(iconName)}${escapeHtml(statusLabels[status] || status)}</span>
        </header>
        <p>${escapeHtml(reason)}</p>
        <div class="opx-model-metrics">
          <span><small>Temps</small><strong>${formatMetric(outcome.elapsed_seconds, ' s')}</strong></span>
          <span><small>Véhicules</small><strong>${formatMetric(outcome.vehicle_count)}</strong></span>
          <span><small>Longueur</small><strong>${formatMetric(outcome.occupied_length_m, ' m')}</strong></span>
          <span><small>Équilibre</small><strong>${formatMetric(outcome.balance_penalty)}</strong></span>
        </div>
        <details>
          <summary>Principe et niveau de maturité</summary>
          <p>${escapeHtml(outcome.description || '')}</p>
          <p class="opx-model-note">${escapeHtml(outcome.execution_note || '')}</p>
        </details>
      </article>`;
  }

  function renderMethodOutcomes(data) {
    const outcomes = Array.isArray(data?.method_outcomes) ? data.method_outcomes : [];
    if (!outcomes.length) return;
    const content = q('#results-content');
    const solutions = q('#solution-cards');
    if (!content || !solutions) return;
    let section = q('#opx-method-portfolio', content);
    if (!section) {
      section = document.createElement('section');
      section.id = 'opx-method-portfolio';
      section.className = 'opx-method-portfolio';
      solutions.before(section);
    }
    const successes = outcomes.filter(outcome => outcome.status === 'success').length;
    section.innerHTML = `
      <div class="opx-portfolio-heading">
        <div><span>Portefeuille indépendant</span><h3>Résultat des cinq modèles</h3></div>
        <strong>${successes}/5 modèles avec un plan</strong>
      </div>
      <p class="opx-portfolio-intro">Chaque modèle est exécuté séparément. Un échec ou un dépassement de temps n'interrompt jamais les autres calculs.</p>
      <div class="opx-model-grid">${outcomes.map(outcomeCard).join('')}</div>`;
  }

  function installResultCapture() {
    if (window.__axioloadOptimizationExperienceFetch) return;
    window.__axioloadOptimizationExperienceFetch = true;
    const previous = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const response = await previous(input, init);
      const url = typeof input === 'string' ? input : input?.url || '';
      if (response.ok && url.includes('/local/optimize')) {
        response.clone().json().then(data => {
          window.setTimeout(() => renderMethodOutcomes(data), 0);
        }).catch(() => {});
      }
      return response;
    };
  }

  function bindClientGrouping() {
    const optimize = q('#optimize');
    if (!optimize || optimize.dataset.opxClientGrouping === '1') return;
    optimize.dataset.opxClientGrouping = '1';
    optimize.addEventListener('click', prepareClientGroups, {capture: true});
  }

  function apply() {
    distinguishWorkspaces();
    removeLockedLabels();
    polishImportActions();
    arrangeLoadingActions();
    bindClientGrouping();
  }

  function init() {
    installResultCapture();
    apply();
    let scheduled = false;
    new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        apply();
      });
    }).observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
