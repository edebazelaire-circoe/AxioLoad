(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  let scheduled = false;

  function replaceOptimizationLabels(root = document) {
    qa('button, span, strong, label, h1, h2, h3, h4, small, p', root).forEach(element => {
      if (element.children.length) return;
      const text = element.textContent.trim();
      if (text === 'Optimisation totale') element.textContent = 'Optimisation complète';
      if (text === 'Lancer l’optimisation totale') element.textContent = 'Lancer l’optimisation complète';
    });
  }

  function hideRedundantFacturxTab() {
    const transformTab = q('nav.tabs [data-tab="facturx"]');
    if (!transformTab) return;
    transformTab.dataset.workspaceGroup = 'facturx';
    transformTab.hidden = true;
    transformTab.classList.add('workspace-group-hidden', 'facturx-primary-hidden');
    transformTab.setAttribute('aria-hidden', 'true');
    transformTab.setAttribute('tabindex', '-1');
  }

  function polishModelDetails(root = document) {
    qa('.opx-model-card details summary, .ovr-model-card details summary', root).forEach(summary => {
      if (summary.textContent.trim() !== 'Détails du modèle') summary.textContent = 'Détails du modèle';
    });
  }

  function solutionRank(card, cell) {
    const value = card?.dataset.solutionRank || cell?.dataset.solutionRank || '';
    const rank = Number(value);
    return Number.isFinite(rank) && rank > 0 ? rank : null;
  }

  function rankLabel(rank) {
    if (rank === 1) return '🏆 1er';
    if (rank === 2) return '🥈 2e';
    if (rank === 3) return '🥉 3e';
    return `${rank}e`;
  }

  function removeSolutionNumbering(card) {
    if (!card) return;
    qa('strong, h2, h3, h4, span', card).forEach(element => {
      if (element.children.length) return;
      if (/^Solution\s+\d+$/i.test(element.textContent.trim())) element.textContent = 'Plan obtenu';
    });
  }

  function modelLabelFor(cell, card) {
    const existing = q('.opx-solution-cell-label span', cell)?.textContent.trim();
    if (existing) return existing;
    const method = card?.dataset.method || cell?.dataset.method || '';
    return method ? 'Modèle correspondant' : 'Résultat du modèle';
  }

  function polishRanking() {
    const row = q('#opx-solution-row');
    if (!row) return;
    const cells = qa(':scope > .opx-solution-cell', row);
    if (!cells.length) return;

    const ranked = cells.map((cell, index) => {
      const card = q('.solution-card', cell);
      const rank = solutionRank(card, cell);
      return {cell, card, rank, index};
    });

    const sorted = [...ranked].sort((left, right) => {
      const leftRank = left.rank ?? 999;
      const rightRank = right.rank ?? 999;
      return leftRank - rightRank || left.index - right.index;
    });
    if (sorted.some((entry, index) => entry.cell !== cells[index])) {
      sorted.forEach(entry => row.append(entry.cell));
    }

    sorted.forEach(({cell, card, rank}) => {
      removeSolutionNumbering(card);
      cell.classList.remove('rank-1', 'rank-2', 'rank-3', 'rank-4', 'rank-5');
      if (!rank) return;
      cell.dataset.solutionRank = String(rank);
      cell.classList.add(`rank-${Math.min(rank, 5)}`);

      const label = q('.opx-solution-cell-label', cell);
      if (label) {
        const model = q('span', label);
        if (model) model.textContent = modelLabelFor(cell, card);
        let badge = q('strong', label);
        if (!badge) {
          badge = document.createElement('strong');
          label.append(badge);
        }
        badge.className = 'opx-ranking-badge';
        badge.textContent = rankLabel(rank);
      }

      if (rank === 1 && !q('.ux-recommended-ribbon', cell)) {
        const ribbon = document.createElement('span');
        ribbon.className = 'ux-recommended-ribbon';
        ribbon.textContent = 'Recommandé';
        cell.append(ribbon);
      }
    });

    const rowLabel = row.previousElementSibling;
    if (rowLabel?.classList.contains('opx-row-label')) rowLabel.textContent = 'Classement des résultats';
    const intro = q('.opx-aligned-portfolio .opx-portfolio-intro');
    if (intro) {
      intro.textContent = 'Chaque modèle est présenté séparément. Les résultats sont ensuite classés avec un trophée ou une médaille afin d’éviter toute confusion entre le numéro du modèle et celui d’une solution.';
    }
  }

  function compactDecisionPanel() {
    const content = q('#results-content');
    const panel = content?.querySelector('.decision-panel');
    if (!content || !panel) return;
    panel.classList.add('ux-decision-compact');
    if (content.lastElementChild !== panel) content.append(panel);
  }

  function sectionForHeading(text) {
    const heading = qa('h2, h3, h4, strong').find(element => element.textContent.trim().toLocaleLowerCase('fr') === text);
    if (!heading) return null;
    return heading.closest('section, article') || heading.parentElement?.parentElement || heading.parentElement;
  }

  function polishInspector() {
    const details = sectionForHeading('inspection de l’objet') || sectionForHeading("inspection de l'objet") || sectionForHeading('détails de l’objet') || sectionForHeading("détails de l'objet");
    const diagnostics = sectionForHeading('diagnostics');
    const exports = sectionForHeading('exports opérationnels');
    details?.classList.add('ux-inspector-details');
    diagnostics?.classList.add('ux-diagnostics-secondary');
    exports?.classList.add('ux-exports-final');

    if (diagnostics && exports && diagnostics.parentElement === exports.parentElement) {
      const parent = diagnostics.parentElement;
      if (exports !== parent.lastElementChild) parent.append(exports);
    }
  }

  function apply() {
    scheduled = false;
    hideRedundantFacturxTab();
    replaceOptimizationLabels();
    polishModelDetails();
    polishRanking();
    compactDecisionPanel();
    polishInspector();
  }

  function scheduleApply() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(apply);
  }

  const observer = new MutationObserver(scheduleApply);
  observer.observe(document.documentElement, {childList: true, subtree: true});
  window.addEventListener('axioload:navigation:changed', scheduleApply);
  window.addEventListener('axioload:workspace:registered', scheduleApply);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scheduleApply, {once: true});
  else scheduleApply();
})();
