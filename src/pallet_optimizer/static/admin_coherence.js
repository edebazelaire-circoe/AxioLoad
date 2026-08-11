(() => {
  'use strict';

  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));

  function statePill(ok, yes = 'OK', no = 'À corriger') {
    return `<span class="coherence-pill ${ok ? 'ok' : 'warn'}">${ok ? yes : no}</span>`;
  }

  function render(target, snapshot) {
    if (!target || !snapshot) return;
    const versions = snapshot.versions || {};
    const deployment = snapshot.deployment || {};
    const warnings = snapshot.warnings || [];
    const modules = snapshot.modules || [];

    target.innerHTML = `
      <section class="admin-card coherence-card">
        <div class="admin-section-title"><div><h3>Cohérence produit</h3><p>État réel des modules, versions et garde-fous du déploiement.</p></div>
          ${warnings.length ? `<span class="coherence-counter">${warnings.length} point(s) à traiter</span>` : '<span class="coherence-pill ok">Aligné</span>'}
        </div>
        <div class="coherence-version-grid">
          <div><small>Runtime</small><strong>${escapeHtml(versions.runtime || 'inconnue')}</strong></div>
          <div><small>Distribution</small><strong>${escapeHtml(versions.distribution || 'inconnue')}</strong></div>
          <div><small>API FastAPI</small><strong>${escapeHtml(versions.api || 'inconnue')}</strong></div>
        </div>
      </section>
      <section class="admin-card coherence-card">
        <h3>Modules visibles côté client</h3>
        <div class="coherence-module-grid">${modules.map(module => `
          <article><div><strong>${escapeHtml(module.label)}</strong><small>${module.permissions.map(escapeHtml).join(' · ')}</small></div>${statePill(Boolean(module.available), 'Disponible', 'Incomplet')}</article>`).join('')}</div>
      </section>
      <section class="admin-card coherence-card">
        <h3>Configuration de sécurité</h3>
        <div class="coherence-module-grid">
          <article><div><strong>Comptes de test</strong><small>Doivent être désactivés en production.</small></div>${statePill(!deployment.test_accounts_enabled, 'Désactivés', 'ACTIFS')}</article>
          <article><div><strong>Cookie Secure</strong><small>Protection de session sur HTTPS.</small></div>${statePill(Boolean(deployment.cookie_secure), 'Activé', 'Désactivé')}</article>
          <article><div><strong>Secret Super Admin</strong><small>Doit provenir de l’environnement, jamais du dépôt.</small></div>${statePill(Boolean(deployment.super_admin_secret_configured), 'Configuré', 'Absent')}</article>
          <article><div><strong>Clé de chiffrement IA</strong><small>Protège les clés API IA stockées.</small></div>${statePill(Boolean(deployment.document_secret_configured), 'Configurée', 'Absente')}</article>
        </div>
      </section>
      ${warnings.length ? `<section class="admin-card coherence-card"><h3>Alertes</h3><div class="coherence-alerts">${warnings.map(item => `<div class="admin-notice ${item.severity === 'critical' ? 'warning' : ''}"><strong>${escapeHtml(item.code)}</strong><span>${escapeHtml(item.message)}</span></div>`).join('')}</div></section>` : ''}`;
  }

  async function load() {
    const panel = document.querySelector('#admin-view-overview');
    if (!panel) {
      setTimeout(load, 120);
      return;
    }
    if (panel.querySelector('#admin-coherence-center')) return;
    const target = document.createElement('div');
    target.id = 'admin-coherence-center';
    target.className = 'admin-grid coherence-center';
    panel.append(target);
    try {
      const response = await fetch('/api/admin/coherence', {credentials: 'same-origin'});
      if (!response.ok) {
        target.remove();
        return;
      }
      render(target, await response.json());
    } catch (_) {
      target.remove();
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load, {once: true});
  else load();
})();
