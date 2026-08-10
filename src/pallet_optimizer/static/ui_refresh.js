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

  function solutionRank(card, cell) {
    const value = card?.dataset.solutionRank || cell?.dataset.solutionRank || '';
    const rank = Number(value);
    return Number.isFinite(rank) && rank > 0 ? rank : null;
  }

  function rankLabel(rank) {
    if (rank === 1) return '🏆 Recommandé';
    if (rank === 2) return '🥈 2e';
    if (rank === 3) return '🥉 3e';
    return `${rank}e`;
  }

  function removeSolutionNumbering(card) {
    if (!card) return;
    qa('strong, h2, h3, h4, span', card).forEach(element => {
      if (element.children.length) return;
      const text = element.textContent.trim();
      if (/^Solution\s+\d+$/i.test(text) || text === 'Plan obtenu') element.classList.add('ux-hide-result-title');
      if (text.toLocaleLowerCase('fr') === 'recommandée' || text.toLocaleLowerCase('fr') === 'recommandé') {
        element.classList.add('ux-hide-inner-recommended');
      }
    });
  }

  function polishRanking() {
    const row = q('#opx-solution-row');
    if (!row) return;
    const cells = qa(':scope > .opx-solution-cell', row);
    if (!cells.length) return;

    cells.forEach(cell => {
      const card = q('.solution-card', cell);
      const rank = solutionRank(card, cell);
      removeSolutionNumbering(card);
      cell.classList.remove('rank-1', 'rank-2', 'rank-3', 'rank-4', 'rank-5');
      q('.ux-recommended-ribbon', cell)?.remove();

      const label = q('.opx-solution-cell-label', cell);
      const model = q('span', label || cell);
      if (model && !/^Modèle\s+\d+$/i.test(model.textContent.trim())) {
        const methodIndex = [...cells].indexOf(cell) + 1;
        model.textContent = `Modèle ${methodIndex}`;
      }

      if (!rank) return;
      cell.dataset.solutionRank = String(rank);
      cell.classList.add(`rank-${Math.min(rank, 5)}`);
      if (label) {
        let badge = q('strong', label);
        if (!badge) {
          badge = document.createElement('strong');
          label.append(badge);
        }
        badge.className = 'opx-ranking-badge';
        badge.textContent = rankLabel(rank);
      }
    });

    const rowLabel = row.previousElementSibling;
    if (rowLabel?.classList.contains('opx-row-label')) rowLabel.textContent = 'Résultats classés';
  }

  function compactDecisionPanel() {
    const content = q('#results-content');
    const panel = content?.querySelector('.decision-panel');
    if (!content || !panel) return;
    panel.classList.add('ux-decision-compact');
    if (content.lastElementChild !== panel) content.append(panel);
  }

  function headingElement(text) {
    const expected = text.toLocaleLowerCase('fr');
    return qa('h2, h3, h4, strong').find(element => element.textContent.trim().toLocaleLowerCase('fr') === expected) || null;
  }

  function sectionForHeading(text) {
    const heading = headingElement(text);
    if (!heading) return null;
    return heading.closest('section, article') || heading.parentElement?.parentElement || heading.parentElement;
  }

  function makeDiagnosticsSecondary(diagnostics) {
    if (!diagnostics || diagnostics.dataset.uxDiagnosticsReady === '1') return;
    diagnostics.dataset.uxDiagnosticsReady = '1';
    diagnostics.classList.add('ux-diagnostics-secondary');
    const heading = [...diagnostics.querySelectorAll('h2, h3, h4, strong')]
      .find(element => element.textContent.trim().toLocaleLowerCase('fr') === 'diagnostics');
    if (!heading) return;

    const disclosure = document.createElement('details');
    disclosure.className = 'ux-diagnostics-disclosure';
    const summary = document.createElement('summary');
    summary.innerHTML = '<span>Diagnostics</span><small>Afficher les informations techniques</small>';
    disclosure.append(summary);

    [...diagnostics.children].forEach(child => {
      if (child !== heading) disclosure.append(child);
    });
    heading.replaceWith(disclosure);
  }

  function polishInspector() {
    const details = sectionForHeading('inspection de l’objet') || sectionForHeading("inspection de l'objet") || sectionForHeading('détails de l’objet') || sectionForHeading("détails de l'objet");
    const diagnostics = sectionForHeading('diagnostics');
    const exports = sectionForHeading('exports opérationnels');
    details?.classList.add('ux-inspector-details');
    makeDiagnosticsSecondary(diagnostics);
    exports?.classList.add('ux-exports-final');

    const parent = details?.parentElement || diagnostics?.parentElement || exports?.parentElement;
    parent?.classList.add('ux-inspector-stack');
    if (parent && exports && exports.parentElement === parent && exports !== parent.lastElementChild) parent.append(exports);
  }

  function polishViewer() {
    const viewer = q('#viewer');
    if (!viewer) return;
    viewer.closest('.viewer-main, .viewer-stage, .viewer-panel')?.classList.add('ux-viewer-rectangular');
  }

  function apply() {
    scheduled = false;
    hideRedundantFacturxTab();
    replaceOptimizationLabels();
    polishRanking();
    compactDecisionPanel();
    polishInspector();
    polishViewer();
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
