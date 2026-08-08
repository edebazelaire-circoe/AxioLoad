(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = { invoices: [], current: null };

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  async function api(url, options = {}) {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body?.detail || `Erreur ${response.status}`);
    return body;
  }

  function icon() {
    return '<span class="ax-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2h9l4 4v16H6zM14 2v5h5M9 11h7M9 15h7M9 19h5"/><path d="M3 8h5v8H3z"/></svg></span>';
  }

  function panelHtml() {
    return `<section id="tab-facturx" class="panel tab-panel" aria-labelledby="facturx-title">
      <div class="panel-heading"><div><div class="eyebrow">Facturation électronique</div><h2 id="facturx-title">Créer et contrôler une facture Factur-X</h2><p class="section-intro">Saisissez ou importez les données, corrigez les anomalies, faites valider la facture puis exportez le XML et le rapport de conformité.</p></div></div>
      <div class="facturx-layout">
        <form id="facturx-form" class="facturx-card">
          <h3>Nouvelle facture</h3>
          <div class="facturx-grid">
            <label>Sens<select name="direction"><option value="outgoing">Facture émise</option><option value="incoming">Facture reçue</option></select></label>
            <label>Type<select name="document_type"><option value="invoice">Facture</option><option value="credit_note">Avoir</option><option value="advance_invoice">Acompte</option></select></label>
            <label>Numéro<input name="invoice_number" required></label>
            <label>Date d’émission<input name="issue_date" type="date" required></label>
            <label>Devise<input name="currency" value="EUR" maxlength="3" required></label>
            <label><span>Autoliquidation</span><input name="reverse_charge" type="checkbox"></label>
          </div>
          <h3>Vendeur</h3><div class="facturx-grid">
            <label>Raison sociale<input name="seller_legal_name" required></label><label>SIREN<input name="seller_siren"></label>
            <label>TVA intracommunautaire<input name="seller_vat"></label><label>Pays<input name="seller_country" value="FR" maxlength="2" required></label>
          </div>
          <h3>Acheteur</h3><div class="facturx-grid">
            <label>Raison sociale<input name="buyer_legal_name" required></label><label>SIREN<input name="buyer_siren"></label>
            <label>TVA intracommunautaire<input name="buyer_vat"></label><label>Pays<input name="buyer_country" value="FR" maxlength="2" required></label>
          </div>
          <h3>Lignes</h3>
          <table class="facturx-lines"><thead><tr><th>Description</th><th>Qté</th><th>Unité</th><th>Prix HT</th><th>TVA %</th><th></th></tr></thead><tbody id="facturx-lines"></tbody></table>
          <div class="facturx-actions"><button id="facturx-add-line" type="button" class="secondary">+ Ajouter une ligne</button><button type="submit" class="primary">Enregistrer le brouillon</button></div>
          <div id="facturx-message" class="facturx-status hidden" role="status"></div>
        </form>
        <aside class="facturx-card"><h3>Factures enregistrées</h3><div id="facturx-list" class="facturx-invoice-list"></div><div id="facturx-detail"></div></aside>
      </div>
    </section>`;
  }

  function addLine(values = {}) {
    const row = document.createElement('tr');
    row.innerHTML = `<td><input name="description" value="${escapeHtml(values.description || '')}" required></td><td><input name="quantity" type="number" min="0" step="0.01" value="${escapeHtml(values.quantity || 1)}" required></td><td><input name="unit_code" value="${escapeHtml(values.unit_code || 'C62')}" required></td><td><input name="unit_price" type="number" min="0" step="0.01" value="${escapeHtml(values.unit_price || 0)}" required></td><td><input name="vat_rate" type="number" min="0" step="0.01" value="${escapeHtml(values.vat_rate ?? 20)}" required></td><td><button type="button" class="secondary facturx-remove-line" aria-label="Supprimer la ligne">×</button></td>`;
    q('#facturx-lines').append(row);
    q('.facturx-remove-line', row).addEventListener('click', () => row.remove());
  }

  function showMessage(message, error = false) {
    const box = q('#facturx-message');
    box.textContent = message;
    box.classList.remove('hidden');
    box.classList.toggle('error', error);
  }

  function payloadFromForm(form) {
    const data = new FormData(form);
    const lines = qa('#facturx-lines tr').map(row => {
      const get = name => q(`[name="${name}"]`, row).value;
      const quantity = Number(get('quantity'));
      const unitPrice = Number(get('unit_price'));
      return {description: get('description'), quantity, unit_code: get('unit_code'), unit_price: unitPrice, vat_rate: Number(get('vat_rate')), line_net_amount: Number((quantity * unitPrice).toFixed(2))};
    });
    const totalNet = lines.reduce((sum, line) => sum + line.line_net_amount, 0);
    const totalTax = lines.reduce((sum, line) => sum + line.line_net_amount * line.vat_rate / 100, 0);
    return {
      direction: data.get('direction'), document_type: data.get('document_type'), invoice_number: data.get('invoice_number'), issue_date: data.get('issue_date'), currency: String(data.get('currency') || 'EUR').toUpperCase(), reverse_charge: data.get('reverse_charge') === 'on',
      seller: {legal_name: data.get('seller_legal_name'), siren: data.get('seller_siren'), vat_number: data.get('seller_vat'), country_code: String(data.get('seller_country') || 'FR').toUpperCase()},
      buyer: {legal_name: data.get('buyer_legal_name'), siren: data.get('buyer_siren'), vat_number: data.get('buyer_vat'), country_code: String(data.get('buyer_country') || 'FR').toUpperCase()},
      lines, total_net: totalNet.toFixed(2), total_tax: totalTax.toFixed(2), total_gross: (totalNet + totalTax).toFixed(2)
    };
  }

  function renderList() {
    const list = q('#facturx-list');
    if (!state.invoices.length) { list.innerHTML = '<p class="facturx-empty">Aucune facture enregistrée.</p>'; return; }
    list.innerHTML = state.invoices.map(invoice => `<button class="facturx-invoice-item" type="button" data-id="${invoice.id}"><strong>${escapeHtml(invoice.invoice_number || 'Sans numéro')}</strong><span>${escapeHtml(invoice.payload?.buyer?.legal_name || invoice.payload?.seller?.legal_name || '')}</span><span class="facturx-pill">${escapeHtml(invoice.status)}</span></button>`).join('');
    qa('[data-id]', list).forEach(button => button.addEventListener('click', () => showDetail(button.dataset.id)));
  }

  async function loadInvoices() {
    state.invoices = await api('/api/facturx/invoices');
    renderList();
  }

  async function showDetail(id) {
    const invoice = await api(`/api/facturx/invoices/${id}`);
    state.current = invoice;
    const report = invoice.validation || {};
    q('#facturx-detail').innerHTML = `<div class="facturx-validation"><h3>${escapeHtml(invoice.invoice_number || 'Facture')}</h3><p>Profil proposé : <strong>${escapeHtml(invoice.profile || report.profile || '')}</strong></p><p>Total TTC : <strong>${escapeHtml(report.totals?.gross || '')} ${escapeHtml(invoice.payload?.currency || '')}</strong></p>${(report.errors || []).length ? `<h4>Erreurs bloquantes</h4><ul>${report.errors.map(item => `<li>${escapeHtml(item.message)}</li>`).join('')}</ul>` : '<p class="facturx-status">Aucune erreur bloquante.</p>'}<div class="facturx-actions"><button id="facturx-validate" class="primary" type="button" ${report.valid ? '' : 'disabled'}>Valider humainement</button><a class="secondary" href="/api/facturx/invoices/${id}/validation-report.json">Rapport</a>${invoice.status === 'validated' ? `<a class="secondary" href="/api/facturx/invoices/${id}/factur-x.xml">XML</a>` : ''}</div></div>`;
    q('#facturx-validate')?.addEventListener('click', async () => { await api(`/api/facturx/invoices/${id}/validate`, {method:'POST'}); await loadInvoices(); await showDetail(id); });
  }

  function openWorkspace() {
    const panel = q('#tab-facturx');
    const switcher = q('#workspace-switcher');
    const nav = q('nav.tabs');
    if (!panel || !switcher || !nav) return;

    qa('main > .tab-panel').forEach(item => item.classList.toggle('active', item === panel));
    panel.style.removeProperty('display');
    panel.setAttribute('aria-hidden', 'false');
    if ('inert' in panel) panel.inert = false;

    document.body.dataset.workspace = 'facturx';
    nav.dataset.workspace = 'facturx';

    qa('[data-workspace]', switcher).forEach(button => {
      button.classList.remove('active');
      button.setAttribute('aria-pressed', 'false');
    });
    const card = q('[data-facturx-workspace]', switcher);
    if (card) {
      card.classList.add('active');
      card.setAttribute('aria-pressed', 'true');
    }

    qa('[data-workspace-group]', nav).forEach(button => {
      button.classList.toggle('workspace-group-hidden', button.dataset.workspaceGroup !== 'facturx');
    });
    qa('.tab', nav).forEach(button => {
      const active = button.dataset.facturxTab === 'data';
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
  }

  function installNavigation() {
    const switcher = q('#workspace-switcher');
    const nav = q('nav.tabs');
    if (!switcher || !nav || q('[data-facturx-workspace]')) return false;

    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'workspace-card facturx-workspace-card';
    card.dataset.facturxWorkspace = 'facturx';
    card.setAttribute('aria-pressed', 'false');
    card.innerHTML = `${icon()}<span><strong>Facturation électronique</strong><small>Créer, contrôler et exporter</small></span>`;
    switcher.append(card);

    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'tab workspace-synthetic-tab';
    tab.textContent = 'Données';
    tab.dataset.workspaceGroup = 'facturx';
    tab.dataset.facturxTab = 'data';
    nav.append(tab);

    card.addEventListener('click', openWorkspace);
    tab.addEventListener('click', openWorkspace);
    return true;
  }

  function init() {
    if (!q('#tab-facturx')) q('main')?.insertAdjacentHTML('beforeend', panelHtml());
    q('#facturx-add-line')?.addEventListener('click', () => addLine());
    q('#facturx-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      try { await api('/api/facturx/invoices', {method:'POST', body:JSON.stringify(payloadFromForm(event.currentTarget))}); showMessage('Brouillon enregistré.'); await loadInvoices(); }
      catch (error) { showMessage(error.message, true); }
    });
    addLine();
    const ready = () => { if (!installNavigation()) window.setTimeout(ready, 80); };
    ready();
    loadInvoices().catch(error => showMessage(error.message, true));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true}); else init();
})();
