(() => {
  'use strict';

  const blockedSelectors = '#admin-create-company, #admin-add-user, [data-resend]';

  function makeText(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
  }

  async function installFixedLoginAccounts() {
    const form = document.querySelector('#login-form');
    if (!form || document.querySelector('.fixed-login-accounts')) return;

    let payload;
    try {
      const response = await fetch('/api/auth/test-accounts', {credentials: 'same-origin'});
      if (!response.ok) return;
      payload = await response.json();
    } catch (_) {
      return;
    }
    if (!payload?.enabled || !Array.isArray(payload.accounts) || payload.accounts.length !== 2) return;

    const section = document.createElement('section');
    section.className = 'fixed-login-accounts';
    section.setAttribute('aria-labelledby', 'fixed-login-accounts-title');

    const title = makeText('p', 'fixed-login-accounts__title', 'Choisir un compte de test');
    title.id = 'fixed-login-accounts-title';
    section.append(title);

    const grid = document.createElement('div');
    grid.className = 'fixed-login-accounts__grid';
    section.append(grid);

    const status = makeText('div', 'fixed-login-status', 'Sélectionnez un profil pour ouvrir directement la vue correspondante.');
    status.setAttribute('role', 'status');
    section.append(status);

    let submitting = false;

    payload.accounts.forEach(account => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'fixed-login-account';
      card.dataset.testAccount = String(account.key || '');
      card.append(
        makeText('span', 'fixed-login-account__badge', account.mode === 'super_admin' ? 'Vision globale' : 'Vision entreprise'),
        makeText('strong', '', String(account.label || 'Compte de test')),
        makeText('p', '', String(account.description || '')),
      );

      const credentials = document.createElement('span');
      credentials.className = 'fixed-login-account__credentials';
      credentials.append(
        makeText('span', '', `Identifiant : ${String(account.identifier || '')}`),
        makeText('span', '', `Mot de passe : ${String(account.password || '')}`),
      );
      if (account.tenant_id) {
        credentials.append(makeText('span', '', `Entreprise : ${String(account.company_name || account.tenant_id)}`));
      }
      card.append(credentials, makeText('span', 'fixed-login-account__action', 'Se connecter avec ce compte'));

      card.addEventListener('click', () => {
        if (submitting) return;
        submitting = true;
        const modeButton = document.querySelector(`[data-auth-mode="${account.mode}"]`);
        modeButton?.click();

        const tenantInput = form.querySelector('[name="tenant_id"]');
        const emailInput = form.querySelector('[name="email"]');
        const passwordInput = form.querySelector('[name="password"]');
        if (!emailInput || !passwordInput) {
          submitting = false;
          return;
        }
        if (tenantInput) tenantInput.value = String(account.tenant_id || '');
        emailInput.value = String(account.identifier || '');
        passwordInput.value = String(account.password || '');
        status.textContent = `Connexion en cours : ${String(account.label || 'compte de test')}…`;
        form.requestSubmit();
        window.setTimeout(() => {
          submitting = false;
          status.textContent = 'La connexion n’a pas abouti. Vous pouvez sélectionner de nouveau le profil.';
        }, 1800);
      });
      grid.append(card);
    });

    const switcher = document.querySelector('.auth-account-switch');
    (switcher || form).before(section);
  }

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

  function init() {
    applyFixedAccountMode();
    installFixedLoginAccounts();
    [80, 250, 700, 1500].forEach(delay => {
      setTimeout(applyFixedAccountMode, delay);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
