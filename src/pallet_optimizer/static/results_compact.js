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
    modelDetails(section).forEach(details => {
      if (details.open !== expanded) details.open = expanded;
    });
    section.classList.toggle('model-details-expanded', expanded);
    const expandedValue = String(expanded);
    if (toggle.getAttribute('aria-expanded') !== expandedValue) {
      toggle.setAttribute('aria-expanded', expandedValue);
    }
    const label = toggle.querySelector('span');
    const expectedLabel = expanded ? 'Masquer les détails des modèles' : 'Détails des modèles';
    if (label && label.textContent !== expectedLabel) label.textContent = expectedLabel;
  }

  function ensureVisible(element) {
    if (element?.hidden) element.hidden = false;
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

    ensureVisible(modelRow);
    [...modelRow.children].forEach(ensureVisible);
    const modelLabel = modelRow.previousElementSibling;
    if (modelLabel?.classList.contains('opx-row-label')) ensureVisible(modelLabel);

    let summary = section.querySelector('.opx-portfolio-summary');
    if (!summary) {
      summary = document.createElement('p');
      summary.className = 'opx-portfolio-summary';
      summary.textContent = 'Comparez les cinq modèles, puis choisissez le plan le mieux classé.';
      title.insertAdjacentElement('afterend', summary);
    }

    const expectedIntro = 'Les cartes du haut résument chaque modèle. Les informations techniques détaillées restent masquées tant que vous ne les demandez pas.';
    if (intro.textContent !== expectedIntro) intro.textContent = expectedIntro;

    let footer = section.querySelector('.opx-model-details-footer');
    if (!footer) {
      footer = document.createElement('div');
      footer.className = 'opx-model-details-footer';
      modelRow.insertAdjacentElement('afterend', footer);
    }

    let toggle = section.querySelector('[data-results-model-toggle]');
    if (!toggle) {
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
    } else if (!toggle.hasAttribute('aria-expanded')) {
      applyDetailsState(section, false);
    }

    if (section.dataset.compactResultsReady !== '2') {
      section.dataset.compactResultsReady = '2';
    }
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
