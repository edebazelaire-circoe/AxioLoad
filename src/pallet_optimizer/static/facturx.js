(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = { invoices: [], parties: [], current: null, editingPartyId: null, sourceName: '' };

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  async function api(url, options = {}) {
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
    const headers = isFormData
      ? {...(options.headers || {})}
      : {'Content-Type': 'application/json', ...(options.headers || {})};
    const response = await fetch(url, {credentials: 'same-origin', ...options, headers});
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body?.detail || `Erreur ${response.status}`);
    return body;
  }

  function icon() {
    return '<span class="ax-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2h9l4 4v16H6zM14 2v5h5M9 11h7M9 15h7M9 19h5"/><path d="M3 8h5v8H3z"/></svg></span>';
  }

  function panelHtml() {
    return `<section id="tab-facturx" class="panel tab-panel" aria-labelledby="facturx-title">
      <div class="panel-heading"><div><div class="eyebrow">Facturation électronique</div><h2 id="facturx-title">Créer et contrôler une facture Factur-X</h2><p class="section-intro">Chargez un PDF ou une image pour préremplir la facture, puis vérifiez les données avant validation et export.</p></div></div>
      <section class="facturx-card facturx-import-card">
        <div><h3>Importer une facture</h3><p>PDF, JPG, JPEG ou PNG, 10 Mo maximum. Le document est analysé avec la connexion IA configurée dans Paramètres puis n’est pas conservé.</p></div>
        <div class="facturx-upload-controls">
          <input id="facturx-source-file" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png">
          <button id="facturx-extract" class="primary" type="button">Analyser et préremplir</button>
        </div>
        <div id="facturx-extract-message" class="facturx-status hidden" role="status"></div>
      </section>
      <div class="facturx-layout">
        <form id="facturx-form" class="facturx-card">
          <h3>Nouvelle facture</h3>
          <div class="facturx-grid">
            <label>Sens<select name="direction"><option value="outgoing">Facture émise</option><option value="incoming">Facture reçue</option></select></label>
            <label>Type<select name="document_type"><option value="invoice">Facture</option><option value="credit_note">Avoir</option><option value="advance_invoice">Acompte</option></select></label>
            <label>Numéro<input name="invoice_number" required></label>
            <label>Date d’émission<input name="issue_date" type="date" required></label>
            <label>Devise<input name="currency" value="EUR" maxlength="3" required></label>
            <label class="facturx-check"><span>Autoliquidation</span><input name="reverse_charge" type="checkbox"></label>
          </div>
          <div class="facturx-section-title"><h3>Vendeur</h3><button class="secondary small" type="button" data-open-party-master>Gérer les tiers</button></div>
          <label class="facturx-party-picker">Préremplir depuis les données de base<select id="facturx-seller-party"><option value="">Sélectionner un tiers</option></select></label>
          <div class="facturx-grid">
            <label>Raison sociale<input name="seller_legal_name" required></label><label>SIREN<input name="seller_siren"></label>
            <label>SIRET<input name="seller_siret"></label><label>TVA intracommunautaire<input name="seller_vat"></label>
            <label>Adresse<input name="seller_address"></label><label>Code postal<input name="seller_postal"></label>
            <label>Ville<input name="seller_city"></label><label>Pays<input name="seller_country" value="FR" maxlength="2" required></label>
          </div>
          <div class="facturx-section-title"><h3>Acheteur</h3><button class="secondary small" type="button" data-open-party-master>Gérer les tiers</button></div>
          <label class="facturx-party-picker">Préremplir depuis les données de base<select id="facturx-buyer-party"><option value="">Sélectionner un tiers</option></select></label>
          <div class="facturx-grid">
            <label>Raison sociale<input name="buyer_legal_name" required></label><label>SIREN<input name="buyer_siren"></label>
            <label>SIRET<input name="buyer_siret"></label><label>TVA intracommunautaire<input name="buyer_vat"></label>
            <label>Adresse<input name="buyer_address"></label><label>Code postal<input name="buyer_postal"></label>
            <label>Ville<input name="buyer_city"></label><label>Pays<input name="buyer_country" value="FR" maxlength="2" required></label>
          </div>
          <h3>Lignes</h3>
          <div class="facturx-table-wrap"><table class="facturx-lines"><thead><tr><th>Description</th><th>Qté</th><th>Unité</th><th>Prix HT</th><th>TVA %</th><th></th></tr></thead><tbody id="facturx-lines"></tbody></table></div>
          <div class="facturx-grid facturx-totals">
            <label>Total HT déclaré<input name="total_net" type="number" step="0.01"></label>
            <label>Total TVA déclaré<input name="total_tax" type="number" step="0.01"></label>
            <label>Total TTC déclaré<input name="total_gross" type="number" step="0.01"></label>
          </div>
          <div class="facturx-actions"><button id="facturx-add-line" type="button" class="secondary">+ Ajouter une ligne</button><button type="submit" class="primary">Enregistrer le brouillon</button></div>
          <div id="facturx-message" class="facturx-status hidden" role="status"></div>
        </form>
        <aside class="facturx-card"><h3>Factures enregistrées</h3><div id="facturx-list" class="facturx-invoice-list"></div><div id="facturx-detail"></div></aside>
      </div>
    </section>`;
  }

  function partyPanelHtml() {
    return `<section id="tab-invoice-parties" class="panel tab-panel" aria-labelledby="invoice-parties-title">
      <div class="panel-heading"><div><div class="eyebrow">Données de base</div><h2 id="invoice-parties-title">Clients et fournisseurs</h2><p class="section-intro">Enregistrez les tiers utilisés pour préremplir les factures. Un SIREN, SIRET ou numéro de TVA identique met à jour le tiers existant au lieu de créer un doublon.</p></div></div>
      <div class="facturx-layout facturx-party-layout">
        <form id="facturx-party-form" class="facturx-card">
          <h3 id="facturx-party-form-title">Nouveau tiers</h3>
          <div class="facturx-grid">
            <label>Type<select name="party_type"><option value="customer">Client</option><option value="supplier">Fournisseur</option><option value="both">Client et fournisseur</option></select></label>
            <label>Raison sociale<input name="legal_name" required></label>
            <label>Nom commercial<input name="trade_name"></label><label>SIREN<input name="siren"></label>
            <label>SIRET<input name="siret"></label><label>TVA intracommunautaire<input name="vat_number"></label>
            <label>Email<input name="email" type="email"></label><label>Téléphone<input name="phone"></label>
            <label>Adresse<input name="address_line1"></label><label>Code postal<input name="postal_code"></label>
            <label>Ville<input name="city"></label><label>Pays<input name="country_code" value="FR" maxlength="2"></label>
          </div>
          <div class="facturx-actions"><button class="primary" type="submit">Enregistrer le tiers</button><button id="facturx-party-cancel" class="secondary hidden" type="button">Annuler la modification</button></div>
          <div id="facturx-party-message" class="facturx-status hidden" role="status"></div>
        </form>
        <aside class="facturx-card"><h3>Tiers enregistrés</h3><div id="facturx-party-list" class="facturx-invoice-list"></div></aside>
      </div>
    </section>`;
  }

  function addLine(values = {}) {
    const row = document.createElement('tr');
    row.innerHTML = `<td><input name="description" value="${escapeHtml(values.description || '')}" required></td><td><input name="quantity" type="number" min="0" step="0.01" value="${escapeHtml(values.quantity || 1)}" required></td><td><input name="unit_code" value="${escapeHtml(values.unit_code || 'C62')}" required></td><td><input name="unit_price" type="number" min="0" step="0.01" value="${escapeHtml(values.unit_price || 0)}" required></td><td><input name="vat_rate" type="number" min="0" step="0.01" value="${escapeHtml(values.vat_rate ?? 20)}" required></td><td><button type="button" class="secondary facturx-remove-line" aria-label="Supprimer la ligne">×</button></td>`;
    q('#facturx-lines').append(row);
    q('.facturx-remove-line', row).addEventListener('click', () => row.remove());
  }

  function setMessage(selector, message, error = false) {
    const box = q(selector);
    if (!box) return;
    box.textContent = message;
    box.classList.remove('hidden');
    box.classList.toggle('error', error);
  }

  function field(form, name) { return q(`[name="${name}"]`, form); }
  function setField(form, name, value) { const input = field(form, name); if (input) input.value = value ?? ''; }

  function partyToForm(side, party) {
    const form = q('#facturx-form');
    setField(form, `${side}_legal_name`, party.legal_name || '');
    setField(form, `${side}_siren`, party.siren || '');
    setField(form, `${side}_siret`, party.siret || '');
    setField(form, `${side}_vat`, party.vat_number || '');
    setField(form, `${side}_address`, party.address_line1 || '');
    setField(form, `${side}_postal`, party.postal_code || '');
    setField(form, `${side}_city`, party.city || '');
    setField(form, `${side}_country`, party.country_code || 'FR');
  }

  function renderPartySelectors() {
    const options = '<option value="">Sélectionner un tiers</option>' + state.parties.map(party => `<option value="${escapeHtml(party.id)}">${escapeHtml(party.legal_name)}${party.siren ? ` · ${escapeHtml(party.siren)}` : ''}</option>`).join('');
    const seller = q('#facturx-seller-party');
    const buyer = q('#facturx-buyer-party');
    if (seller) seller.innerHTML = options;
    if (buyer) buyer.innerHTML = options;
  }

  function renderPartyList() {
    const list = q('#facturx-party-list');
    if (!list) return;
    if (!state.parties.length) {
      list.innerHTML = '<p class="facturx-empty">Aucun client ou fournisseur enregistré.</p>';
      return;
    }
    const typeLabel = {customer: 'Client', supplier: 'Fournisseur', both: 'Client et fournisseur'};
    list.innerHTML = state.parties.map(party => `<article class="facturx-party-item"><div><strong>${escapeHtml(party.legal_name)}</strong><span>${escapeHtml(typeLabel[party.party_type] || party.party_type)}</span><small>${escapeHtml(party.siret || party.siren || party.vat_number || '')}</small></div><div class="facturx-actions"><button type="button" class="secondary small" data-edit-party="${party.id}">Modifier</button><button type="button" class="secondary small" data-delete-party="${party.id}">Désactiver</button></div></article>`).join('');
    qa('[data-edit-party]', list).forEach(button => button.addEventListener('click', () => editParty(button.dataset.editParty)));
    qa('[data-delete-party]', list).forEach(button => button.addEventListener('click', () => deleteParty(button.dataset.deleteParty)));
  }

  async function loadParties() {
    state.parties = await api('/api/facturx/parties');
    renderPartySelectors();
    renderPartyList();
  }

  function resetPartyForm() {
    const form = q('#facturx-party-form');
    if (!form) return;
    form.reset();
    field(form, 'country_code').value = 'FR';
    state.editingPartyId = null;
    q('#facturx-party-form-title').textContent = 'Nouveau tiers';
    q('#facturx-party-cancel').classList.add('hidden');
  }

  function editParty(id) {
    const party = state.parties.find(item => item.id === id);
    const form = q('#facturx-party-form');
    if (!party || !form) return;
    state.editingPartyId = id;
    Object.entries({
      party_type: party.party_type, legal_name: party.legal_name, trade_name: party.trade_name,
      siren: party.siren, siret: party.siret, vat_number: party.vat_number, email: party.email,
      phone: party.phone, address_line1: party.address_line1, postal_code: party.postal_code,
      city: party.city, country_code: party.country_code || 'FR'
    }).forEach(([name, value]) => setField(form, name, value));
    q('#facturx-party-form-title').textContent = `Modifier ${party.legal_name}`;
    q('#facturx-party-cancel').classList.remove('hidden');
    form.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  async function deleteParty(id) {
    await api(`/api/facturx/parties/${id}`, {method: 'DELETE'});
    await loadParties();
    setMessage('#facturx-party-message', 'Tiers désactivé.');
  }

  function partyPayload(form) {
    const data = new FormData(form);
    return Object.fromEntries([...data.entries()].map(([key, value]) => [key, String(value).trim()]));
  }

  function payloadFromForm(form) {
    const data = new FormData(form);
    const lines = qa('#facturx-lines tr').map(row => {
      const get = name => q(`[name="${name}"]`, row).value;
      const quantity = Number(get('quantity'));
      const unitPrice = Number(get('unit_price'));
      return {description: get('description'), quantity, unit_code: get('unit_code'), unit_price: unitPrice, vat_rate: Number(get('vat_rate')), line_net_amount: Number((quantity * unitPrice).toFixed(2))};
    });
    const computedNet = lines.reduce((sum, line) => sum + line.line_net_amount, 0);
    const computedTax = lines.reduce((sum, line) => sum + line.line_net_amount * line.vat_rate / 100, 0);
    const totalNet = data.get('total_net') === '' ? computedNet : Number(data.get('total_net'));
    const totalTax = data.get('total_tax') === '' ? computedTax : Number(data.get('total_tax'));
    const totalGross = data.get('total_gross') === '' ? totalNet + totalTax : Number(data.get('total_gross'));
    const side = prefix => ({
      legal_name: data.get(`${prefix}_legal_name`), siren: data.get(`${prefix}_siren`), siret: data.get(`${prefix}_siret`),
      vat_number: data.get(`${prefix}_vat`), address_line1: data.get(`${prefix}_address`), postal_code: data.get(`${prefix}_postal`),
      city: data.get(`${prefix}_city`), country_code: String(data.get(`${prefix}_country`) || 'FR').toUpperCase()
    });
    return {
      direction: data.get('direction'), document_type: data.get('document_type'), invoice_number: data.get('invoice_number'), issue_date: data.get('issue_date'), currency: String(data.get('currency') || 'EUR').toUpperCase(), reverse_charge: data.get('reverse_charge') === 'on',
      seller: side('seller'), buyer: side('buyer'), lines,
      total_net: totalNet.toFixed(2), total_tax: totalTax.toFixed(2), total_gross: totalGross.toFixed(2),
      source_name: state.sourceName || ''
    };
  }

  function fillInvoiceForm(payload) {
    const form = q('#facturx-form');
    if (!form) return;
    setField(form, 'direction', payload.direction || 'outgoing');
    setField(form, 'document_type', payload.document_type || 'invoice');
    setField(form, 'invoice_number', payload.invoice_number || '');
    setField(form, 'issue_date', payload.issue_date || '');
    setField(form, 'currency', payload.currency || 'EUR');
    field(form, 'reverse_charge').checked = payload.reverse_charge === true;
    partyToForm('seller', payload.seller || {});
    partyToForm('buyer', payload.buyer || {});
    q('#facturx-lines').innerHTML = '';
    (payload.lines || []).forEach(addLine);
    if (!(payload.lines || []).length) addLine();
    setField(form, 'total_net', payload.total_net || '');
    setField(form, 'total_tax', payload.total_tax || '');
    setField(form, 'total_gross', payload.total_gross || '');
    state.sourceName = payload.source_name || '';
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

  function installNavigation() {
    const switcher = q('#workspace-switcher');
    const nav = q('nav.tabs');
    if (!switcher || !nav) return false;

    if (!q('[data-workspace="facturx"]', switcher)) {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'workspace-card facturx-workspace-card';
      card.dataset.workspace = 'facturx';
      card.setAttribute('aria-pressed', 'false');
      card.innerHTML = `${icon()}<span><strong>Facturation électronique</strong><small>Créer, contrôler et exporter</small></span>`;
      switcher.append(card);
    }
    if (!q('[data-tab="facturx"]', nav)) {
      const tab = document.createElement('button');
      tab.type = 'button'; tab.className = 'tab'; tab.textContent = 'Données';
      tab.dataset.tab = 'facturx'; tab.dataset.workspaceGroup = 'facturx'; nav.append(tab);
    }
    if (!q('[data-tab="invoice-parties"]', nav)) {
      const tab = document.createElement('button');
      tab.type = 'button'; tab.className = 'tab'; tab.textContent = 'Clients / fournisseurs';
      tab.dataset.tab = 'invoice-parties'; tab.dataset.workspaceGroup = 'database'; nav.append(tab);
    }
    window.dispatchEvent(new CustomEvent('axioload:workspace:registered', {detail: {workspace: 'facturx'}}));
    return true;
  }

  function bindEvents() {
    q('#facturx-add-line')?.addEventListener('click', () => addLine());
    q('#facturx-seller-party')?.addEventListener('change', event => { const party = state.parties.find(item => item.id === event.target.value); if (party) partyToForm('seller', party); });
    q('#facturx-buyer-party')?.addEventListener('change', event => { const party = state.parties.find(item => item.id === event.target.value); if (party) partyToForm('buyer', party); });
    qa('[data-open-party-master]').forEach(button => button.addEventListener('click', () => q('nav.tabs [data-tab="invoice-parties"]')?.click()));

    q('#facturx-extract')?.addEventListener('click', async () => {
      const fileInput = q('#facturx-source-file');
      const file = fileInput?.files?.[0];
      if (!file) { setMessage('#facturx-extract-message', 'Sélectionnez un PDF ou une image.', true); return; }
      const button = q('#facturx-extract');
      button.disabled = true;
      setMessage('#facturx-extract-message', 'Analyse du document en cours…');
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('direction', field(q('#facturx-form'), 'direction').value || 'outgoing');
        const result = await api('/api/facturx/extract', {method: 'POST', body: formData});
        fillInvoiceForm(result.payload || {});
        setMessage('#facturx-extract-message', result.message || 'Document analysé. Vérifiez les données préremplies.');
      } catch (error) {
        setMessage('#facturx-extract-message', error.message, true);
      } finally {
        button.disabled = false;
      }
    });

    q('#facturx-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      try { await api('/api/facturx/invoices', {method:'POST', body:JSON.stringify(payloadFromForm(event.currentTarget))}); setMessage('#facturx-message', 'Brouillon enregistré.'); await loadInvoices(); }
      catch (error) { setMessage('#facturx-message', error.message, true); }
    });

    q('#facturx-party-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      try {
        const payload = partyPayload(event.currentTarget);
        const url = state.editingPartyId ? `/api/facturx/parties/${state.editingPartyId}` : '/api/facturx/parties';
        const method = state.editingPartyId ? 'PUT' : 'POST';
        await api(url, {method, body: JSON.stringify(payload)});
        resetPartyForm();
        await loadParties();
        setMessage('#facturx-party-message', 'Tiers enregistré et disponible pour le préremplissage.');
      } catch (error) { setMessage('#facturx-party-message', error.message, true); }
    });
    q('#facturx-party-cancel')?.addEventListener('click', resetPartyForm);
  }

  function init() {
    if (!q('#tab-facturx')) q('main')?.insertAdjacentHTML('beforeend', panelHtml());
    if (!q('#tab-invoice-parties')) q('main')?.insertAdjacentHTML('beforeend', partyPanelHtml());
    addLine();
    bindEvents();
    const ready = () => { if (!installNavigation()) window.setTimeout(ready, 80); };
    ready();
    Promise.all([loadInvoices(), loadParties()]).catch(error => setMessage('#facturx-message', error.message, true));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true}); else init();
})();
