(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  let requestedPanel = null;
  let reconciliationFrame = 0;

  function usable(element) {
    return Boolean(
      element &&
      element.isConnected &&
      !element.hidden &&
      !element.disabled &&
      element.getAttribute('aria-disabled') !== 'true'
    );
  }

  function panelForControl(control) {
    if (!control) return null;
    if (control.id === 'open-settings') return q('#tab-settings');
    if (control.id === 'open-admin') return q('#tab-admin');
    const tabName = control.dataset?.tab;
    return tabName ? q(`#tab-${CSS.escape(tabName)}`) : null;
  }

  function syncPanelAccessibility() {
    qa('main > .tab-panel').forEach(panel => {
      const active = panel.classList.contains('active');
      panel.setAttribute('aria-hidden', String(!active));
      if ('inert' in panel) panel.inert = !active;
    });
  }

  function reconcilePanels() {
    reconciliationFrame = 0;
    const panels = qa('main > .tab-panel');
    const activePanels = panels.filter(panel => panel.classList.contains('active'));
    const preferred = requestedPanel && requestedPanel.isConnected ? requestedPanel : null;
    requestedPanel = null;

    if (preferred && activePanels.includes(preferred)) {
      activePanels.forEach(panel => panel.classList.toggle('active', panel === preferred));
    } else if (activePanels.length > 1) {
      const visible = activePanels.filter(panel => getComputedStyle(panel).display !== 'none');
      const keep = visible.at(-1) || activePanels.at(-1);
      activePanels.forEach(panel => panel.classList.toggle('active', panel === keep));
    }

    syncPanelAccessibility();
  }

  function scheduleReconciliation(panel = null) {
    if (panel) requestedPanel = panel;
    if (reconciliationFrame) cancelAnimationFrame(reconciliationFrame);
    queueMicrotask(syncPanelAccessibility);
    reconciliationFrame = requestAnimationFrame(reconcilePanels);
  }

  function activateChoiceFromCard(event) {
    const choice = event.target.closest?.('label.theme-choice, label.total-mode-toggle');
    if (!choice || event.target.matches('input, select, textarea, button, a')) return;
    const input = q('input:not(:disabled)', choice);
    if (!input) return;
    if (input.type === 'radio') {
      if (!input.checked) {
        input.checked = true;
        input.dispatchEvent(new Event('change', {bubbles: true}));
      }
    } else if (input.type === 'checkbox') {
      input.checked = !input.checked;
      input.dispatchEvent(new Event('change', {bubbles: true}));
    }
    event.preventDefault();
  }

  document.addEventListener('click', event => {
    activateChoiceFromCard(event);

    const control = event.target.closest?.(
      '.tab[data-tab], #open-settings, #open-admin, #close-settings, #close-admin, [data-workspace], [data-workspace-group]'
    );
    if (!usable(control)) return;
    scheduleReconciliation(panelForControl(control));
  }, false);

  document.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const choice = event.target.closest?.('label.theme-choice, label.total-mode-toggle');
    if (!choice || event.target.matches('input, button, a, select, textarea')) return;
    event.preventDefault();
    choice.click();
  });

  const observer = new MutationObserver(records => {
    if (records.some(record => record.type === 'attributes' && record.attributeName === 'class')) {
      scheduleReconciliation();
    }
  });

  function init() {
    qa('main > .tab-panel').forEach(panel => observer.observe(panel, {attributes: true, attributeFilter: ['class']}));
    syncPanelAccessibility();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
