(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  let accessibilityFrame = 0;

  function syncPanelAccessibility() {
    accessibilityFrame = 0;
    qa('main > .tab-panel').forEach(panel => {
      const active = panel.classList.contains('active');
      panel.setAttribute('aria-hidden', String(!active));
      if ('inert' in panel) panel.inert = !active;
    });
  }

  function scheduleAccessibilitySync() {
    if (accessibilityFrame) cancelAnimationFrame(accessibilityFrame);
    accessibilityFrame = requestAnimationFrame(syncPanelAccessibility);
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
    scheduleAccessibilitySync();
  }, false);

  document.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const choice = event.target.closest?.('label.theme-choice, label.total-mode-toggle');
    if (!choice || event.target.matches('input, button, a, select, textarea')) return;
    event.preventDefault();
    choice.click();
  });

  window.addEventListener('axioload:navigation:changed', scheduleAccessibilitySync);
  window.addEventListener('pageshow', scheduleAccessibilitySync);

  function init() {
    syncPanelAccessibility();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
