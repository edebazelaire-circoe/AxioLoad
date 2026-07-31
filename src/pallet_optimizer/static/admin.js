(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
  const formatDate = value => value ? new Date(value).toLocaleString('fr-FR') : '—';
  const monthStart = () => {
    const date = new Date();
    date.setDate(1);
    return date.toISOString().slice(0, 10);
  };
  const today = () => new Date().toISOString().slice(0, 10);

  const statusLabels = {
    draft: 'Brouillon', invited: 'Invitée', invitation_expired: 'Invitation expirée',
    to_complete: 'À compléter', pending_validation: 'En attente de validation',
    correction_required: 'Correction demandée', active: 'Active', suspended: 'Suspendue',
    archived: 'Archivée', refused: 'Refusée'
  };
  const sectionLabels = {
    accounts: 'Comptes et entreprises', usage: 'Utilisation du logiciel',
    quality: 'Qualité et fonctionnement', api: 'API'
  };
  const metricLabels = {
    companies: 'Entreprises', active_companies: 'Entreprises actives', users: 'Utilisateurs',
    pending_invitations: 'Invitations en attente', optimizations: 'Optimisations',
    validations: 'Validations', exports: 'Exports', active_time_minutes: 'Temps actif',
    successful: 'Calculs réussis', warnings: 'Calculs avec avertissement', failures: 'Échecs',
    average_compute_seconds: 'Temps moyen de calcul', calls: 'Appels API',
    active_keys: 'Clés actives', errors: 'Erreurs API', expiring_keys: 'Clés avec expiration'
  };

  const state = {
    bootstrap: null,
    selectedCompany: null,
    detail: null,
    detailTab: 'general',
    from: monthStart(),
    to: today()
  };

  async function adminApi(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      credentials: 'same-origin',
      headers: {...(options.headers || {})}
    });
    if (!response.ok) {
      let detail = response.status === 401
        ? 'Session super administrateur expirée. Reconnectez-vous.'
        : `Erreur ${response.status}`;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_) {}
      if (response.status === 401) {
        setTimeout(() => { location.href = '/login?mode=super_admin'; }, 650);
      }
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function showToast(message, error = false) {
    let toast = q('#admin-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'admin-toast';
      toast.className = 'message';
      toast.style.cssText = 'position:fixed;right:20px;bottom:20px;z-index:200;max-width:420px';
      document.body.append(toast);
    }
    toast.textContent = message;
    toast.className = `message ${error ? 'error' : 'success'}`;
    toast.classList.remove('hidden');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.add('hidden'), 4500);
  }

  function dialog(title, content, onSubmit) {
    let overlay = q('#admin-dialog');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'admin-dialog';
      overlay.className = 'admin-dialog';
      document.body.append(overlay);
    }
    overlay.innerHTML = `<section class="admin-dialog-card" role="dialog" aria-modal="true">
      <div class="admin-dialog-head"><h3>${escapeHtml(title)}</h3><button type="button" class="secondary" data-close>Fermer</button></div>
      <div data-dialog-body>${content}</div>
    </section>`;
    overlay.classList.add('open');
    const close = () => overlay.classList.remove('open');
    q('[data-close]', overlay)?.addEventListener('click', close);
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); }, {once: true});
    const form = q('form', overlay);
    if (form && onSubmit) {
      form.addEventListener('submit', async event => {
        event.preventDefault();
        const submit = q('[type="submit"]', form);
        if (submit) submit.disabled = true;
        try {
          await onSubmit(form, close);
        } catch (error) {
          showToast(error.message || String(error), true);
        } finally {
          if (submit) submit.disabled = false;
        }
      });
    }
    return overlay;
  }

  function showSecret(title, secret, note) {
    const overlay = dialog(title, `<div class="admin-notice warning">${escapeHtml(note)}</div>
      <div class="admin-secret">${escapeHtml(secret)}</div>
      <div class="admin-actions" style="margin-top:14px"><button type="button" class="primary" data-copy>Copier</button></div>`);
    q('[data-copy]', overlay)?.addEventListener('click', async () => {
      await navigator.clipboard.writeText(secret);
      showToast('Copié dans le presse-papiers.');
    });
  }

  function metricValue(metric) {
    const suffix = metric.unit === 'minutes' ? ' min' : metric.unit === 'seconds' ? ' s' : '';
    return `${Number(metric.value || 0).toLocaleString('fr-FR', {maximumFractionDigits: 2})}${suffix}`;
  }

  function renderDashboard(target, dashboard) {
    if (!target || !dashboard?.sections) return;
    target.innerHTML = Object.entries(dashboard.sections).map(([section, metrics]) => `
      <section class="admin-card">
        <h3>${sectionLabels[section] || section}</h3>
        <div class="admin-metric-grid">
          ${Object.entries(metrics).map(([key, metric]) => {
            const trendClass = metric.trend_pct > 0 ? 'admin-trend-up' : metric.trend_pct < 0 ? 'admin-trend-down' : '';
            const sign = metric.trend_pct > 0 ? '+' : '';
            return `<article class="admin-metric"><span>${metricLabels[key] || key}</span>
              <strong>${metricValue(metric)}</strong>
              <small>${metric.share_pct}% de la référence · <b class="${trendClass}">${sign}${metric.trend_pct}%</b> vs période précédente</small>
            </article>`;
          }).join('')}
        </div>
      </section>`).join('');
  }

  function renderAudit(target, events = []) {
    if (!target) return;
    target.innerHTML = events.length
      ? `<div class="admin-audit-list">${events.map(event => `<article class="admin-audit-item">
          <strong>${escapeHtml(event.action)}</strong>
          <small>${formatDate(event.created_at)} · ${escapeHtml(event.actor)}${event.tenant_id ? ` · ${escapeHtml(event.tenant_id)}` : ''}</small>
        </article>`).join('')}</div>`
      : '<div class="admin-empty">Aucun événement enregistré.</div>';
  }

  function companyRow(company) {
    return `<tr data-company="${escapeHtml(company.id)}">
      <td><strong>${escapeHtml(company.name)}</strong><small style="display:block;color:var(--muted)">${escapeHtml(company.id)}</small></td>
      <td><span class="admin-status-pill" data-status="${company.status}">${statusLabels[company.status] || company.status}</span></td>
      <td>${company.active_users_count}/${company.users_count}</td>
      <td>${company.active_api_keys_count}/${company.api_keys_count}</td>
      <td>${formatDate(company.updated_at || company.created_at)}</td>
      <td><button type="button" class="secondary" data-open-company>Ouvrir</button></td>
    </tr>`;
  }

  function renderCompanies() {
    const body = q('#admin-company-table tbody');
    if (!body || !state.bootstrap) return;
    const filter = (q('#admin-company-search')?.value || '').trim().toLowerCase();
    const status = q('#admin-company-status')?.value || 'all';
    const companies = state.bootstrap.companies.filter(company =>
      (!filter || `${company.name} ${company.id}`.toLowerCase().includes(filter)) &&
      (status === 'all' || company.status === status)
    );
    body.innerHTML = companies.length
      ? companies.map(companyRow).join('')
      : '<tr><td colspan="6" class="admin-empty">Aucune entreprise ne correspond aux filtres.</td></tr>';
    qa('[data-open-company]', body).forEach(button => {
      button.addEventListener('click', () => openCompany(button.closest('tr').dataset.company));
    });
  }

  function permissionRows(values, mode = 'company') {
    return state.bootstrap.permissions.map(permission => {
      const value = mode === 'company' ? Boolean(values[permission.key]) : values[permission.key] || 'inherited';
      const control = mode === 'company'
        ? `<input type="checkbox" data-permission="${permission.key}" ${value ? 'checked' : ''}>`
        : `<select data-permission="${permission.key}">
            <option value="inherited" ${value === 'inherited' ? 'selected' : ''}>Hérité</option>
            <option value="allow" ${value === 'allow' ? 'selected' : ''}>Autorisé</option>
            <option value="deny" ${value === 'deny' ? 'selected' : ''}>Refusé</option>
          </select>`;
      return `<div class="admin-permission-row"><div><strong>${escapeHtml(permission.label)}</strong>
        <small>${escapeHtml(permission.module)} · ${escapeHtml(permission.key)}</small></div>${control}</div>`;
    }).join('');
  }

  function collectPermissions(root, mode = 'company') {
    const output = {};
    qa('[data-permission]', root).forEach(control => {
      output[control.dataset.permission] = mode === 'company' ? control.checked : control.value;
    });
    return output;
  }

  function createCompanyDialog() {
    dialog('Inviter une entreprise', `<form><div class="admin-form-grid">
      <label class="full">Nom de l’entreprise<input name="company_name" required></label>
      <label>Prénom du contact principal<input name="first_name" required></label>
      <label>Nom du contact principal<input name="last_name" required></label>
      <label class="full">Adresse e-mail<input name="email" type="email" required></label>
      </div><div class="admin-actions" style="margin-top:16px"><button type="submit" class="primary">Créer l’invitation</button></div></form>`,
      async (form, close) => {
        const data = Object.fromEntries(new FormData(form));
        const result = await adminApi('/api/admin/companies', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        });
        close();
        showSecret(
          'Lien d’activation valable 24 heures',
          result.invitation.activation_url,
          result.email_delivery === 'smtp_not_configured'
            ? 'Le branchement SMTP n’est pas encore configuré. Copiez ce lien pour le transmettre manuellement.'
            : 'Invitation prête à être envoyée.'
        );
        await loadBootstrap();
      });
  }

  async function loadBootstrap() {
    state.bootstrap = await adminApi(`/api/admin/bootstrap?from=${encodeURIComponent(state.from)}&to=${encodeURIComponent(state.to)}`);
    renderDashboard(q('#admin-global-dashboard'), state.bootstrap.dashboard);
    renderCompanies();
    renderAudit(q('#admin-global-audit'), state.bootstrap.audit);
    const smtp = q('#admin-smtp-state');
    if (smtp) {
      smtp.className = `admin-notice ${state.bootstrap.email.configured ? 'success' : 'warning'}`;
      smtp.textContent = state.bootstrap.email.configured
        ? 'Le connecteur SMTP est configuré.'
        : 'Le connecteur SMTP n’est pas encore configuré. Les invitations restent copiables manuellement.';
    }
  }

  function userRows(users) {
    return users.map(user => `<tr data-user="${user.id}">
      <td><strong>${escapeHtml(user.first_name)} ${escapeHtml(user.last_name)}</strong><small style="display:block;color:var(--muted)">${escapeHtml(user.email)}</small></td>
      <td>${user.role === 'primary' ? 'Principal' : 'Utilisateur'}</td>
      <td><span class="admin-status-pill" data-status="${user.status === 'active' ? 'active' : user.status}">${escapeHtml(user.status)}</span></td>
      <td>${formatDate(user.activated_at || user.created_at)}</td>
      <td><div class="admin-actions"><button class="secondary" data-user-rights>Droits</button>
        ${!user.active ? '<button class="secondary" data-resend>Renvoyer</button>' : '<button class="row-delete" data-disable>Désactiver</button>'}
      </div></td>
    </tr>`).join('');
  }

  function apiKeyRows(keys) {
    return keys.map(key => `<tr data-key="${key.id}">
      <td><strong>${escapeHtml(key.label)}</strong><small style="display:block;color:var(--muted)">${escapeHtml(key.masked)}</small></td>
      <td>${key.scopes.length} droit(s)</td>
      <td>${key.expires_at ? formatDate(key.expires_at) : 'Sans expiration'}</td>
      <td><span class="admin-status-pill" data-status="${key.active ? 'active' : 'suspended'}">${key.active ? 'Active' : key.revoked_at ? 'Révoquée' : key.expired ? 'Expirée' : 'Bloquée'}</span></td>
      <td><button class="row-delete" data-revoke ${key.revoked_at ? 'disabled' : ''}>Révoquer</button></td>
    </tr>`).join('');
  }

  function renderCompanyDetail() {
    const {company, users, api_keys: keys, dashboard, audit} = state.detail;
    q('#admin-company-list-view')?.classList.add('hidden');
    const detail = q('#admin-company-detail');
    if (!detail) return;
    detail.classList.add('active');
    detail.dataset.tenantId = company.id;
    q('#admin-company-title').textContent = company.name;
    q('#admin-company-subtitle').innerHTML = `<span class="admin-status-pill" data-status="${company.status}">${statusLabels[company.status] || company.status}</span> · ${company.users_count} utilisateur(s) · ${company.api_keys_count} clé(s) API`;

    q('#admin-company-general').innerHTML = `
      ${company.profile.pending_validation ? '<div class="admin-notice warning">Des informations sensibles sont en attente de validation.</div>' : ''}
      <div class="admin-grid">
        <section class="admin-card"><h3>Fiche entreprise</h3><dl>
          <dt>Raison sociale</dt><dd>${escapeHtml(company.profile.legal_name || company.name)}</dd>
          <dt>Adresse</dt><dd>${escapeHtml(company.profile.address || 'À compléter')}</dd>
          <dt>Pays</dt><dd>${escapeHtml(company.profile.country || 'À compléter')}</dd>
          <dt>Contact</dt><dd>${escapeHtml(`${company.profile.contact_first_name || ''} ${company.profile.contact_last_name || ''}`.trim() || 'À compléter')} · ${escapeHtml(company.profile.contact_email || '')}</dd>
          <dt>Téléphone</dt><dd>${escapeHtml(company.profile.phone || 'À compléter')}</dd>
          <dt>SIRET</dt><dd>${escapeHtml(company.profile.siret || 'Facultatif')}</dd>
        </dl>${company.profile.validation_comment ? `<div class="admin-notice warning">${escapeHtml(company.profile.validation_comment)}</div>` : ''}</section>
        <section class="admin-card"><h3>État du compte</h3>
          <label>Statut<select id="admin-company-status-edit">${Object.entries(statusLabels).map(([value, label]) => `<option value="${value}" ${value === company.status ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
          <label style="margin-top:10px">Mode de suspension<select id="admin-suspension-mode"><option value="block" ${company.suspension_mode === 'block' ? 'selected' : ''}>Blocage total</option><option value="read_only" ${company.suspension_mode === 'read_only' ? 'selected' : ''}>Lecture seule</option></select></label>
          <label style="display:flex;gap:8px;align-items:center;margin-top:10px"><input id="admin-reactivate-keys" type="checkbox">Réactiver aussi les clés API valides</label>
          <div class="admin-actions" style="margin-top:14px"><button class="primary" id="admin-save-company-status">Appliquer</button><button class="secondary" id="admin-enter-assistance">Accéder à l’espace client</button></div>
        </section>
      </div>
      ${company.profile.pending_validation ? '<section class="admin-card" style="margin-top:16px"><h3>Décision sur la fiche</h3><div class="admin-actions"><button class="primary" data-profile-decision="approve">Valider</button><button class="secondary" data-profile-decision="request_correction">Demander une correction</button><button class="row-delete" data-profile-decision="reject">Refuser</button></div></section>' : ''}`;

    q('#admin-company-permissions').innerHTML = `<section class="admin-card"><div class="admin-section-title"><div><h3>Droits communs de l’entreprise</h3><p>Chaque utilisateur hérite de cette base.</p></div><button class="primary" id="admin-save-company-permissions">Enregistrer</button></div><div class="admin-permission-grid">${permissionRows(company.permissions, 'company')}</div></section>`;
    q('#admin-company-users').innerHTML = `<section class="admin-card"><div class="admin-section-title"><div><h3>Utilisateurs</h3><p>Invitations, droits et désactivation.</p></div><button class="primary" id="admin-add-user">+ Inviter un utilisateur</button></div><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Utilisateur</th><th>Rôle</th><th>Statut</th><th>Activation</th><th>Actions</th></tr></thead><tbody>${userRows(users)}</tbody></table></div></section>`;
    q('#admin-company-api').innerHTML = `<section class="admin-card"><div class="admin-section-title"><div><h3>Clés API</h3><p>Les secrets sont affichés une seule fois.</p></div><button class="primary" id="admin-add-api-key">+ Créer une clé</button></div><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Clé</th><th>Droits</th><th>Expiration</th><th>État</th><th>Action</th></tr></thead><tbody>${keys.length ? apiKeyRows(keys) : '<tr><td colspan="5" class="admin-empty">Aucune clé API.</td></tr>'}</tbody></table></div></section>`;

    const companyDashboard = q('#admin-company-dashboard');
    companyDashboard.innerHTML = `<section class="admin-card admin-dashboard-filter-card"><div class="admin-section-title"><div><h3>Usage de l’entreprise</h3><p>Vue consolidée ou filtrée par utilisateur.</p></div><div class="admin-filter-group"><label>Utilisateurs<select id="admin-dashboard-users" multiple size="${Math.min(Math.max(users.length, 2), 5)}">${users.map(user => `<option value="${user.id}">${escapeHtml(user.first_name)} ${escapeHtml(user.last_name)}</option>`).join('')}</select></label><button class="primary" id="admin-apply-user-filter">Appliquer</button><button class="secondary" id="admin-clear-user-filter">Vue entreprise</button></div></div></section><div id="admin-company-dashboard-metrics" class="admin-grid admin-dashboard-metrics"></div>`;
    renderDashboard(q('#admin-company-dashboard-metrics'), dashboard);
    renderAudit(q('#admin-company-audit'), audit);
    bindCompanyActions();
    switchDetailTab(state.detailTab);
  }

  function switchDetailTab(tab) {
    state.detailTab = tab;
    qa('[data-detail-tab]').forEach(button => button.classList.toggle('active', button.dataset.detailTab === tab));
    qa('.admin-detail-pane').forEach(pane => pane.classList.toggle('active', pane.id === `admin-company-${tab}`));
  }

  async function openCompany(tenantId) {
    state.selectedCompany = tenantId;
    window.__axioloadSelectedTenant = tenantId;
    state.detail = await adminApi(`/api/admin/companies/${encodeURIComponent(tenantId)}`);
    renderCompanyDetail();
  }

  function bindCompanyActions() {
    q('#admin-save-company-status')?.addEventListener('click', async () => {
      await adminApi(`/api/admin/companies/${state.selectedCompany}/status`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
          status: q('#admin-company-status-edit').value,
          suspension_mode: q('#admin-suspension-mode').value,
          reactivate_keys: q('#admin-reactivate-keys').checked
        })
      });
      showToast('Statut de l’entreprise mis à jour.');
      await openCompany(state.selectedCompany);
      await loadBootstrap();
    });

    q('#admin-enter-assistance')?.addEventListener('click', async () => {
      await adminApi(`/api/admin/companies/${state.selectedCompany}/assistance`, {method: 'POST'});
      location.href = '/';
    });

    qa('[data-profile-decision]').forEach(button => button.addEventListener('click', async () => {
      const decision = button.dataset.profileDecision;
      const comment = decision === 'approve' ? '' : prompt('Commentaire à transmettre au client :') || '';
      if (decision !== 'approve' && !comment.trim()) return;
      await adminApi(`/api/admin/companies/${state.selectedCompany}/profile-decision`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({decision, comment})
      });
      showToast('Décision enregistrée.');
      await openCompany(state.selectedCompany);
      await loadBootstrap();
    }));

    q('#admin-save-company-permissions')?.addEventListener('click', async () => {
      await adminApi(`/api/admin/companies/${state.selectedCompany}/permissions`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(collectPermissions(q('#admin-company-permissions'), 'company'))
      });
      showToast('Droits communs enregistrés.');
      await openCompany(state.selectedCompany);
    });

    q('#admin-add-user')?.addEventListener('click', inviteUserDialog);
    qa('[data-user-rights]').forEach(button => button.addEventListener('click', () => userRightsDialog(button.closest('tr').dataset.user)));
    qa('[data-resend]').forEach(button => button.addEventListener('click', async () => {
      const userId = button.closest('tr').dataset.user;
      const result = await adminApi(`/api/admin/companies/${state.selectedCompany}/users/${userId}/resend`, {method: 'POST'});
      showSecret('Nouvelle invitation valable 24 heures', result.activation_url, 'Le lien précédent a été invalidé.');
    }));
    qa('[data-disable]').forEach(button => button.addEventListener('click', async () => {
      const userId = button.closest('tr').dataset.user;
      if (!confirm('Désactiver cet utilisateur ?')) return;
      await adminApi(`/api/admin/companies/${state.selectedCompany}/users/${userId}/disable`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
      });
      showToast('Utilisateur désactivé.');
      await openCompany(state.selectedCompany);
    }));

    q('#admin-apply-user-filter')?.addEventListener('click', async () => {
      const selected = qa('#admin-dashboard-users option:checked').map(option => option.value);
      const params = new URLSearchParams({tenant_id: state.selectedCompany, from: state.from, to: state.to});
      if (selected.length) params.set('users', selected.join(','));
      renderDashboard(q('#admin-company-dashboard-metrics'), await adminApi(`/api/admin/dashboard?${params}`));
    });
    q('#admin-clear-user-filter')?.addEventListener('click', async () => {
      qa('#admin-dashboard-users option').forEach(option => { option.selected = false; });
      const params = new URLSearchParams({tenant_id: state.selectedCompany, from: state.from, to: state.to});
      renderDashboard(q('#admin-company-dashboard-metrics'), await adminApi(`/api/admin/dashboard?${params}`));
    });

    q('#admin-add-api-key')?.addEventListener('click', apiKeyDialog);
    qa('[data-revoke]').forEach(button => button.addEventListener('click', async () => {
      if (!confirm('Révoquer définitivement cette clé ?')) return;
      await adminApi(`/api/admin/companies/${state.selectedCompany}/api-keys/${button.closest('tr').dataset.key}`, {method: 'DELETE'});
      showToast('Clé révoquée.');
      await openCompany(state.selectedCompany);
    }));
  }

  function inviteUserDialog() {
    dialog('Inviter un utilisateur', `<form><div class="admin-form-grid">
      <label>Prénom<input name="first_name" required></label><label>Nom<input name="last_name" required></label>
      <label class="full">Adresse e-mail<input name="email" type="email" required></label></div>
      <details style="margin-top:14px"><summary>Préparer les exceptions de droits</summary><div class="admin-permission-grid" style="margin-top:10px">${permissionRows({}, 'user')}</div></details>
      <div class="admin-actions" style="margin-top:16px"><button class="primary" type="submit">Créer l’invitation</button></div></form>`,
      async (form, close) => {
        const payload = Object.fromEntries(new FormData(form));
        payload.permissions = collectPermissions(form, 'user');
        const result = await adminApi(`/api/admin/companies/${state.selectedCompany}/users`, {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
        });
        close();
        showSecret('Invitation utilisateur valable 24 heures', result.invitation.activation_url, 'Le nouvel utilisateur choisira lui-même son mot de passe.');
        await openCompany(state.selectedCompany);
      });
  }

  function userRightsDialog(userId) {
    const user = state.detail.users.find(item => item.id === userId);
    dialog(`Droits de ${user.first_name} ${user.last_name}`, `<form>
      <div class="admin-notice">Hérité reprend la règle commune. Autorisé ou Refusé remplace cette règle.</div>
      <div class="admin-permission-grid">${permissionRows(user.permission_overrides, 'user')}</div>
      <div class="admin-actions" style="margin-top:16px"><button class="primary" type="submit">Enregistrer</button></div></form>`,
      async (form, close) => {
        await adminApi(`/api/admin/companies/${state.selectedCompany}/users/${userId}/permissions`, {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(collectPermissions(form, 'user'))
        });
        close();
        showToast('Droits individuels enregistrés.');
        await openCompany(state.selectedCompany);
      });
  }

  function apiKeyDialog() {
    const allowed = Object.entries(state.detail.company.permissions).filter(([, enabled]) => enabled).map(([key]) => key);
    dialog('Créer une clé API', `<form><div class="admin-form-grid">
      <label class="full">Nom de la clé<input name="label" placeholder="ERP production" required></label>
      <label class="full">Expiration<input name="expires_at" type="datetime-local"><small>Laissez vide pour une clé sans expiration.</small></label></div>
      <h4>Droits de la clé</h4><div class="admin-permission-grid">${state.bootstrap.permissions.filter(item => allowed.includes(item.key)).map(item => `<label class="admin-permission-row"><span><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.key)}</small></span><input type="checkbox" data-scope="${item.key}"></label>`).join('')}</div>
      <div class="admin-actions" style="margin-top:16px"><button class="primary" type="submit">Générer la clé</button></div></form>`,
      async (form, close) => {
        const data = new FormData(form);
        const rawExpiry = data.get('expires_at');
        const result = await adminApi(`/api/admin/companies/${state.selectedCompany}/api-keys`, {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
            label: data.get('label'),
            expires_at: rawExpiry ? new Date(rawExpiry).toISOString() : null,
            scopes: qa('[data-scope]:checked', form).map(input => input.dataset.scope)
          })
        });
        close();
        showSecret('Clé API visible une seule fois', result.secret, 'Copiez-la maintenant. Seule son empreinte sera conservée.');
        await openCompany(state.selectedCompany);
      });
  }

  function buildAdminPanel() {
    if (q('#open-admin')) return;
    const topbar = q('.topbar');
    const settingsButton = q('#open-settings');
    const main = q('main');
    if (!topbar || !settingsButton || !main) return;

    let actions = q('.topbar-actions');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'topbar-actions';
      settingsButton.before(actions);
      actions.append(settingsButton);
    }

    const button = document.createElement('button');
    button.id = 'open-admin';
    button.className = 'settings-access admin-access';
    button.type = 'button';
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 4.5 5.2v5.9c0 4.8 3.1 9.2 7.5 10.9 4.4-1.7 7.5-6.1 7.5-10.9V5.2L12 2Zm0 4.1a2.7 2.7 0 1 1 0 5.4 2.7 2.7 0 0 1 0-5.4Zm4.2 10.4H7.8v-.7c0-1.9 2.8-3 4.2-3s4.2 1.1 4.2 3v.7Z"/></svg><span>Super Admin</span>';
    actions.prepend(button);

    const panel = document.createElement('section');
    panel.id = 'tab-admin';
    panel.className = 'panel tab-panel admin-page';
    panel.innerHTML = `
      <div class="panel-heading admin-heading"><div><div class="eyebrow">Administration générale</div><h2>Pilotage AxioLoad</h2><p class="section-intro">Entreprises, utilisateurs, accès, activité et assistance.</p></div><button id="close-admin" class="secondary">Retour à l’application</button></div>
      <div id="admin-smtp-state" class="admin-notice warning"></div>
      <div class="admin-shell"><nav class="admin-nav">
        <button class="secondary active" data-admin-view="overview">Vue globale</button>
        <button class="secondary" data-admin-view="companies">Entreprises</button>
        <button class="secondary" data-admin-view="audit">Journal d’audit</button>
      </nav><div class="admin-content">
        <section id="admin-view-overview" class="admin-view active"><div class="admin-toolbar"><div><h3>Dashboard global</h3><p>Le mois en cours est affiché par défaut.</p></div><div class="admin-filter-group"><label>Du<input id="admin-period-from" type="date" value="${state.from}"></label><label>Au<input id="admin-period-to" type="date" value="${state.to}"></label><button class="primary" id="admin-apply-period">Appliquer</button></div></div><div id="admin-global-dashboard" class="admin-grid"></div></section>
        <section id="admin-view-companies" class="admin-view"><div id="admin-company-list-view"><div class="admin-toolbar"><div><h3>Entreprises clientes</h3><p>Création, validation et administration.</p></div><button class="primary" id="admin-create-company">+ Inviter une entreprise</button></div><div class="admin-filter-group" style="margin-bottom:12px"><label>Recherche<input id="admin-company-search" placeholder="Nom ou identifiant"></label><label>Statut<select id="admin-company-status"><option value="all">Tous</option>${Object.entries(statusLabels).map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select></label></div><div class="admin-table-wrap"><table id="admin-company-table" class="admin-table"><thead><tr><th>Entreprise</th><th>Statut</th><th>Utilisateurs</th><th>Clés API</th><th>Mise à jour</th><th></th></tr></thead><tbody></tbody></table></div></div>
          <section id="admin-company-detail" class="admin-detail"><div class="admin-detail-head"><div><button id="admin-back-companies" class="secondary">← Toutes les entreprises</button><h3 id="admin-company-title"></h3><p id="admin-company-subtitle"></p></div></div><div class="admin-detail-tabs"><button class="secondary active" data-detail-tab="general">Général</button><button class="secondary" data-detail-tab="permissions">Accès</button><button class="secondary" data-detail-tab="users">Utilisateurs</button><button class="secondary" data-detail-tab="dashboard">Dashboard</button><button class="secondary" data-detail-tab="api">API</button><button class="secondary" data-detail-tab="audit">Audit</button></div><div id="admin-company-general" class="admin-detail-pane active"></div><div id="admin-company-permissions" class="admin-detail-pane"></div><div id="admin-company-users" class="admin-detail-pane"></div><div id="admin-company-dashboard" class="admin-detail-pane admin-grid"></div><div id="admin-company-api" class="admin-detail-pane"></div><div id="admin-company-audit" class="admin-detail-pane"></div></section>
        </section>
        <section id="admin-view-audit" class="admin-view"><div class="admin-toolbar"><div><h3>Journal d’audit global</h3><p>Les changements sensibles restent traçables.</p></div></div><div id="admin-global-audit"></div></section>
      </div></div>`;
    main.append(panel);

    let previousTab = q('.tab.active')?.dataset.tab || 'vehicles';
    const open = async () => {
      previousTab = q('.tab.active')?.dataset.tab || previousTab;
      qa('.tab').forEach(item => item.classList.remove('active'));
      qa('.tab-panel').forEach(item => item.classList.remove('active'));
      panel.classList.add('active');
      button.classList.add('active');
      try {
        await loadBootstrap();
      } catch (error) {
        showToast(error.message || String(error), true);
      }
    };
    const close = () => {
      panel.classList.remove('active');
      button.classList.remove('active');
      if (typeof switchTab === 'function') switchTab(previousTab);
    };

    button.addEventListener('click', open);
    q('#close-admin', panel).addEventListener('click', close);
    qa('[data-admin-view]', panel).forEach(nav => nav.addEventListener('click', () => {
      qa('[data-admin-view]', panel).forEach(item => item.classList.toggle('active', item === nav));
      qa('.admin-view', panel).forEach(view => view.classList.toggle('active', view.id === `admin-view-${nav.dataset.adminView}`));
    }));
    q('#admin-apply-period', panel).addEventListener('click', async () => {
      state.from = q('#admin-period-from').value;
      state.to = q('#admin-period-to').value;
      await loadBootstrap();
    });
    q('#admin-create-company', panel).addEventListener('click', createCompanyDialog);
    q('#admin-company-search', panel).addEventListener('input', renderCompanies);
    q('#admin-company-status', panel).addEventListener('change', renderCompanies);
    q('#admin-back-companies', panel).addEventListener('click', () => {
      q('#admin-company-detail').classList.remove('active');
      q('#admin-company-list-view').classList.remove('hidden');
    });
    qa('[data-detail-tab]', panel).forEach(tab => tab.addEventListener('click', () => switchDetailTab(tab.dataset.detailTab)));
  }

  async function installAssistanceBanner() {
    try {
      const response = await fetch('/api/company/context', {credentials: 'same-origin'});
      const context = response.ok ? await response.json() : null;
      if (!context) return;
      if (context.mode === 'assistance' && context.company?.id !== 'local') {
        const banner = document.createElement('div');
        banner.className = 'admin-assistance-banner';
        banner.innerHTML = `<strong>Mode assistance · ${escapeHtml(context.company.name)} · Toute intervention est tracée.</strong><button type="button">Quitter l’espace client</button>`;
        document.body.prepend(banner);
        q('button', banner).addEventListener('click', async () => {
          await fetch('/api/admin/assistance/exit', {method: 'POST', credentials: 'same-origin'});
          location.href = '/';
        });
      }
      applyPermissionVisibility(context.permissions || {});
      installCompanyProfile(context);
      installVehicleGovernance(context);
    } catch (_) {}
  }

  function installCompanyProfile(context) {
    if (!context?.company || context.company.id === 'local' || context.mode === 'assistance') return;
    q('#open-admin')?.classList.add('hidden');
    const settings = q('#tab-settings .settings-sections');
    if (!settings || q('#company-profile-card')) return;
    q('#account-form')?.closest('.settings-card')?.classList.add('hidden');
    q('#api-settings-title')?.closest('.settings-card')?.classList.add('hidden');
    const profile = context.company.profile || {};
    const card = document.createElement('section');
    card.id = 'company-profile-card';
    card.className = 'settings-card full-width';
    card.innerHTML = `<div class="settings-card-heading"><div class="settings-icon" aria-hidden="true">E</div><div><h3>Fiche entreprise</h3><p>Données administratives de votre entreprise.</p></div></div>
      ${profile.pending_validation ? '<div class="admin-notice warning">Une modification sensible reste en attente de validation.</div>' : ''}
      ${profile.validation_comment ? `<div class="admin-notice warning">${escapeHtml(profile.validation_comment)}</div>` : ''}
      <form id="company-profile-form" class="settings-form"><div class="admin-form-grid">
        <label class="full">Raison sociale<input name="legal_name" value="${escapeHtml(profile.legal_name || context.company.name)}" required></label>
        <label class="full">SIRET facultatif<input name="siret" value="${escapeHtml(profile.siret || '')}"></label>
        <label class="full">Adresse complète<textarea name="address" rows="3" required>${escapeHtml(profile.address || '')}</textarea></label>
        <label>Pays<input name="country" value="${escapeHtml(profile.country || '')}" required></label>
        <label>Téléphone<input name="phone" value="${escapeHtml(profile.phone || '')}" required></label>
        <label>Prénom du contact<input name="contact_first_name" value="${escapeHtml(profile.contact_first_name || '')}" required></label>
        <label>Nom du contact<input name="contact_last_name" value="${escapeHtml(profile.contact_last_name || '')}" required></label>
        <label class="full">E-mail de contact<input name="contact_email" type="email" value="${escapeHtml(profile.contact_email || '')}" required></label>
      </div><div class="settings-actions"><button class="primary" type="submit">Enregistrer la fiche</button></div></form><div id="company-profile-message" class="message hidden"></div>`;
    settings.prepend(card);
    q('#company-profile-form', card).addEventListener('submit', async event => {
      event.preventDefault();
      const response = await fetch('/api/company/profile', {
        method: 'PUT', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))
      });
      const body = await response.json().catch(() => ({}));
      const box = q('#company-profile-message', card);
      box.textContent = response.ok ? 'Fiche enregistrée.' : body.detail || 'Enregistrement impossible.';
      box.className = `message ${response.ok ? 'success' : 'error'}`;
      box.classList.remove('hidden');
    });
  }

  function applyPermissionVisibility(permissions) {
    const map = {
      vehicles: 'vehicles.view', data: 'data.view', results: 'results.view',
      history: 'history.view', route: 'route.view', total: 'total.view'
    };
    qa('.tab[data-tab]').forEach(tab => {
      const permission = map[tab.dataset.tab];
      if (permission && permissions[permission] === false) tab.hidden = true;
    });
  }

  function installVehicleGovernance(context) {
    const tableBody = q('#vehicle-table tbody');
    if (!tableBody) return;
    const decorate = () => {
      const vehicles = window.PLO_VEHICLES || [];
      qa('tr', tableBody).forEach(row => {
        const modelId = q('[data-v="model_id"]', row)?.value;
        const vehicle = vehicles.find(item => item.model_id === modelId);
        if (!vehicle) return;
        row.dataset.vehicleOrigin = vehicle.origin || 'custom';
        if (vehicle.origin === 'global') {
          row.classList.add('vehicle-global-row');
          qa('[data-v]', row).forEach(input => { input.disabled = true; });
          const deleteButton = q('.vehicle-delete', row);
          if (deleteButton && !deleteButton.dataset.duplicateReady) {
            const duplicate = deleteButton.cloneNode(true);
            duplicate.dataset.duplicateReady = '1';
            duplicate.textContent = 'Dupliquer';
            duplicate.className = 'secondary small';
            deleteButton.replaceWith(duplicate);
            duplicate.addEventListener('click', async event => {
              event.preventDefault();
              const newId = prompt('Identifiant de la copie personnalisée :', `${modelId}_custom`);
              if (!newId) return;
              const name = prompt('Nom de la copie :', `${vehicle.name} personnalisé`) || `${vehicle.name} personnalisé`;
              const response = await fetch(`/api/vehicles/${encodeURIComponent(modelId)}/duplicate`, {
                method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({model_id: newId, name})
              });
              if (!response.ok) throw new Error((await response.json()).detail || 'Duplication impossible');
              if (typeof loadVehicles === 'function') await loadVehicles();
              showToast('Véhicule dupliqué.');
            });
          }
        } else {
          const nameCell = row.children[1];
          if (nameCell && !q('.admin-origin-pill', nameCell)) {
            nameCell.insertAdjacentHTML('beforeend', '<span class="admin-origin-pill custom">Personnalisé</span>');
          }
        }
      });
      if (context.mode !== 'assistance') q('#reset-vehicles')?.classList.add('hidden');
    };
    new MutationObserver(decorate).observe(tableBody, {childList: true, subtree: true});
    decorate();
  }

  function installHistoryAnnotations() {
    const list = q('#history-list');
    if (!list) return;
    const annotate = async () => {
      let cache = [];
      try {
        const response = await fetch('/api/history', {credentials: 'same-origin'});
        cache = response.ok ? await response.json() : [];
      } catch (_) { return; }
      qa('.history-item', list).forEach(article => {
        const run = cache.find(item => article.textContent.includes(item.id.slice(0, 8)));
        if (!run || article.dataset.adminAnnotated) return;
        article.dataset.adminAnnotated = '1';
        const top = q('.history-top-row', article);
        if (run.support_intervention && top) top.insertAdjacentHTML('beforeend', '<span class="admin-support-pill">Intervention du support AxioLoad</span>');
      });
    };
    new MutationObserver(annotate).observe(list, {childList: true, subtree: true});
  }

  function installActivityTracking() {
    let lastAction = Date.now();
    ['pointerdown', 'keydown', 'scroll', 'change'].forEach(eventName => {
      document.addEventListener(eventName, () => { lastAction = Date.now(); }, {passive: true});
    });
    setInterval(() => {
      if (!document.hidden && Date.now() - lastAction <= 15 * 60 * 1000) {
        fetch('/api/company/activity', {
          method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({active_seconds: 60, event_type: 'activity'})
        }).catch(() => {});
      }
    }, 60 * 1000);
  }

  const init = () => {
    buildAdminPanel();
    installAssistanceBanner();
    installHistoryAnnotations();
    installActivityTracking();
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
