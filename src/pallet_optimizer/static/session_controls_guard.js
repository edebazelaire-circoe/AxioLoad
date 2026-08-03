(() => {
  'use strict';

  const q = selector => document.querySelector(selector);
  let contextPromise = null;

  function loadContext() {
    if (!contextPromise) {
      contextPromise = fetch('/api/company/context', {credentials: 'same-origin'})
        .then(response => response.ok ? response.json() : null)
        .catch(() => null);
    }
    return contextPromise;
  }

  function isAuthenticated(context) {
    if (!context) return false;
    const directManagement = context.mode === 'assistance'
      && context.company?.id === 'local'
      && context.actor
      && context.actor !== 'Utilisateur local';
    const assistance = context.mode === 'assistance' && context.company?.id !== 'local';
    return Boolean(context.user) || directManagement || assistance;
  }

  function createLogoutButton(context) {
    const topbar = q('.topbar');
    if (!topbar) return false;
    if (q('#site-logout')) return true;

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
          await fetch('/api/admin/assistance/exit', {
            method: 'POST',
            credentials: 'same-origin',
          }).catch(() => null);
        }
        await fetch('/api/auth/logout', {
          method: 'POST',
          credentials: 'same-origin',
        }).catch(() => null);
      } finally {
        localStorage.removeItem('axioload.superadmin.active');
        location.href = '/login';
      }
    });
    return true;
  }

  async function install() {
    const context = await loadContext();
    if (!isAuthenticated(context)) return true;
    return createLogoutButton(context);
  }

  function start() {
    [0, 100, 300, 800, 1600].forEach(delay => {
      window.setTimeout(() => { void install(); }, delay);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
})();
