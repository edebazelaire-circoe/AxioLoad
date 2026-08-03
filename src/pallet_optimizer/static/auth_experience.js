(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];

  function setLabelText(label, text) {
    if (!label) return;
    const node = [...label.childNodes].find(child => child.nodeType === Node.TEXT_NODE);
    if (node && node.textContent !== text) node.textContent = text;
  }

  function showMessage(message, text, error = false) {
    if (!message) return;
    message.textContent = text;
    message.className = `message ${error ? 'error' : 'success'}`;
    message.classList.remove('hidden');
  }

  function installLoginModes() {
    const form = q('#login-form');
    const message = q('#login-message');
    if (!form || !message || q('.auth-account-switch')) return false;

    const tenantInput = q('[name="tenant_id"]', form);
    const emailInput = q('[name="email"]', form);
    const passwordInput = q('[name="password"]', form);
    const tenantLabel = tenantInput?.closest('label');
    const emailLabel = emailInput?.closest('label');
    const eyebrow = q('.login-shell .eyebrow');
    const title = q('.login-shell h1');
    const intro = q('.login-shell h1 + p');
    const help = q('.login-help');
    const actions = q('.login-actions', form);
    if (!tenantInput || !emailInput || !passwordInput || !tenantLabel || !emailLabel || !actions) return false;

    const switcher = document.createElement('div');
    switcher.className = 'auth-account-switch';
    switcher.setAttribute('role', 'tablist');
    switcher.innerHTML = `
      <button type="button" role="tab" data-auth-mode="user">Compte utilisateur</button>
      <button type="button" role="tab" data-auth-mode="super_admin">Centre de gestion</button>`;
    form.before(switcher);

    const adminNote = document.createElement('div');
    adminNote.className = 'auth-admin-note';
    adminNote.textContent = 'Utilisez l’adresse e-mail ou le pseudo du compte du Centre de gestion.';
    form.before(adminNote);

    const tenantHint = document.createElement('small');
    tenantHint.className = 'auth-field-hint';
    tenantHint.textContent = 'Facultatif. À préciser seulement si votre adresse est utilisée dans plusieurs entreprises.';
    tenantLabel.append(tenantHint);

    const forgotButton = document.createElement('button');
    forgotButton.type = 'button';
    forgotButton.className = 'auth-forgot-link';
    forgotButton.textContent = 'Mot de passe oublié ?';
    actions.prepend(forgotButton);

    let mode = new URLSearchParams(location.search).get('mode') === 'super_admin' ? 'super_admin' : 'user';

    const applyMode = nextMode => {
      mode = nextMode;
      qa('[data-auth-mode]', switcher).forEach(button => {
        const active = button.dataset.authMode === mode;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', String(active));
      });
      const admin = mode === 'super_admin';
      tenantLabel.hidden = admin;
      tenantInput.required = false;
      emailInput.type = admin ? 'text' : 'email';
      emailInput.autocomplete = 'username';
      emailInput.placeholder = admin ? 'Adresse e-mail ou pseudo' : '';
      setLabelText(emailLabel, admin ? 'Adresse e-mail ou pseudo' : 'Adresse e-mail');
      adminNote.classList.toggle('visible', admin);
      forgotButton.hidden = admin;
      if (eyebrow) eyebrow.textContent = admin ? 'Centre de gestion AxioLoad' : 'Espace client';
      if (title) title.textContent = admin ? 'Connexion au Centre de gestion' : 'Connexion';
      if (intro) intro.textContent = admin
        ? 'Connectez-vous pour gérer les entreprises, les utilisateurs et les paramètres globaux.'
        : 'Votre adresse e-mail suffit dans la majorité des cas.';
      if (help) help.hidden = admin;
      emailInput.focus();
    };

    qa('[data-auth-mode]', switcher).forEach(button => {
      button.addEventListener('click', () => {
        if (!button.disabled) applyMode(button.dataset.authMode);
      });
    });
    applyMode(mode);

    forgotButton.addEventListener('click', async () => {
      if (forgotButton.disabled) return;
      message.classList.add('hidden');
      const email = emailInput.value.trim();
      if (!email) {
        showMessage(message, 'Renseignez votre adresse e-mail avant de demander une réinitialisation.', true);
        emailInput.focus();
        return;
      }
      forgotButton.disabled = true;
      try {
        const response = await fetch('/api/auth/forgot-password', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({tenant_id: tenantInput.value.trim(), email}),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || 'Demande impossible');
        showMessage(message, body.message || 'La demande a été transmise au Centre de gestion.');
      } catch (error) {
        showMessage(message, error.message || String(error), true);
      } finally {
        forgotButton.disabled = false;
      }
    });

    form.addEventListener('submit', async event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      message.classList.add('hidden');
      const button = q('button[type="submit"]', form);
      if (!button || button.disabled) return;
      button.disabled = true;
      try {
        const admin = mode === 'super_admin';
        const endpoint = admin ? '/api/auth/super-admin-login' : '/api/auth/login';
        const payload = admin
          ? {identifier: emailInput.value.trim(), password: passwordInput.value}
          : {tenant_id: tenantInput.value.trim(), email: emailInput.value.trim(), password: passwordInput.value};
        const response = await fetch(endpoint, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || 'Connexion impossible');
        location.href = !admin && body.must_change_password ? '/change-password' : '/';
      } catch (error) {
        showMessage(message, error.message || String(error), true);
      } finally {
        button.disabled = false;
      }
    }, {capture: true});
    return true;
  }

  function removeDirectAdminAssistanceBanner() {
    qa('.admin-assistance-banner').forEach(banner => {
      if (banner.textContent.includes('Entreprise locale')) banner.remove();
    });
  }

  function logoutButton(context) {
    const topbar = q('.topbar');
    if (!topbar || q('#site-logout')) return false;
    const button = document.createElement('button');
    button.id = 'site-logout';
    button.type = 'button';
    button.className = 'settings-access auth-logout';
    button.setAttribute('aria-label', 'Se déconnecter');
    button.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10"/></svg>
      <span>Se déconnecter</span>`;
    topbar.append(button);
    button.addEventListener('click', async () => {
      if (button.disabled) return;
      button.disabled = true;
      try {
        if (context.mode === 'assistance' && context.company?.id !== 'local') {
          await fetch('/api/admin/assistance/exit', {method: 'POST', credentials: 'same-origin'}).catch(() => null);
        }
        await fetch('/api/auth/logout', {method: 'POST', credentials: 'same-origin'});
      } finally {
        localStorage.removeItem('axioload.superadmin.active');
        location.href = '/login';
      }
    });
    return true;
  }

  async function installApplicationSession() {
    if (!q('#open-settings')) return false;
    let context;
    try {
      const response = await fetch('/api/company/context', {credentials: 'same-origin'});
      context = response.ok ? await response.json() : null;
    } catch (_) {
      context = null;
    }
    if (!context) return false;

    const directAdmin = context.mode === 'assistance' && context.company?.id === 'local'
      && context.actor && context.actor !== 'Utilisateur local';
    const assistance = context.mode === 'assistance' && context.company?.id !== 'local';
    const authenticatedUser = Boolean(context.user);
    const authenticated = directAdmin || assistance || authenticatedUser;

    if (directAdmin) {
      localStorage.setItem('axioload.superadmin.active', '1');
      [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(removeDirectAdminAssistanceBanner, delay));
    } else if (!assistance) {
      localStorage.removeItem('axioload.superadmin.active');
    }

    if (authenticated) logoutButton(context);

    document.addEventListener('click', event => {
      const adminButton = event.target.closest?.('#open-admin');
      if (!adminButton || adminButton.disabled || adminButton.hidden || directAdmin || assistance) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      location.href = '/login?mode=super_admin';
    }, true);
    return true;
  }

  const init = () => {
    installLoginModes();
    installApplicationSession();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
