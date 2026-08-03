(() => {
  'use strict';

  const blockedSelectors = '#admin-create-company, #admin-add-user, [data-resend]';

  function applyFixedAccountMode() {
    document.body.dataset.fixedTestAccounts = '1';

    document.querySelectorAll(blockedSelectors).forEach(button => {
      button.disabled = true;
      button.hidden = true;
      button.setAttribute('aria-hidden', 'true');
    });

    const panel = document.querySelector('#tab-admin');
    const heading = panel?.querySelector('.admin-heading');
    if (heading && !panel.querySelector('#fixed-test-accounts-notice')) {
      const notice = document.createElement('div');
      notice.id = 'fixed-test-accounts-notice';
      notice.className = 'admin-notice success';
      notice.textContent = 'Mode de test : deux comptes fixes sont actifs. Les invitations et la création de comptes sont temporairement désactivées.';
      heading.after(notice);
    }
  }

  document.addEventListener('click', event => {
    const blocked = event.target.closest?.(blockedSelectors);
    if (blocked) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (event.target.closest?.('#open-admin, [data-open-company], [data-detail-tab="users"]')) {
      setTimeout(applyFixedAccountMode, 0);
      setTimeout(applyFixedAccountMode, 120);
    }
  }, true);

  [0, 80, 250, 700, 1500].forEach(delay => {
    setTimeout(applyFixedAccountMode, delay);
  });
})();
