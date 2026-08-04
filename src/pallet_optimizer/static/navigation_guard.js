(() => {
  'use strict';

  const NAVIGATION_SELECTOR = [
    '.tab[data-tab]',
    '[data-workspace]',
    '[data-workspace-group]',
    '[data-admin-view]',
    '#open-settings',
    '#open-admin'
  ].join(',');
  const LOCK_MS = 250;
  const SAFETY_MS = 1800;
  let locked = false;
  let releaseTimer = 0;
  let safetyTimer = 0;
  let queuedControl = null;

  function ensureIndicator() {
    let indicator = document.querySelector('#navigation-loading-indicator');
    if (indicator) return indicator;
    indicator = document.createElement('div');
    indicator.id = 'navigation-loading-indicator';
    indicator.className = 'navigation-loading-indicator';
    indicator.setAttribute('role', 'status');
    indicator.setAttribute('aria-live', 'polite');
    indicator.innerHTML = '<span class="navigation-spinner" aria-hidden="true"></span><span>Chargement…</span>';
    document.body.append(indicator);
    return indicator;
  }

  function replayQueuedNavigation() {
    const control = queuedControl;
    queuedControl = null;
    if (!control || !control.isConnected || control.disabled || control.hidden || control.getAttribute('aria-disabled') === 'true') return;
    window.setTimeout(() => control.click(), 0);
  }

  function releaseNavigation() {
    locked = false;
    document.body.classList.remove('navigation-is-loading');
    document.body.removeAttribute('aria-busy');
    ensureIndicator().classList.remove('visible');
    window.clearTimeout(releaseTimer);
    window.clearTimeout(safetyTimer);
    replayQueuedNavigation();
  }

  function lockNavigation() {
    locked = true;
    document.body.classList.add('navigation-is-loading');
    document.body.setAttribute('aria-busy', 'true');
    ensureIndicator().classList.add('visible');
    window.clearTimeout(releaseTimer);
    window.clearTimeout(safetyTimer);
    releaseTimer = window.setTimeout(releaseNavigation, LOCK_MS);
    safetyTimer = window.setTimeout(releaseNavigation, SAFETY_MS);
  }

  document.addEventListener('click', event => {
    const control = event.target.closest?.(NAVIGATION_SELECTOR);
    if (!control || control.disabled || control.hidden || control.getAttribute('aria-disabled') === 'true') return;

    if (locked) {
      queuedControl = control;
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    lockNavigation();
  }, true);

  window.addEventListener('pageshow', releaseNavigation);
  window.addEventListener('load', releaseNavigation, {once: true});
})();
