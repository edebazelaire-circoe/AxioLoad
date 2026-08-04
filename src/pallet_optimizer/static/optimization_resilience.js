(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];

  function arrangeCalculationActions() {
    const panel = q('#tab-data');
    const actions = q('.form-actions', panel || document);
    const add = q('#add-row', panel || document);
    const duplicate = q('#duplicate-row', panel || document);
    const optimize = q('#optimize', panel || document);
    const budget = q('#budget-seconds', panel || document)?.closest('label');
    if (!panel || !actions || !add || !duplicate || !optimize || !budget) return false;

    actions.classList.add('opx-resilient-actions');
    budget.classList.add('opx-resilient-budget');
    actions.append(add, duplicate, budget, optimize);

    const oldBudgetRow = q('#opx-budget-row', panel);
    if (oldBudgetRow && !oldBudgetRow.children.length) oldBudgetRow.remove();
    return true;
  }

  function resultNotice(data) {
    const outcomes = Array.isArray(data?.method_outcomes) ? data.method_outcomes : [];
    const solutions = Array.isArray(data?.solutions) ? data.solutions : [];
    if (!solutions.length || !outcomes.length) return;

    const successes = outcomes.filter(outcome => outcome.status === 'success');
    const incomplete = outcomes.filter(outcome => ['failure', 'timeout', 'not_run'].includes(outcome.status));
    if (!incomplete.length) return;

    const content = q('#results-content');
    if (!content) return;
    let notice = q('#opx-partial-success-notice', content);
    if (!notice) {
      notice = document.createElement('div');
      notice.id = 'opx-partial-success-notice';
      notice.className = 'opx-partial-success-notice';
      content.prepend(notice);
    }
    notice.innerHTML = `<strong>Résultat disponible</strong><span>${successes.length} modèle(s) ont produit une solution valide. Les ${incomplete.length} autre(s) calcul(s) n'ont pas abouti, sans annuler le meilleur plan retenu.</span>`;
  }

  function installResultCapture() {
    if (window.__axioloadOptimizationResilienceFetch) return;
    window.__axioloadOptimizationResilienceFetch = true;
    const previous = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const response = await previous(input, init);
      const url = typeof input === 'string' ? input : input?.url || '';
      if (response.ok && url.includes('/local/optimize')) {
        response.clone().json().then(data => {
          if (Array.isArray(data?.solutions) && data.solutions.length) {
            const errorBox = q('#data-errors');
            if (errorBox) {
              errorBox.textContent = '';
              errorBox.classList.add('hidden');
            }
            window.setTimeout(() => resultNotice(data), 0);
          }
        }).catch(() => {});
      }
      return response;
    };
  }

  function init() {
    installResultCapture();
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(arrangeCalculationActions, delay));

    const panel = q('#tab-data');
    if (panel && panel.dataset.opxResilienceObserver !== '1') {
      panel.dataset.opxResilienceObserver = '1';
      const observer = new MutationObserver(() => arrangeCalculationActions());
      observer.observe(panel, {childList: true, subtree: true});
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
