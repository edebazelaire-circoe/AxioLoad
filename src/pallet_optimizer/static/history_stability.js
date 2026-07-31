(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  const CACHE_TTL_MS = 5 * 60 * 1000;
  const NETWORK_WINDOW_MS = 30 * 1000;
  const MAX_NETWORK_REQUESTS = 3;
  let cachedResponse = null;
  let cachedAt = 0;
  let inFlight = null;
  let refreshPermit = 0;
  let refreshReason = 'initial';
  let networkRequests = [];

  // Le précédent accès par jeton du panneau Super Admin n'est plus utilisé.
  try { sessionStorage.removeItem('axioload.admin.token'); } catch (_) {}

  function requestInfo(input, init = {}) {
    const rawUrl = typeof input === 'string' ? input : input?.url || '';
    const method = String(init.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase();
    let pathname = '';
    try {
      pathname = new URL(rawUrl, window.location.href).pathname;
    } catch (_) {}
    return {method, pathname};
  }

  function grantRefresh(reason = 'user') {
    refreshPermit = 1;
    refreshReason = reason;
  }

  function invalidateHistoryCache(reason = 'mutation') {
    cachedResponse = null;
    cachedAt = 0;
    grantRefresh(reason);
  }

  function rememberNetworkRequest() {
    const now = Date.now();
    networkRequests = networkRequests.filter(timestamp => now - timestamp < NETWORK_WINDOW_MS);
    networkRequests.push(now);
  }

  function circuitIsOpen() {
    const now = Date.now();
    networkRequests = networkRequests.filter(timestamp => now - timestamp < NETWORK_WINDOW_MS);
    return networkRequests.length >= MAX_NETWORK_REQUESTS;
  }

  function publishHistory(response, source) {
    if (!response.ok) return;
    response.clone().json().then(rows => {
      if (!Array.isArray(rows)) return;
      window.dispatchEvent(new CustomEvent('axioload:history-data', {
        detail: {rows, source, loadedAt: Date.now()},
      }));
    }).catch(() => {});
  }

  function isConcreteHistoryAction(target) {
    return Boolean(target?.closest?.(
      '.tab[data-tab="history"], #refresh-history, [data-history-refresh], [data-action="refresh-history"]'
    ));
  }

  // La permission est donnée avant les gestionnaires de clic de l'application.
  document.addEventListener('click', event => {
    if (isConcreteHistoryAction(event.target)) grantRefresh('user-action');
  }, true);

  window.addEventListener('axioload:history-refresh-request', event => {
    grantRefresh(event.detail?.reason || 'explicit-request');
  });

  window.fetch = async (input, init = {}) => {
    const {method, pathname} = requestInfo(input, init);
    const isHistoryList = method === 'GET' && pathname === '/api/history';
    const mutatesHistory = pathname.startsWith('/api/history') && method !== 'GET';

    if (!isHistoryList) {
      const response = await nativeFetch(input, init);
      if (mutatesHistory && response.ok) {
        invalidateHistoryCache('history-mutation');
        window.dispatchEvent(new CustomEvent('axioload:history-changed'));
      }
      return response;
    }

    const explicitlyAllowed = refreshPermit > 0;

    // Sans action concrète, une donnée déjà chargée est réutilisée. Une mutation
    // ou un clic sur l'onglet Historique autorise exactement un nouvel appel.
    if (cachedResponse && !explicitlyAllowed) return cachedResponse.clone();
    if (inFlight) return (await inFlight).clone();

    // Garde-fou ultime : même en cas de régression DOM, pas plus de trois appels
    // réseau en trente secondes lorsqu'une réponse de secours existe.
    if (circuitIsOpen() && cachedResponse) return cachedResponse.clone();

    refreshPermit = 0;
    const source = explicitlyAllowed ? refreshReason : cachedResponse ? 'cache-refresh' : 'initial-load';
    rememberNetworkRequest();

    inFlight = nativeFetch(input, init)
      .then(response => {
        if (response.ok) {
          cachedResponse = response.clone();
          cachedAt = Date.now();
          publishHistory(response, source);
        }
        return response;
      })
      .finally(() => {
        inFlight = null;
      });

    return (await inFlight).clone();
  };

  window.AxioHistoryTransport = {
    invalidate: invalidateHistoryCache,
    allowNextRefresh: grantRefresh,
    refresh(reason = 'manual') {
      grantRefresh(reason);
      return window.fetch('/api/history?limit=200');
    },
    diagnostics() {
      return {
        hasCache: Boolean(cachedResponse),
        cacheAgeMs: cachedAt ? Date.now() - cachedAt : null,
        requestsInWindow: networkRequests.length,
        refreshPermit,
      };
    },
  };
})();
