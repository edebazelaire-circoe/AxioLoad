(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  const statusLabels = {
    success: 'Réussi',
    failure: 'Échec',
    timeout: 'Temps atteint',
    not_run: 'Non lancé'
  };

  let latestResult = null;
  let arranging = false;
  let solutionObserver = null;

  const icon = status => {
    const path = status === 'success'
      ? '<path d="m5 12 4 4L19 6"/>'
      : '<path d="M12 3 2 21h20zM12 9v5M12 18h.01"/>';
    return `<span class="ovr-icon"><svg viewBox="0 0 24 24" aria-hidden="true">${path}</svg></span>`;
  };

  const formatMetric = (value, suffix = '') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'Non disponible';
    return `${Number(value).toLocaleString('fr-FR', {maximumFractionDigits: 2})}${suffix}`;
  };

  function normalizedOutcome(solution, index) {
    return {
      index: index + 1,
      code: solution?.method_code || `solution-${index + 1}`,
      name: solution?.method_name || `Méthode ${index + 1}`,
      short_label: 'Solution disponible',
      description: solution?.method_description || '',
      execution_note: '',
      status: 'success',
      elapsed_seconds: null,
      vehicle_count: solution?.vehicle_count,
      occupied_length_m: solution?.occupied_length_m,
      balance_penalty: solution?.balance_penalty,
      reason: 'Une solution valide a été produite par ce modèle.'
    };
  }

  function outcomeCard(outcome) {
    const status = outcome.status || 'failure';
    const reason = outcome.reason || (status === 'success'
      ? 'Une solution valide a été produite.'
      : 'Aucune solution exploitable n’a été produite.');
    return `<article class="opx-model-card ovr-model-card status-${escapeHtml(status)}" data-method="${escapeHtml(outcome.code || '')}">
      <header>
        <span class="opx-model-number">${escapeHtml(outcome.index || '')}</span>
        <span class="opx-model-heading">
          <strong>${escapeHtml(outcome.name || outcome.code || 'Modèle')}</strong>
          <small>${escapeHtml(outcome.short_label || '')}</small>
        </span>
        <span class="opx-model-status">${icon(status)}${escapeHtml(statusLabels[status] || status)}</span>
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

  function ensurePortfolio() {
    const content = q('#results-content');
    const source = q('#solution-cards');
    if (!content || !source) return null;

    let section = q('#opx-method-portfolio', content);
    if (!section) {
      section = document.createElement('section');
      section.id = 'opx-method-portfolio';
      source.before(section);
    }
    section.className = 'opx-method-portfolio opx-aligned-portfolio';
    section.innerHTML = `<div class="opx-portfolio-heading">
      <div><span>Comparaison alignée</span><h3>Résultat des cinq modèles</h3></div>
      <strong id="ovr-success-count"></strong>
    </div>
    <p class="opx-portfolio-intro">Les cinq modèles restent dans le premier bloc. Le second bloc contient cinq emplacements strictement alignés : une solution exploitable ou l’échec du modèle correspondant.</p>
    <p class="opx-mobile-scroll-hint">Balayez horizontalement pour comparer les cinq colonnes.</p>
    <div class="opx-comparison-scroll" role="region" aria-label="Comparaison des cinq modèles et de leurs solutions" tabindex="0">
      <div class="opx-comparison-board">
        <div class="opx-row-label">Modèles d’optimisation</div>
        <div id="opx-model-row" class="opx-five-column-row opx-model-row"></div>
        <div class="opx-row-label">Solutions correspondantes</div>
        <div id="opx-solution-row" class="opx-five-column-row opx-solution-row"></div>
      </div>
    </div>`;
    return section;
  }

  function buildSolutionCell(outcome, solution, card) {
    const cell = document.createElement('article');
    cell.className = 'opx-solution-cell has-solution';
    cell.dataset.method = outcome.code || solution.method_code || '';
    cell.innerHTML = `<div class="opx-solution-cell-label"><span>Modèle ${escapeHtml(outcome.index || '')}</span><strong>Solution ${escapeHtml(solution.rank || '')}</strong></div><div class="opx-solution-slot"></div>`;
    card.dataset.method = solution.method_code || outcome.code || '';
    card.dataset.solutionRank = String(solution.rank || '');
    q('.opx-solution-slot', cell).append(card);
    return cell;
  }

  function buildFailureCell(outcome) {
    const status = outcome.status || 'failure';
    const reason = outcome.reason || (status === 'timeout'
      ? 'Le temps de calcul disponible a été atteint.'
      : 'Ce modèle n’a pas produit de plan valide.');
    const cell = document.createElement('article');
    cell.className = `opx-solution-cell without-solution status-${escapeHtml(status)}`;
    cell.dataset.method = outcome.code || '';
    cell.innerHTML = `<div class="opx-solution-cell-label"><span>Modèle ${escapeHtml(outcome.index || '')}</span><strong>${escapeHtml(statusLabels[status] || status)}</strong></div><div class="opx-no-solution"><span class="opx-failure-icon">${icon(status)}</span><strong>Aucune solution disponible</strong><p>${escapeHtml(reason)}</p></div>`;
    return cell;
  }

  function orderedOutcomes(solutions, outcomes) {
    if (outcomes.length) {
      return [...outcomes].sort((left, right) => Number(left.index || 0) - Number(right.index || 0));
    }
    return solutions.map(normalizedOutcome);
  }

  function arrangeSolutions() {
    if (arranging || !latestResult) return false;
    const source = q('#solution-cards');
    if (!source) return false;

    const sourceCards = qa(':scope > .solution-card', source);
    const alreadyMovedCards = qa('#opx-solution-row .solution-card');
    const cards = sourceCards.length ? sourceCards : alreadyMovedCards;
    const solutions = Array.isArray(latestResult.solutions) ? latestResult.solutions : [];
    const outcomes = Array.isArray(latestResult.method_outcomes) ? latestResult.method_outcomes : [];
    if (cards.length < solutions.length) return false;

    arranging = true;
    try {
      const section = ensurePortfolio();
      if (!section) return false;
      const modelRow = q('#opx-model-row', section);
      const solutionRow = q('#opx-solution-row', section);
      const ordered = orderedOutcomes(solutions, outcomes);
      const entries = solutions.map((solution, index) => ({solution, card: cards[index]}));
      const entriesByMethod = new Map(entries.map(entry => [entry.solution.method_code, entry]));
      const usedEntries = new Set();

      modelRow.innerHTML = ordered.map(outcomeCard).join('');
      solutionRow.innerHTML = '';

      ordered.forEach(outcome => {
        let entry = entriesByMethod.get(outcome.code);
        if (!entry && outcome.status === 'success') {
          entry = entries.find(candidate => !usedEntries.has(candidate));
        }
        if (entry && entry.card) {
          usedEntries.add(entry);
          solutionRow.append(buildSolutionCell(outcome, entry.solution, entry.card));
        } else {
          solutionRow.append(buildFailureCell(outcome));
        }
      });

      const successCount = ordered.filter(outcome => outcome.status === 'success').length || solutions.length;
      const count = q('#ovr-success-count', section);
      if (count) count.textContent = `${successCount}/${ordered.length || solutions.length} modèles avec un plan`;
      source.classList.add('opx-source-solution-cards');
      return true;
    } finally {
      arranging = false;
    }
  }

  function rememberResult(data) {
    if (!Array.isArray(data?.solutions) || !Array.isArray(data?.method_outcomes)) return;
    latestResult = data;
    [0, 30, 100].forEach(delay => window.setTimeout(arrangeSolutions, delay));
  }

  function installFetchCapture() {
    if (window.__axioloadVerticalResultsFetch) return;
    window.__axioloadVerticalResultsFetch = true;
    const previous = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const response = await previous(input, init);
      const url = typeof input === 'string' ? input : input?.url || '';
      if (response.ok && (url.includes('/local/optimize') || url.includes('/api/history/'))) {
        response.clone().json().then(rememberResult).catch(() => {});
      }
      return response;
    };
  }

  function observeSolutionCards() {
    const source = q('#solution-cards');
    if (!source || solutionObserver) return Boolean(source);
    solutionObserver = new MutationObserver(records => {
      const addedCard = records.some(record => [...record.addedNodes].some(node => node.nodeType === Node.ELEMENT_NODE && (node.matches?.('.solution-card') || node.querySelector?.('.solution-card'))));
      if (addedCard) window.setTimeout(arrangeSolutions, 0);
    });
    solutionObserver.observe(source, {childList: true});
    return true;
  }

  function init() {
    installFetchCapture();
    [0, 50, 200, 700].forEach(delay => window.setTimeout(observeSolutionCards, delay));
  }

  window.AxioVerticalResults = {
    render(data) {
      rememberResult(data);
    },
    arrange: arrangeSolutions
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
