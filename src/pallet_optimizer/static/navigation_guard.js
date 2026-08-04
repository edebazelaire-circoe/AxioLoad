(() => {
  'use strict';

  const NAVIGATION_SELECTOR = [
    '.tab[data-tab]',
    '[data-workspace]',
    '[data-workspace-group]',
    '[data-admin-view]',
    '[data-detail-tab]',
    '#open-settings',
    '#open-admin',
    '#close-settings',
    '#close-admin'
  ].join(',');

  function unavailable(control) {
    return Boolean(
      !control ||
      control.disabled ||
      control.hidden ||
      control.getAttribute('aria-disabled') === 'true'
    );
  }

  document.addEventListener('click', event => {
    const control = event.target.closest?.(NAVIGATION_SELECTOR);
    if (!control) return;
    if (unavailable(control)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    document.body.dataset.lastNavigation =
      control.dataset.tab ||
      control.dataset.workspace ||
      control.dataset.workspaceGroup ||
      control.dataset.adminView ||
      control.dataset.detailTab ||
      control.id ||
      'navigation';
  }, true);
})();
