(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body?.detail || `Erreur ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function hideLegacyAdminConfiguration() {
    q('#dc-admin-ai')?.remove();
  }

  function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('fr-FR');
  }

  function setMessage(element, text, kind = 'info') {
    if (!element) return;
    element.textContent = text;
    element.className = `message company-endpoint-message ${kind}`;
    element.hidden = !text;
  }

  function renderStatus(config) {
    const status = q('#company-ai-endpoint-status');
    if (!status) return;
    if (!config.configured) {
      status.innerHTML = '<span class="company-endpoint-dot idle"></span><span><strong>Aucune passerelle configurée</strong><small>Le contrôle documentaire restera indisponible tant qu’un endpoint n’aura pas été enregistré.</small></span>';
      return;
    }
    const checked = formatDate(config.endpoint_verified_at);
    const updated = formatDate(config.updated_at);
    const detail = checked
      ? `Connexion testée le ${checked}`
      : updated
        ? `Adresse enregistrée le ${updated}, connexion non testée`
        : 'Adresse enregistrée, connexion non testée';
    status.innerHTML = `<span class="company-endpoint-dot ${checked ? 'ready' : 'pending'}"></span><span><strong>${config.endpoint_host || 'Passerelle configurée'}</strong><small>${detail}</small></span>`;
  }

  function renderCard(card, config) {
    card.classList.add('company-endpoint-card');
    card.setAttribute('aria-labelledby', 'company-ai-endpoint-title');
    card.innerHTML = `
      <div class="settings-card-heading company-endpoint-heading">
        <div class="settings-icon company-endpoint-icon" aria-hidden="true">↗</div>
        <div>
          <h3 id="company-ai-endpoint-title">Connexion à votre passerelle IA</h3>
          <p>Indiquez uniquement l’adresse HTTPS du service IA administré par votre entreprise.</p>
        </div>
      </div>
      <div class="company-endpoint-explanation">
        <strong>Votre entreprise garde la main.</strong>
        <p>${config.explanation}</p>
      </div>
      <div id="company-ai-endpoint-status" class="company-endpoint-status" role="status" aria-live="polite"></div>
      <label class="company-endpoint-field" for="company-ai-endpoint-url">
        <span>Endpoint de la passerelle IA</span>
        <input id="company-ai-endpoint-url" type="url" inputmode="url" autocomplete="url" spellcheck="false" placeholder="https://ia.votre-entreprise.fr/axioload/document-control" value="">
        <small>AxioLoad enverra les documents et le contrat JSON à cette adresse. Aucun champ de clé API, de modèle ou de fournisseur n’est conservé dans AxioLoad.</small>
      </label>
      <div class="company-endpoint-contract">
        <span>Contrat technique</span>
        <code>${config.contract_version || 'axioload.document-control.v1'}</code>
      </div>
      <div class="settings-actions company-endpoint-actions">
        <button id="company-ai-endpoint-save" class="primary" type="button">Enregistrer l’endpoint</button>
        <button id="company-ai-endpoint-test" class="secondary" type="button">Tester la connexion</button>
        <button id="company-ai-endpoint-delete" class="secondary danger-secondary" type="button">Supprimer</button>
      </div>
      <div id="company-ai-endpoint-message" class="message company-endpoint-message" role="status" aria-live="polite" hidden></div>`;

    const input = q('#company-ai-endpoint-url', card);
    const save = q('#company-ai-endpoint-save', card);
    const test = q('#company-ai-endpoint-test', card);
    const remove = q('#company-ai-endpoint-delete', card);
    const message = q('#company-ai-endpoint-message', card);
    input.value = config.endpoint_url || '';
    test.disabled = !config.configured;
    remove.disabled = !config.configured;
    renderStatus(config);

    save.addEventListener('click', async () => {
      const endpointUrl = input.value.trim();
      if (!endpointUrl) {
        setMessage(message, 'Renseignez l’adresse HTTPS de votre passerelle IA.', 'error');
        input.focus();
        return;
      }
      save.disabled = true;
      test.disabled = true;
      remove.disabled = true;
      setMessage(message, 'Enregistrement de l’endpoint…');
      try {
        const updated = await api('/api/company/document-ai-endpoint', {
          method: 'PUT',
          body: JSON.stringify({endpoint_url: endpointUrl})
        });
        input.value = updated.endpoint_url || endpointUrl;
        renderStatus(updated);
        test.disabled = false;
        remove.disabled = false;
        setMessage(message, 'Endpoint enregistré. Testez maintenant la connexion.', 'success');
      } catch (error) {
        setMessage(message, error.message || String(error), 'error');
      } finally {
        save.disabled = false;
        if (input.value.trim()) {
          test.disabled = false;
          remove.disabled = false;
        }
      }
    });

    test.addEventListener('click', async () => {
      test.disabled = true;
      setMessage(message, 'Test de la passerelle en cours…');
      try {
        const result = await api('/api/company/document-ai-endpoint/test', {method: 'POST', body: '{}'});
        const current = await api('/api/company/document-ai-endpoint');
        renderStatus(current);
        setMessage(message, `${result.message} Temps de réponse : ${result.latency_ms} ms.`, 'success');
      } catch (error) {
        setMessage(message, error.message || String(error), 'error');
      } finally {
        test.disabled = false;
      }
    });

    remove.addEventListener('click', async () => {
      if (!window.confirm('Supprimer cet endpoint ? Le contrôle documentaire ne pourra plus lancer d’analyse.')) return;
      remove.disabled = true;
      setMessage(message, 'Suppression de l’endpoint…');
      try {
        await api('/api/company/document-ai-endpoint', {method: 'DELETE'});
        input.value = '';
        const empty = {
          configured: false,
          endpoint_host: '',
          endpoint_verified_at: null,
          updated_at: null
        };
        renderStatus(empty);
        test.disabled = true;
        setMessage(message, 'Endpoint supprimé.', 'success');
      } catch (error) {
        remove.disabled = false;
        setMessage(message, error.message || String(error), 'error');
      }
    });
  }

  async function installCompanyEndpointCard() {
    const title = q('#api-settings-title');
    const card = title?.closest('.settings-card');
    if (!card || card.dataset.companyEndpointReady === '1') return Boolean(card);
    card.dataset.companyEndpointReady = 'loading';
    try {
      const config = await api('/api/company/document-ai-endpoint');
      card.dataset.companyEndpointReady = '1';
      renderCard(card, config);
      return true;
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        card.remove();
        return true;
      }
      card.dataset.companyEndpointReady = '0';
      card.innerHTML = `
        <div class="settings-card-heading">
          <div class="settings-icon" aria-hidden="true">↗</div>
          <div><h3>Connexion à votre passerelle IA</h3><p>La configuration n’a pas pu être chargée.</p></div>
        </div>
        <div class="message error">${String(error.message || error)}</div>`;
      return false;
    }
  }

  function init() {
    hideLegacyAdminConfiguration();
    installCompanyEndpointCard();
    [100, 350, 900, 1800].forEach(delay => window.setTimeout(() => {
      hideLegacyAdminConfiguration();
      installCompanyEndpointCard();
    }, delay));
    document.addEventListener('click', event => {
      if (event.target.closest?.('#open-settings')) {
        window.setTimeout(installCompanyEndpointCard, 0);
      }
      if (event.target.closest?.('#open-admin, [data-company], [data-detail-tab]')) {
        [0, 100, 350].forEach(delay => window.setTimeout(hideLegacyAdminConfiguration, delay));
      }
    }, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
