(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];

  const TITLES = {
    transform: {
      title: 'Transformer et contrôler une facture Factur-X',
      intro: 'Chargez un PDF ou une image pour préremplir la facture, puis vérifiez les données avant validation et export.'
    },
    history: {
      title: 'Historique des factures électroniques',
      intro: 'Retrouvez les factures enregistrées, leur état de validation et les exports disponibles.'
    }
  };

  let currentMode = 'transform';
  let observer = null;

  function visibleWorkspaceButtons() {
    const switcher = q('#workspace-switcher');
    if (!switcher) return [];
    return qa('[data-workspace]', switcher).filter(button => {
      if (button.hidden || button.hasAttribute('hidden')) return false;
      return getComputedStyle(button).display !== 'none';
    });
  }

  function syncWorkspaceCount() {
    const switcher = q('#workspace-switcher');
    if (!switcher) return;
    const count = visibleWorkspaceButtons().length;
    switcher.dataset.visibleCount = String(count);
    switcher.classList.toggle('single-workspace', count === 1);
  }

  function setHeading(mode) {
    const panel = q('#tab-facturx');
    if (!panel) return;
    const title = q('#facturx-title', panel);
    const intro = q('.panel-heading .section-intro', panel);
    if (title) title.textContent = TITLES[mode].title;
    if (intro) intro.textContent = TITLES[mode].intro;
  }

  function setTabState(mode) {
    const transformTab = q('nav.tabs [data-tab="facturx"]');
    const historyTab = q('nav.tabs [data-facturx-view="history"]');
    const inWorkspace = document.body.dataset.workspace === 'facturx';

    if (transformTab) {
      const active = mode === 'transform';
      transformTab.classList.toggle('active', active);
      transformTab.setAttribute('aria-selected', String(active));
      transformTab.hidden = !inWorkspace;
      transformTab.classList.toggle('workspace-group-hidden', !inWorkspace);
      transformTab.toggleAttribute('aria-hidden', !inWorkspace);
      if (inWorkspace) transformTab.removeAttribute('tabindex');
      else transformTab.setAttribute('tabindex', '-1');
    }
    if (historyTab) {
      const active = mode === 'history';
      historyTab.classList.toggle('active', active);
      historyTab.setAttribute('aria-selected', String(active));
      historyTab.hidden = !inWorkspace;
      historyTab.classList.toggle('workspace-group-hidden', !inWorkspace);
    }
  }

  function showMode(mode) {
    const panel = q('#tab-facturx');
    if (!panel || !['transform', 'history'].includes(mode)) return;
    currentMode = mode;
    panel.classList.toggle('facturx-transform-mode', mode === 'transform');
    panel.classList.toggle('facturx-history-mode', mode === 'history');
    setHeading(mode);
    setTabState(mode);
  }

  function ensureTabs() {
    const nav = q('nav.tabs');
    const transformTab = q('nav.tabs [data-tab="facturx"]');
    if (!nav || !transformTab) return false;

    transformTab.textContent = 'Nouvelle facture';
    transformTab.setAttribute('aria-label', 'Nouvelle facture');
    transformTab.dataset.workspaceGroup = 'facturx';
    if (transformTab.dataset.facturxModeBound !== '1') {
      transformTab.dataset.facturxModeBound = '1';
      transformTab.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        showMode('transform');
      });
    }

    let historyTab = q('nav.tabs [data-facturx-view="history"]');
    if (!historyTab) {
      historyTab = document.createElement('button');
      historyTab.type = 'button';
      historyTab.className = 'tab';
      historyTab.textContent = 'Historique';
      historyTab.dataset.facturxView = 'history';
      historyTab.dataset.workspaceGroup = 'facturx';
      historyTab.setAttribute('aria-selected', 'false');
      transformTab.insertAdjacentElement('afterend', historyTab);
      historyTab.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        showMode('history');
      });
    }
    setTabState(currentMode);
    return true;
  }

  function observeWorkspaceVisibility() {
    const switcher = q('#workspace-switcher');
    if (!switcher || observer) return;
    observer = new MutationObserver(syncWorkspaceCount);
    observer.observe(switcher, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden', 'style', 'class']
    });
  }

  function install() {
    const panel = q('#tab-facturx');
    const switcher = q('#workspace-switcher');
    if (!panel || !switcher || !ensureTabs()) return false;
    observeWorkspaceVisibility();
    syncWorkspaceCount();
    showMode(currentMode);
    return true;
  }

  window.addEventListener('axioload:workspace:registered', event => {
    if (event.detail?.workspace === 'facturx') {
      window.setTimeout(() => {
        install();
        syncWorkspaceCount();
      }, 0);
    }
  });

  window.addEventListener('axioload:navigation:changed', event => {
    ensureTabs();
    if (event.detail?.workspace === 'facturx' && event.detail?.tab === 'facturx') {
      showMode('transform');
    } else {
      setTabState(currentMode);
    }
  });

  function init() {
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(install, delay));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
