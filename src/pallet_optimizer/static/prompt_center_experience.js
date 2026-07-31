(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  let analyticsRuns = [];
  let contextPromise = null;

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body?.detail || `Erreur ${response.status}`);
    return body;
  }

  function messageBox(root, text, error = false) {
    let box = q('[data-prompt-message]', root);
    if (!box) {
      box = document.createElement('div');
      box.dataset.promptMessage = '1';
      root.append(box);
    }
    box.textContent = text;
    box.className = `message ${error ? 'error' : 'success'}`;
  }

  function ensurePromptPanel() {
    let panel = q('#tab-prompt-center');
    if (panel) return panel;
    panel = document.createElement('section');
    panel.id = 'tab-prompt-center';
    panel.className = 'panel tab-panel prompt-center-page';
    panel.innerHTML = `
      <div class="panel-heading prompt-center-heading">
        <div>
          <div class="eyebrow">Bibliothèque documentaire</div>
          <h2>Prompts de contrôle documentaire</h2>
          <p class="section-intro">Les règles affichées dépendent de votre rôle dans AxioLoad.</p>
        </div>
        <span class="prompt-center-version" data-prompt-version></span>
      </div>
      <div id="prompt-center-content" class="prompt-center-content"><div class="admin-empty">Chargement…</div></div>`;
    q('main')?.append(panel);
    panel.addEventListener('click', handlePromptSave);
    return panel;
  }

  function activateDatabaseWorkspace(promptButton) {
    document.body.dataset.workspace = 'database';
    qa('[data-workspace]').forEach(button => {
      const active = button.dataset.workspace === 'database';
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    qa('[data-workspace-group]').forEach(button => {
      button.hidden = button.dataset.workspaceGroup !== 'database';
      button.classList.toggle('active', button === promptButton);
      button.setAttribute('aria-selected', String(button === promptButton));
    });
    const nav = q('nav.tabs');
    if (nav) nav.dataset.workspace = 'database';
  }

  async function openPromptCenter(promptButton) {
    const panel = ensurePromptPanel();
    activateDatabaseWorkspace(promptButton);
    qa('.tab-panel').forEach(item => item.classList.toggle('active', item === panel));
    await loadPromptCenter(panel);
  }

  function systemPromptCard(profile) {
    const status = profile.is_default ? 'Base fournie' : `Version ${profile.version}`;
    return `<details class="prompt-editor-card" data-prompt-kind="system" data-profile-key="${escapeHtml(profile.key)}">
      <summary><span><strong>${escapeHtml(profile.title)}</strong><small>${escapeHtml(profile.description)}</small></span><b>${escapeHtml(status)}</b></summary>
      <div class="prompt-editor-body">
        <label>Prompt système<textarea rows="9" maxlength="16000" data-prompt-text>${escapeHtml(profile.instructions)}</textarea></label>
        <div class="prompt-editor-actions"><small>Dernière modification : ${escapeHtml(profile.updated_by || 'system')}</small><button type="button" class="primary" data-save-prompt>Enregistrer</button></div>
        <div data-prompt-message></div>
      </div>
    </details>`;
  }

  function renderSuperAdminPrompts(root, data) {
    root.innerHTML = `
      <div class="prompt-role-notice super-admin"><strong>Centre de gestion</strong><span>Vous pouvez modifier le socle commun et tous les prompts système. Chaque enregistrement crée une nouvelle version.</span></div>
      <details class="prompt-editor-card prompt-core-card" open data-prompt-kind="core">
        <summary><span><strong>Socle commun de sécurité et de méthode</strong><small>Règles appliquées à toutes les analyses documentaires.</small></span><b>Version ${data.core.version}</b></summary>
        <div class="prompt-editor-body">
          <label>Socle commun<textarea rows="13" maxlength="20000" data-prompt-text>${escapeHtml(data.core.instructions)}</textarea></label>
          <div class="prompt-editor-actions"><small>Dernière modification : ${escapeHtml(data.core.updated_by || 'system')}</small><button type="button" class="primary" data-save-prompt>Enregistrer le socle</button></div>
          <div data-prompt-message></div>
        </div>
      </details>
      <div class="prompt-section-title"><h3>Prompts système par cas documentaire</h3><p>Ces bases sont combinées au socle commun, puis au complément propre à chaque entreprise.</p></div>
      <div class="prompt-editor-list">${data.profiles.map(systemPromptCard).join('')}</div>`;
  }

  function companyPromptCard(profile, editable) {
    const status = profile.configured ? `Complément v${profile.company_version}` : 'Aucun complément';
    return `<details class="prompt-editor-card company-prompt-card" data-prompt-kind="company" data-left-type="${escapeHtml(profile.left_type)}" data-right-type="${escapeHtml(profile.right_type)}">
      <summary><span><strong>${escapeHtml(profile.title)}</strong><small>${escapeHtml(profile.description)}</small></span><b>${escapeHtml(status)}</b></summary>
      <div class="prompt-editor-body">
        <details class="prompt-base-preview"><summary>Consulter la base AxioLoad, version ${escapeHtml(profile.system_version)}</summary><pre>${escapeHtml(profile.system_instructions)}</pre></details>
        <label>Complément métier de l’entreprise<textarea rows="7" maxlength="12000" data-prompt-text ${editable ? '' : 'disabled'} placeholder="Ajoutez uniquement les règles propres à votre entreprise ou à ce rapprochement documentaire.">${escapeHtml(profile.company_instructions)}</textarea></label>
        <div class="prompt-editor-actions"><small>${editable ? 'Ce complément s’ajoute à la base AxioLoad sans la remplacer.' : 'Consultation seule. La modification est réservée à l’administrateur principal.'}</small>${editable ? '<button type="button" class="primary" data-save-prompt>Enregistrer le complément</button>' : ''}</div>
        <div data-prompt-message></div>
      </div>
    </details>`;
  }

  function renderCompanyPrompts(root, data) {
    root.innerHTML = `
      <div class="prompt-role-notice company"><strong>${escapeHtml(data.company?.name || 'Entreprise')}</strong><span>La base AxioLoad reste en lecture seule. Seul le complément métier de l’entreprise peut être adapté.</span></div>
      ${data.is_primary_admin ? '' : '<div class="admin-notice warning">Vous pouvez consulter les prompts, mais seul l’administrateur principal de l’entreprise peut enregistrer un complément.</div>'}
      <div class="prompt-section-title"><h3>Compléments métier par cas documentaire</h3><p>Chaque complément est appliqué uniquement aux contrôles de votre entreprise.</p></div>
      <div class="prompt-editor-list">${data.profiles.map(profile => companyPromptCard(profile, data.is_primary_admin)).join('')}</div>`;
  }

  async function loadPromptCenter(panel) {
    const root = q('#prompt-center-content', panel);
    root.innerHTML = '<div class="admin-empty">Chargement des prompts…</div>';
    try {
      const data = await api('/api/prompt-center');
      q('[data-prompt-version]', panel).textContent = data.system_prompt_version || '';
      if (data.mode === 'super_admin') renderSuperAdminPrompts(root, data);
      else renderCompanyPrompts(root, data);
    } catch (error) {
      root.innerHTML = `<div class="admin-notice warning">${escapeHtml(error.message || String(error))}</div>`;
    }
  }

  async function handlePromptSave(event) {
    const button = event.target.closest('[data-save-prompt]');
    if (!button) return;
    const card = button.closest('[data-prompt-kind]');
    const textarea = q('[data-prompt-text]', card);
    const kind = card.dataset.promptKind;
    let endpoint = '/api/prompt-center/core';
    if (kind === 'system') endpoint = `/api/prompt-center/system/${encodeURIComponent(card.dataset.profileKey)}`;
    if (kind === 'company') endpoint = `/api/prompt-center/company/${encodeURIComponent(card.dataset.leftType)}/${encodeURIComponent(card.dataset.rightType)}`;
    button.disabled = true;
    const original = button.textContent;
    button.textContent = 'Enregistrement…';
    try {
      const result = await api(endpoint, {method: 'PUT', body: JSON.stringify({instructions: textarea.value})});
      const badge = q('summary > b', card);
      if (badge) badge.textContent = kind === 'company' ? `Complément v${result.version}` : `Version ${result.version}`;
      messageBox(card, 'Prompt enregistré et versionné.');
    } catch (error) {
      messageBox(card, error.message || String(error), true);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function removeLegacyPromptAdminView() {
    q('[data-admin-view="document-prompts"]')?.remove();
    q('#admin-view-document-prompts')?.remove();
  }

  function polishManagementCenter() {
    const button = q('#open-admin');
    const panel = q('#tab-admin');
    if (button) {
      const label = q('span', button);
      if (label) label.textContent = 'Centre de gestion';
      button.setAttribute('aria-label', 'Ouvrir le Centre de gestion');
    }
    if (!panel) return;
    const eyebrow = q('.admin-heading .eyebrow', panel);
    const title = q('.admin-heading h2', panel);
    const intro = q('.admin-heading .section-intro', panel);
    if (eyebrow) eyebrow.textContent = 'Centre de gestion';
    if (title) title.textContent = 'Pilotage des comptes et des utilisateurs';
    if (intro) intro.textContent = 'Dashboard, entreprises, utilisateurs, accès, activité et assistance.';
    const overview = q('[data-admin-view="overview"]', panel);
    if (overview) overview.textContent = 'Dashboard';
    const nav = q('.admin-nav', panel);
    if (nav && !q('[data-admin-view="costs-roadmap"]', nav)) {
      const costs = document.createElement('button');
      costs.type = 'button';
      costs.className = 'secondary management-costs-roadmap';
      costs.dataset.adminView = 'costs-roadmap';
      costs.disabled = true;
      costs.innerHTML = '<span>Coûts</span><small>À venir</small>';
      nav.append(costs);
    }
    removeLegacyPromptAdminView();
  }

  async function applyRoleLayout() {
    if (!contextPromise) {
      contextPromise = fetch('/api/company/context', {credentials: 'same-origin'})
        .then(response => response.ok ? response.json() : null)
        .catch(() => null);
    }
    const context = await contextPromise;
    const directManagement = context?.mode === 'assistance' && context?.company?.id === 'local';
    if (directManagement) q('#open-settings')?.classList.add('hidden');
  }

  function ensureHistoryAnalytics() {
    const dashboard = q('.settings-card[aria-labelledby="dashboard-title"]');
    const history = q('#tab-history');
    const filters = q('.history-filters', history || document);
    if (!dashboard || !history || !filters) return false;
    if (dashboard.parentElement !== history) filters.before(dashboard);
    dashboard.classList.add('history-dashboard-card');
    const title = q('#dashboard-title', dashboard);
    const intro = title?.parentElement?.querySelector('p');
    if (title) title.textContent = 'Vue d’ensemble de l’historique';
    if (intro) intro.textContent = 'Repérez les statuts, les volumes et les calculs atypiques avant de parcourir le détail des dossiers.';
    q('.dashboard-grid', dashboard)?.classList.add('legacy-dashboard-charts');
    if (!q('#history-analytics', dashboard)) {
      const block = document.createElement('div');
      block.id = 'history-analytics';
      block.className = 'history-analytics';
      block.innerHTML = `
        <div id="history-status-tags" class="history-status-tags"></div>
        <section class="history-scatter-card">
          <div><h4>Nuage des optimisations</h4><p>Métrage linéaire en abscisse, temps de calcul en ordonnée. La taille représente le nombre de véhicules.</p></div>
          <canvas id="history-scatter" width="1100" height="360" aria-label="Nuage de points des optimisations"></canvas>
          <div class="history-scatter-legend"><span data-tone="success">Réussi / validé</span><span data-tone="warning">À revoir</span><span data-tone="failure">Échec</span></div>
        </section>`;
      const cards = q('#dashboard-cards', dashboard);
      if (cards) cards.before(block); else q('.settings-card-heading', dashboard)?.after(block);
    }
    const settingsIntro = q('#settings-title')?.parentElement?.querySelector('.section-intro');
    if (settingsIntro) settingsIntro.textContent = 'Gérez votre compte, l’apparence et les connexions de l’application.';
    return true;
  }

  function toneFor(status) {
    const normalized = String(status || '').toLowerCase();
    if (['failure', 'failed', 'rejected', 'error'].includes(normalized)) return 'failure';
    if (['warning', 'review', 'pending'].includes(normalized)) return 'warning';
    return 'success';
  }

  function renderStatusTags(runs) {
    const root = q('#history-status-tags');
    if (!root) return;
    const counts = runs.reduce((output, run) => {
      output[toneFor(run.status)] += 1;
      return output;
    }, {success: 0, warning: 0, failure: 0});
    root.innerHTML = `
      <span class="history-status-tag total"><strong>${runs.length}</strong><small>Total</small></span>
      <span class="history-status-tag success"><strong>${counts.success}</strong><small>Réussis / validés</small></span>
      <span class="history-status-tag warning"><strong>${counts.warning}</strong><small>À revoir</small></span>
      <span class="history-status-tag failure"><strong>${counts.failure}</strong><small>Échecs</small></span>`;
  }

  function drawScatter(runs) {
    const canvas = q('#history-scatter');
    if (!canvas) return;
    const points = runs.map(run => ({
      x: Number(run.linear_meters),
      y: Number(run.elapsed_seconds),
      vehicles: Math.max(1, Number(run.vehicle_count) || 1),
      tone: toneFor(run.status)
    })).filter(point => Number.isFinite(point.x) && Number.isFinite(point.y));
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const width = Math.max(620, canvas.clientWidth || 1000);
    const height = 340;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext('2d');
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);
    const styles = getComputedStyle(document.documentElement);
    const ink = styles.getPropertyValue('--ink').trim() || '#102A3A';
    const muted = styles.getPropertyValue('--muted').trim() || '#607486';
    const line = styles.getPropertyValue('--line').trim() || '#D5E1E8';
    const colors = {success: '#40B1A1', warning: '#F8AF44', failure: '#E73147'};
    const margin = {left: 58, right: 22, top: 24, bottom: 48};
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    ctx.font = '12px Inter, Segoe UI, Arial, sans-serif';
    ctx.strokeStyle = line;
    ctx.fillStyle = muted;
    ctx.lineWidth = 1;
    for (let index = 0; index <= 5; index += 1) {
      const x = margin.left + plotW * index / 5;
      const y = margin.top + plotH * index / 5;
      ctx.beginPath(); ctx.moveTo(x, margin.top); ctx.lineTo(x, margin.top + plotH); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(margin.left, y); ctx.lineTo(margin.left + plotW, y); ctx.stroke();
    }
    ctx.fillText('Métrage linéaire', margin.left + plotW / 2 - 42, height - 12);
    ctx.save(); ctx.translate(16, margin.top + plotH / 2 + 40); ctx.rotate(-Math.PI / 2); ctx.fillText('Temps de calcul (s)', 0, 0); ctx.restore();
    if (!points.length) {
      ctx.fillStyle = muted;
      ctx.textAlign = 'center';
      ctx.fillText('Aucune optimisation exploitable pour le moment.', margin.left + plotW / 2, margin.top + plotH / 2);
      ctx.textAlign = 'left';
      return;
    }
    const xValues = points.map(point => point.x);
    const yValues = points.map(point => point.y);
    const xMin = Math.min(...xValues, 0);
    const xMax = Math.max(...xValues, xMin + 1);
    const yMin = 0;
    const yMax = Math.max(...yValues, 1);
    ctx.fillStyle = muted;
    for (let index = 0; index <= 5; index += 1) {
      const xValue = xMin + (xMax - xMin) * index / 5;
      const yValue = yMax - (yMax - yMin) * index / 5;
      ctx.fillText(xValue.toFixed(1), margin.left + plotW * index / 5 - 8, margin.top + plotH + 20);
      ctx.fillText(yValue.toFixed(1), 18, margin.top + plotH * index / 5 + 4);
    }
    points.forEach(point => {
      const x = margin.left + (point.x - xMin) / (xMax - xMin) * plotW;
      const y = margin.top + plotH - (point.y - yMin) / (yMax - yMin) * plotH;
      const radius = Math.min(13, 4 + Math.sqrt(point.vehicles) * 2.2);
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = `${colors[point.tone]}CC`;
      ctx.fill();
      ctx.strokeStyle = colors[point.tone];
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
    ctx.fillStyle = ink;
  }

  async function refreshHistoryAnalytics() {
    if (!ensureHistoryAnalytics()) return;
    try {
      analyticsRuns = await api('/api/history?limit=200');
      renderStatusTags(analyticsRuns);
      drawScatter(analyticsRuns);
      if (typeof window.renderDashboard === 'function') window.renderDashboard();
    } catch (_) {
      renderStatusTags([]);
      drawScatter([]);
    }
  }

  function bindNavigationInterception() {
    document.addEventListener('click', event => {
      const promptButton = event.target.closest('[data-workspace-tab="prompts"]');
      if (promptButton) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        openPromptCenter(promptButton);
        return;
      }
      const historyButton = event.target.closest('[data-tab="history"]');
      if (historyButton) setTimeout(refreshHistoryAnalytics, 80);
      if (event.target.closest('#refresh-history')) setTimeout(refreshHistoryAnalytics, 120);
    }, true);
  }

  function installAll() {
    ensurePromptPanel();
    ensureHistoryAnalytics();
    polishManagementCenter();
    removeLegacyPromptAdminView();
  }

  function init() {
    bindNavigationInterception();
    installAll();
    applyRoleLayout();
    refreshHistoryAnalytics();
    new MutationObserver(installAll).observe(document.body, {childList: true, subtree: true});
    window.addEventListener('resize', () => drawScatter(analyticsRuns));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();