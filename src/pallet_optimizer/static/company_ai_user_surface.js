(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  let installPromise = null;
  let installFrame = 0;

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

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

  function neutralizeLegacySuperadminCard() {
    const pane = q('#admin-company-api');
    if (!pane) return;
    const existing = q('#dc-admin-ai', pane);
    if (existing?.dataset.companyAiSentinel === '1') return;

    const sentinel = document.createElement('span');
    sentinel.id = 'dc-admin-ai';
    sentinel.dataset.companyAiSentinel = '1';
    sentinel.hidden = true;
    sentinel.setAttribute('aria-hidden', 'true');

    if (existing) existing.replaceWith(sentinel);
    else pane.prepend(sentinel);
  }

  function replaceStaleDocumentMessage() {
    const message = q('#dc-message');
    if (!message) return;
    if (message.textContent.includes('Le superadministrateur doit compléter la fiche entreprise')) {
      message.textContent = 'Le responsable principal de l’entreprise doit configurer la connexion IA dans Paramètres.';
    }
  }

  function setMessage(element, text, kind = 'info') {
    if (!element) return;
    element.textContent = text;
    element.className = `message company-endpoint-message ${kind}`;
    element.hidden = !text;
  }

  function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('fr-FR');
  }

  function modelOptions(config) {
    const models = Array.isArray(config.allowed_models) ? config.allowed_models : [];
    return models.map(model => {
      const selected = model.id === config.model ? ' selected' : '';
      const suffix = model.recommended ? ' · Recommandé' : '';
      return `<option value="${escapeHtml(model.id)}"${selected}>${escapeHtml(model.label)}${suffix}</option>`;
    }).join('');
  }

  function selectedModelDescription(config, modelId) {
    const models = Array.isArray(config.allowed_models) ? config.allowed_models : [];
    return models.find(model => model.id === modelId)?.description || '';
  }

  function findOrCreateSettingsCard() {
    const settings = q('#tab-settings .settings-sections');
    if (!settings) return null;

    let card = q('#company-ai-user-card');
    if (!card) {
      card = q('#api-settings-title')?.closest('.settings-card') || q('.company-endpoint-card', settings);
    }
    if (!card) {
      card = document.createElement('section');
      card.className = 'settings-card full-width';
      settings.append(card);
    }
    card.id = 'company-ai-user-card';
    card.classList.add('settings-card', 'full-width', 'company-endpoint-card');
    card.setAttribute('aria-labelledby', 'company-ai-connection-title');
    return card;
  }

  function statusMarkup(config) {
    if (!config.configured) {
      return '<span class="company-endpoint-dot idle"></span><span><strong>Aucune connexion IA active</strong><small>Le responsable principal doit choisir une solution dans cet onglet Paramètres.</small></span>';
    }
    const endpointMode = config.connection_mode === 'endpoint';
    const checkedAt = formatDate(endpointMode ? config.endpoint_verified_at : config.api_verified_at);
    const updatedAt = formatDate(config.updated_at);
    const detail = checkedAt
      ? `Connexion testée le ${checkedAt}`
      : updatedAt
        ? `Configuration enregistrée le ${updatedAt}, connexion non testée`
        : 'Configuration enregistrée';
    const title = endpointMode
      ? (config.endpoint_host || 'Passerelle de l’entreprise')
      : `${config.model || 'Modèle OpenAI'}${config.api_key_hint ? ` · clé •••• ${config.api_key_hint}` : ''}`;
    return `<span class="company-endpoint-dot ${checkedAt ? 'ready' : 'pending'}"></span><span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(detail)}</small></span>`;
  }

  function renderReadOnly(card, config) {
    const mode = config.connection_mode === 'openai_api_key' ? 'Clé API OpenAI' : 'Passerelle de l’entreprise';
    card.dataset.companyEndpointReady = 'readonly';
    card.innerHTML = `
      <div class="settings-card-heading company-endpoint-heading">
        <div class="settings-icon company-endpoint-icon" aria-hidden="true">↗</div>
        <div>
          <h3 id="company-ai-connection-title">Connexion à l’intelligence artificielle</h3>
          <p>La connexion du contrôle documentaire appartient à votre entreprise.</p>
        </div>
      </div>
      <div class="company-endpoint-explanation">
        <strong>Configuration située dans l’espace utilisateur.</strong>
        <p>${escapeHtml(config.explanation || '')}</p>
      </div>
      <div class="company-endpoint-status" role="status" aria-live="polite">${statusMarkup(config)}</div>
      <div class="notice neutral-notice">
        <strong>Mode actuel :</strong> ${escapeHtml(config.configured ? mode : 'aucun mode actif')}.<br>
        Connectez-vous avec le compte responsable principal de l’entreprise pour modifier cette configuration.
      </div>`;
  }

  function syncMode(card, config) {
    const mode = q('input[name="company-ai-mode"]:checked', card)?.value || 'endpoint';
    const endpointPanel = q('#company-ai-endpoint-panel', card);
    const apiPanel = q('#company-ai-api-panel', card);
    const save = q('#company-ai-connection-save', card);
    if (!endpointPanel || !apiPanel || !save) return;

    endpointPanel.hidden = mode !== 'endpoint';
    apiPanel.hidden = mode !== 'openai_api_key';
    endpointPanel.querySelectorAll('input,select').forEach(control => { control.disabled = mode !== 'endpoint'; });
    apiPanel.querySelectorAll('input,select').forEach(control => { control.disabled = mode !== 'openai_api_key'; });
    save.textContent = mode === 'endpoint' ? 'Enregistrer la passerelle' : 'Enregistrer la clé API';

    qa('.company-ai-mode-choice', card).forEach(choice => {
      const input = q('input', choice);
      choice.classList.toggle('selected', input?.checked === true);
    });

    const model = q('#company-ai-model', card);
    const description = q('#company-ai-model-description', card);
    if (model && description) description.textContent = selectedModelDescription(config, model.value);
  }

  function renderManager(card, config) {
    const mode = config.connection_mode === 'openai_api_key' ? 'openai_api_key' : 'endpoint';
    const endpointChecked = mode === 'endpoint' ? ' checked' : '';
    const apiChecked = mode === 'openai_api_key' ? ' checked' : '';
    const keyPlaceholder = config.api_key_configured
      ? `Clé déjà enregistrée · •••• ${config.api_key_hint || ''}`
      : 'sk-proj-…';

    card.dataset.companyEndpointReady = '1';
    card.innerHTML = `
      <div class="settings-card-heading company-endpoint-heading">
        <div class="settings-icon company-endpoint-icon" aria-hidden="true">↗</div>
        <div>
          <h3 id="company-ai-connection-title">Connexion à l’intelligence artificielle</h3>
          <p>Le responsable de l’entreprise choisit l’une des deux méthodes de connexion.</p>
        </div>
      </div>
      <div class="company-endpoint-explanation">
        <strong>Configuration réservée au responsable principal.</strong>
        <p>${escapeHtml(config.explanation || '')}</p>
      </div>
      <div id="company-ai-connection-status" class="company-endpoint-status" role="status" aria-live="polite">${statusMarkup(config)}</div>

      <fieldset class="company-ai-mode-selector">
        <legend>Mode de connexion</legend>
        <label class="company-ai-mode-choice${mode === 'endpoint' ? ' selected' : ''}">
          <input type="radio" name="company-ai-mode" value="endpoint"${endpointChecked}>
          <span class="company-ai-mode-icon" aria-hidden="true">↗</span>
          <span><strong>Passerelle de mon entreprise</strong><small>Votre infrastructure conserve les clés, le fournisseur, le modèle et la facturation.</small></span>
        </label>
        <label class="company-ai-mode-choice${mode === 'openai_api_key' ? ' selected' : ''}">
          <input type="radio" name="company-ai-mode" value="openai_api_key"${apiChecked}>
          <span class="company-ai-mode-icon" aria-hidden="true">⌁</span>
          <span><strong>Clé API OpenAI</strong><small>Connexion directe plus simple. La clé est chiffrée et n’est jamais réaffichée.</small></span>
        </label>
      </fieldset>

      <div id="company-ai-endpoint-panel" class="company-ai-mode-panel">
        <label class="company-endpoint-field" for="company-ai-endpoint-url">
          <span>Endpoint de la passerelle IA</span>
          <input id="company-ai-endpoint-url" type="url" inputmode="url" autocomplete="url" spellcheck="false" placeholder="https://ia.votre-entreprise.fr/axioload/document-control" value="${escapeHtml(config.endpoint_url || '')}">
          <small>AxioLoad transmet le contrat JSON et les deux documents à cette adresse HTTPS, sans ajouter de clé d’authentification.</small>
        </label>
        <div class="company-endpoint-contract">
          <span>Contrat technique</span>
          <code>${escapeHtml(config.contract_version || 'axioload.document-control.v1')}</code>
        </div>
      </div>

      <div id="company-ai-api-panel" class="company-ai-mode-panel">
        <label class="company-endpoint-field" for="company-ai-model">
          <span>Modèle OpenAI autorisé</span>
          <select id="company-ai-model">${modelOptions(config)}</select>
          <small id="company-ai-model-description"></small>
        </label>
        <div class="company-ai-model-note">
          <strong>Liste contrôlée par AxioLoad</strong>
          <span>Seuls les modèles présents dans cette liste peuvent être enregistrés. GPT-5 mini est recommandé par défaut.</span>
        </div>
        <label class="company-endpoint-field" for="company-ai-api-key">
          <span>Clé API OpenAI</span>
          <input id="company-ai-api-key" type="password" autocomplete="new-password" spellcheck="false" placeholder="${escapeHtml(keyPlaceholder)}" value="">
          <small>${config.api_key_configured ? 'Laissez ce champ vide pour conserver la clé enregistrée.' : 'La clé sera chiffrée avec la clé serveur AxioLoad avant son enregistrement.'}</small>
        </label>
        <label class="company-ai-retention-confirmation">
          <input id="company-ai-retention-confirmed" type="checkbox"${config.vendor_zero_retention_confirmed ? ' checked' : ''}>
          <span>Je confirme avoir vérifié la politique de conservation des données du compte OpenAI utilisé. AxioLoad envoie les requêtes avec <code>store: false</code>.</span>
        </label>
      </div>

      <div class="settings-actions company-endpoint-actions">
        <button id="company-ai-connection-save" class="primary" type="button">Enregistrer</button>
        <button id="company-ai-connection-test" class="secondary" type="button">Tester la connexion</button>
        <button id="company-ai-connection-delete" class="secondary danger-secondary" type="button">Supprimer la configuration</button>
      </div>
      <div id="company-ai-connection-message" class="message company-endpoint-message" role="status" aria-live="polite" hidden></div>`;

    const save = q('#company-ai-connection-save', card);
    const test = q('#company-ai-connection-test', card);
    const remove = q('#company-ai-connection-delete', card);
    const message = q('#company-ai-connection-message', card);
    const model = q('#company-ai-model', card);

    qa('input[name="company-ai-mode"]', card).forEach(input => {
      input.addEventListener('change', () => syncMode(card, config));
    });
    model?.addEventListener('change', () => syncMode(card, config));

    test.disabled = !config.configured;
    remove.disabled = !config.configured;
    syncMode(card, config);

    save.addEventListener('click', async () => {
      const selectedMode = q('input[name="company-ai-mode"]:checked', card)?.value || 'endpoint';
      const payload = selectedMode === 'endpoint'
        ? {
            connection_mode: 'endpoint',
            endpoint_url: q('#company-ai-endpoint-url', card)?.value.trim() || ''
          }
        : {
            connection_mode: 'openai_api_key',
            model: q('#company-ai-model', card)?.value || '',
            api_key: q('#company-ai-api-key', card)?.value.trim() || '',
            vendor_zero_retention_confirmed: q('#company-ai-retention-confirmed', card)?.checked === true
          };

      if (selectedMode === 'endpoint' && !payload.endpoint_url) {
        setMessage(message, 'Renseignez l’adresse HTTPS de votre passerelle IA.', 'error');
        q('#company-ai-endpoint-url', card)?.focus();
        return;
      }
      if (selectedMode === 'openai_api_key' && !payload.api_key && !config.api_key_configured) {
        setMessage(message, 'Renseignez une clé API OpenAI.', 'error');
        q('#company-ai-api-key', card)?.focus();
        return;
      }

      save.disabled = true;
      test.disabled = true;
      remove.disabled = true;
      setMessage(message, 'Enregistrement de la connexion IA…');
      try {
        const updated = await api('/api/company/document-ai-config', {
          method: 'PUT',
          body: JSON.stringify(payload)
        });
        renderManager(card, updated);
        setMessage(q('#company-ai-connection-message', card), 'Configuration enregistrée. Vous pouvez maintenant tester la connexion.', 'success');
      } catch (error) {
        setMessage(message, error.message || String(error), 'error');
        save.disabled = false;
        test.disabled = !config.configured;
        remove.disabled = !config.configured;
      }
    });

    test.addEventListener('click', async () => {
      test.disabled = true;
      setMessage(message, 'Test de la connexion IA en cours…');
      try {
        const result = await api('/api/company/document-ai-config/test', {method: 'POST', body: '{}'});
        const current = await api('/api/company/document-ai-config');
        renderManager(card, current);
        setMessage(q('#company-ai-connection-message', card), `${result.message} Temps de réponse : ${result.latency_ms} ms.`, 'success');
      } catch (error) {
        setMessage(message, error.message || String(error), 'error');
        test.disabled = false;
      }
    });

    remove.addEventListener('click', async () => {
      if (!window.confirm('Supprimer toute la configuration IA de cette entreprise ?')) return;
      remove.disabled = true;
      setMessage(message, 'Suppression de la configuration IA…');
      try {
        await api('/api/company/document-ai-config', {method: 'DELETE'});
        const empty = await api('/api/company/document-ai-config');
        renderManager(card, empty);
        setMessage(q('#company-ai-connection-message', card), 'Configuration IA supprimée.', 'success');
      } catch (error) {
        remove.disabled = false;
        setMessage(message, error.message || String(error), 'error');
      }
    });
  }

  async function loadUserConfiguration() {
    try {
      const config = await api('/api/company/document-ai-config');
      return {...config, can_manage: true};
    } catch (error) {
      if (error.status !== 401 && error.status !== 403) throw error;
      return api('/api/company/document-ai-status');
    }
  }

  async function installUserSettingsCard({force = false} = {}) {
    const card = findOrCreateSettingsCard();
    if (!card) return false;
    if (!force && ['1', 'readonly', 'loading'].includes(card.dataset.companyEndpointReady || '')) return true;
    card.dataset.companyEndpointReady = 'loading';
    try {
      const config = await loadUserConfiguration();
      if (config.can_manage === false) renderReadOnly(card, config);
      else renderManager(card, config);
      return true;
    } catch (error) {
      card.dataset.companyEndpointReady = 'error';
      card.innerHTML = `
        <div class="settings-card-heading">
          <div class="settings-icon" aria-hidden="true">↗</div>
          <div><h3 id="company-ai-connection-title">Connexion à l’intelligence artificielle</h3><p>La configuration n’a pas pu être chargée.</p></div>
        </div>
        <div class="message error">${escapeHtml(error.message || String(error))}</div>`;
      return false;
    }
  }

  function scheduleInstall(force = false) {
    if (installFrame) cancelAnimationFrame(installFrame);
    installFrame = requestAnimationFrame(() => {
      installFrame = 0;
      if (installPromise && !force) return;
      installPromise = installUserSettingsCard({force}).finally(() => { installPromise = null; });
    });
  }

  function keepSurfacesConsistent() {
    neutralizeLegacySuperadminCard();
    replaceStaleDocumentMessage();
    if (q('#tab-settings .settings-sections')) scheduleInstall(false);
  }

  function init() {
    keepSurfacesConsistent();
    const observer = new MutationObserver(keepSurfacesConsistent);
    observer.observe(document.documentElement, {childList: true, subtree: true, characterData: true});

    document.addEventListener('click', event => {
      if (event.target.closest?.('#open-settings')) scheduleInstall(true);
      if (event.target.closest?.('#open-admin, [data-company], [data-detail-tab]')) {
        requestAnimationFrame(neutralizeLegacySuperadminCard);
      }
    }, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
