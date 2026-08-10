(() => {
  'use strict';

  let observer = null;

  function removeLegacyStatusPanel() {
    document.querySelector('#method-status-panel')?.remove();
  }

  function modelDetails(section) {
    return [...section.querySelectorAll('#opx-model-row .opx-model-card details, #opx-model-row .ovr-model-card details')];
  }

  function applyDetailsState(section, expanded) {
    const toggle = section.querySelector('[data-results-model-toggle]');
    if (!toggle) return;
    modelDetails(section).forEach(details => { details.open = expanded; });
    section.classList.toggle('model-details-expanded', expanded);
    toggle.setAttribute('aria-expanded', String(expanded));
    const label = toggle.querySelector('span');
    if (label) label.textContent = expanded ? 'Masquer les détails des modèles' : 'Détails des modèles';
  }

  function enhancePortfolio() {
    removeLegacyStatusPanel();
    const section = document.querySelector('#opx-method-portfolio');
    if (!section || section.dataset.compactResultsReady === '2') return;

    const heading = section.querySelector('.opx-portfolio-heading');
    const title = heading?.querySelector('h3');
    const intro = section.querySelector('.opx-portfolio-intro');
    const modelRow = section.querySelector('#opx-model-row');
    const solutionRow = section.querySelector('#opx-solution-row');
    if (!heading || !title || !intro || !modelRow || !solutionRow) return;

    section.dataset.compactResultsReady = '2';
    modelRow.hidden = false;
    const modelLabel = modelRow.previousElementSibling;
    if (modelLabel?.classList.contains('opx-row-label')) modelLabel.hidden = false;

    section.querySelector('.opx-portfolio-summary')?.remove();
    title.insertAdjacentHTML('afterend', '<p class="opx-portfolio-summary">Comparez les cinq modèles, puis choisissez le plan le mieux classé.</p>');
    intro.textContent = 'Les cartes du haut résument chaque modèle. Les informations techniques détaillées restent masquées tant que vous ne les demandez pas.';

    let footer = section.querySelector('.opx-model-details-footer');
    if (!footer) {
      footer = document.createElement('div');
      footer.className = 'opx-model-details-footer';
      modelRow.insertAdjacentElement('afterend', footer);
    }

    let toggle = section.querySelector('[data-results-model-toggle]');
    if (toggle) toggle.remove();
    toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'opx-model-toggle';
    toggle.dataset.resultsModelToggle = '1';
    toggle.setAttribute('aria-controls', 'opx-model-row');
    toggle.innerHTML = '<span>Détails des modèles</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>';
    footer.append(toggle);

    applyDetailsState(section, false);
    toggle.addEventListener('click', () => {
      const next = toggle.getAttribute('aria-expanded') !== 'true';
      applyDetailsState(section, next);
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
