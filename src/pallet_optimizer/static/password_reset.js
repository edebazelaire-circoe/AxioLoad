(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
  const formatDate = value => value ? new Date(value).toLocaleString('fr-FR') : '—';

  async function api(url, options = {}) {
    const response = await fetch(url, {...options, credentials: 'same-origin'});
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (response.status === 401) {
      location.href = '/login?mode=super_admin';
      throw new Error('Connexion au Centre de gestion requise');
    }
    if (!response.ok) throw new Error(body?.detail || `Erreur ${response.status}`);
    return body;
  }

  function modal(title, content) {
    let overlay = q('#password-reset-dialog');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'password-reset-dialog';
      overlay.className = 'admin-dialog';
      document.body.append(overlay);
    }
    overlay.innerHTML = `<section class="admin-dialog-card" role="dialog" aria-modal="true">
      <div class="admin-dialog-head"><h3>${escapeHtml(title)}</h3><button type="button" class="secondary" data-close>Fermer</button></div>
      <div>${content}</div>
    </section>`;
    overlay.classList.add('open');
    const close = () => overlay.classList.remove('open');
    q('[data-close]', overlay)?.addEventListener('click', close);
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); }, {once: true});
    return overlay;
  }

  async function resetUser(userId, label = 'cet utilisateur') {
    const confirmed = confirm(`Réinitialiser le mot de passe de ${label} ? Toutes ses sessions en cours seront fermées.`);
    if (!confirmed) return false;
    const result = await api(`/api/admin/users/${encodeURIComponent(userId)}/password-reset`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    });
    const overlay = modal('Nouveau mot de passe temporaire', `
      <p>Transmettez ce mot de passe à l’utilisateur par votre canal habituel. Il ne sera plus affiché après fermeture.</p>
      <div class="password-secret">${escapeHtml(result.temporary_password)}</div>
      <div class="admin-actions"><button type="button" class="primary" data-copy-password>Copier</button></div>`);
    q('[data-copy-password]', overlay)?.addEventListener('click', async event => {
      const button = event.currentTarget;
      if (button.disabled) return;
      button.disabled = true;
      try {
        await navigator.clipboard.writeText(result.temporary_password);
        button.textContent = 'Copié';
      } finally {
        button.disabled = false;
      }
    });
    return true;
  }

  function installChangePasswordForm() {
    const form = q('#change-password-form');
    const message = q('#change-password-message');
    if (!form || !message || form.dataset.ready) return false;
    form.dataset.ready = '1';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(form));
      if (values.new_password !== values.confirm_password) {
        message.textContent = 'Les deux nouveaux mots de passe ne correspondent pas.';
        message.className = 'message error';
        message.classList.remove('hidden');
        return;
      }
      const submit = q('[type="submit"]', form);
      if (!submit || submit.disabled) return;
      submit.disabled = true;
      try {
        await api('/api/auth/change-password', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({current_password: values.current_password, new_password: values.new_password}),
        });
        message.textContent = 'Mot de passe enregistré. Redirection vers AxioLoad…';
        message.className = 'message success';
        message.classList.remove('hidden');
        setTimeout(() => { location.href = '/'; }, 500);
      } catch (error) {
        message.textContent = error.message || String(error);
        message.className = 'message error';
        message.classList.remove('hidden');
      } finally {
        submit.disabled = false;
      }
    });
    return true;
  }

  async function loadRequests(target) {
    if (!target || target.dataset.loading === '1') return;
    target.dataset.loading = '1';
    target.innerHTML = '<div class="admin-empty">Chargement…</div>';
    try {
      const result = await api('/api/admin/password-reset-requests?status=pending');
      const requests = result.requests || [];
      target.innerHTML = requests.length ? `<div class="password-reset-list">${requests.map(item => `
        <article class="password-reset-item">
          <div><strong>${escapeHtml(item.user_name || item.email)}</strong><small>${escapeHtml(item.email)} · ${escapeHtml(item.company_name)}</small><small>Demandé le ${escapeHtml(formatDate(item.created_at))}</small></div>
          <button type="button" class="primary password-reset-button" data-reset-request="${escapeHtml(item.user_id)}" data-reset-label="${escapeHtml(item.user_name || item.email)}">Réinitialiser</button>
        </article>`).join('')}</div>` : '<div class="admin-empty">Aucune demande en attente.</div>';
      qa('[data-reset-request]', target).forEach(button => button.addEventListener('click', async () => {
        if (button.disabled) return;
        button.disabled = true;
        try {
          const changed = await resetUser(button.dataset.resetRequest, button.dataset.resetLabel);
          if (changed) await loadRequests(target);
        } catch (error) {
          alert(error.message || String(error));
        } finally {
          button.disabled = false;
        }
      }));
    } catch (error) {
      target.innerHTML = `<div class="admin-notice warning">${escapeHtml(error.message || String(error))}</div>`;
    } finally {
      target.dataset.loading = '0';
    }
  }

  function installAdminPasswordView() {
    const panel = q('#tab-admin');
    const nav = q('.admin-nav', panel || document);
    const content = q('.admin-content', panel || document);
    if (!panel || !nav || !content) return false;
    if (q('[data-admin-view="passwords"]', nav)) return true;

    const navButton = document.createElement('button');
    navButton.type = 'button';
    navButton.className = 'secondary';
    navButton.dataset.adminView = 'passwords';
    navButton.textContent = 'Mots de passe';
    nav.append(navButton);

    const view = document.createElement('section');
    view.id = 'admin-view-passwords';
    view.className = 'admin-view';
    view.innerHTML = `<div class="admin-toolbar"><div><h3>Demandes de réinitialisation</h3><p>Le Centre de gestion attribue directement un mot de passe temporaire. Aucun lien ni code de récupération n’est généré.</p></div><button type="button" class="secondary" data-refresh-passwords>Actualiser</button></div><div data-password-requests></div>`;
    content.append(view);

    navButton.addEventListener('click', () => {
      if (navButton.disabled) return;
      qa('[data-admin-view]', nav).forEach(item => item.classList.toggle('active', item === navButton));
      qa('.admin-view', content).forEach(item => item.classList.toggle('active', item === view));
      loadRequests(q('[data-password-requests]', view));
    });
    q('[data-refresh-passwords]', view)?.addEventListener('click', event => {
      if (event.currentTarget.disabled) return;
      loadRequests(q('[data-password-requests]', view));
    });
    return true;
  }

  function decorateUserRows() {
    const target = q('#admin-company-users');
    if (!target) return false;
    qa('tr[data-user]', target).forEach(row => {
      if (q('[data-direct-password-reset]', row)) return;
      const statusText = row.textContent || '';
      if (!statusText.includes('active') && !statusText.includes('Active')) return;
      const cell = row.lastElementChild;
      if (!cell) return;
      const actions = q('.admin-actions', cell) || cell;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'secondary';
      button.dataset.directPasswordReset = row.dataset.user;
      button.textContent = 'Réinitialiser le mot de passe';
      actions.append(button);
      button.addEventListener('click', async () => {
        if (button.disabled) return;
        button.disabled = true;
        const label = q('strong', row)?.textContent || 'cet utilisateur';
        try { await resetUser(row.dataset.user, label); }
        catch (error) { alert(error.message || String(error)); }
        finally { button.disabled = false; }
      });
    });
    return true;
  }

  function installUserRowsObserver() {
    const target = q('#admin-company-users');
    if (!target || target.dataset.passwordObserverReady === '1') return Boolean(target);
    target.dataset.passwordObserverReady = '1';
    let scheduled = false;
    new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        decorateUserRows();
      });
    }).observe(target, {childList: true, subtree: true});
    decorateUserRows();
    return true;
  }

  function installAdminFeatures() {
    installAdminPasswordView();
    installUserRowsObserver();
  }

  const init = () => {
    installChangePasswordForm();
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(installAdminFeatures, delay));
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
