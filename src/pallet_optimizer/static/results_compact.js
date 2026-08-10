(() => {
  'use strict';

  let observer = null;

  function removeLegacyStatusPanel() {
    document.querySelector('#method-status-panel')?.remove();
  }

  function modelDetails(section) {
    return [...section.querySelectorAll('#opx-model-row .ovr-model-card details')];
  }

  function applyExpandedState(section, expanded) {
    const toggle = section.querySelector('[data-results-model-toggle]');
    if (!toggle) return;

    modelDetails(section).forEach(details => {
      if (details.open !== expanded) details.open = expanded;
    });
    section.classList.toggle('model-details-expanded', expanded);
    toggle.setAttribute('aria-expanded', String(expanded));
    const label = toggle.querySelector('span');
    const expected = expanded ? 'Masquer les détails des modèles' : 'Détails des modèles';
    if (label && label.textContent !== expected) label.textContent = expected;
  }

  function enhancePortfolio() {
    removeLegacyStatusPanel();
    const section = document.querySelector('#opx-method-portfolio');
    if (!section) return;

    const heading = section.querySelector('.opx-portfolio-heading');
    const title = heading?.querySelector('h3');
    const intro = section.querySelector('.opx-portfolio-intro');
    const modelRow = section.querySelector('#opx-model-row');
    const solutionRow = section.querySelector('#opx-solution-row');
    if (!heading || !title || !intro || !modelRow || !solutionRow) return;

    modelRow.hidden = false;
    [...modelRow.children].forEach(card => { card.hidden = false; });
    const modelLabel = modelRow.previousElementSibling;
    if (modelLabel?.classList.contains('opx-row-label')) modelLabel.hidden = false;

    let summary = section.querySelector('.opx-portfolio-summary');
    if (!summary) {
      summary = document.createElement('p');
      summary.className = 'opx-portfolio-summary';
      summary.textContent = 'Cinq modèles indépendants, cinq résultats comparables sur le même cas.';
      title.insertAdjacentElement('afterend', summary);
    }

    const introText = 'Les cartes du haut résument les cinq modèles. Les informations techniques restent masquées jusqu’à l’ouverture des détails.';
    if (intro.textContent !== introText) intro.textContent = introText;

    let footer = section.querySelector('.opx-model-details-footer');
    if (!footer) {
      footer = document.createElement('div');
      footer.className = 'opx-model-details-footer';
      modelRow.insertAdjacentElement('afterend', footer);
    }

    let toggle = footer.querySelector('[data-results-model-toggle]');
    if (!toggle) {
      toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'opx-model-toggle';
      toggle.dataset.resultsModelToggle = '1';
      toggle.setAttribute('aria-controls', 'opx-model-row');
      toggle.innerHTML = '<span>Détails des modèles</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>';
      footer.append(toggle);
      toggle.addEventListener('click', () => {
        const next = toggle.getAttribute('aria-expanded') !== 'true';
        applyExpandedState(section, next);
      });
    }

    if (!toggle.hasAttribute('aria-expanded')) applyExpandedState(section, false);
  }

  function run() {
    removeLegacyStatusPanel();
    enhancePortfolio();
  }

  function init() {
    run();
    const root = document.querySelector('#results-content') || document.body;
    observer = new MutationObserver(records => {
      if (records.some(record => record.addedNodes.length || record.removedNodes.length)) run();
    });
    observer.observe(root, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
