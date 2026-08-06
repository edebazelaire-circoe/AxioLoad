(() => {
  'use strict';

  const STORAGE_KEY = 'logipilot.results.modelsExpanded';
  let observer = null;

  function removeLegacyStatusPanel() {
    document.querySelector('#method-status-panel')?.remove();
  }

  function readExpandedState() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === 'true';
    } catch (_) {
      return false;
    }
  }

  function storeExpandedState(expanded) {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(expanded));
    } catch (_) {
      // The control remains functional if browser storage is unavailable.
    }
  }

  function applyExpandedState(section, expanded) {
    const modelRow = section.querySelector('#opx-model-row');
    const modelLabel = modelRow?.previousElementSibling;
    const toggle = section.querySelector('[data-results-model-toggle]');
    if (!modelRow || !toggle) return;

    modelRow.hidden = !expanded;
    if (modelLabel?.classList.contains('opx-row-label')) modelLabel.hidden = !expanded;
    section.classList.toggle('models-expanded', expanded);
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.querySelector('span').textContent = expanded ? 'Masquer les modèles' : 'Voir le détail des modèles';
  }

  function enhancePortfolio() {
    removeLegacyStatusPanel();
    const section = document.querySelector('#opx-method-portfolio');
    if (!section || section.dataset.compactResultsReady === '1') return;

    const heading = section.querySelector('.opx-portfolio-heading');
    const title = heading?.querySelector('h3');
    const intro = section.querySelector('.opx-portfolio-intro');
    const modelRow = section.querySelector('#opx-model-row');
    if (!heading || !title || !intro || !modelRow) return;

    section.dataset.compactResultsReady = '1';
    title.insertAdjacentHTML(
      'afterend',
      '<p class="opx-portfolio-summary">Cinq modèles indépendants, cinq réponses comparables sur le même cas.</p>'
    );
    intro.textContent = 'Chaque solution reste alignée avec le modèle qui l’a produite. Un échec conserve son emplacement afin de rendre la comparaison immédiate.';

    const actions = document.createElement('div');
    actions.className = 'opx-portfolio-actions';
    const count = heading.querySelector('#ovr-success-count');
    if (count) actions.append(count);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'opx-model-toggle';
    toggle.dataset.resultsModelToggle = '1';
    toggle.setAttribute('aria-controls', 'opx-model-row');
    toggle.innerHTML = '<span>Voir le détail des modèles</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>';
    actions.append(toggle);
    heading.append(actions);

    const expanded = readExpandedState();
    applyExpandedState(section, expanded);
    toggle.addEventListener('click', () => {
      const next = toggle.getAttribute('aria-expanded') !== 'true';
      applyExpandedState(section, next);
      storeExpandedState(next);
    });
  }

  function run() {
    removeLegacyStatusPanel();
    enhancePortfolio();
  }

  function init() {
    run();
    const root = document.querySelector('#results-content') || document.body;
    observer = new MutationObserver(run);
    observer.observe(root, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
