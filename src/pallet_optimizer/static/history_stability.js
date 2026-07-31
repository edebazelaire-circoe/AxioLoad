(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  const CACHE_TTL_MS = 1500;
  let inFlight = null;
  let cachedResponse = null;
  let cachedAt = 0;

  function requestInfo(input, init = {}) {
    const rawUrl = typeof input === 'string' ? input : input?.url || '';
    const method = String(init.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase();
    let pathname = '';
    try {
      pathname = new URL(rawUrl, window.location.href).pathname;
    } catch (_) {}
    return {method, pathname};
  }

  function invalidateHistoryCache() {
    cachedResponse = null;
    cachedAt = 0;
  }

  window.fetch = async (input, init = {}) => {
    const {method, pathname} = requestInfo(input, init);
    const isHistoryList = method === 'GET' && pathname === '/api/history';
    const mutatesHistory = pathname.startsWith('/api/history') && method !== 'GET';

    if (!isHistoryList) {
      const response = await nativeFetch(input, init);
      if (mutatesHistory && response.ok) invalidateHistoryCache();
      return response;
    }

    const now = Date.now();
    if (cachedResponse && now - cachedAt < CACHE_TTL_MS) return cachedResponse.clone();

    if (!inFlight) {
      inFlight = nativeFetch(input, init)
        .then(response => {
          if (response.ok) {
            cachedResponse = response.clone();
            cachedAt = Date.now();
          }
          return response;
        })
        .finally(() => {
          inFlight = null;
        });
    }

    const response = await inFlight;
    return response.clone();
  };

  window.AxioHistoryTransport = {
    invalidate: invalidateHistoryCache,
  };
})();
